"""Damaged voice settings fail before starting chat or calling speech services."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from gateway import app as module


class VoiceConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_reset_rejects_broken_defaults_without_replacing_working_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config').mkdir()
            reference = root/'reference.wav'
            reference.write_bytes(b'reference')
            current = root/'config/voice.json'
            default = root/'config/voice-default.json'
            valid = {'ref_audio_path': str(reference), 'prompt_lang': 'zh',
                     'prompt_text': '你好', 'label': '正常音色'}
            current.write_text(json.dumps(valid))
            before = current.read_bytes()
            with patch.object(module, 'ROOT', root), patch.object(module, 'VOICE_FILE', current), \
                 patch.object(module, 'VOICE_DEFAULT', default):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),
                                             base_url='http://test', trust_env=False) as client:
                    for broken in (b'{', b'null', b'[]', json.dumps({**valid, 'ref_audio_path': str(root/'missing.wav')}).encode(), None):
                        with self.subTest(broken=broken):
                            if broken is None:
                                default.unlink()
                            else:
                                default.write_bytes(broken)
                            response = await client.post('/api/voice/reset')
                            self.assertEqual(response.status_code, 503)
                            self.assertEqual(current.read_bytes(), before)
                            self.assertEqual(list(current.parent.glob('*.tmp')), [])
                    default.write_text(json.dumps({**valid, 'label': '默认音色'}))
                    self.assertEqual((await client.post('/api/voice/reset')).json()['text'], '默认音色')
                    self.assertEqual(current.read_bytes(), default.read_bytes())

    async def test_reset_storage_failure_preserves_voice_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root/'voice.json'
            default = root/'voice-default.json'
            reference = root/'reference.wav'
            reference.write_bytes(b'reference')
            current.write_bytes(b'working voice config')
            default.write_text(json.dumps({'ref_audio_path': str(reference), 'prompt_lang': 'zh', 'prompt_text': '你好'}))
            with patch.object(module, 'VOICE_FILE', current), patch.object(module, 'VOICE_DEFAULT', default), \
                 patch.object(Path, 'replace', side_effect=PermissionError('replacement denied')):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),
                                             base_url='http://test', trust_env=False) as client:
                    self.assertEqual((await client.post('/api/voice/reset')).status_code, 503)
            self.assertEqual(current.read_bytes(), b'working voice config')
            self.assertEqual(list(root.glob('*.tmp')), [])

    async def test_voice_display_reports_damaged_config_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config').mkdir()
            path = root/'config/voice.json'
            reference = root/'reference.wav'
            reference.write_bytes(b'reference')
            with patch.object(module, 'ROOT', root), patch.object(module, 'VOICE_FILE', path):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),
                                             base_url='http://test', trust_env=False) as client:
                    for broken in (b'{', b'null', b'[]', b'{}'):
                        with self.subTest(broken=broken):
                            path.write_bytes(broken)
                            self.assertEqual((await client.get('/api/voice')).status_code, 503)
                    path.write_text(json.dumps({'ref_audio_path': str(reference), 'prompt_lang': 'zh',
                                                'prompt_text': '你好', 'label': '恢复后的音色'}))
                    self.assertEqual((await client.get('/api/voice')).json(), {'text': '恢复后的音色'})

    async def test_corrupt_settings_return_recoverable_status_without_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config').mkdir()
            reference = root / 'ref.wav'
            reference.write_bytes(b'reference')
            valid = {'ref_audio_path': str(reference), 'prompt_lang': 'zh', 'prompt_text': '你好'}
            damaged = [None, [], {}, {**valid, 'ref_audio_path': 7},
                       {**valid, 'ref_audio_path': str(root / 'missing.wav')},
                       {**valid, 'prompt_lang': ''}, {**valid, 'prompt_text': None},
                       {**valid, 'validate_speech': 'false'}]
            path = root / 'config/voice.json'
            with patch.object(module, 'ROOT', root), patch.object(module, 'jobs', {}):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),
                                             base_url='http://test') as client:
                    for raw in [b'{', b'\xff', *[json.dumps(v).encode() for v in damaged], None]:
                        if raw is None:
                            path.unlink()
                        else:
                            path.write_bytes(raw)
                        for endpoint in ('/api/tts', '/api/chat/jobs'):
                            with self.subTest(raw=raw, endpoint=endpoint):
                                response = await client.post(endpoint, json={'text': '你好'})
                                self.assertEqual(response.status_code, 503, response.text)
                                self.assertIn('恢复默认音色', response.json()['detail'])
                                self.assertFalse(module.jobs)
                    path.write_text(json.dumps(valid))
                    self.assertEqual(module.validated_voice(), valid)
                    self.assertEqual(module.validated_voice({**valid, 'prompt_text': ''})['prompt_text'], '')


if __name__ == '__main__':
    unittest.main()
