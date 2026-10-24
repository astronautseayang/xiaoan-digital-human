"""Real SQLite scheduling, parsing and chat routing regressions (no live reminders)."""
import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo
import httpx
from gateway.care import CareEngine
from gateway.reminders import command
from gateway.companion import respectful_reply, save_salutation
from gateway import app as module

ROOT = Path(__file__).resolve().parents[1]


class ReminderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        (self.root / 'config/care.json').write_bytes((ROOT / 'config/care.json').read_bytes())
        self.spoken = []
        async def synth(text, **kwargs):
            self.spoken.append(text)
            return b'RIFF-test'
        self.synth = synth
        self.engine = CareEngine(self.root, synth, None)
        self.now = datetime(2026, 10, 24, 12, 50, tzinfo=ZoneInfo('Asia/Shanghai'))

    async def asyncTearDown(self):
        await asyncio.gather(*list(self.engine.tasks))
        self.engine.db.close()
        self.temp.cleanup()

    async def test_exact_request_durable_once_and_medication_text(self):
        result = command(self.engine, '今天12点52的时候提醒我吃药', self.now)
        self.assertIn('已设置提醒：2026年10月24日 12:52', result)
        command(self.engine, '今天12点52的时候提醒我吃药', self.now)
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM reminders').fetchone()[0], 1)
        second = CareEngine(self.root, self.synth, None)
        try:
            second.tick(self.now + timedelta(minutes=1))
            self.assertEqual(len(second.rows()), 0)
            second.tick(self.now + timedelta(minutes=2))
            second.tick(self.now + timedelta(minutes=2, seconds=10))
            await asyncio.gather(*list(second.tasks))
            self.assertEqual(len(second.rows()), 1)
            self.assertIn('请您吃药', second.rows()[0]['text'])
            self.assertIn('不要重复服药', second.rows()[0]['text'])
        finally:
            second.db.close()

    async def test_past_invalid_missing_or_unsupported_never_confirm(self):
        for text in ['今天12点49提醒我吃药', '今天25点提醒我吃药', '今天12点60提醒我吃药',
                     '提醒我吃药', '今天13点提醒我', '下周三8点提醒我吃药', '不要今天13点提醒我吃药',
                     '如果今天13点提醒我吃药', '修改吃药提醒到下午三点']:
            result = command(self.engine, text, self.now)
            self.assertIsNotNone(result, text)
            self.assertNotIn('已设置', result, text)
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM reminders').fetchone()[0], 0)

    async def test_chinese_time_relative_daily_list_cancel(self):
        for text, expected in [('明天下午三点半提醒我喝水', '2026-10-25T15:30'),
                               ('后天上午八点一刻提醒我散步', '2026-10-26T08:15'),
                               ('十分钟后提醒我关火', '2026-10-24T13:00'),
                               ('每天十二点五十二分提醒我吃药', '2026-10-24T12:52'),
                               ('提醒我明天8:05吃早饭', '2026-10-25T08:05')]:
            self.assertIn('已设置', command(self.engine, text, self.now))
            self.assertTrue(self.engine.db.execute('SELECT due FROM reminders ORDER BY rowid DESC LIMIT 1').fetchone()[0].startswith(expected))
        self.assertIn('喝水', command(self.engine, '查看提醒', self.now))
        row = self.engine.db.execute("SELECT * FROM reminders WHERE task='喝水'").fetchone()
        self.assertIn('已取消1条', command(self.engine, '取消提醒' + row['id'][:8], self.now))
        self.assertIn('已取消4条', command(self.engine, '取消全部提醒', self.now))
        self.assertEqual(command(self.engine, '查看提醒', self.now), '目前没有待办提醒。')

    async def test_missed_doses_not_replayed_daily_resumes(self):
        command(self.engine, '今天12点52提醒我吃药', self.now)
        command(self.engine, '每天12点52提醒我喝水', self.now)
        self.engine.tick(self.now + timedelta(hours=1))
        self.assertEqual(self.engine.db.execute("SELECT state FROM reminders WHERE task='吃药'").fetchone()[0], 'missed')
        self.assertIn('2026-10-25T12:52', self.engine.db.execute("SELECT due FROM reminders WHERE daily=1").fetchone()[0])
        self.assertFalse(any(r['title'] == '备忘提醒' for r in self.engine.rows()))

    async def test_one_minute_and_polite_prefixes(self):
        for text in ['一分钟后提醒我喝水', '一分钟后，提醒我喝水。',
                     '小安，提醒我一分钟后喝水', '请提醒我一分钟后喝水',
                     '小安，请提醒我一分钟以后喝水', '一分钟之后提醒我喝水']:
            with self.subTest(text=text):
                result = command(self.engine, text, self.now)
                self.assertIn('已设置提醒', result)
                row = self.engine.db.execute("SELECT * FROM reminders WHERE state='scheduled'").fetchone()
                self.assertEqual(row['task'], '喝水')
                self.assertEqual(datetime.fromisoformat(row['due']), self.now + timedelta(minutes=1))
                command(self.engine, '取消全部提醒', self.now)

    async def test_both_chat_paths_execute_tools_without_llm(self):
        previous = (module.ROOT, module.AUDIO, module.synthesize, getattr(module.app.state, 'care', None))
        module.ROOT, module.AUDIO, module.synthesize, module.app.state.care = self.root, self.root, self.synth, self.engine
        save_salutation(self.root, '爷爷')
        try:
            result = await module.chat(module.ChatRequest(text='明天12点52提醒我吃药'))
            self.assertTrue(result['text'].startswith('爷爷，已设置提醒'))
            job = {'text': '', 'clips': [], 'error': '', 'done': False}
            await module.run_chat_job(job, module.ChatRequest(text='查看提醒'), {})
            self.assertFalse(job['error'])
            self.assertIn('吃药', job['text'])
            self.assertEqual(job['clips'][0]['text'], job['text'])
        finally:
            module.ROOT, module.AUDIO, module.synthesize, module.app.state.care = previous

    def test_respectful_address_preserves_family_topics(self):
        self.assertEqual(respectful_reply('好孩子，今天开心吗？乖孩子，休息一下。', '爷爷'), '爷爷，今天开心吗？爷爷，休息一下。')
        self.assertNotIn('好孩子', respectful_reply('您真是个好孩子。', '爷爷'))
        self.assertEqual(respectful_reply('您的孙子是个好孩子。', '爷爷'), '您的孙子是个好孩子。')


if __name__ == '__main__':
    unittest.main()
