"""Network city estimation and factual weather replies, independent of the LLM."""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import math
from pathlib import Path
import re
import time
import httpx
from gateway.chinese import simplified


class WeatherError(ValueError):
    pass


CODES = {0:'晴',1:'大部晴朗',2:'局部多云',3:'阴',45:'雾',48:'雾凇',
         51:'小毛毛雨',53:'毛毛雨',55:'较强毛毛雨',56:'冻毛毛雨',57:'较强冻毛毛雨',
         61:'小雨',63:'中雨',65:'大雨',66:'小冻雨',67:'较强冻雨',
         71:'小雪',73:'中雪',75:'大雪',77:'米雪',80:'小阵雨',81:'阵雨',82:'强阵雨',
         85:'小阵雪',86:'强阵雪',95:'雷雨',96:'雷雨伴小冰雹',99:'雷雨伴较强冰雹'}


def chinese_name(value):
    value = simplified(str(value or ''))
    return value if re.search(r'[\u4e00-\u9fff]', value) and not re.search('[A-Za-z]',value) else '所选地区'


class WeatherService:
    def __init__(self, root, client):
        self.path = Path(root)/'config/location.json'
        self.client = client
        self.lock = asyncio.Lock()
        self.cache = {}

    def location(self):
        if not self.path.exists():
            return None
        try:
            p = json.loads(self.path.read_text())
            if not (-90 <= float(p['latitude']) <= 90 and -180 <= float(p['longitude']) <= 180):
                return None
            return p
        except (ValueError, KeyError, TypeError):
            return None

    def save(self, p):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
        tmp.chmod(0o600)
        tmp.replace(self.path)
        return p

    async def request(self, url, params=None):
        try:
            r = await self.client.get(url,params=params,timeout=8)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data,dict):
                raise ValueError('Invalid response')
            return data
        except (ValueError, OSError, httpx.HTTPError) as exc:
            raise WeatherError('天气或定位服务暂时无法连接，请稍后重试。') from exc

    async def resolve(self, city, country=None):
        name = re.sub(r'(?:市|县)$','',city.strip())
        data = await self.request('https://geocoding-api.open-meteo.com/v1/search',
                                  {'name':name,'count':10,'language':'zh','format':'json'})
        results = data.get('results') or []
        if country:
            results = [r for r in results if r.get('country_code')==country]
        if not results:
            raise WeatherError('没有找到这个城市，请输入完整城市名，例如“定位到杭州市”。')
        # Prefer an exact localized name, then a Chinese city, then population.
        p = max(results,key=lambda r:(re.sub(r'(?:市|县)$','',r['name'])==name,
                    r.get('country_code')=='CN',r.get('population',0)))
        return {'city':chinese_name(p['name']), 'region':chinese_name(p.get('admin1',p['name'])),
                'latitude':p['latitude'],'longitude':p['longitude'],'timezone':p.get('timezone','auto')}

    async def _auto(self):
        data = await self.request('https://ipwho.is/',{'lang':'zh'})
        if data.get('success') is not True:
            raise WeatherError('网络定位未成功，请输入“定位到”加城市名称。')
        try:
            latitude, longitude = float(data['latitude']),float(data['longitude'])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):raise ValueError()
        except (ValueError,KeyError,TypeError) as exc:
            raise WeatherError('没有获得有效位置，请手动设置城市。') from exc
        try:
            p = await self.resolve(data['city'],data.get('country_code'))
        except WeatherError:
            p = {'city':chinese_name(data.get('city')), 'region':chinese_name(data.get('region')),
                 'latitude':latitude,'longitude':longitude,'timezone':'auto'}
        # Use the network estimate, not geocoder's city centroid.
        p.update(latitude=latitude,longitude=longitude,source='network',updated_at=datetime.now().isoformat(timespec='seconds'))
        return self.save(p)

    async def auto(self):
        async with self.lock:
            return await self._auto()

    async def set_city(self, city):
        async with self.lock:
            p = await self.resolve(city)
            p.update(source='manual',updated_at=datetime.now().isoformat(timespec='seconds'))
            return self.save(p)

    async def get(self, city=None, refresh=False):
        async with self.lock:
            p = await self.resolve(city) if city else self.location()
            if not p:
                p = await self._auto()
            p = dict(p)
            if city:p['source']='query'
            key = (round(p['latitude'],4),round(p['longitude'],4))
            cached = self.cache.get(key)
            if cached and cached[1]['days'][0]['date'] != datetime.now(ZoneInfo(cached[1]['timezone'])).date().isoformat():
                cached = None
            if cached and not refresh and time.monotonic()-cached[0]<600:
                return {**cached[1],'location':p,'cached':True}
            try:
                raw = await self.request('https://api.open-meteo.com/v1/forecast',{
                    'latitude':p['latitude'],'longitude':p['longitude'],'timezone':'auto',
                    'current':'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m',
                    'daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code',
                    'forecast_days':3,'wind_speed_unit':'ms'})
                c,d = raw['current'],raw['daily']
                days = [{'date':date,'condition':CODES.get(d['weather_code'][i],'天气状况未提供'),
                         'high':d['temperature_2m_max'][i],'low':d['temperature_2m_min'][i],
                         'rain_probability':d['precipitation_probability_max'][i]} for i,date in enumerate(d['time'])]
                for value in (c['temperature_2m'],c['apparent_temperature'],c['relative_humidity_2m'],c['wind_speed_10m']):
                    if not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Missing current data')
                for day in days:
                    for field in ('high','low','rain_probability'):
                        if not isinstance(day[field],(int,float)) or not math.isfinite(day[field]):raise ValueError('Missing daily data')
                ZoneInfo(raw['timezone'])
                datetime.fromisoformat(c['time'])
                result = {'location':p,'condition':CODES.get(c['weather_code'],'天气状况未提供'),
                          'temperature':c['temperature_2m'],'feels_like':c['apparent_temperature'],
                          'humidity':c['relative_humidity_2m'],'wind_speed':c['wind_speed_10m'],
                          'observed_at':c['time'],'timezone':raw['timezone'],'days':days,
                          'provider':'Open-Meteo','stale':False,'cached':False,
                          'fetched_at':datetime.now().isoformat(timespec='seconds')}
                if len(days)<3:raise ValueError('Missing forecast')
            except (WeatherError,KeyError,IndexError,TypeError,ValueError) as exc:
                if cached and time.monotonic()-cached[0]<3600:
                    return {**cached[1],'location':p,'stale':True,'cached':True}
                raise WeatherError('暂时没有取得有效天气数据，请稍后重试；我不会猜测天气。') from exc
            self.cache[key] = (time.monotonic(),result)
            # Bound memory when asking about many cities.
            if len(self.cache)>32:self.cache.pop(next(iter(self.cache)))
            return result

    async def command(self, text):
        text = text.strip(' 。！？?!，,')
        manual = re.fullmatch(r'(?:小安[，, ]*)?(?:请)?(?:把)?(?:定位|位置|所在城市)(?:设置为|切换到|改到|设为|改为|设到|到)\s*([\u4e00-\u9fffA-Za-z ·]{2,30})',text)
        try:
            if manual:
                p = await self.set_city(manual[1])
                return f'已将天气位置设置为{p["city"]}。您可以问我今天或明天的天气。'
            if re.fullmatch(r'(?:请)?(?:重新|自动)(?:定位|获取位置)',text):
                p = await self.auto()
                return f'网络估算位置是{p["city"]}，可能有偏差。可以输入“定位到”加城市名称修正。'
            if re.fullmatch(r'(?:小安[，, ]*)?(?:请问|请)?(?:我(?:现在)?在(?:哪里|哪儿)|我的位置|当前位置|所在城市|定位(?:一下)?)',text):
                p = self.location() or await self.auto()
                if p['source']=='network':
                    return f'网络估算您目前在{p["city"]}，只能估算城市，不能确定街道地址。若不准确，可以输入“定位到”加城市名称修正。'
                return f'您手动设置的天气城市是{p["city"]}。这不是设备的实时定位，需要时可以点击重新定位。'
            if not re.search(r'天气|气温|下雨|下雪|带伞|冷不冷|热不热|温度多少',text):
                return None
            if re.search(r'提醒|备忘|闹钟',text):return None
            if re.search(r'昨天|前天|上周|下周|大后天|周[一二三四五六日天]|星期|\d+月|[一二三四五六七八九十\d]+[天日]后',text):
                return '目前可以查询现在、今天、明天和后天的天气。请告诉我您要查哪一天。'
            day = 2 if '后天' in text else 1 if '明天' in text else 0
            prefix = re.split(r'天气|气温|下雨|下雪|冷不冷|热不热|带伞|温度多少',text,maxsplit=1)[0]
            prefix = re.sub(r'今天|今日|现在|明天|后天','',prefix)
            prefix = re.sub(r'^(?:小安[，, ]*|请问|请|帮我|给我|我想知道|我想问|查询|查一下|查查|更新|刷新|重新查询|看看|看一下|告诉我|一下|那么|那)+','',prefix)
            prefix = prefix.strip(' 的在，,')
            prefix = re.sub(r'(?:会不会|要不要|需不需要|是不是|是否|需要|会|要)$','',prefix).strip(' 的在，,')
            city = prefix if prefix and prefix not in ('这里','这边','我们这边','我这里','当地','本地','我所在城市','外面','出门要','要不要','需要','是否会','会不会','会') else None
            w = await self.get(city=city)
            return weather_reply(w,day)
        except WeatherError as exc:
            return str(exc)


