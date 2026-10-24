"""Gateway bridge for offline KWS subprocess and local WebSocket clients."""
import asyncio
import contextlib
import io
import json
import logging
from pathlib import Path
import sys
import time

from starlette.datastructures import UploadFile

log = logging.getLogger('human.wake')


class WakeService:
    def __init__(self, root, recognize, command, care):
        self.root, self.recognize, self.command, self.care = root, recognize, command, care
        self.clients = set()
        self.process = None
        self.ready = False
        self.state = 'starting'
        self.error = ''
        self.keyword = json.loads((root/'config/wake.json').read_text())['keyword']
        self.tasks = set()
        self.write_lock = asyncio.Lock()
        self.last_control = 0
        self.generation = 0

    def snapshot(self):
        return {'type': 'status', 'ready': self.ready, 'state': self.state,
                'keyword': self.keyword, 'error': self.error,
                'worker_pid': self.process.pid if self.process else None}

    def publish(self, event):
        if event.get('type') in ('wake', 'state'):
            self.state = event.get('state', self.state)
        for queue in tuple(self.clients):
            if queue.full():
                # Levels may be dropped, state transitions must always fit.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    async def control(self, data):
        if self.process and self.process.returncode is None:
            async with self.write_lock:
                try:
                    self.process.stdin.write((json.dumps(data)+'\n').encode())
                    await self.process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass

    async def receive_control(self, data):
        # Only allow named controls; incoming clients cannot inject wake events.
        if data.get('type') == 'control':
            self.last_control = time.monotonic()
            await self.control({k: bool(data[k]) for k in ('enabled', 'suppress') if k in data})
        elif data.get('type') == 'finish_listen':
            await self.control({'finish_listen': True})
        elif data.get('type') == 'cancel_listen':
            self.generation += 1
            tasks = tuple(self.tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.control({'cancel_listen': True})
        elif data.get('type') == 'manual_listen':
            # A visible microphone is the fallback for missed wake words.
            await self.control({'manual_listen': True})

    async def audio(self, event):
        generation = self.generation
        path = Path(event['path'])
        try:
            self.publish({'type': 'state', 'state': 'thinking'})
            with path.open('rb') as source:
                result = await self.recognize(UploadFile(io.BytesIO(source.read()), filename='wake.wav'),
                                              care_event_id=event.get('care_event_id', ''))
            if generation == self.generation:
                if result.get('input_notice'):
                    self.publish({'type': 'state', 'state': 'error', 'error': result['input_notice']})
                else:
                    self.publish({'type': 'transcript', **result})
        except Exception:
            log.exception('Wake ASR failed')
            self.publish({'type': 'state', 'state': 'error', 'error': '没有听清，请再叫一声小安'})
        finally:
            path.unlink(missing_ok=True)
            # Give the client time to start its normal chat pipeline and suppress KWS.
            if generation == self.generation:
                await asyncio.sleep(.5)
                if generation == self.generation:
                    await self.control({'resume': True})

    async def run(self):
        try:
            while True:
                try:
                    self.process = await asyncio.create_subprocess_exec(
                        sys.executable, '-u', '-m', 'gateway.wake_worker', cwd=self.root,
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
                    while line := await self.process.stdout.readline():
                        event = json.loads(line)
                        kind = event.get('type')
                        if event.get('ready'):
                            self.ready = True
                            self.error = ''
                        if kind == 'audio':
                            task = asyncio.create_task(self.audio(event))
                            self.tasks.add(task)
                            task.add_done_callback(self.tasks.discard)
                        elif kind == 'command':
                            self.command(event['text'], event.get('care_event_id', ''))
                        else:
                            self.publish(event)
                    await self.process.wait()
                    raise RuntimeError('唤醒麦克风进程已退出')
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.ready = False
                    self.error = str(exc)
                    self.publish({'type': 'status', **self.snapshot()})
                    log.exception('Wake worker restarting')
                    await asyncio.sleep(3)
        finally:
            self.ready = False
            for task in tuple(self.tasks):
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            if self.process and self.process.returncode is None:
                self.process.stdin.close()
                try:
                    await asyncio.wait_for(self.process.wait(), 3)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()

    async def heartbeat(self):
        while True:
            rows = self.care.rows()
            # A disappearing client cannot keep the backend stuck in a playback pause.
            payload = {'care_event_id': rows[0]['id'] if rows else ''}
            if time.monotonic()-self.last_control > 3:
                payload['suppress'] = False
            await self.control(payload)
            await asyncio.sleep(.25)
