"""A failed wake worker is reaped before the restart backoff begins."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gateway.wake import WakeService


class WakeLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_control_waiting_for_lock_tolerates_worker_disappearing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config').mkdir()
            (root/'config/wake.json').write_text('{"keyword":"小安"}')
            service = WakeService(root, None, None, None)
            service.process = SimpleNamespace(returncode=None)
            await service.write_lock.acquire()
            task = asyncio.create_task(service.control({'suppress': False}))
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            service.process = None
            service.write_lock.release()
            await asyncio.wait_for(task, 1)

    async def test_heartbeat_recovers_from_care_query_and_control_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config').mkdir()
            (root/'config/wake.json').write_text('{"keyword":"小安"}')
            attempts = 0
            sent = []
            recovered = asyncio.Event()
            def rows():
                nonlocal attempts
                attempts += 1
                if attempts <= 2:
                    raise OSError('temporary care database failure')
                return [{'id': 'current-event'}]
            service = WakeService(root, None, None, SimpleNamespace(rows=rows))
            async def control(data):
                sent.append(data)
                if len(sent) in (2, 3):
                    raise OSError('temporary worker pipe failure')
                if len(sent) >= 4:
                    recovered.set()
            service.control = control
            with self.assertLogs('human.wake', level='WARNING') as logs:
                task = asyncio.create_task(service.heartbeat())
                try:
                    await asyncio.wait_for(recovered.wait(), 2)
                    self.assertFalse(task.done())
                    self.assertEqual(sent[0], {'care_event_id': '', 'suppress': False})
                    self.assertEqual(sent[-1], {'care_event_id': 'current-event', 'suppress': False})
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            self.assertTrue(task.cancelled())
            self.assertEqual(len(logs.records), 2, 'Repeated failures flooded the log')

    async def test_recording_cleanup_failure_does_not_block_resume_or_cancellation(self):
        for outcome in ('transcript', 'recognition_error', 'cancelled'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root/'config').mkdir()
                (root/'config/wake.json').write_text('{"keyword":"小安"}')
                entered = asyncio.Event()
                controls = []
                async def recognize(*args, **kwargs):
                    entered.set()
                    if outcome == 'recognition_error':
                        raise RuntimeError('recognition failed')
                    if outcome == 'cancelled':
                        await asyncio.Event().wait()
                    return {'text': '你好'}
                async def control(data):
                    controls.append(data)
                service = WakeService(root, recognize, None, None)
                service.control = control
                events = asyncio.Queue()
                service.clients.add(events)
                recording = root/'pending.wav'
                recording.write_bytes(b'audio')
                unlink = Path.unlink
                def denied(path, *args, **kwargs):
                    if path == recording:
                        raise PermissionError('recording is temporarily locked')
                    return unlink(path, *args, **kwargs)
                with patch.object(Path, 'unlink', denied), self.assertLogs('human.wake', level='WARNING'):
                    service.start_audio({'path': str(recording)})
                    task = next(iter(service.tasks))
                    await asyncio.wait_for(entered.wait(), 1)
                    if outcome == 'cancelled':
                        await service.cancel_audio()
                    else:
                        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 2)
                    await asyncio.sleep(0)
                    self.assertFalse(service.tasks)
                    if outcome == 'cancelled':
                        self.assertTrue(task.cancelled(), 'Cleanup failure masked cancellation')
                        self.assertFalse(controls, 'Cancelled recording resumed the worker')
                        self.assertFalse(any(event['type'] == 'transcript' for event in events._queue))
                    else:
                        self.assertIsNone(task.exception(), 'Cleanup failure escaped audio task')
                        self.assertEqual(controls, [{'resume': True}])
                        expected = ({'type': 'transcript', 'text': '你好'} if outcome == 'transcript' else
                                    {'type': 'state', 'state': 'error', 'error': '没有听清，请再叫一声小安'})
                        self.assertIn(expected, list(events._queue))
                # Once the storage issue is gone, later cleanup can still succeed.
                recording.unlink()
                self.assertFalse(recording.exists())

    async def test_cancel_before_audio_starts_removes_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config').mkdir()
            (root/'config/wake.json').write_text('{"keyword":"小安"}')
            service = WakeService(root, None, None, None)
            recording = root / 'pending.wav'
            recording.write_bytes(b'audio')
            service.start_audio({'path': str(recording)})
            await service.cancel_audio()
            self.assertFalse(recording.exists())
            self.assertFalse(service.tasks)

    async def test_cancelled_cleanup_keeps_worker_available_for_final_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config').mkdir()
            (root/'config/wake.json').write_text('{"keyword":"小安"}')
            service = WakeService(root, None, None, None)
        waiting = asyncio.Event()
        exited = asyncio.Event()

        class Process:
            returncode = None
            stdin = None

            async def wait(self):
                waiting.set()
                await exited.wait()
                return self.returncode

        process = service.process = Process()
        cleanup = asyncio.create_task(service.stop_worker())
        await waiting.wait()
        cleanup.cancel()
        await asyncio.gather(cleanup, return_exceptions=True)
        self.assertIs(service.process, process)
        process.returncode = 0
        exited.set()
        await service.stop_worker()
        self.assertIsNone(service.process)

    async def test_failed_protocol_closes_worker_before_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config').mkdir()
            (root/'config/wake.json').write_text('{"keyword":"小安"}')
            service = WakeService(root, None, None, None)
            backoff = asyncio.Event()
            closed = asyncio.Event()
            recognizing = asyncio.Event()
            controls = []
            events = asyncio.Queue()
            service.clients.add(events)

            async def recognize(*args, **kwargs):
                recognizing.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    # A backend may finish despite cancellation. Its old result
                    # must not become a transcript for the replacement worker.
                    return {'text': '旧录音的迟到结果'}

            async def control(data):
                controls.append(data)

            service.recognize = recognize
            service.control = control
            recording = root / 'old.wav'
            recording.write_bytes(b'audio')
            service.start_audio({'path': str(recording)})
            audio_task = next(iter(service.tasks))
            await recognizing.wait()

            class Process:
                pid = 123
                returncode = None

                def __init__(self):
                    self.stdin = self
                    self.stdout = self

                async def readline(self):
                    return b'not-json\n'

                def close(self):
                    self.returncode = 0
                    closed.set()

                async def wait(self):
                    await closed.wait()
                    return self.returncode

                def kill(self):
                    self.close()

            process = Process()

            async def create(*args, **kwargs):
                return process

            async def sleep(delay):
                if delay == 3:
                    backoff.set()
                    await asyncio.Event().wait()

            with patch('gateway.wake.asyncio.create_subprocess_exec', create), \
                 patch('gateway.wake.asyncio.sleep', sleep):
                task = asyncio.create_task(service.run())
                try:
                    await asyncio.wait_for(backoff.wait(), 1)
                    self.assertTrue(closed.is_set(), 'Old worker still owns microphone during restart')
                    self.assertIsNone(service.process)
                    self.assertFalse(service.ready)
                    self.assertEqual(service.state, 'error')
                    self.assertTrue(audio_task.done(), 'Old ASR task survived worker restart')
                    self.assertFalse(recording.exists())
                    self.assertFalse(any(event['type'] == 'transcript' for event in events._queue))
                    self.assertFalse(controls, 'Old task resumed the replacement worker')
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
