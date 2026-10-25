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
        async with self.write_lock:
            # Waiting for another write may overlap worker shutdown/restart.
            process = self.process
            if process is None or process.returncode is not None:
                return
            try:
                process.stdin.write((json.dumps(data)+'\n').encode())
                await process.stdin.drain()
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
            await self.cancel_audio()
            await self.control({'cancel_listen': True})
        elif data.get('type') == 'manual_listen':
            # A visible microphone is the fallback for missed wake words.
            await self.control({'manual_listen': True})

    async def cancel_audio(self):
        # Invalidate before awaiting: backends can return a late result even
        # after cancellation, and must not affect the replacement worker.
        self.generation += 1
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def remove_recording(path):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.warning('Could not remove wake recording %s', path, exc_info=True)

    def start_audio(self, event):
        path = Path(event['path'])
        task = asyncio.create_task(self.audio(event))
        self.tasks.add(task)

        def finished(task):
            self.tasks.discard(task)
            # Cancellation before the coroutine starts skips its finally block.
            self.remove_recording(path)
            if not task.cancelled() and task.exception() is not None:
                log.error('Wake audio task failed: %s', task.exception())

        task.add_done_callback(finished)

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
            if generation == self.generation:
                self.publish({'type': 'state', 'state': 'error', 'error': '没有听清，请再叫一声小安'})
        finally:
            # A storage cleanup failure must not prevent listening from
            # resuming, or replace the task's cancellation with an OSError.
            self.remove_recording(path)
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
                            self.start_audio(event)
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
                    self.state = 'error'
                    self.error = str(exc)
                    self.publish({'type': 'status', **self.snapshot()})
                    log.exception('Wake worker restarting')
                    # Reap the old process before overwriting its handle. A
                    # protocol/command failure can leave it holding the mic.
                    await self.cancel_audio()
                    await self.stop_worker()
                    await asyncio.sleep(3)
        finally:
            self.ready = False
            await self.cancel_audio()
            await self.stop_worker()

    async def stop_worker(self):
        process = self.process
        if process is None:
            return
        if process.returncode is None:
            if process.stdin:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), 3)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
        else:
            await process.wait()
        if self.process is process:
            self.process = None

    async def heartbeat(self):
        query_failed = control_failed = False
        while True:
            rows = []
            try:
                rows = self.care.rows()
                query_failed = False
            except Exception:
                if not query_failed:
                    log.exception('Wake heartbeat care query failed; retrying')
                query_failed = True
            # A disappearing client cannot keep the backend stuck in a playback pause.
            payload = {'care_event_id': rows[0]['id'] if rows else ''}
            if time.monotonic()-self.last_control > 3:
                payload['suppress'] = False
            try:
                await self.control(payload)
                control_failed = False
            except Exception:
                if not control_failed:
                    log.exception('Wake heartbeat control failed; retrying')
                control_failed = True
            await asyncio.sleep(.25)
