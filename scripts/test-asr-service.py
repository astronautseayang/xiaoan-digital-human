"""SenseVoice error/fallback/cache/API regression with isolated config/model doubles."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
import numpy as np
import httpx
from fastapi import UploadFile, HTTPException
from gateway import app as module
from gateway.asr_service import ASRService, ASRUnavailable, input_bytes
from gateway.asr_cache import ensure, cached
from gateway.input_logic import interpret

class ASRTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'config').mkdir()
        (self.root/'config/asr.json').write_bytes((module.ROOT/'config/asr.json').read_bytes())
        self.service=ASRService(self.root)
        self.audio=np.full(16000,.1,dtype=np.float32)
    def tearDown(self):self.tmp.cleanup()

    def test_tags_chinese_itn_and_no_decoder_hotword_claim(self):
        calls=[]
        def generate(**kw):
            calls.append(kw);return [{'text':'<|zh|><|NEUTRAL|><|Speech|><|withitn|>定位到杭州。'}]
        self.service.model=SimpleNamespace(generate=generate);self.service.device='cpu'
        self.assertEqual(self.service.transcribe(self.audio),'定位到杭州。')
        self.assertTrue(calls[0]['use_itn']);self.assertEqual(calls[0]['language'],'zh')
        self.assertNotIn('hotword',calls[0]);self.assertFalse(self.service.status()['native_hotword_bias'])
        self.service.model=SimpleNamespace(generate=lambda **kw:[{'text':'<|nospeech|>'}])
        self.assertEqual(self.service.transcribe(self.audio),'')

    def test_inference_cuda_failure_cpu_fallback(self):
        self.service.device='cuda:0'
        def fail(**kw):raise RuntimeError('CUDA out of memory')
        self.service.model=SimpleNamespace(generate=fail)
        def load(settings,**kw):
            self.assertTrue(self.service.cpu_fallback)
            self.service.device='cpu';self.service.model=SimpleNamespace(generate=lambda **kw:[{'text':'提醒我喝水。'}])
        with patch.object(self.service,'_release',lambda:setattr(self.service,'model',None)),patch.object(self.service,'_load',load):
            self.assertEqual(self.service.transcribe(self.audio),'提醒我喝水。')
            self.assertEqual(self.service.device,'cpu')

    def test_initialization_cuda_failure_cpu_fallback(self):
        attempts=[]
        def load(settings,force_cpu=False):
            attempts.append(force_cpu);self.service.device='cpu' if force_cpu else 'cuda:0'
            if not force_cpu:raise RuntimeError('CUDA initialization')
            self.service.model=object()
        with patch.object(self.service,'_release',lambda:setattr(self.service,'model',None)),patch.object(self.service,'_load',load):
            self.service.warmup();self.assertEqual(attempts,[False,True])

    def test_cpu_retries_bounded_and_no_fabricated_text(self):
        calls=[]
        def load(settings):
            calls.append(1);self.service.device='cpu'
            self.service.model=SimpleNamespace(generate=lambda **kw:None)
        with patch.object(self.service,'_load',load),patch.object(self.service,'_release',lambda:setattr(self.service,'model',None)):
            with self.assertRaises(ASRUnavailable):self.service.transcribe(self.audio)
        self.assertEqual(len(calls),2)

    def test_raw_pcm_and_offline_cache_failure(self):
        raw=(self.audio*32767).astype('<i2').tobytes()
        wav=input_bytes(raw,'audio.pcm')
        with wave.open(io.BytesIO(wav)) as f:
            self.assertEqual((f.getframerate(),f.getsampwidth(),f.getnchannels()),(16000,2,1))
            self.assertEqual(f.readframes(f.getnframes()),raw)
        self.assertFalse(cached(self.root/'models/asr/SenseVoiceSmall'))
        with self.assertRaises(RuntimeError):ensure(self.root,offline=True)

    def test_hotwords_only_correct_command_slots(self):
        self.assertEqual(interpret('定位到易乌',hotwords=['义乌市']).text,'定位到义乌')
        self.assertEqual(interpret('两分钟后提刑我喝水',hotwords=['提醒']).text,'两分钟后提醒我喝水')
        self.assertEqual(interpret('我今天去易乌',hotwords=['义乌市']).text,'我今天去易乌')

    async def test_config_api_and_asr_errors(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test') as c:
            with patch.object(module,'ROOT',self.root):
                r=await c.put('/api/asr/config',json={'hotwords':['杭州','义乌市']});self.assertEqual(r.status_code,200)
                self.assertEqual((await c.get('/api/asr/config')).json()['hotwords'],['杭州','义乌市'])
                self.assertEqual((await c.put('/api/asr/config',json={'hotwords':['']})).status_code,422)
            with patch.object(module.speaker_input,'prepare',lambda *a,**kw:self.audio.copy()),patch.object(module.asr_service,'transcribe',side_effect=ASRUnavailable('failure')):
                r=await c.post('/api/asr',files={'file':('test.wav',b'fixture','audio/wav')});self.assertEqual(r.status_code,503)
                self.assertNotIn('text',r.json())

if __name__=='__main__':unittest.main()
