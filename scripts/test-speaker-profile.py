"""Corrupt speaker profiles must never authorize a voice command."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import httpx
from gateway import app as module
from gateway.speaker_input import SpeakerInput, InputRejected

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.speaker=SpeakerInput(Path(self.tmp.name))
        self.speaker.path.parent.mkdir()
        self.audio=np.ones(32000,dtype=np.float32)
        self.clean=patch('gateway.speaker_input.clean_audio',return_value=self.audio)
        self.vad=patch('gateway.speaker_input.speech_only',return_value=self.audio)
        self.embed=patch.object(self.speaker,'embedding',return_value=np.array([1.,0.],dtype=np.float32))
        for p in (self.clean,self.vad,self.embed):p.start();self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
    def write(self,value):self.speaker.path.write_text(json.dumps(value))
    def test_corruption_rejected_without_overwriting_profile(self):
        bad=[None, [], {}, {'enabled':'false','embedding':[1.,0.]},
             {'enabled':True,'embedding':[]}, {'enabled':True,'embedding':[float('nan'),0.]},
             {'enabled':True,'embedding':[float('inf'),0.]}, {'enabled':True,'embedding':[0.,0.]},
             {'enabled':True,'embedding':[[1.,0.]]}, {'enabled':True,'embedding':['1',0.]},
             {'enabled':True,'embedding':[True,0.]},
             {'enabled':True,'embedding':[1.,0.],'threshold':float('nan')},
             {'enabled':True,'embedding':[1.,0.],'window_threshold':-1}]
        for value in bad:
            with self.subTest(value=value):
                self.write(value);before=self.speaker.path.read_bytes()
                with self.assertRaises(InputRejected):self.speaker.prepare(b'audio')
                self.assertEqual(self.speaker.path.read_bytes(),before)
        self.speaker.path.write_text('{broken')
        with self.assertRaises(InputRejected):self.speaker.prepare(b'audio')
    def test_dimension_mismatch_rejected(self):
        self.write({'enabled':True,'embedding':[1.,0.,0.]})
        with self.assertRaises(InputRejected):self.speaker.prepare(b'audio')
    def test_valid_match_mismatch_and_disabled(self):
        self.write({'enabled':True,'embedding':[1.,0.]})
        self.assertEqual(len(self.speaker.prepare(b'audio')),32000)
        self.write({'enabled':True,'embedding':[0.,1.]})
        with self.assertRaises(InputRejected):self.speaker.prepare(b'audio')
        self.write({'enabled':False,'embedding':[]})
        self.assertEqual(len(self.speaker.prepare(b'audio')),32000)
    def test_explicit_transcription_bypasses_profile(self):
        self.speaker.path.write_text('{broken')
        self.assertEqual(len(self.speaker.prepare(b'audio',verify=False)),32000)

class ProfileApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_storage_errors_preserve_profile_and_recover(self):
        with tempfile.TemporaryDirectory() as tmp:
            speaker = SpeakerInput(Path(tmp))
            speaker.path.parent.mkdir()
            original = b'{"enabled":false,"embedding":[1.0,0.0]}'
            speaker.model_path.parent.mkdir(parents=True)
            speaker.model_path.touch()
            write_text, replace = Path.write_text, Path.replace
            audio = np.ones(96000, dtype=np.float32)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app, raise_app_exceptions=False),
                                         base_url='http://test', trust_env=False) as client:
                with patch.object(module, 'speaker_input', speaker), \
                     patch('gateway.speaker_input.clean_audio', return_value=audio), \
                     patch('gateway.speaker_input.speech_only', return_value=audio), \
                     patch.object(speaker, 'embedding', return_value=np.array([1.,0.], dtype=np.float32)):
                    for endpoint in ('setting', 'enroll'):
                        async def submit():
                            if endpoint == 'setting':
                                return await client.put('/api/speaker/profile', json={'enabled':True})
                            return await client.post('/api/speaker/enroll', files={'file':('voice.wav', b'fixture', 'audio/wav')})
                        for failure in ('write', 'replace'):
                            with self.subTest(endpoint=endpoint, failure=failure):
                                speaker.path.write_bytes(original)
                                def failed_write(target, data, *args, **kwargs):
                                    if target.suffix == '.tmp':
                                        target.write_bytes(b'{partial')
                                        raise OSError('disk full')
                                    return write_text(target, data, *args, **kwargs)
                                def failed_replace(source, target):
                                    if target == speaker.path:
                                        raise PermissionError('replacement denied')
                                    return replace(source, target)
                                with patch.object(Path, 'write_text', failed_write if failure == 'write' else write_text), \
                                     patch.object(Path, 'replace', failed_replace if failure == 'replace' else replace):
                                    response = await submit()
                                self.assertEqual(response.status_code, 503)
                                self.assertIn('保存', response.json()['detail'])
                                self.assertEqual(speaker.path.read_bytes(), original)
                                self.assertEqual(list(speaker.path.parent.glob('*.tmp')), [])
                                self.assertFalse((await client.get('/api/speaker/profile')).json()['enabled'])
                                response = await submit()
                                self.assertEqual(response.status_code, 200)
                                self.assertTrue(response.json()['enabled'])
                                self.assertEqual(speaker.path.stat().st_mode & 0o777, 0o600)

    async def test_profile_is_private_before_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            speaker = SpeakerInput(Path(tmp))
            replace = Path.replace
            observed = []
            def inspect_replace(source, target):
                observed.append(source.stat().st_mode & 0o777)
                return replace(source, target)
            with patch.object(Path, 'replace', inspect_replace):
                speaker.save({'enabled':False, 'embedding':[1.,0.]})
            self.assertEqual(observed, [0o600])

    async def test_invalid_profile_has_actionable_error_and_no_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            speaker=SpeakerInput(Path(tmp))
            speaker.path.parent.mkdir()
            speaker.path.write_text('{broken')
            with patch.object(module,'speaker_input',speaker),patch('gateway.speaker_input.clean_audio',return_value=np.ones(32000,dtype=np.float32)),patch('gateway.speaker_input.speech_only',side_effect=lambda a:a),patch.object(module,'handle_care_text') as command,patch.object(module.asr_service,'transcribe') as transcribe:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test',trust_env=False) as client:
                    r=await client.get('/api/speaker/profile')
                    self.assertEqual(r.status_code,422)
                    self.assertIn('重新录入',r.json()['detail'])
                    r=await client.post('/api/asr',files={'file':('test.wav',b'fixture','audio/wav')})
                    self.assertEqual(r.status_code,200)
                    self.assertEqual(r.json()['text'],'')
                    self.assertIn('重新录入',r.json()['input_notice'])
                    command.assert_not_called()
                    transcribe.assert_not_called()

if __name__=='__main__':unittest.main()
