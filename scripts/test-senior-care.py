"""Offline tests: scheduler, durable priority delivery, alarm retry and real FFmpeg DSP."""
import asyncio
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
import wave
from zoneinfo import ZoneInfo
import numpy as np
import httpx
from gateway.care import CareEngine, command_for
from gateway.senior_audio import process_senior_speech

ROOT = Path(__file__).resolve().parents[1]

class CareTests(unittest.IsolatedAsyncioTestCase):
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