def number(value):
    return f'{value:g}' if isinstance(value,(int,float)) else '暂无数据'


def weather_reply(w,day=0):
    city=w['location']['city'];d=w['days'][day]
    stale='天气更新失败，以下是此前取得的数据。' if w['stale'] else ''
    estimated='位置由网络估算。' if w['location'].get('source')=='network' else ''
    when=('今天','明天','后天')[day]
    if day:
        main=f'{city}{when}（{d["date"]}）预计{d["condition"]}，气温{number(d["low"])}到{number(d["high"])}摄氏度，最高降水概率{number(d["rain_probability"])}%。'
    else:
        main=f'{city}目前{w["condition"]}，气温{number(w["temperature"])}摄氏度，体感{number(w["feels_like"])}摄氏度。今天最低{number(d["low"])}、最高{number(d["high"])}摄氏度，最高降水概率{number(d["rain_probability"])}%。湿度{number(w["humidity"])}%，风速每秒{number(w["wind_speed"])}米。'
    advice='出门建议带伞，留意路面湿滑。' if (d['rain_probability'] or 0)>=40 or re.search('雨|雪',d['condition']) else ''
    return stale+main+advice+estimated+f'数据时间为{w["observed_at"].replace("T"," ")}（当地时间），来源为开放气象。'
