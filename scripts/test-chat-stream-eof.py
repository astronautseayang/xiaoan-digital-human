"""A socket EOF alone cannot prove the model completed its answer."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gateway import app as module


class Stream:
    def __init__(self, terminal):
        self.terminal = terminal
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        yield 'data: ' + json.dumps({'choices': [{'delta': {'content': '今天天气不错，我们可以一起聊聊散步和日常生活。'}}]})
        if isinstance(self.terminal, list):
            for payload in self.terminal:
                yield 'data: ' + json.dumps(payload)
            yield 'data: [DONE]'
            return
        if self.terminal in ('stop', 'length'):
            yield 'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': self.terminal}]})
        if self.terminal == 'done':
            yield 'data: [DONE]'
        if self.terminal in ('stop-open', 'length-open'):
            reason = self.terminal.removesuffix('-open')
            yield 'data: ' + json.dumps({'choices': [{'delta': {'content': '最后一句也应保留。'}, 'finish_reason': reason}]})
            await asyncio.Event().wait()
        if self.terminal == 'empty-stop-open':
            yield 'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
            await asyncio.Event().wait()


class Client:
    def __init__(self, terminal):
        self.terminal = terminal

    def stream(self, *args, **kwargs):
        self.response = Stream(self.terminal)
        return self.response


class StreamEofTests(unittest.IsolatedAsyncioTestCase):
    async def run_job(self, terminal):
        async def local(*args):
            return None

        async def synth(*args, **kwargs):
            return b'test audio'

        job = dict(text='', clips=[], done=False, text_done=False, error='', truncated=False, finish_reason='')
        client = Client(terminal)
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'AUDIO', Path(directory)), \
             patch.object(module, 'jobs', {}), patch.object(module, 'local_reply', local), \
             patch.object(module, 'synthesize', synth), patch.object(module.app.state, 'client', client, create=True):
            await asyncio.wait_for(module.run_chat_job(job, module.ChatRequest(text='测试'), {}), 2)
        self.assertTrue(job['done'] and job['text_done'])
        self.assertTrue(client.response.closed)
        return job

    async def test_eof_without_completion_is_failure_and_next_job_succeeds(self):
        job = await self.run_job(None)
        self.assertTrue(job['error'], 'Partial answer was advertised as successful')
        self.assertEqual(job['clips'], [], 'Unconfirmed buffered tail was synthesized')
        retry = await self.run_job('stop')
        self.assertFalse(retry['error'])
        self.assertTrue(retry['clips'])

    async def test_explicit_done_and_finish_reason_allow_clean_eof(self):
        for terminal in ('done', 'stop', 'length'):
            with self.subTest(terminal=terminal):
                job = await self.run_job(terminal)
                self.assertFalse(job['error'])
                self.assertTrue(job['clips'])
                self.assertEqual(job['truncated'], terminal == 'length')

    async def test_finish_reason_completes_without_waiting_for_socket_close(self):
        for terminal in ('stop-open', 'length-open', 'empty-stop-open'):
            with self.subTest(terminal=terminal):
                job = await self.run_job(terminal)
                self.assertFalse(job['error'])
                self.assertTrue(job['clips'])
                self.assertEqual(job['truncated'], terminal == 'length-open')
                self.assertEqual(job['finish_reason'], 'length' if terminal == 'length-open' else 'stop')
                if terminal != 'empty-stop-open':
                    self.assertTrue(job['text'].endswith('最后一句也应保留。'))

    async def test_malformed_fields_cannot_become_successful_completion(self):
        choices = [
            {'delta': {}, 'finish_reason': value}
            for value in (True, 1, {}, [], 'content_filter', 'tool_calls', 'unexpected')
        ] + [{'delta': {'content': value}} for value in (False, 0, [], {}, 123)] + [
            {'delta': []}, {'delta': 'invalid'},
        ]
        for choice in choices:
            with self.subTest(choice=choice):
                job = await self.run_job([{'choices': [choice]}])
                self.assertTrue(job['error'], 'Malformed frame was accepted')
                self.assertIsInstance(job['finish_reason'], str)
                self.assertEqual(job['clips'], [])

    async def test_role_usage_and_null_content_frames_remain_compatible(self):
        frames = [{'choices': []}, {'choices': [{'delta': {'role': 'assistant'}}]},
                  {'choices': [{'delta': {'content': None}}]},
                  {'choices': [{'delta': None, 'finish_reason': 'stop'}]}]
        job = await self.run_job(frames)
        self.assertFalse(job['error'])
        self.assertEqual(job['finish_reason'], 'stop')
        self.assertTrue(job['clips'])


if __name__ == '__main__':
    unittest.main()
