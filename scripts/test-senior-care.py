"""Offline tests: scheduler, durable priority delivery, alarm retry and real FFmpeg DSP."""
import asyncio
from datetime import datetime
import io
import json
import sqlite3
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import wave
from zoneinfo import ZoneInfo
import numpy as np
import httpx
from gateway.care import CareEngine, command_for
from gateway.senior_audio import process_senior_speech

ROOT = Path(__file__).resolve().parents[1]

class CareTests(unittest.IsolatedAsyncioTestCase):
    async def test_constructor_schema_failure_closes_its_connection(self):
        connection = sqlite3.connect(':memory:')
        error = sqlite3.OperationalError('injected schema initialization failure')
        try:
            with patch('gateway.care.sqlite3.connect', return_value=connection), \
                 patch('gateway.care.reminders.initialize', side_effect=error):
                with self.assertRaises(sqlite3.OperationalError) as raised:
                    CareEngine(self.root, self.engine.synthesize, self.client)
                self.assertIs(raised.exception, error)
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute('SELECT 1')
        finally:
            connection.close()

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'config/care.json').write_bytes((ROOT/'config/care.json').read_bytes())
        async def synth(text):
            return b'audio-test'
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        self.engine = CareEngine(self.root, synth, self.client)

    async def asyncTearDown(self):
        await asyncio.gather(*list(self.engine.tasks), return_exceptions=True)
        self.engine.db.close()
        await self.client.aclose()
        self.temp.cleanup()

    async def test_audio_storage_failures_preserve_published_file_and_recover(self):
        audio = self.root/'artifacts/care-audio'
        audio.mkdir(parents=True)
        original_write = Path.write_bytes
        original_replace = Path.replace
        for existing in (False, True):
            for failure in ('write', 'replace'):
                with self.subTest(existing=existing, failure=failure):
                    key = f'atomic-{existing}-{failure}'
                    final = audio/(key+'.wav')
                    self.engine.db.execute("INSERT INTO events (id,text,audio_state) VALUES (?,?,'pending')", (key,'测试'))
                    self.engine.db.commit()
                    if existing:
                        final.write_bytes(b'previous-audio')
                    def write(path, data):
                        if path.parent == audio and failure == 'write':
                            original_write(path, data[:3])
                            raise OSError('Injected partial audio write')
                        return original_write(path, data)
                    def replace(path, target):
                        if path.parent == audio and failure == 'replace':
                            raise PermissionError('Injected audio replace failure')
                        return original_replace(path, target)
                    with patch.object(Path, 'write_bytes', write), patch.object(Path, 'replace', replace):
                        await self.engine.render(key, '测试')
                    row = self.engine.db.execute('SELECT * FROM events WHERE id=?', (key,)).fetchone()
                    self.assertEqual(row['audio_state'], 'failed')
                    if existing:
                        self.assertEqual(final.read_bytes(), b'previous-audio')
                    else:
                        self.assertFalse(final.exists())
                    self.assertEqual(list(audio.glob('*.tmp')), [])
                    await self.engine.render(key, '测试')
                    row = self.engine.db.execute('SELECT * FROM events WHERE id=?', (key,)).fetchone()
                    self.assertEqual(row['audio_state'], 'ready')
                    self.assertEqual(row['audio_url'], '/care-audio/'+key+'.wav')
                    self.assertEqual(final.read_bytes(), b'audio-test')
                    self.assertEqual(list(audio.glob('*.tmp')), [])

    async def test_daily_boundaries_and_duplicate_ticks(self):
        zone = ZoneInfo('Asia/Shanghai')
        for hour in range(24):
            moment = datetime(2026, 10, 23, hour, 0, 59, tzinfo=zone)
            self.engine.tick(moment)
            self.engine.tick(moment)
        self.engine.tick(datetime(2026, 10, 23, 18, 30, tzinfo=zone))
        rows = self.engine.db.execute('SELECT * FROM events').fetchall()
        self.assertEqual(len(rows), 16)
        self.assertEqual(sum(r['kind']=='hourly' for r in rows), 14)
        await asyncio.gather(*list(self.engine.tasks))
        self.assertEqual(self.engine.db.execute("SELECT count(*) FROM events WHERE audio_state='ready'").fetchone()[0], 16)
        # Deduplication survives a second engine instance / process restart.
        second = CareEngine(self.root, self.engine.synthesize, self.client)
        second.tick(datetime(2026, 10, 23, 12, 0, tzinfo=zone))
        self.assertEqual(second.db.execute('SELECT count(*) FROM events').fetchone()[0], 16)
        second.db.close()

    async def test_emergency_preempts_reminder_ack_and_dedup(self):
        hourly = self.engine.create('hourly','报时','喝水')
        reminder = self.engine.create('reminder','用药','遵医嘱')
        emergency = self.engine.create('emergency','求助','有人求助')
        self.assertEqual(self.engine.create('emergency','求助','重复识别'), emergency)
        self.assertEqual([r['id'] for r in self.engine.rows()], [emergency, reminder, hourly])
        self.assertEqual(self.engine.ack(), emergency)
        self.assertEqual(self.engine.rows()[0]['id'], reminder)
        self.engine.db.execute('UPDATE events SET expires=0 WHERE id=?',(hourly,))
        self.engine.db.commit()
        self.assertEqual(len(self.engine.rows()),1)

    async def test_ack_is_bound_to_utterance_event(self):
        hourly = self.engine.create('hourly', '报时', '喝水')
        emergency = self.engine.create('emergency', '求助', '有人求助')
        self.assertEqual(self.engine.ack(hourly), hourly)
        self.assertEqual(self.engine.rows()[0]['id'], emergency)
        self.assertFalse(self.engine.ack(''))
        self.assertEqual(self.engine.rows()[0]['id'], emergency)

    async def test_alarm_retry_survives_ack(self):
        self.engine.config['alert_webhook']='https://care.example/alert'
        calls=[]
        def handler(req):
            calls.append(json.loads(req.content))
            return httpx.Response(503 if len(calls)==1 else 200)
        await self.client.aclose()
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.engine.client=self.client
        key=self.engine.create('emergency','求助','请查看')
        await self.engine.push_alerts()
        row=self.engine.db.execute('SELECT * FROM events WHERE id=?',(key,)).fetchone()
        self.assertEqual(row['push_state'],'retry')
        self.engine.ack(key)
        self.engine.db.execute('UPDATE events SET next_push=0')
        self.engine.db.commit()
        await self.engine.push_alerts()
        self.assertEqual(self.engine.db.execute('SELECT push_state FROM events').fetchone()[0],'sent')
        self.assertEqual(calls[0]['event_id'],calls[1]['event_id'])

    async def test_restart_recovers_unfinished_audio(self):
        self.engine.db.execute("INSERT INTO events (id,kind,priority,title,text,created,expires) VALUES ('recover','reminder',80,'标题','文本',strftime('%s','now'),9999999999)")
        self.engine.db.commit()
        runner=asyncio.create_task(self.engine.run())
        for _ in range(30):
            await asyncio.sleep(.01)
            row=self.engine.db.execute("SELECT audio_state FROM events WHERE id='recover'").fetchone()
            if row[0]=='ready':break
        self.assertEqual(row[0],'ready')
        runner.cancel()
        await asyncio.gather(runner,return_exceptions=True)
        # run() closes its database; open it again for fixture teardown.
        import sqlite3
        self.engine.db=sqlite3.connect(self.root/'artifacts/care.sqlite3')

    async def test_restart_repairs_missing_empty_and_failed_audio(self):
        audio = self.root/'artifacts/care-audio'
        audio.mkdir(parents=True)
        for key, state in [('pending','pending'),('failed','failed'),('missing','ready'),
                           ('empty','ready'),('valid','ready'),('ack','failed'),('expired','failed')]:
            self.engine.db.execute('''INSERT INTO events
                (id,kind,priority,title,text,created,expires,audio_state,audio_url,acknowledged)
                VALUES (?, 'reminder',80,'恢复测试',?,strftime('%s','now'),?,?,?,?)''',
                (key,key,0 if key=='expired' else 9999999999,state,'/care-audio/'+key+'.wav',int(key=='ack')))
        self.engine.db.commit()
        (audio/'empty.wav').write_bytes(b'')
        (audio/'valid.wav').write_bytes(b'existing-audio')
        calls=[]
        async def synth(text):
            calls.append(text)
            return b'recovered-audio'
        second=CareEngine(self.root,synth,self.client)
        with patch.object(second,'tick'):
            runner=asyncio.create_task(second.run())
            try:
                for _ in range(50):
                    await asyncio.sleep(.01)
                    if len(calls)>=4:break
                self.assertCountEqual(calls,['pending','failed','missing','empty'])
                for key in ('pending','failed','missing','empty'):
                    row=self.engine.db.execute('SELECT audio_state FROM events WHERE id=?',(key,)).fetchone()
                    self.assertEqual(row[0],'ready',key)
                    self.assertEqual((audio/(key+'.wav')).read_bytes(),b'recovered-audio')
                self.assertEqual((audio/'valid.wav').read_bytes(),b'existing-audio')
            finally:
                runner.cancel()
                await asyncio.gather(runner,return_exceptions=True)

    async def test_failed_recovery_is_not_retried_each_tick(self):
        self.engine.db.execute("INSERT INTO events (id,kind,priority,title,text,created,expires,audio_state) VALUES ('failed','reminder',80,'标题','文本',strftime('%s','now'),9999999999,'failed')")
        self.engine.db.commit()
        calls=[]
        async def fail(text):
            calls.append(text)
            raise RuntimeError('Injected TTS failure')
        second=CareEngine(self.root,fail,self.client)
        twice=asyncio.Event()
        ticks=0
        def tick(now):
            nonlocal ticks
            ticks+=1
            if ticks>=2:twice.set()
        with patch.object(second,'tick',tick):
            runner=asyncio.create_task(second.run())
            try:
                await asyncio.wait_for(twice.wait(),2)
                self.assertEqual(len(calls),1)
                self.assertFalse(runner.done())
                self.assertEqual(self.engine.db.execute("SELECT audio_state FROM events WHERE id='failed'").fetchone()[0],'failed')
            finally:
                runner.cancel()
                await asyncio.gather(runner,return_exceptions=True)

    async def test_old_audio_cleanup_failure_does_not_stop_scheduler(self):
        key = self.engine.create('hourly', '过期记录', '测试')
        await asyncio.gather(*list(self.engine.tasks))
        self.engine.db.execute('UPDATE events SET created=0, expires=0 WHERE id=?', (key,))
        self.engine.db.commit()
        second = CareEngine(self.root, self.engine.synthesize, self.client)
        twice = asyncio.Event()
        ticks = 0
        original_tick = second.tick
        original_unlink = Path.unlink

        def tick(now):
            nonlocal ticks
            original_tick(now)
            ticks += 1
            if ticks >= 2:
                twice.set()

        def unlink(path, *args, **kwargs):
            if path.name == key + '.wav':
                raise PermissionError('Injected cleanup failure')
            return original_unlink(path, *args, **kwargs)

        with patch.object(second, 'tick', tick), patch.object(Path, 'unlink', unlink):
            runner = asyncio.create_task(second.run())
            try:
                await asyncio.wait_for(twice.wait(), 2)
                self.assertFalse(runner.done())
                self.assertIsNotNone(self.engine.db.execute('SELECT id FROM events WHERE id=?', (key,)).fetchone())
            finally:
                runner.cancel()
                await asyncio.gather(runner, return_exceptions=True)

        self.engine.prune_history()
        self.assertIsNone(self.engine.db.execute('SELECT id FROM events WHERE id=?', (key,)).fetchone())
        self.assertFalse((self.root/'artifacts/care-audio'/(key+'.wav')).exists())

    async def test_scheduler_recovers_after_database_write_lock(self):
        second = CareEngine(self.root, self.engine.synthesize, self.client)
        second.db.execute('PRAGMA busy_timeout=0')
        attempted = asyncio.Event()
        recovered = asyncio.Event()
        original_tick = second.tick
        moment = datetime(2026, 10, 24, 13, 0, tzinfo=second.zone)
        def tick(now):
            attempted.set()
            original_tick(moment)
            recovered.set()
        self.engine.db.execute('BEGIN IMMEDIATE')
        with patch.object(second, 'tick', tick):
            runner = asyncio.create_task(second.run())
            try:
                await asyncio.wait_for(attempted.wait(), 1)
                self.assertFalse(runner.done(), 'Temporary database lock stopped scheduler')
                self.engine.db.rollback()
                await asyncio.wait_for(recovered.wait(), 2)
                await asyncio.gather(*list(second.tasks))
                rows = self.engine.db.execute("SELECT * FROM events WHERE occurrence='2026-10-24:hourly:13:00'").fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['audio_state'], 'ready')
            finally:
                self.engine.db.rollback()
                runner.cancel()
                await asyncio.gather(runner, return_exceptions=True)

    async def test_startup_audio_recovery_survives_database_write_lock(self):
        self.engine.db.execute("INSERT INTO events (id,kind,priority,title,text,created,expires) VALUES ('locked-start','reminder',80,'标题','恢复音频',strftime('%s','now'),9999999999)")
        self.engine.db.commit()
        calls = []
        rendered = asyncio.Event()
        async def synth(text):
            calls.append(text)
            rendered.set()
            return b'recovered-audio'
        second = CareEngine(self.root, synth, self.client)
        second.db.execute('PRAGMA busy_timeout=0')
        attempted = asyncio.Event()
        original_rows = second.rows
        def rows():
            result = original_rows()
            attempted.set()
            return result
        self.engine.db.execute('BEGIN IMMEDIATE')
        with patch.object(second, 'rows', rows), patch.object(second, 'tick'):
            runner = asyncio.create_task(second.run())
            try:
                await asyncio.wait_for(attempted.wait(), 1)
                self.assertFalse(runner.done(), 'Startup database lock stopped scheduler')
                self.engine.db.rollback()
                await asyncio.wait_for(rendered.wait(), 2)
                await asyncio.gather(*list(second.tasks))
                self.assertEqual(calls, ['恢复音频'])
                row = self.engine.db.execute("SELECT * FROM events WHERE id='locked-start'").fetchone()
                self.assertEqual(row['audio_state'], 'ready')
                self.assertEqual((self.root/'artifacts/care-audio/locked-start.wav').read_bytes(), b'recovered-audio')
            finally:
                self.engine.db.rollback()
                runner.cancel()
                await asyncio.gather(runner, return_exceptions=True)

    async def test_partial_startup_recovery_does_not_repeat_failed_speech(self):
        for key in ('first', 'second'):
            self.engine.db.execute("INSERT INTO events (id,kind,priority,title,text,created,expires) VALUES (?,'reminder',80,'标题',?,strftime('%s','now'),9999999999)", (key, key))
        self.engine.db.commit()
        calls = []
        released = asyncio.Event()
        completed = asyncio.Event()
        async def synth(text):
            calls.append(text)
            await released.wait()
            if text == 'first':
                raise RuntimeError('Injected first-card TTS failure')
            completed.set()
            return b'second-audio'
        second = CareEngine(self.root, synth, self.client)
        second.db.execute('PRAGMA busy_timeout=0')
        locked = asyncio.Event()
        original_notify = second.notify
        def notify():
            original_notify()
            if not locked.is_set():
                self.engine.db.execute('BEGIN IMMEDIATE')
                locked.set()
        with patch.object(second, 'notify', notify), patch.object(second, 'tick'):
            runner = asyncio.create_task(second.run())
            try:
                await asyncio.wait_for(locked.wait(), 1)
                self.assertFalse(runner.done())
                self.engine.db.rollback()
                released.set()
                await asyncio.wait_for(completed.wait(), 2)
                await asyncio.gather(*list(second.tasks))
                self.assertEqual(calls, ['first', 'second'])
                states = {r['id']: r['audio_state'] for r in self.engine.db.execute('SELECT * FROM events')}
                self.assertEqual(states, {'first': 'failed', 'second': 'ready'})
            finally:
                self.engine.db.rollback()
                released.set()
                runner.cancel()
                await asyncio.gather(runner, return_exceptions=True)

    async def test_history_cleanup_keeps_pending_alerts_and_recent_events(self):
        expired = self.engine.create('hourly', '过期记录', '测试')
        pending = self.engine.create('emergency', '待发送记录', '测试')
        recent = self.engine.create('hourly', '近期记录', '测试')
        await asyncio.gather(*list(self.engine.tasks))
        self.engine.db.execute('UPDATE events SET created=0 WHERE id IN (?,?)', (expired, pending))
        self.engine.db.execute("UPDATE events SET push_state='retry' WHERE id=?", (pending,))
        self.engine.db.commit()
        self.engine.prune_history()
        rows = self.engine.db.execute('SELECT id FROM events').fetchall()
        self.assertEqual({r['id'] for r in rows}, {pending, recent})
        for key in (pending, recent):
            self.assertTrue((self.root/'artifacts/care-audio'/(key+'.wav')).exists())
        self.assertFalse((self.root/'artifacts/care-audio'/(expired+'.wav')).exists())

    def test_commands(self):
        for phrase in ('我跌倒了','救命！','胸口疼','刚刚摔倒了','胸痛'):
            self.assertEqual(command_for(phrase),'emergency')
        self.assertEqual(command_for('知道了。'),'ack')
        self.assertEqual(command_for('我还不知道了怎么办'),'')
        self.assertEqual(command_for('你好'),'')

