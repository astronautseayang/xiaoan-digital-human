"""Malformed upstream completion data must not become an internal server error."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from gateway import app as module


class ModelResponseTests(unittest.IsolatedAsyncioTestCase):
    def malformed(self):
        return [None, [], {}, {'choices': []}, {'choices': [None]},
                {'choices': [{'message': None}]},
                *[{'choices': [{'message': {'content': value}}]} for value in (None, 3, [], {}, '   ')],
                *[{'choices': [{'finish_reason': reason, 'message': {'content': '不应当播出的部分回答。'}}]}
                  for reason in (True, 0, {}, [], '', 'content_filter', 'tool_calls', 'unknown')]]

    async def test_direct_malformed_response_is_502_without_speech_or_files(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(module, 'AUDIO', Path(directory)), \
             patch.object(module, 'local_reply', AsyncMock(return_value=None)), \
             patch.object(module, 'synthesize', AsyncMock()) as synth:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app, raise_app_exceptions=False), base_url='http://test') as client:
                for payload in self.malformed():
                    with self.subTest(payload=payload), patch.object(module, 'upstream_json', AsyncMock(return_value=payload)):
                        response = await client.post('/api/chat', json={'text': '测试'})
                        self.assertEqual(response.status_code, 502)
                        self.assertIn('格式异常', response.json()['detail'])
                synth.assert_not_awaited()
                self.assertEqual(list(Path(directory).iterdir()), [])

    async def test_malformed_translation_uses_chinese_fallback(self):
        for payload in self.malformed():
            with self.subTest(payload=payload), patch.object(module, 'upstream_json', AsyncMock(return_value=payload)):
                result = await module.chinese_output('This is a long English sentence.')
                self.assertEqual(result, '这部分我还没能用中文说明清楚，请您换个问法。')

    async def test_valid_completion_and_translation_still_work(self):
        payload = {'choices': [{'message': {'content': '  今天可以慢慢散步。  '}}]}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(module, 'AUDIO', Path(directory)), \
             patch.object(module, 'local_reply', AsyncMock(return_value=None)), \
             patch.object(module, 'upstream_json', AsyncMock(return_value=payload)), \
             patch.object(module, 'synthesize', AsyncMock(return_value=b'audio')):
            result = await module.chat(module.ChatRequest(text='测试'))
            self.assertIn('今天可以慢慢散步。', result['text'])
            self.assertEqual(await module.chinese_output('Please walk slowly outside.'), '今天可以慢慢散步。')

    async def test_supported_and_legacy_finish_reasons_remain_compatible(self):
        for reason in (None, 'stop', 'length'):
            with self.subTest(reason=reason):
                payload = {'choices': [{'finish_reason': reason, 'message': {'content': '有效文字'}}]}
                self.assertEqual(module.completion_text(payload), '有效文字')


if __name__ == '__main__':
    unittest.main()
