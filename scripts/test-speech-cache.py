"""Cache expiry, resource limits, voice isolation and successful audio reuse."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import httpx
from gateway import app as module
from gateway.speech_cache import SpeechCache, speech_key


class CacheTests(unittest.TestCase):
    def test_truncated_processed_audio_is_not_published_or_cached(self):
        async def run():
            for channels in (1, 2):
                output = io.BytesIO()
                with wave.open(output, 'wb') as wav:
                    wav.setparams((channels, 2, 32000, 0, 'NONE', 'not compressed'))
                    wav.writeframes(b'\0\0' * 100 * channels)
                good = output.getvalue()
                for missing in (1, 2, 4):
                    with self.subTest(channels=channels, missing=missing), tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        (root/'config').mkdir()
                        audio = root/'audio'
                        audio.mkdir()
                        ref = root/'ref.wav'
                        ref.write_bytes(good)
                        voice = {'ref_audio_path': str(ref), 'prompt_text': '参考', 'prompt_lang': 'zh'}
                        (root/'config/voice.json').write_text(json.dumps(voice))
                        cache = SpeechCache()
                        class Response:
                            content = good
                            def raise_for_status(self): pass
                        class Client:
                            async def post(self, *args, **kwargs): return Response()
                        async def local(*args): return '您好。'
                        with patch.object(module, 'ROOT', root), patch.object(module, 'AUDIO', audio), \
                             patch.object(module, 'speech_cache', cache), patch.object(module, 'local_reply', local), \
                             patch.object(module.app.state, 'client', Client(), create=True), \
                             patch.object(module, 'process_senior_speech', return_value=good[:-missing]) as process:
                            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://test') as client:
                                for endpoint in ('/api/tts', '/api/chat'):
                                    response = await client.post(endpoint, json={'text': '您好。'})
                                    self.assertEqual(response.status_code, 502)
                                    self.assertIn('语音处理失败', response.json()['detail'])
                                    self.assertFalse(cache.entries)
                                    self.assertEqual(list(audio.iterdir()), [])
                                job = dict(text='', clips=[], error='', done=False)
                                await module.run_chat_job(job, module.ChatRequest(text='您好。'), voice)
                                self.assertTrue(job['done'])
                                self.assertTrue(job['error'])
                                self.assertEqual(job['clips'], [])
                                self.assertFalse(cache.entries)
                                process.return_value = good
                                for _ in range(2):
                                    response = await client.post('/api/tts', json={'text': '您好。'})
                                    self.assertEqual(response.status_code, 200)
                                    self.assertEqual(response.content, good)
                                self.assertEqual(process.call_count, 4)
        asyncio.run(run())

    def test_reference_read_failures_return_unavailable_and_recover(self):
        async def run():
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setparams((1, 2, 32000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\0\0' * 100)
            audio = output.getvalue()
            calls = []
            class Response:
                content = audio
                def raise_for_status(self): pass
            class Client:
                async def post(self, *args, **kwargs):
                    calls.append(True)
                    return Response()
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root/'config').mkdir()
                reference = root/'ref.wav'
                reference.write_bytes(audio)
                config = root/'config/voice.json'
                config.write_text(json.dumps({'ref_audio_path': str(reference),
                                              'prompt_text': '参考', 'prompt_lang': 'zh'}))
                before = config.read_bytes()
                read_bytes = Path.read_bytes
                cache = SpeechCache()
                with patch.object(module, 'ROOT', root), patch.object(module, 'speech_cache', cache), \
                     patch.object(module.app.state, 'client', Client(), create=True), \
                     patch.object(module, 'process_senior_speech', return_value=audio):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),
                                                 base_url='http://test', trust_env=False) as client:
                        for error in (PermissionError, FileNotFoundError, IsADirectoryError):
                            with self.subTest(error=error):
                                def failed_read(path):
                                    if path == reference:
                                        raise error('reference became unavailable after validation')
                                    return read_bytes(path)
                                with patch.object(Path, 'read_bytes', failed_read):
                                    response = await client.post('/api/tts', json={'text': '您好'})
                                self.assertEqual(response.status_code, 503)
                                self.assertIn('参考录音', response.json()['detail'])
                                self.assertFalse(calls)
                                self.assertFalse(cache.entries)
                                self.assertEqual(config.read_bytes(), before)
                        for _ in range(2):
                            response = await client.post('/api/tts', json={'text': '您好'})
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.content, audio)
                        self.assertEqual(len(calls), 1)
        asyncio.run(run())

    def test_expiry_and_limits(self):
        now = [0]
        cache = SpeechCache(max_entries=2, max_bytes=5, ttl=10, clock=lambda: now[0])
        cache.put('a', b'aa'); cache.put('b', b'bb')
        self.assertEqual(cache.get('a'), b'aa')
        cache.put('c', b'cc')
        self.assertIsNone(cache.get('b'))
        cache.put('large', b'xxxxxx')
        self.assertIsNone(cache.get('large'))
        cache.put('a', b'aaaa')
        self.assertIsNone(cache.get('c'))
        self.assertEqual(cache.size, 4)
        now[0] = 10
        self.assertIsNone(cache.get('a'))
        self.assertEqual(cache.size, 0)

    def test_reference_and_voice_changes_invalidate(self):
        with tempfile.TemporaryDirectory() as directory:
            ref = Path(directory) / 'ref.wav'; ref.write_bytes(b'one')
            voice = {'ref_audio_path': str(ref), 'prompt_text': '参考', 'prompt_lang': 'zh'}
            key = speech_key('你好', 'zh', voice)
            self.assertNotEqual(key, speech_key('您好', 'zh', voice))
            self.assertNotEqual(key, speech_key('你好', 'en', voice))
            self.assertNotEqual(key, speech_key('你好', 'zh', {**voice, 'prompt_text': '变更'}))
            ref.write_bytes(b'two')
            self.assertNotEqual(key, speech_key('你好', 'zh', voice))

    def test_only_successful_processed_audio_is_reused(self):
        async def run():
            output = io.BytesIO()
            with wave.open(output, 'wb') as w:
                w.setparams((1, 2, 32000, 0, 'NONE', 'not compressed'))
                w.writeframes(b'\0\0' * 100)
            data = output.getvalue()
            class Response:
                content = data
                def raise_for_status(self): pass
            calls = []
            class Client:
                async def post(self, *args, **kwargs):
                    calls.append(True)
                    return Response()
            with tempfile.TemporaryDirectory() as directory:
                ref = Path(directory) / 'ref.wav'; ref.write_bytes(data)
                voice = {'ref_audio_path': str(ref), 'prompt_text': '参考', 'prompt_lang': 'zh'}
                with patch.object(module, 'speech_cache', SpeechCache()), \
                     patch.object(module.app.state, 'client', Client(), create=True), \
                     patch.object(module, 'process_senior_speech', side_effect=[ValueError('injected'), data]) as process:
                    with self.assertRaises(module.HTTPException):
                        await module.synthesize('您好', voice=voice)
                    self.assertEqual(await module.synthesize('您好', voice=voice), data)
                    self.assertEqual(await module.synthesize('您好', voice=voice), data)
                    self.assertEqual(len(calls), 2)
                    self.assertEqual(process.call_count, 2)
        asyncio.run(run())


unittest.main()
