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
from gateway.asr_cache import ensure, cached, config
from gateway.input_logic import interpret

class ASRTests(unittest.IsolatedAsyncioTestCase):
    async def test_transcription_without_execution_keeps_speaker_checks(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://test') as client:
            for query, executes, verifies in [
                ('?execute_commands=false', False, True),
                ('', True, True),
                ('?care_commands=false', False, False),
            ]:
                with self.subTest(query=query), \
                     patch.object(module, 'input_bytes', return_value=self.audio.copy()), \
                     patch.object(module.speaker_input, 'prepare', side_effect=lambda audio, **kw: audio) as prepare, \
                     patch.object(module.asr_service, 'transcribe', return_value='救命'), \
                     patch.object(module, 'handle_care_text', return_value={'care_command':'emergency'}) as command:
                    response = await client.post('/api/asr'+query, files={'file':('test.wav', b'fixture', 'audio/wav')})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()['text'], '救命')
                    self.assertEqual(prepare.call_args.kwargs['verify'], verifies)
                    self.assertEqual(command.call_count, int(executes))
                    if executes:
                        self.assertEqual(response.json()['care_command'], 'emergency')
                    else:
                        self.assertNotIn('care_command', response.json())

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

    def test_cuda_fallback_keeps_cpu_retry_budget(self):
        for retries in (0, 1, 2):
            with self.subTest(retries=retries):
                settings=json.loads((self.root/'config/asr.json').read_text())
                settings['retries']=retries
                (self.root/'config/asr.json').write_text(json.dumps(settings))
                self.service=ASRService(self.root)
                self.service.device='cuda:0'
                def fail(**kw):raise RuntimeError('transient inference failure')
                self.service.model=SimpleNamespace(generate=fail)
                loads=[]
                def load(settings):
                    loads.append(1)
                    self.service.device='cpu'
                    self.service.model=SimpleNamespace(generate=fail if len(loads)<=retries else lambda **kw:[{'text':'恢复成功'}])
                with patch.object(self.service,'_load',load),patch.object(self.service,'_release',lambda:setattr(self.service,'model',None)),patch('gateway.asr_service.time.sleep'):
                    self.assertEqual(self.service.transcribe(self.audio),'恢复成功')
                self.assertEqual(len(loads),retries+1)

    def test_exhausted_model_is_discarded_and_next_request_recovers(self):
        def fail(**kw):raise RuntimeError('broken model')
        self.service.device='cpu'
        self.service.model=SimpleNamespace(generate=fail)
        loads=[]
        def load(settings):
            loads.append(1)
            self.service.model=SimpleNamespace(generate=fail)
        with patch.object(self.service,'_load',load),patch.object(self.service,'_release',lambda:setattr(self.service,'model',None)),patch('gateway.asr_service.time.sleep'):
            with self.assertRaises(ASRUnavailable):self.service.transcribe(self.audio)
            self.assertEqual(len(loads),1)
            self.assertIsNone(self.service.model)
            self.assertTrue(self.service.last_error)
            def recover(settings):
                self.service.model=SimpleNamespace(generate=lambda **kw:[{'text':'重新加载成功'}])
            with patch.object(self.service,'_load',recover):
                self.assertEqual(self.service.transcribe(self.audio),'重新加载成功')
            self.assertEqual(self.service.last_error,'')

    def test_cuda_and_cpu_failure_still_has_bounded_attempts(self):
        for retries in (0, 1, 2):
            with self.subTest(retries=retries):
                settings=json.loads((self.root/'config/asr.json').read_text())
                settings['retries']=retries
                (self.root/'config/asr.json').write_text(json.dumps(settings))
                self.service=ASRService(self.root)
                self.service.device='cuda:0'
                calls=[]
                def fail(**kw):
                    calls.append(self.service.device)
                    raise RuntimeError('persistent failure')
                self.service.model=SimpleNamespace(generate=fail)
                def load(settings):
                    self.service.device='cpu'
                    self.service.model=SimpleNamespace(generate=fail)
                with patch.object(self.service,'_load',load),patch.object(self.service,'_release',lambda:setattr(self.service,'model',None)),patch('gateway.asr_service.time.sleep'):
                    with self.assertRaises(ASRUnavailable):self.service.transcribe(self.audio)
                self.assertEqual(calls,['cuda:0']+['cpu']*(retries+1))
                self.assertIsNone(self.service.model)

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

    def test_invalid_config_is_rejected_before_model_initialization(self):
        path = self.root/'config/asr.json'
        original = json.loads(path.read_text())
        invalid = [None, [], 'broken', {**original, 'model_dir': None},
                   {**original, 'model_dir': ''}, {**original, 'cpu_threads': True},
                   {**original, 'retries': False}]
        missing = dict(original)
        del missing['model_dir']
        invalid.append(missing)
        for settings in invalid:
            with self.subTest(settings=settings):
                path.write_text(json.dumps(settings))
                with self.assertRaises(ValueError):
                    config(self.root)
                with patch.object(self.service, '_load') as load:
                    with self.assertRaises(ValueError):
                        self.service.warmup()
                    load.assert_not_called()
        # Missing hotwords is supported consistently by both config and status.
        del original['hotwords']
        path.write_text(json.dumps(original))
        self.assertEqual(config(self.root)['hotwords'], [])
        self.assertEqual(self.service.status()['hotwords'], [])

    async def test_broken_config_routes_report_unavailable_and_recover(self):
        path = self.root/'config/asr.json'
        original = path.read_bytes()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),
                                     base_url='http://test', trust_env=False) as client:
            with patch.object(module, 'ROOT', self.root), patch.object(module, 'asr_service', self.service):
                for broken in (b'{', b'[]', b'null', None):
                    with self.subTest(broken=broken):
                        if broken is None:
                            path.unlink()
                        else:
                            path.write_bytes(broken)
                        self.assertEqual((await client.get('/api/asr/config')).status_code, 503)
                        self.assertEqual((await client.get('/api/asr/status')).status_code, 503)
                        self.assertEqual((await client.put('/api/asr/config', json={'hotwords':['杭州']})).status_code, 503)
                        if broken is not None:
                            self.assertEqual(path.read_bytes(), broken)
                        else:
                            self.assertFalse(path.exists())
                path.write_bytes(original)
                self.assertEqual((await client.get('/api/asr/config')).status_code, 200)
                self.assertEqual((await client.get('/api/asr/status')).status_code, 200)
                self.assertEqual((await client.put('/api/asr/config', json={'hotwords':['杭州']})).status_code, 200)
                self.assertEqual(config(self.root)['hotwords'], ['杭州'])

    async def test_hotword_storage_failure_preserves_config_and_recovers(self):
        path = self.root/'config/asr.json'
        original = path.read_bytes()
        write_text, replace = Path.write_text, Path.replace
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app, raise_app_exceptions=False),
                                     base_url='http://test', trust_env=False) as client:
            with patch.object(module, 'ROOT', self.root):
                for failure in ('write', 'replace'):
                    with self.subTest(failure=failure):
                        path.write_bytes(original)
                        def failed_write(target, data, *args, **kwargs):
                            if target.parent == path.parent and target.suffix == '.tmp':
                                target.write_bytes(b'{partial')
                                raise OSError('disk full')
                            return write_text(target, data, *args, **kwargs)
                        def failed_replace(source, target):
                            if target == path:
                                raise PermissionError('config replacement denied')
                            return replace(source, target)
                        with patch.object(Path, 'write_text', failed_write if failure == 'write' else write_text), \
                             patch.object(Path, 'replace', failed_replace if failure == 'replace' else replace):
                            response = await client.put('/api/asr/config', json={'hotwords':['杭州']})
                        self.assertEqual(response.status_code, 503)
                        self.assertIn('保存', response.json()['detail'])
                        self.assertEqual(path.read_bytes(), original)
                        self.assertEqual(list(path.parent.glob('*.tmp')), [])
                        self.assertEqual((await client.get('/api/asr/config')).json(), config(self.root))
                        response = await client.put('/api/asr/config', json={'hotwords':['杭州', '杭州', ' 义乌市 ']})
                        self.assertEqual(response.status_code, 200)
                        expected = {**json.loads(original), 'hotwords':['杭州', '义乌市']}
                        self.assertEqual(response.json(), expected)
                        self.assertEqual(config(self.root), expected)
                        self.assertEqual(list(path.parent.glob('*.tmp')), [])

    async def test_readiness_tracks_config_damage_and_recovery_with_loaded_model(self):
        path = self.root/'config/asr.json'
        original = path.read_bytes()
        model = self.service.model = SimpleNamespace(generate=lambda **kw: [{'text': '正常识别'}])
        upstream_calls = []
        async def upstream(request):
            upstream_calls.append(str(request.url))
            return httpx.Response(200, json={'status': 'ok'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream), trust_env=False) as backend, \
                   httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),
                                     base_url='http://test', trust_env=False) as client:
            with patch.object(module, 'asr_service', self.service), \
                 patch.object(module.app.state, 'client', backend, create=True), \
                 patch.object(module.app.state, 'care_task', SimpleNamespace(done=lambda: False), create=True), \
                 patch.object(module.app.state, 'wake', SimpleNamespace(snapshot=lambda: {'ready': True}), create=True):
                self.assertTrue((await client.get('/ready')).json()['ready'])
                for broken in (b'{', b'[]', None):
                    with self.subTest(broken=broken):
                        if broken is None:
                            path.unlink()
                        else:
                            path.write_bytes(broken)
                        response = await client.get('/ready')
                        self.assertEqual(response.status_code, 200)
                        state = response.json()
                        self.assertFalse(state['asr'])
                        self.assertFalse(state['ready'])
                        self.assertTrue(state['tts'] and state['llm'] and state['care'])
                        self.assertIs(self.service.model, model)
                path.write_bytes(original)
                self.assertTrue((await client.get('/ready')).json()['ready'])
                self.assertEqual(self.service.transcribe(self.audio), '正常识别')
                self.service.model = None
                self.assertFalse((await client.get('/ready')).json()['asr'])
                self.assertEqual(len(upstream_calls), 12)

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