class AudioTests(unittest.TestCase):
    def test_short_phrase_loudness_is_not_attenuated(self):
        rate=32000
        t=np.arange(rate)/rate
        data=io.BytesIO()
        with wave.open(data,'wb') as wav:
            wav.setparams((1,2,rate,0,'NONE','not compressed'))
            wav.writeframes((300*np.sin(2*np.pi*440*t)).astype('<i2').tobytes())
        output=process_senior_speech(data.getvalue())
        measured=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i','pipe:0','-af',
            'loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json','-f','null','-'],
            input=output,capture_output=True,check=True)
        diagnostic=measured.stderr.decode()
        stats=json.loads(diagnostic[diagnostic.rfind('{'):diagnostic.rfind('}')+1])
        self.assertAlmostEqual(float(stats['input_i']),-16,delta=1)
        self.assertLessEqual(float(stats['input_tp']),-1)

    def test_pcm_validity_peak_and_tail(self):
        rate=32000
        t=np.arange(rate*3)/rate
        signal=(np.sin(2*np.pi*200*t)+.18*np.sin(2*np.pi*2400*t))*.6
        buf=io.BytesIO()
        with wave.open(buf,'wb') as f:
            f.setparams((1,2,rate,0,'NONE','not compressed'))
            f.writeframes((signal*32767).astype('<i2').tobytes())
        output=process_senior_speech(buf.getvalue())
        with wave.open(io.BytesIO(output),'rb') as f:
            self.assertEqual(f.getframerate(),32000)
            self.assertEqual(f.getnchannels(),1)
            self.assertEqual(f.getsampwidth(),2)
            values=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
            self.assertGreaterEqual(f.getnframes(),rate*3.2)
        self.assertLessEqual(np.max(np.abs(values.astype(float))),29204)
        self.assertEqual(np.max(np.abs(values[-3000:])),0)
        self.assertGreater(np.sqrt(np.mean(values[:rate*3].astype(float)**2)),2000)

if __name__=='__main__':unittest.main()
