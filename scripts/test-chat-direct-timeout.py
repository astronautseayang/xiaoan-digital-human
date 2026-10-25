"""Direct chat has a total deadline, including waiting for the speech lock."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from gateway import app as module


class DirectTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, stage):
        cancelled = asyncio.Event()
        lock = asyncio.Lock()

        async def blocked(*args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def waiting_speech(*args, **kwargs):
            try:
                async with lock:
                    return b'audio'
            finally:
                cancelled.set()

        async def slow_model(*args, **kwargs):
            await asyncio.sleep(.04)
            return {'choices': [{'message': {'content': '今天一起聊聊。'}}]}

        async def slow_speech(*args, **kwargs):
            try:
                await asyncio.sleep(.04)
                return b'audio'
            finally:
                cancelled.set()

        if stage == 'lock':
            await lock.acquire()
        model = blocked if stage == 'model' else slow_model if stage == 'total' else AsyncMock()
        speech = waiting_speech if stage == 'lock' else slow_speech if stage == 'total' else AsyncMock()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(module, 'AUDIO', Path(directory)), \
             patch.object(module, 'CHAT_TIMEOUT_SECONDS', .06), \
             patch.object(module, 'local_reply', AsyncMock(return_value='您好。' if stage == 'lock' else None)), \
             patch.object(module, 'upstream_json', model), \
             patch.object(module, 'synthesize', speech):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://test') as client:
                response = await asyncio.wait_for(client.post('/api/chat', json={'text': '测试'}), .5)
                self.assertEqual(response.status_code, 504)
                self.assertIn('超时', response.json()['detail'])
                self.assertTrue(cancelled.is_set())
                self.assertEqual(list(Path(directory).iterdir()), [])
                if stage == 'lock':
                    lock.release()
                    await asyncio.wait_for(lock.acquire(), .1)
                    lock.release()
                with patch.object(module, 'local_reply', AsyncMock(return_value='您好。')), \
                     patch.object(module, 'synthesize', AsyncMock(return_value=b'audio')):
                    retry = await client.post('/api/chat', json={'text': '再次测试'})
                self.assertEqual(retry.status_code, 200)
                self.assertEqual(len(list(Path(directory).glob('*.wav'))), 1)

    async def test_model_wait_is_bounded(self):
        await self.exercise('model')

    async def test_speech_queue_wait_is_bounded_and_removed(self):
        await self.exercise('lock')

    async def test_deadline_covers_sum_of_stages(self):
        await self.exercise('total')

    async def test_request_cancellation_reaches_child_work(self):
        entered = asyncio.Event()
        stopped = asyncio.Event()

        async def blocked(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        with patch.object(module, 'local_reply', blocked):
            task = asyncio.create_task(module.chat(module.ChatRequest(text='测试')))
            await asyncio.wait_for(entered.wait(), .5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(stopped.is_set())


if __name__ == '__main__':
    unittest.main()
