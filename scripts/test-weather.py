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

    async def test_saved_coordinate_strings_are_normalized_and_broken_locations_recover(self):
        await self.service.set_city('上海')
        valid = self.service.location()
        self.service.path.write_text(json.dumps({**valid, 'latitude': '31.22', 'longitude': '121.45'}))
        weather = await self.service.get()
        self.assertIsInstance(weather['location']['latitude'], float)
        for broken in ({'latitude':31, 'longitude':121}, {**valid, 'city':7},
                       {**valid, 'latitude':True}, {**valid, 'source':None}):
            with self.subTest(broken=broken):
                self.service.path.write_text(json.dumps(broken))
                self.assertIsNone(self.service.location())
                self.assertEqual((await self.service.get())['location']['source'], 'network')

    async def test_bad_disk_record_does_not_block_startup_or_other_records(self):
        await self.service.get()
        rows = json.loads(self.service.cache_path.read_text())
        bad = copy.deepcopy(rows[0])
        bad['weather']['location']['city'] = 7
        self.service.cache_path.write_text(json.dumps([bad, *rows]))
        restarted = WeatherService(self.root, self.client)
        self.assertEqual(len(restarted.cache), 1)
        self.assertEqual(len(restarted.cities), 1)
        self.assertNotIn(7, restarted.cities)

    async def test_disk_forecast_without_condition_is_not_used(self):
        await self.service.get()
        rows = json.loads(self.service.cache_path.read_text())
        del rows[0]['weather']['days'][1]['condition']
        self.service.cache_path.write_text(json.dumps(rows))
        restarted = WeatherService(self.root, self.client)
        self.assertFalse(restarted.cache)

    async def test_malformed_geocoder_does_not_overwrite_saved_location(self):
        await self.service.set_city('上海')
        before = self.service.path.read_bytes()
        for results in ({'name':'杭州'}, [None], [{'name':'杭州','latitude':999,'longitude':120}],
                        [{'name':'杭州','latitude':True,'longitude':120}]):
            with self.subTest(results=results):
                async def request(*args, **kwargs):
                    return {'results': results}
                with patch.object(self.service, 'request', request):
                    with self.assertRaises(WeatherError):
                        await self.service.set_city('杭州')
                self.assertEqual(self.service.path.read_bytes(), before)
                self.assertNotIn('杭州', self.service.cities)

    async def test_geocoder_can_skip_bad_candidate_and_normalize_coordinates(self):
        async def request(*args, **kwargs):
            return {'results': [None, {'name':'杭州'}, {'name':'杭州','latitude':'30.3',
                'longitude':'120.1','timezone':'Asia/Shanghai','country_code':'CN'}]}
        with patch.object(self.service, 'request', request):
            location = await self.service.set_city('杭州')
        self.assertEqual(location['latitude'], 30.3)
        self.assertEqual(location['longitude'], 120.1)

    async def test_auto_location_missing_city_uses_coordinates_without_crashing(self):
        async def request(*args, **kwargs):
            return {'success':True, 'latitude':31.22, 'longitude':121.45}
        with patch.object(self.service, 'request', request):
            location = await self.service.auto()
        self.assertEqual(location['source'], 'network')
        self.assertEqual(location['city'], '所选地区')
        self.assertEqual(self.service.location()['latitude'], 31.22)

    async def test_auto_location_boolean_coordinates_preserve_saved_location(self):
        await self.service.set_city('上海')
        before = self.service.path.read_bytes()
        async def request(*args, **kwargs):
            return {'success':True, 'latitude':True, 'longitude':121.45, 'city':'上海'}
        with patch.object(self.service, 'request', request):
            with self.assertRaises(WeatherError):
                await self.service.auto()
        self.assertEqual(self.service.path.read_bytes(), before)

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
        self.service.retry_after.clear()
        self.bad=False;self.raw['daily']['temperature_2m_max'][0]=None
        with self.assertRaises(WeatherError):await self.service.get()
        self.assertFalse(self.service.cache)

    def invalid_forecasts(self):
        for section, field, value in (
            ('current', 'relative_humidity_2m', -1),
            ('current', 'relative_humidity_2m', 101),
            ('current', 'wind_speed_10m', -0.1),
            ('daily', 'precipitation_probability_max', [-1, 80, 10]),
            ('daily', 'precipitation_probability_max', [101, 80, 10]),
            ('daily', 'temperature_2m_max', [15, 25, 26]),
            ('daily', 'time', [self.raw['daily']['time'][0]] * 3),
            ('daily', 'time', [self.raw['daily']['time'][i] for i in (0, 2, 1)]),
        ):
            raw = copy.deepcopy(self.raw)
            raw[section][field] = value
            yield field, raw

    async def test_inconsistent_forecasts_are_rejected_without_cache(self):
        await self.service.set_city('上海')
        original = self.raw
        for field, raw in list(self.invalid_forecasts()):
            with self.subTest(field=field, value=raw):
                self.raw = raw
                self.service.retry_after.clear()
                with self.assertRaises(WeatherError):
                    await self.service.get(refresh=True)
                self.assertFalse(self.service.cache)
                self.assertFalse(self.service.cache_path.exists())
        self.raw = original

    async def test_inconsistent_refresh_preserves_valid_fallback(self):
        valid = await self.service.get()
        saved = self.service.cache_path.read_bytes()
        for field, raw in list(self.invalid_forecasts()):
            with self.subTest(field=field):
                self.raw = raw
                self.service.retry_after.clear()
                result = await self.service.get(refresh=True)
                self.assertTrue(result['stale'])
                self.assertEqual(result['days'], valid['days'])
                self.assertEqual(result['humidity'], valid['humidity'])
                self.assertEqual(self.service.cache_path.read_bytes(), saved)

    async def test_inconsistent_disk_rows_do_not_replace_valid_cache(self):
        await self.service.get()
        rows = json.loads(self.service.cache_path.read_text())
        for field, value in (('humidity', 101), ('wind_speed', -1),
                             ('rain_probability', 101), ('high', 0),
                             ('date', rows[0]['weather']['days'][0]['date'])):
            with self.subTest(field=field):
                bad = copy.deepcopy(rows[0])
                if field in ('humidity', 'wind_speed'):
                    bad['weather'][field] = value
                else:
                    bad['weather']['days'][1][field] = value
                self.service.cache_path.write_text(json.dumps([*rows, bad]))
                restarted = WeatherService(self.root, self.client)
                self.assertEqual(len(restarted.cache), 1)
                self.assertEqual(next(iter(restarted.cache.values()))[1], rows[0]['weather'])

    async def test_oversized_forecast_numbers_use_normal_failure_and_recover(self):
        await self.service.set_city('上海')
        original = copy.deepcopy(self.raw)
        self.raw['current']['temperature_2m'] = 10**400
        with self.assertRaises(WeatherError):
            await self.service.get()
        self.assertFalse(self.service.cache)
        self.service.retry_after.clear()
        with patch.object(module.app.state, 'weather', self.service, create=True):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),
                                         base_url='http://test', trust_env=False) as client:
                response = await client.get('/api/weather')
                self.assertEqual(response.status_code, 503)
                self.assertIn('不会猜测天气', response.json()['detail'])
        self.raw = copy.deepcopy(original)
        self.service.retry_after.clear()
        valid = await self.service.get()
        saved = self.service.cache_path.read_bytes()
        self.raw['daily']['temperature_2m_max'][1] = 10**400
        fallback = await self.service.get(refresh=True)
        self.assertTrue(fallback['stale'])
        self.assertEqual(fallback['days'], valid['days'])
        self.assertEqual(saved, self.service.cache_path.read_bytes())
        self.raw = original
        self.service.retry_after.clear()
        self.assertFalse((await self.service.get(refresh=True))['stale'])

    async def test_oversized_disk_numbers_do_not_block_startup(self):
        await self.service.get()
        rows = json.loads(self.service.cache_path.read_text())
        for field in ('saved_at', 'temperature', 'latitude'):
            with self.subTest(field=field):
                bad = copy.deepcopy(rows[0])
                target = bad if field == 'saved_at' else (
                    bad['weather']['location'] if field == 'latitude' else bad['weather'])
                target[field] = 10**400
                self.service.cache_path.write_text(json.dumps([bad, *rows]))
                restarted = WeatherService(self.root, self.client)
                self.assertEqual(len(restarted.cache), 1)
                self.assertEqual(next(iter(restarted.cache.values()))[1], rows[0]['weather'])

    async def test_oversized_saved_coordinates_are_recoverable(self):
        await self.service.set_city('上海')
        location = self.service.location()
        self.service.path.write_text(json.dumps({**location, 'latitude': 10**400}))
        self.assertIsNone(self.service.location())
        self.assertEqual((await self.service.get())['location']['source'], 'network')

    async def test_oversized_network_coordinates_preserve_saved_location(self):
        await self.service.set_city('上海')
        before = self.service.path.read_bytes()
        async def request(*args, **kwargs):
            return {'success': True, 'latitude': 10**400, 'longitude': 121.45}
        with patch.object(self.service, 'request', request):
            with self.assertRaises(WeatherError):
                await self.service.auto()
        self.assertEqual(before, self.service.path.read_bytes())

    async def test_oversized_geocoder_candidates_are_skipped(self):
        await self.service.set_city('上海')
        before = self.service.path.read_bytes()
        good = {'name': '杭州', 'latitude': 30.3, 'longitude': 120.1,
                'timezone': 'Asia/Shanghai', 'country_code': 'CN'}
        invalid = [{**good, 'latitude': 10**400}, {**good, 'population': 10**400}]
        async def request(*args, **kwargs):
            return {'results': invalid}
        with patch.object(self.service, 'request', request):
            with self.assertRaises(WeatherError):
                await self.service.set_city('杭州')
            self.assertEqual(before, self.service.path.read_bytes())
            invalid.append(good)
            self.assertEqual((await self.service.set_city('杭州'))['latitude'], 30.3)

    async def test_restart_keeps_weather_and_known_query_city_offline(self):
        await self.service.set_city('上海')
        await self.service.get(city='杭州')
        restarted=WeatherService(self.root,self.client)
        self.offline=True
        n=len(self.calls)
        w=await restarted.get(city='杭州市')
        self.assertEqual(w['location']['city'],'杭州')
        self.assertTrue(w['cached']);self.assertEqual(len(self.calls),n)
        w=await restarted.get(city='杭州',refresh=True)
        self.assertTrue(w['stale'])
        self.assertEqual(restarted.location()['city'],'上海')
        self.assertEqual(restarted.cache_path.stat().st_mode & 0o777,0o600)

    async def test_transient_error_retries_but_permanent_error_does_not(self):
        for status, expected in [(503,2),(429,2),(400,1)]:
            calls=[]
            async def handle(req):
                calls.append(req)
                return httpx.Response(status if len(calls)==1 else 200,json={'ok':True})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                service=WeatherService(self.root,client)
                if status==400:
                    with self.assertRaises(WeatherError):await service.request('https://example.test/')
                else:self.assertTrue((await service.request('https://example.test/'))['ok'])
            self.assertEqual(len(calls),expected)

    async def test_failure_cooldown_and_recovery(self):
        await self.service.set_city('上海');await self.service.get()
        self.offline=True
        self.assertTrue((await self.service.get(refresh=True))['stale'])
        n=len(self.calls)
        for _ in range(3):
            self.assertTrue((await self.service.get(refresh=True))['stale'])
        self.assertEqual(len(self.calls),n)
        self.offline=False
        self.service.retry_after={k:0 for k in self.service.retry_after}
        self.assertFalse((await self.service.get(refresh=True))['stale'])
        self.assertFalse(self.service.retry_after)

    async def test_same_city_offline_avoids_geocoding(self):
        await self.service.set_city('上海');await self.service.get()
        self.offline=True;n=len(self.calls)
        w=await self.service.get(city='上海市')
        self.assertTrue(w['cached']);self.assertEqual(len(self.calls),n)

    async def test_parallel_reads_share_one_forecast(self):
        await self.service.set_city('上海');n=len(self.calls)
        results=await asyncio.gather(*(self.service.get() for _ in range(8)))
        self.assertEqual(len(self.calls),n+1)
        self.assertEqual(sum(not w['cached'] for w in results),1)

    async def test_expired_or_previous_day_disk_cache_not_used(self):
        await self.service.get()
        rows=json.loads(self.service.cache_path.read_text())
        rows[0]['saved_at']-=3601
        self.service.cache_path.write_text(json.dumps(rows))
        self.assertFalse(WeatherService(self.root,self.client).cache)
        rows[0]['saved_at']+=3601
        rows[0]['weather']['days'][0]['date']='2000-01-01'
        self.service.cache_path.write_text(json.dumps(rows))
        self.assertFalse(WeatherService(self.root,self.client).cache)

    async def test_bad_timezone_is_reported_as_weather_failure(self):
        await self.service.set_city('上海');self.raw['timezone']='invalid/timezone'
        with self.assertRaises(WeatherError):await self.service.get()
        self.assertFalse(self.service.cache)

    async def test_cache_storage_failures_keep_memory_and_previous_disk_cache(self):
        await self.service.set_city('上海')
        await self.service.get()
        saved = self.service.cache_path.read_bytes()
        original_write = Path.write_text
        original_replace = Path.replace
        for failure in ('write', 'replace'):
            with self.subTest(failure=failure):
                self.raw['current']['temperature_2m'] += 1
                def write(path, data, *args, **kwargs):
                    if path.parent == self.service.cache_path.parent and failure == 'write':
                        original_write(path, data[:8], *args, **kwargs)
                        raise OSError('Injected partial weather cache write')
                    return original_write(path, data, *args, **kwargs)
                def replace(path, target):
                    if target == self.service.cache_path and failure == 'replace':
                        raise PermissionError('Injected cache replacement failure')
                    return original_replace(path, target)
                with patch.object(Path, 'write_text', write), patch.object(Path, 'replace', replace):
                    result = await self.service.get(refresh=True)
                self.assertFalse(result['stale'])
                self.assertEqual(result['temperature'], self.raw['current']['temperature_2m'])
                n = len(self.calls)
                self.assertEqual((await self.service.get())['temperature'], result['temperature'])
                self.assertEqual(len(self.calls), n)
                self.assertEqual(self.service.cache_path.read_bytes(), saved)
                self.assertEqual(list(self.service.cache_path.parent.glob('*.tmp')), [])
        result = await self.service.get(refresh=True)
        restarted = WeatherService(self.root, self.client)
        self.offline = True
        self.assertEqual((await restarted.get())['temperature'], result['temperature'])

    async def test_cache_data_is_written_with_private_permissions(self):
        await self.service.set_city('上海')
        original_write = Path.write_text
        permissions = []
        def write(path, data, *args, **kwargs):
            result = original_write(path, data, *args, **kwargs)
            if path.parent == self.service.cache_path.parent:
                permissions.append(path.stat().st_mode & 0o777)
            return result
        with patch.object(Path, 'write_text', write):
            await self.service.get()
        self.assertEqual(permissions, [0o600])

    async def test_location_storage_failures_are_recoverable(self):
        await self.service.set_city('上海')
        original = self.service.path.read_bytes()
        original_write = Path.write_text
        original_replace = Path.replace
        for failure in ('write', 'replace'):
            for automatic in (False, True):
                with self.subTest(failure=failure, automatic=automatic):
                    def write(path, data, *args, **kwargs):
                        if path.parent == self.service.path.parent:
                            if failure == 'write':
                                original_write(path, data[:5], *args, **kwargs)
                                raise OSError('Injected partial location write')
                        return original_write(path, data, *args, **kwargs)
                    def replace(path, target):
                        if target == self.service.path and failure == 'replace':
                            raise PermissionError('Injected location replace failure')
                        return original_replace(path, target)
                    with patch.object(module.app.state, 'weather', self.service, create=True):
                        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app, raise_app_exceptions=False), base_url='http://test') as c:
                            with patch.object(Path, 'write_text', write), patch.object(Path, 'replace', replace):
                                r = await c.post('/api/location/auto') if automatic else await c.put('/api/location', json={'city':'杭州'})
                                self.assertEqual(r.status_code, 503)
                                self.assertIn('保存失败', r.json()['detail'])
                                reply = await self.service.command('自动定位' if automatic else '定位到杭州')
                                self.assertIn('保存失败', reply)
                    self.assertEqual(self.service.path.read_bytes(), original)
                    self.assertEqual(list(self.service.path.parent.glob('*.tmp')), [])
        await self.service.set_city('杭州')
        self.assertEqual(self.service.location()['city'], '杭州')
        self.assertEqual(self.service.path.stat().st_mode & 0o777, 0o600)

    async def test_location_is_private_before_writing(self):
        original_write = Path.write_text
        observed = []
        def write(path, data, *args, **kwargs):
            result = original_write(path, data, *args, **kwargs)
            if path.parent == self.service.path.parent:
                observed.append(path.stat().st_mode & 0o777)
            return result
        with patch.object(Path, 'write_text', write):
            await self.service.set_city('上海')
        self.assertEqual(observed, [0o600])

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
