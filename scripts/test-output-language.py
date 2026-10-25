"""Chinese rewrite fallback must tolerate malformed callback output."""
import asyncio
import unittest
from unittest.mock import AsyncMock

from gateway.output_language import chinese_reply

FALLBACK = '这部分我还没能用中文说明清楚，请您换个问法。'


class OutputLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_rewrite_results_use_fallback(self):
        for value in (None, 1, [], {}, b'bytes', '', ' \n\t ', 'still English'):
            with self.subTest(value=value):
                rewrite = AsyncMock(return_value=value)
                self.assertEqual(await chinese_reply('Unexpected English sentence.', rewrite), FALLBACK)
                rewrite.assert_awaited_once()

    async def test_valid_rewrite_preserves_chinese_and_numbers(self):
        rewrite = AsyncMock(return_value='  請您下午3點喝100毫升溫水。  ')
        self.assertEqual(await chinese_reply('Drink some water at 3 pm.', rewrite), '请您下午3点喝100毫升温水。')

    async def test_chinese_and_known_words_need_no_rewrite(self):
        rewrite = AsyncMock(side_effect=AssertionError('unnecessary model request'))
        self.assertEqual(await chinese_reply('爺爺，今天12點52分。', rewrite), '爷爷，今天12点52分。')
        self.assertEqual(await chinese_reply('OK，謝謝。', rewrite), '好的，谢谢。')
        rewrite.assert_not_awaited()

    async def test_failure_falls_back_and_cancellation_propagates(self):
        self.assertEqual(await chinese_reply('Unexpected English sentence.', AsyncMock(side_effect=RuntimeError('offline'))), FALLBACK)
        with self.assertRaises(asyncio.CancelledError):
            await chinese_reply('Unexpected English sentence.', AsyncMock(side_effect=asyncio.CancelledError()))


if __name__ == '__main__':
    unittest.main()
