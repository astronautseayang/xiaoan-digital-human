"""Command correction, ambiguity, negative intent and ASR-to-action regression."""
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import httpx
import numpy as np
from fastapi import UploadFile
from gateway import app as module
from gateway.input_logic import interpret
from gateway.weather import WeatherService
from gateway.care import CareEngine

class InputLogicTests(unittest.IsolatedAsyncioTestCase):
    def test_homophones_and_valid_spelling(self):
        for source, expected in [
            ('订为到行舟','定位到杭州'), ('小安，请订位到杭洲。','定位到杭州'),
            ('定为到上害','定位到上海'), ('定位到北经','定位到北京'),
            ('定位到温洲市','定位到温州'), ('定位到常洲','定位到常州'),
            ('明天行舟天气怎么样','明天杭州天气怎么样'),
            ('一分钟后替醒我喝水','一分钟后提醒我喝水')]:
            self.assertEqual(interpret(source).text,expected)
        for city in ['苏州','宿州','台州','泰州','杭州','长春','厦门']:
            self.assertEqual(interpret('定位到'+city).text,'定位到'+city)
        for text in ['定位到苏周','定位到泰洲']:
            self.assertTrue(interpret(text).clarification)

    def test_conversation_and_time_are_preserved(self):
        for text in ['我喜欢在湖上行舟','我说定位到杭州但是识别错了','不要定位到行舟',
                     '能不能定位到行舟','如果订为到行舟会怎么样','定位到杭州然后提醒我喝水',
                     '一分钟后提醒我喝水','今天12点52提醒我吃药','取消全部提醒',
                     '定位到不存在地区']:
            self.assertEqual(interpret(text).text,text)
            self.assertFalse(interpret(text).clarification)

    async def test_asr_endpoint_returns_corrected_and_original(self):
        with patch.object(module.asr_service,'transcribe',lambda audio:'订为到行舟'),patch.object(module.speaker_input,'prepare',lambda *a,**kw:np.full(16000,.1,dtype=np.float32)),patch.object(module,'handle_care_text',lambda *a:{'care_command':''}):
            result=await module.asr(UploadFile(filename='speech.wav',file=io.BytesIO(b'fixture')))
            self.assertEqual(result['text'],'定位到杭州')
            self.assertEqual(result['raw_text'],'订为到行舟');self.assertTrue(result['corrected'])
            # Enrollment transcription must remain faithful.
            result=await module.asr(UploadFile(filename='speech.wav',file=io.BytesIO(b'fixture')),care_commands=False)
            self.assertEqual(result['text'],'订为到行舟');self.assertFalse(result['corrected'])

    async def test_local_action_persists_and_ambiguity_does_not_execute(self):
        calls=[]
        async def handle(req):
            calls.append(req.url.params['name'])
            return httpx.Response(200,json={'results':[{'name':'杭州','latitude':30.3,'longitude':120.1,'country_code':'CN','timezone':'Asia/Shanghai'}]})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'config').mkdir()
            (root/'config/care.json').write_bytes((module.ROOT/'config/care.json').read_bytes())
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                weather=WeatherService(root,client)
                async def synth(*a,**kw):return b'wave'
                care=CareEngine(root,synth,None)
                try:
                    with patch.object(module.app.state,'weather',weather,create=True),patch.object(module.app.state,'care',care,create=True):
                        result=await module.local_reply('订为到行舟')
                        self.assertIn('设置为杭州',result);self.assertEqual(calls,['杭州'])
                        saved=weather.path.read_bytes()
                        self.assertIn('苏州、宿州',await module.local_reply('定位到苏周'))
                        self.assertEqual(weather.path.read_bytes(),saved);self.assertEqual(calls,['杭州'])
                        self.assertIsNone(await module.local_reply('不要订为到行舟'))
                        self.assertIn('已设置提醒',await module.local_reply('一分钟后替醒我喝水'))
                        row=care.db.execute('SELECT * FROM reminders').fetchone()
                        self.assertEqual(row['task'],'喝水')
                        await module.local_reply('不要一分钟后替醒我吃药')
                        self.assertEqual(care.db.execute('SELECT count(*) FROM reminders').fetchone()[0],1)
                finally:
                    care.db.close()

if __name__=='__main__':unittest.main()
