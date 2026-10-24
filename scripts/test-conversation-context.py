"""Multi-turn weather, location and actual reminder transactions, isolated state."""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from gateway import app as module
from gateway.care import CareEngine
from gateway.weather import WeatherService
from gateway.conversation_context import resolve
from zoneinfo import ZoneInfo


def history(user,answer):
    return [module.Message(role='user',content=user),module.Message(role='assistant',content=answer)]

class ContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'config').mkdir();(self.root/'config/care.json').write_bytes((module.ROOT/'config/care.json').read_bytes())
        self.calls=[]
        today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
        async def handle(req):
            self.calls.append(req)
            if 'geocoding' in req.url.host:
                city=req.url.params['name']
                return httpx.Response(200,json={'results':[{'name':city,'latitude':30.3 if city=='杭州' else 31.2,'longitude':120.1,'timezone':'Asia/Shanghai'}]})
            return httpx.Response(200,json={'timezone':'Asia/Shanghai','current':{'time':str(today)+'T12:00','temperature_2m':20,'apparent_temperature':20,'relative_humidity_2m':60,'weather_code':3,'wind_speed_10m':2},'daily':{'time':[str(today+timedelta(days=i)) for i in range(3)],'weather_code':[3,61,0],'temperature_2m_max':[25]*3,'temperature_2m_min':[18]*3,'precipitation_probability_max':[20,70,10]}})
        self.client=httpx.AsyncClient(transport=httpx.MockTransport(handle));self.weather=WeatherService(self.root,self.client)
        async def synth(*a,**kw):return b'wave'
        self.synth=synth;self.care=CareEngine(self.root,synth,None)
        self.patches=[patch.object(module.app.state,'care',self.care,create=True),patch.object(module.app.state,'weather',self.weather,create=True)]
        for p in self.patches:p.start()
        await self.weather.set_city('上海')

    async def asyncTearDown(self):
        for p in reversed(self.patches):p.stop()
        self.care.db.close();await self.client.aclose();self.tmp.cleanup()

    async def test_weather_day_city_and_umbrella_chain(self):
        user='杭州今天天气怎么样';answer=await module.local_reply(user)
        user2='那明天呢';answer2=await module.local_reply(user2,history(user,answer));self.assertIn('杭州明天',answer2)
        user3='那上海呢';answer3=await module.local_reply(user3,history(user2,answer2));self.assertIn('上海明天',answer3)
        answer4=await module.local_reply('要带伞吗',history(user3,answer3));self.assertIn('上海明天',answer4);self.assertIn('带伞',answer4)
        self.assertEqual(self.weather.location()['city'],'上海')

    async def test_location_and_city_clarification(self):
        answer=await module.local_reply('订为到行舟')
        answer2=await module.local_reply('换成宁波',history('订为到行舟',answer))
        self.assertIn('设置为宁波',answer2);self.assertEqual(self.weather.location()['city'],'宁波')
        answer3=await module.local_reply('那明天呢',history('换成宁波',answer2));self.assertIn('宁波明天',answer3)
        ambiguous=await module.local_reply('定位到苏周')
        self.assertIn('设置为苏州',await module.local_reply('苏州',history('定位到苏周',ambiguous)))

    async def test_reminder_change_atomic_cancel_and_expired(self):
        answer=await module.local_reply('一分钟后提醒我喝水')
        original=self.care.db.execute('SELECT * FROM reminders').fetchone()
        changed=await module.local_reply('改成两分钟后',history('一分钟后提醒我喝水',answer))
        self.assertIn('已修改提醒',changed)
        rows=self.care.db.execute("SELECT * FROM reminders WHERE state='scheduled'").fetchall();self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['task'],'喝水');self.assertGreater(datetime.fromisoformat(rows[0]['due']),datetime.fromisoformat(original['due']))
        cancelled=await module.local_reply('取消这个提醒',history('改成两分钟后',changed));self.assertIn('已取消1条',cancelled)
        self.assertIn('已失效',await module.local_reply('改成三分钟后',history('改成两分钟后',changed)))

    async def test_failed_change_keeps_original(self):
        answer=await module.local_reply('一分钟后提醒我吃药')
        result=await module.local_reply('改成零分钟后',history('一分钟后提醒我吃药',answer))
        self.assertIn('还没有设置提醒',result)
        self.assertEqual(self.care.db.execute("SELECT count(*) FROM reminders WHERE state='scheduled'").fetchone()[0],1)

    async def test_pending_reminder_missing_time_and_task(self):
        answer=await module.local_reply('提醒我喝水');self.assertIn('具体时间',answer)
        follow=await module.local_reply('两分钟后',history('提醒我喝水',answer));self.assertIn('已设置提醒',follow);self.assertIn('喝水',follow)
        answer=await module.local_reply('三分钟后提醒我');self.assertIn('做什么',answer)
        self.assertIn('吃药',await module.local_reply('吃药',history('三分钟后提醒我',answer)))

    async def test_topic_change_and_no_cross_session_memory(self):
        self.assertTrue(resolve('那明天呢').reply)
        self.assertEqual(resolve('那明天呢',history('我喜欢散步','您可以慢慢散步。')).text,'那明天呢')
        self.assertTrue(resolve('改成两分钟后',history('讲个故事','从前有座山。')).reply)
        self.assertIsNone(await module.local_reply('不要换成杭州',history('定位到上海','已将天气位置设置为上海。')))
        self.assertIsNone(await module.local_reply('我们聊聊音乐',history('定位到上海','已将天气位置设置为上海。')))

    async def test_no_internal_ids_and_ordinal_cancellation(self):
        answer=await module.local_reply('一分钟后提醒我喝水')
        self.assertNotIn('编号',answer)
        first=self.care.db.execute('SELECT * FROM reminders').fetchone()
        self.assertNotIn(first['id'][:8],answer)
        await module.local_reply('两分钟后提醒我散步')
        listing=await module.local_reply('查看提醒')
        self.assertNotIn(first['id'][:8],listing)
        self.assertIn('已取消',await module.local_reply('取消第一个提醒'))
        self.assertEqual(self.care.db.execute("SELECT task FROM reminders WHERE state='scheduled'").fetchone()['task'],'散步')

    async def test_complete_and_streaming_use_history(self):
        answer=await module.local_reply('杭州今天天气')
        req=module.ChatRequest(text='那明天呢',history=history('杭州今天天气',answer))
        with patch.object(module,'AUDIO',self.root),patch.object(module,'synthesize',self.synth):
            result=await module.chat(req);self.assertIn('杭州明天',result['text'])
            job={'text':'','clips':[],'done':False,'text_done':False,'error':'','truncated':False}
            await module.run_chat_job(job,req,{})
            self.assertFalse(job['error']);self.assertIn('杭州明天',job['text']);self.assertTrue(job['clips'])

if __name__=='__main__':unittest.main()
