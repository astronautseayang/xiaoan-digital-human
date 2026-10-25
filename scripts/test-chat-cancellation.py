"""Cancelling a request must not interrupt the background job's cleanup."""
import asyncio
import copy
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
import httpx
from gateway import app as module


class ChatCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_startup_failure_closes_created_resources(self):
        for stage in ('WeatherService', 'CareEngine', 'WakeService'):
            with self.subTest(stage=stage):
                error = RuntimeError('injected ' + stage + ' startup failure')
                client = SimpleNamespace(aclose=AsyncMock())
                care = SimpleNamespace(run=AsyncMock(), db=SimpleNamespace(close=Mock()))
                fake_app = SimpleNamespace(state=SimpleNamespace())
                before = asyncio.all_tasks()
                with patch.object(module.asr_service, 'warmup'), \
                     patch.object(module.httpx, 'AsyncClient', return_value=client), \
                     patch.object(module, 'WeatherService', side_effect=error if stage == 'WeatherService' else None), \
                     patch.object(module, 'CareEngine', side_effect=error if stage == 'CareEngine' else None, return_value=care), \
                     patch.object(module, 'WakeService', side_effect=error if stage == 'WakeService' else None), \
                     patch.object(module, 'job_tasks', set()), patch.object(module, 'job_handles', {}), \
                     patch.object(module, 'asr_tasks', set()):
                    try:
                        with self.assertRaises(RuntimeError) as raised:
                            await module.lifespan(fake_app).__aenter__()
                        self.assertIs(raised.exception, error)
                        client.aclose.assert_awaited_once()
                        if stage == 'WakeService':
                            care.db.close.assert_called_once()
                        self.assertFalse(asyncio.all_tasks() - before, 'Startup left a background task')
                    finally:
                        leaked = asyncio.all_tasks() - before
                        for task in leaked:
                            task.cancel()
                        await asyncio.gather(*leaked, return_exceptions=True)

    async def test_lifespan_exception_or_cancellation_still_cleans_resources(self):
        for error in (RuntimeError('injected lifespan failure'), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                running = set()
                started = asyncio.Event()
                async def idle():
                    running.add(asyncio.current_task())
                    if len(running) == 3:
                        started.set()
                    await asyncio.Event().wait()
                client = SimpleNamespace(aclose=AsyncMock())
                fake_app = SimpleNamespace(state=SimpleNamespace())
                with patch.object(module, 'jobs', {}), patch.object(module, 'job_handles', {}), \
                     patch.object(module, 'job_tasks', set()), patch.object(module, 'asr_tasks', set()), \
                     patch.object(module.asr_service, 'warmup'), \
                     patch.object(module.httpx, 'AsyncClient', return_value=client), \
                     patch.object(module, 'WeatherService'), \
                     patch.object(module, 'CareEngine', return_value=SimpleNamespace(run=idle)), \
                     patch.object(module, 'WakeService', return_value=SimpleNamespace(run=idle, heartbeat=idle)):
                    lifecycle = module.lifespan(fake_app)
                    await lifecycle.__aenter__()
                    await asyncio.wait_for(started.wait(), 1)
                    try:
                        # asynccontextmanager propagates the original body exception
                        # by returning False from __aexit__ after cleanup.
                        self.assertFalse(await lifecycle.__aexit__(type(error), error, error.__traceback__))
                        self.assertTrue(all(task.done() for task in running), 'Background tasks leaked')
                        client.aclose.assert_awaited_once()
                    finally:
                        for task in running:
                            task.cancel()
                        await asyncio.gather(*running, return_exceptions=True)

    async def test_cancel_terminal_job_preserves_success_failure_and_cancellation(self):
        for reason in ('stop', 'length', 'timeout', 'repetition', '', 'cancelled'):
            for retained_handle in (False, True):
                with self.subTest(reason=reason, retained_handle=retained_handle):
                    job = {'done': True, 'text_done': True, 'finish_reason': reason,
                           'created': time.monotonic(), 'text': '已有回答',
                           'error': '原错误' if reason in ('timeout', 'repetition', '') else '',
                           'clips': [{'audio_url': '/audio/existing.wav'}]}
                    original = copy.deepcopy(job)
                    task = asyncio.create_task(asyncio.sleep(0))
                    await task
                    with patch.object(module, 'jobs', {'test': job}), \
                         patch.object(module, 'job_handles', {'test': task} if retained_handle else {}):
                        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://test') as client:
                            for _ in range(2):
                                response = await client.delete('/api/chat/jobs/test')
                                self.assertEqual(response.status_code, 200)
                                self.assertEqual(response.json(), {'id': 'test', 'done': True})
                                self.assertEqual(job, original)
                            response = await client.get('/api/chat/jobs/test')
                            self.assertEqual(response.json(), original)

    async def check_cleanup(self, cancel_request):
        started = asyncio.Event()
        cleaning = asyncio.Event()
        release = asyncio.Event()
        cleaned = asyncio.Event()
        async def background():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
                cleaned.set()
        job = {'done': False, 'text_done': False, 'finish_reason': ''}
        task = asyncio.create_task(background())
        await started.wait()
        with patch.object(module, 'jobs', {'test': job}), patch.object(module, 'job_handles', {'test': task}):
            first = asyncio.create_task(module.cancel_chat_job('test'))
            second = None
            try:
                await asyncio.wait_for(cleaning.wait(), 1)
                if cancel_request:
                    first.cancel()
                    await asyncio.gather(first, return_exceptions=True)
                else:
                    second = asyncio.create_task(module.cancel_chat_job('test'))
                    await asyncio.sleep(0)
                self.assertFalse(task.done(), 'Request cancellation interrupted resource cleanup')
                self.assertFalse(job['done'], 'Job slot released before cleanup finished')
                release.set()
                await asyncio.gather(task, first, *([second] if second else []), return_exceptions=True)
                await asyncio.sleep(0)
                self.assertTrue(cleaned.is_set())
                self.assertTrue(job['done'] and job['text_done'])
                self.assertEqual(job['finish_reason'], 'cancelled')
            finally:
                release.set()
                for pending in (task, first, second):
                    if pending is not None and not pending.done():
                        pending.cancel()
                await asyncio.gather(*[t for t in (task, first, second) if t is not None], return_exceptions=True)

    async def test_cancel_request_disconnection_preserves_cleanup(self):
        await self.check_cleanup(True)

    async def test_simultaneous_cancellations_preserve_cleanup(self):
        await self.check_cleanup(False)

    async def test_cancel_before_background_starts_finishes_job(self):
        async def background():
            self.fail('Cancelled job should not start')
        job = {'done': False}
        task = asyncio.create_task(background())
        with patch.object(module, 'jobs', {'test': job}), patch.object(module, 'job_handles', {'test': task}):
            await module.cancel_chat_job('test')
            self.assertTrue(task.cancelled())
            self.assertTrue(job['done'] and job['text_done'])
            self.assertEqual(job['finish_reason'], 'cancelled')

    async def check_shutdown_cleanup(self, cancel_first):
        started, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))
        async def background():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
                cleaned.set()
        async def idle():
            await asyncio.Event().wait()
        async def close():
            self.assertTrue(cleaned.is_set(), 'HTTP client closed before job cleanup')
        client = SimpleNamespace(aclose=AsyncMock(side_effect=close))
        state = SimpleNamespace()
        fake_app = SimpleNamespace(state=state)
        job = {'done': False, 'text_done': False, 'finish_reason': ''}
        task = asyncio.create_task(background())
        await started.wait()
        with patch.object(module, 'jobs', {'test': job}), \
             patch.object(module, 'job_handles', {'test': task}), \
             patch.object(module, 'job_tasks', {task}), \
             patch.object(module.asr_service, 'warmup'), \
             patch.object(module.httpx, 'AsyncClient', return_value=client), \
             patch.object(module, 'WeatherService'), \
             patch.object(module, 'CareEngine', return_value=SimpleNamespace(run=idle)), \
             patch.object(module, 'WakeService', return_value=SimpleNamespace(run=idle, heartbeat=idle)):
            lifecycle = module.lifespan(fake_app)
            await lifecycle.__aenter__()
            request = asyncio.create_task(module.cancel_chat_job('test')) if cancel_first else None
            shutdown = None
            try:
                if cancel_first:
                    await asyncio.wait_for(cleaning.wait(), 1)
                waiting = asyncio.Event()
                gather = asyncio.gather
                def observe_gather(*tasks, **kwargs):
                    if task in tasks:
                        waiting.set()
                    return gather(*tasks, **kwargs)
                with patch.object(module.asyncio, 'gather', observe_gather):
                    shutdown = asyncio.create_task(lifecycle.__aexit__(None, None, None))
                    await asyncio.wait_for(waiting.wait(), 1)
                    await asyncio.sleep(0)
                self.assertFalse(task.done(), 'Shutdown cancelled a job already cleaning up')
                self.assertFalse(shutdown.done())
                self.assertTrue(cleaning.is_set())
                release.set()
                await asyncio.wait_for(asyncio.gather(task, shutdown, *([request] if request else []), return_exceptions=True), 1)
                self.assertTrue(cleaned.is_set())
                self.assertTrue(job['done'])
                client.aclose.assert_awaited_once()
                self.assertFalse(shutdown.result())
            finally:
                release.set()
                await asyncio.gather(task, *([request] if request else []), *([shutdown] if shutdown else []), return_exceptions=True)

    async def test_shutdown_waits_for_already_cancelled_job_cleanup(self):
        await self.check_shutdown_cleanup(True)

    async def test_shutdown_cancels_active_job_and_waits_before_closing_client(self):
        await self.check_shutdown_cleanup(False)


if __name__ == '__main__':
    unittest.main()
