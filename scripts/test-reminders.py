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

    async def test_complete_relative_durations(self):
        for duration, minutes in [('一个小时三十分钟', 90), ('两小时又十五分钟', 135),
                                  ('1.5小时', 90), ('1．5小时', 90), ('半小时', 30),
                                  ('半个小时', 30), ('一个半小时', 90), ('一小时半', 90)]:
            for text in [duration+'后提醒我吃饭', '提醒我'+duration+'以后吃饭']:
                with self.subTest(text=text):
                    self.assertIn('已设置提醒', command(self.engine, text, self.now))
                    row = self.engine.db.execute("SELECT * FROM reminders WHERE state='scheduled'").fetchone()
                    self.assertEqual(row['task'], '吃饭')
                    self.assertEqual(datetime.fromisoformat(row['due']), self.now+timedelta(minutes=minutes))
                    command(self.engine, '取消全部提醒', self.now)

    async def test_negative_and_multiple_times_never_commit(self):
        for text in ['-1分钟后提醒我喝水', '负一小时后提醒我喝水', '−1.5小时后提醒我喝水',
                     '一小时后和两小时后提醒我喝水', '一小时后今天三点提醒我喝水',
                     '一天一小时后提醒我喝水', '一个小时零三十分钟后提醒我喝水']:
            with self.subTest(text=text):
                self.assertNotIn('已设置提醒', command(self.engine, text, self.now))
                self.assertEqual(self.engine.db.execute('SELECT count(*) FROM reminders').fetchone()[0], 0)

    async def test_midnight_is_not_noon(self):
        now = self.now.replace(hour=10)
        for time, expected in [('今天晚上十二点', '2026-10-25T00:00'),
                               ('明天晚上十二点半', '2026-10-26T00:30'),
                               ('明天凌晨十二点', '2026-10-25T00:00'),
                               ('今天中午十二点', '2026-10-24T12:00'),
                               ('每天晚上十二点', '2026-10-25T00:00')]:
            with self.subTest(time=time):
                self.assertIn('已设置提醒', command(self.engine, time+'提醒我休息', now))
                row = self.engine.db.execute('SELECT due FROM reminders ORDER BY rowid DESC LIMIT 1').fetchone()
                self.assertTrue(row['due'].startswith(expected), row['due'])
                command(self.engine, '取消全部提醒', now)

    async def test_explicit_clock_seconds_are_not_silently_discarded(self):
        for clock in ('明天8点30分20秒', '明天八点三十分零五秒', '明天8点30秒', '明天8:30:20'):
            for text in (clock+'提醒我关火', '提醒我'+clock+'关火'):
                with self.subTest(text=text):
                    self.engine.db.execute('DELETE FROM reminders')
                    self.engine.db.commit()
                    result = command(self.engine, text, self.now)
                    self.assertNotIn('已设置提醒', result)
                    self.assertEqual(self.engine.db.execute('SELECT count(*) FROM reminders').fetchone()[0], 0)
        for text in ('提醒我明天8点做三十秒伸展', '明天8点提醒我做三十秒伸展'):
            with self.subTest(text=text):
                self.engine.db.execute('DELETE FROM reminders')
                self.engine.db.commit()
                result = command(self.engine, text, self.now)
                self.assertIn('已设置提醒', result)
                row = self.engine.db.execute("SELECT * FROM reminders WHERE state='scheduled'").fetchone()
                self.assertEqual(row['task'], '做三十秒伸展')
                self.assertEqual(datetime.fromisoformat(row['due']), self.now.replace(hour=8, minute=0)+timedelta(days=1))
                command(self.engine, '取消全部提醒', self.now)

    async def test_decimal_clocks_never_become_partial_times(self):
        for clock in ('明天8.5点', '明天8．5点', '明天8点30.5分', '明天8:30.5', '明天8点.5分'):
            for text in (clock+'提醒我关火', '提醒我'+clock+'关火'):
                with self.subTest(text=text):
                    self.engine.db.execute('DELETE FROM reminders')
                    self.engine.db.commit()
                    self.assertNotIn('已设置提醒', command(self.engine, text, self.now))
                    self.assertEqual(self.engine.db.execute('SELECT count(*) FROM reminders').fetchone()[0], 0)
        for text in ('明天8点提醒我测量1.5升水', '提醒我明天8点测量1.5升水'):
            with self.subTest(text=text):
                self.engine.db.execute('DELETE FROM reminders')
                self.engine.db.commit()
                self.assertIn('已设置提醒', command(self.engine, text, self.now))
                row = self.engine.db.execute("SELECT * FROM reminders WHERE state='scheduled'").fetchone()
                self.assertEqual(row['task'], '测量1.5升水')
                self.assertEqual(datetime.fromisoformat(row['due']), self.now.replace(hour=8, minute=0)+timedelta(days=1))
                command(self.engine, '取消全部提醒', self.now)

    async def test_task_words_do_not_change_time_or_recurrence(self):
        for task in ('看月亮', '记录每天步数', '准备下午的会议', '确认后天行程', '复习去年笔记'):
            with self.subTest(task=task):
                command(self.engine, '取消全部提醒', self.now)
                result = command(self.engine, '提醒我明天8点' + task, self.now)
                self.assertIn('已设置提醒', result)
                row = self.engine.db.execute("SELECT * FROM reminders WHERE state='scheduled'").fetchone()
                self.assertEqual(row['task'], task)
                self.assertEqual(datetime.fromisoformat(row['due']), self.now.replace(hour=8, minute=0)+timedelta(days=1))
                self.assertEqual(row['daily'], 0)
                command(self.engine, '取消全部提醒', self.now)

    async def test_relative_task_words_do_not_create_daily_reminder(self):
        result = command(self.engine, '提醒我十分钟后记录每天步数', self.now)
        self.assertIn('已设置提醒', result)
        row = self.engine.db.execute("SELECT * FROM reminders WHERE state='scheduled'").fetchone()
        self.assertEqual(row['daily'], 0)
        self.assertEqual(row['task'], '记录每天步数')
        self.assertEqual(datetime.fromisoformat(row['due']), self.now+timedelta(minutes=10))

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
