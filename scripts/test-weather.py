"""Weather routing/cache/location regression. All locations and network data isolated."""
import asyncio
import copy
from datetime import datetime,timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import httpx
from gateway.weather import WeatherService, WeatherError
from gateway import app as module

class WeatherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.calls=[];self.offline=False;self.bad=False
        today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
        self.raw={'timezone':'Asia/Shanghai','current':{'time':str(today)+'T12:00','temperature_2m':20.5,'relative_humidity_2m':70,'apparent_temperature':21,'weather_code':61,'wind_speed_10m':3.2},'daily':{'time':[str(today+timedelta(days=i)) for i in range(3)],'temperature_2m_max':[23,25,26],'temperature_2m_min':[16,17,18],'precipitation_probability_max':[65,80,10],'weather_code':[61,63,0]}}
        async def handle(req):
            self.calls.append(req)
            if self.offline:raise httpx.ConnectError('offline',request=req)
            if req.url.host=='ipwho.is':return httpx.Response(200,json={'success':True,'city':'Shanghai','country_code':'CN','latitude':31.22,'longitude':121.45})
            if req.url.host=='geocoding-api.open-meteo.com':
                name=req.url.params['name']
                if name=='不存在地区':return httpx.Response(200,json={})
                city='杭州' if name=='杭州' else '上海'
                return httpx.Response(200,json={'results':[{'name':city,'latitude':30.3 if city=='杭州' else 31.22,'longitude':120.1,'country_code':'CN','admin1':'浙江' if city=='杭州' else '上海市','timezone':'Asia/Shanghai'}]})
            return httpx.Response(200,json={} if self.bad else self.raw)
        self.client=httpx.AsyncClient(transport=httpx.MockTransport(handle),trust_env=False)
        self.service=WeatherService(self.root,self.client)

    async def asyncTearDown(self):
        await self.client.aclose();self.tmp.cleanup()

    async def test_auto_cache_force_and_failure(self):
        w=await self.service.get();self.assertEqual(w['location']['city'],'上海');self.assertEqual(w['location']['source'],'network')
        n=len(self.calls);self.assertTrue((await self.service.get())['cached']);self.assertEqual(len(self.calls),n)
        await self.service.get(refresh=True);self.assertEqual(len(self.calls),n+1)
        self.offline=True
        self.assertTrue((await self.service.get(refresh=True))['stale'])
        old=self.service.cache.copy()
        self.service.cache={k:(0,v[1]) for k,v in old.items()}
        with self.assertRaises(WeatherError):await self.service.get()
        self.assertEqual(self.service.path.stat().st_mode & 0o777,0o600)

    async def test_manual_persistence_and_query_does_not_change_home(self):
        await self.service.set_city('杭州市');self.assertEqual(self.service.location()['city'],'杭州')
        w=await self.service.get(city='上海');self.assertEqual(w['location']['source'],'query')
        self.assertEqual(self.service.location()['city'],'杭州')
        before=self.service.path.read_bytes()
        with self.assertRaises(WeatherError):await self.service.set_city('不存在地区')
        self.assertEqual(before,self.service.path.read_bytes())
        self.assertEqual(WeatherService(self.root,self.client).location()['city'],'杭州')

    async def test_chinese_intents_forecasts_and_no_hallucination(self):
        for q,day,city in [('今天天气怎么样',0,None),('小安，明天需要带伞吗',1,None),('上海明天天气',1,'上海'),('明天上海天气',1,'上海'),('后天杭州会下雨吗',2,'杭州')]:
            result=await self.service.command(q)
            self.assertIn(('今天','明天','后天')[day],result,q)
            self.assertIn(city or '上海',result,q)
            self.assertNotRegex(result,'[A-Za-z]')
            self.assertIn('开放气象',result)
        for q in ['定位到杭州','把位置设置为杭州市','小安，请定位到杭州']:
            self.assertIn('设置为杭州',await self.service.command(q))
        self.assertIn('手动设置',await self.service.command('我现在在哪里'))
        self.assertIn('目前可以查询',await self.service.command('三天后天气'))
        self.assertIsNone(await self.service.command('一分钟后提醒我喝水'))
        self.assertIsNone(await self.service.command('帮我设置明天的天气提醒'))
        self.assertIsNone(await self.service.command('我今天很开心'))
        self.assertIn('目前可以查询',await self.service.command('下周天气'))
        self.offline=True;self.service.cache.clear()
        result=await self.service.command('今天天气');self.assertIn('不会猜测',result)

    async def test_invalid_weather_not_published(self):
        await self.service.set_city('上海');self.bad=True
        with self.assertRaises(WeatherError):await self.service.get()
        self.assertFalse(self.service.cache)
        self.bad=False;self.raw['daily']['temperature_2m_max'][0]=None
        with self.assertRaises(WeatherError):await self.service.get()
        self.assertFalse(self.service.cache)

    async def test_routes_and_both_chat_paths_bypass_llm(self):
        spoken=[]
        async def synth(text,**kw):spoken.append(text);return b'wave'
        # A weather answer must not need a model stream or completion at all.
        with patch.object(module.app.state,'weather',self.service,create=True),patch.object(module,'AUDIO',self.root),patch.object(module,'synthesize',synth):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test') as c:
                self.assertEqual((await c.get('/api/weather')).status_code,200)
                self.assertEqual((await c.put('/api/location',json={'city':'杭州'})).status_code,200)
                self.assertEqual((await c.get('/api/location')).json()['location']['city'],'杭州')
                self.assertEqual((await c.put('/api/location',json={'city':'不存在地区'})).status_code,422)
                r=await c.post('/api/chat',json={'text':'明天天气怎么样'});self.assertEqual(r.status_code,200);self.assertIn('杭州明天',r.json()['text'])
                job={'text':'','clips':[],'done':False,'text_done':False,'error':'','truncated':False}
                await module.run_chat_job(job,module.ChatRequest(text='今天天气怎么样'),{})
                self.assertTrue(job['done']);self.assertFalse(job['error']);self.assertIn('杭州目前',job['text'])
                self.assertEqual(spoken[-1],job['text'])
                self.assertEqual((await c.post('/api/location/auto')).status_code,200)
                self.assertEqual((await c.get('/api/location')).json()['location']['source'],'network')

if __name__=='__main__':unittest.main()
