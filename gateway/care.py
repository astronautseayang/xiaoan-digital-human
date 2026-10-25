"""Durable local care scheduler and acknowledged priority event delivery."""
import asyncio
from datetime import datetime
import json
import logging
import re
import sqlite3
import time
import uuid
from zoneinfo import ZoneInfo

from gateway.companion import greeting
from gateway import reminders

log = logging.getLogger('human.care')
EMERGENCY_WORDS = ('跌倒', '摔倒', '救命', '胸口疼', '胸痛')


def command_for(text):
    value = re.sub(r'[\W_]+', '', text)
    if any(word in value for word in EMERGENCY_WORDS):
        return 'emergency'
    if value in ('知道了', '我知道了', '好的知道了'):
        return 'ack'
    return ''


class CareEngine:
    def __init__(self, root, synthesize, client):
        self.root, self.synthesize, self.client = root, synthesize, client
        self.config = json.loads((root / 'config/care.json').read_text())
        self.zone = ZoneInfo(self.config['timezone'])
        path = root / 'artifacts/care.sqlite3'
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('''CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, occurrence TEXT UNIQUE,
                kind TEXT, priority INTEGER, title TEXT, text TEXT, created REAL, expires REAL,
                acknowledged INTEGER DEFAULT 0, audio_url TEXT DEFAULT '', audio_state TEXT DEFAULT 'pending',
                push_state TEXT DEFAULT 'local_only', push_attempts INTEGER DEFAULT 0, next_push REAL DEFAULT 0)''')
            self.db.commit()
            reminders.initialize(self.db)
            self.changed = asyncio.Event()
            self.version = 0
            self.tasks = set()
        except BaseException:
            self.db.close()
            raise

    def notify(self):
        self.version += 1
        self.changed.set()

    def spawn(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def rows(self):
        now = time.time()
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM events WHERE acknowledged=0 AND expires>? ORDER BY priority DESC, seq', (now,))]

    def ack(self, event_id=None):
        # A spoken acknowledgement closes the foreground card only.
        if event_id is None:
            rows = self.rows()
            event_id = rows[0]['id'] if rows else ''
        self.db.execute('UPDATE events SET acknowledged=1 WHERE id=?', (event_id,))
        self.db.commit()
        self.notify()
        return event_id

    def create(self, kind, title, text, occurrence=None, commit=True):
        text = greeting(self.root, text)
        now = time.time()
        emergency = kind == 'emergency'
        if emergency:
            recent = self.db.execute("SELECT id FROM events WHERE kind='emergency' AND acknowledged=0 AND created>?", (now-30,)).fetchone()
            if recent:
                return recent['id']
        event_id = uuid.uuid4().hex
        cursor = self.db.execute('''INSERT OR IGNORE INTO events
            (id,occurrence,kind,priority,title,text,created,expires,push_state)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (event_id, occurrence, kind, 100 if emergency else (80 if kind == 'reminder' else 70), title, text, now,
             now + (86400 if emergency else 1800),
             'pending' if emergency and self.config.get('alert_webhook') else 'local_only'))
        if commit:
            self.db.commit()
        if cursor.rowcount:
            self.notify()
            self.spawn(self.render(event_id, text))
        return event_id

    async def render(self, event_id, text):
        try:
            data = await self.synthesize(text)
            audio = self.root / 'artifacts/care-audio'
            audio.mkdir(parents=True, exist_ok=True)
            destination = audio / (event_id + '.wav')
            temporary = audio / (event_id + '.' + uuid.uuid4().hex + '.tmp')
            try:
                temporary.write_bytes(data)
                temporary.replace(destination)
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    log.warning('Could not remove temporary care audio: %s', temporary, exc_info=True)
            self.db.execute("UPDATE events SET audio_url=?,audio_state='ready' WHERE id=?",
                            ('/care-audio/' + event_id + '.wav', event_id))
        except Exception:
            log.exception('Care TTS failed: %s', event_id)
            self.db.execute("UPDATE events SET audio_state='failed' WHERE id=?", (event_id,))
        self.db.commit()
        self.notify()

    def tick(self, now):
        now = now.astimezone(self.zone)
        reminders.tick(self, now)
        # Only the current minute is eligible; restart never replays old medication reminders.
        date = now.strftime('%Y-%m-%d')
        clock = now.strftime('%H:%M')
        if now.minute == 0 and 8 <= now.hour <= 21:
            self.create('hourly', '整点关怀',
                        f'现在是{now.hour}点整。请喝几口温水。如果身体允许，请扶稳后起身，慢慢走动一下。', date + ':hourly:' + clock)
        for item in self.config['reminders']:
            if item['time'] == clock:
                self.create('reminder', item['title'], item['text'], date + ':' + item['id'])

    async def push_alerts(self):
        for row in self.db.execute("SELECT * FROM events WHERE push_state IN ('pending','retry') AND next_push<=?", (time.time(),)).fetchall():
            try:
                response = await self.client.post(self.config['alert_webhook'], json={
                    'event_id': row['id'], 'kind': row['kind'], 'text': row['text'],
                    'created': row['created'], 'device': self.config.get('device_name', '数字人')}, timeout=5)
                response.raise_for_status()
                state = 'sent'
            except Exception:
                log.exception('Care alert delivery failed')
                state = 'retry'
            attempts = row['push_attempts'] + 1
            self.db.execute('UPDATE events SET push_state=?,push_attempts=?,next_push=? WHERE id=?',
                            (state, attempts, time.time()+min(300, 5*2**min(attempts, 6)), row['id']))
            self.db.commit()
            self.notify()

    def prune_history(self):
        # Keep deduplication history for seven days. A failed file removal
        # retains its row for retry without stopping reminder delivery.
        cutoff = time.time()-7*86400
        old = self.db.execute("SELECT id FROM events WHERE created<? AND push_state NOT IN ('pending','retry')", (cutoff,)).fetchall()
        for row in old:
            try:
                (self.root / 'artifacts/care-audio' / (row['id']+'.wav')).unlink(missing_ok=True)
            except OSError:
                log.warning('Could not remove old care audio: %s', row['id'], exc_info=True)
                continue
            self.db.execute('DELETE FROM events WHERE id=?', (row['id'],))
        self.db.commit()

    async def run(self):
        try:
            recovering = True
            recovered_audio = set()
            next_cleanup = 0
            while True:
                try:
                    if recovering:
                        # Recover once per active card, including after a
                        # temporary database error partway through startup.
                        for row in self.rows():
                            if row['id'] in recovered_audio:
                                continue
                            path = self.root / 'artifacts/care-audio' / (row['id']+'.wav')
                            try:
                                available = path.is_file() and path.stat().st_size > 0
                            except OSError:
                                available = False
                            if row['audio_state'] != 'ready' or not available:
                                self.db.execute("UPDATE events SET audio_state='pending',audio_url='' WHERE id=?", (row['id'],))
                                self.db.commit()
                                self.notify()
                                self.spawn(self.render(row['id'], row['text']))
                                recovered_audio.add(row['id'])
                        recovering = False
                        recovered_audio.clear()
                    self.tick(datetime.now(self.zone))
                    await self.push_alerts()
                    if time.monotonic() >= next_cleanup:
                        self.prune_history()
                        next_cleanup = time.monotonic()+60
                except sqlite3.OperationalError:
                    # Another local writer or a temporary storage failure
                    # must not permanently stop reminder scheduling.
                    self.db.rollback()
                    log.exception('Care database operation failed; retrying next tick')
                await asyncio.sleep(1)
        finally:
            for task in list(self.tasks):
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.db.close()
