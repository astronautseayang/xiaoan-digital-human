"""A cancelled request must not release ASR serialization while its thread runs."""
import asyncio
import io
import threading
import unittest
from unittest.mock import patch
import numpy as np
from fastapi import UploadFile
from gateway import app as module


class ASRCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def check_cancelled_request(self, fail_worker):
        loop = asyncio.get_running_loop()
        started, second_started = asyncio.Event(), asyncio.Event()
        release = threading.Event()
        transcribed = threading.Event()
        calls = []
        def prepare(*args, **kwargs):
            calls.append(True)
            if len(calls) == 1:
                loop.call_soon_threadsafe(started.set)
                if not release.wait(3):
                    raise RuntimeError('Test did not release the worker')
            else:
                loop.call_soon_threadsafe(second_started.set)
            return np.full(16000, .1, dtype=np.float32)
        def upload():
            return UploadFile(file=io.BytesIO(b'fixture'), filename='voice.wav')
        def transcribe(audio):
            transcribed.set()
            if fail_worker and len(calls) == 1:
                raise RuntimeError('Late worker failure')
            return '迟到的识别结果'
        lock = asyncio.Lock()
        with patch.object(module, 'asr_lock', lock), \
             patch.object(module, 'asr_tasks', set()), \
             patch.object(module.speaker_input, 'prepare', side_effect=prepare), \
             patch.object(module.asr_service, 'transcribe', side_effect=transcribe), \
             patch.object(module, 'handle_care_text') as command:
            first = asyncio.create_task(module.asr(upload()))
            second = None
            try:
                await asyncio.wait_for(started.wait(), 1)
                first.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(first, 1)
                self.assertTrue(lock.locked(), 'ASR lock released while processing thread still runs')
                second = asyncio.create_task(module.asr(upload(), care_commands=False))
                await asyncio.sleep(0)
                self.assertFalse(second_started.is_set())
                self.assertEqual(len(calls), 1)
                queued = asyncio.create_task(module.asr(upload(), care_commands=False))
                await asyncio.sleep(0)
                queued.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await queued
                self.assertEqual(len(calls), 1, 'Cancelled queued request started processing')
                command.assert_not_called()
                release.set()
                response = await asyncio.wait_for(second, 2)
                self.assertEqual(response['text'], '迟到的识别结果')
                self.assertTrue(second_started.is_set())
                self.assertFalse(lock.locked())
                self.assertFalse(module.asr_tasks)
                command.assert_not_called()
            finally:
                release.set()
                await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
                await asyncio.to_thread(transcribed.wait, 2)
                # Let a retained worker finish before restoring test doubles.
                for _ in range(100):
                    if not lock.locked(): break
                    await asyncio.sleep(.01)

    async def test_cancelled_request_keeps_thread_serialized_and_discards_result(self):
        await self.check_cancelled_request(False)

    async def test_late_worker_failure_releases_serialization_and_next_request_recovers(self):
        await self.check_cancelled_request(True)


if __name__ == '__main__':
    unittest.main()
