"""Cloned speech must contain speech and cover the response before publication."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave
import httpx
from gateway import app as module
from gateway.voice_quality import coverage, SpeechQualityError, validate_cloned_speech
from gateway.speech_cache import SpeechCache
from gateway.asr_service import ASRUnavailable


def wav():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as w:
        w.setparams((1, 2, 32000, 0, 'NONE', 'not compressed'))
        w.writeframes(b'\0\0' * 32000)
    return buffer.getvalue()


class QualityTests(unittest.TestCase):
    def test_quality_asr_unavailable_reports_503_without_retrying_tts(self):
        async def run():
            audio = wav()
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root/'config').mkdir()
                ref = root/'reference.wav'
                ref.write_bytes(audio)
                config = root/'config/voice.json'
                config.write_text(json.dumps({'ref_audio_path':str(ref), 'prompt_lang':'zh',
                                              'prompt_text':'参考内容', 'validate_speech':True}))
                before = config.read_bytes()
                recognizer = Mock()
                recognizer.transcribe.side_effect = ASRUnavailable('recognizer exhausted its retries')
                backend = Mock()
                backend.content = audio
                requests = []
                class Client:
                    async def post(self, *args, **kwargs):
                        requests.append(True)
                        return backend
                cache = SpeechCache()
                with patch.object(module, 'ROOT', root), \
                     patch.object(module.app.state, 'client', Client(), create=True), \
                     patch.object(module, 'speech_cache', cache), \
                     patch.object(module, 'cleaned_reference', return_value=str(ref)), \
                     patch.object(module, 'asr_service', recognizer), \
                     patch('gateway.voice_quality.speech_only', side_effect=lambda data:data), \
                     patch.object(module, 'process_senior_speech', return_value=audio) as process:
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app, raise_app_exceptions=False),
                                                 base_url='http://test', trust_env=False) as client:
                        response = await client.post('/api/tts', json={'text':'您好，请慢慢说。'})
                        self.assertEqual(response.status_code, 503)
                        self.assertIn('校验', response.json()['detail'])
                        self.assertNotIn('重新录入', response.json()['detail'])
                        self.assertEqual(len(requests), 1)
                        self.assertFalse(cache.entries)
                        process.assert_not_called()
                        self.assertEqual(config.read_bytes(), before)
                        recognizer.transcribe.side_effect = None
                        recognizer.transcribe.return_value = '您好，请慢慢说。'
                        for _ in range(2):
                            response = await client.post('/api/tts', json={'text':'您好，请慢慢说。'})
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.content, audio)
                        self.assertEqual(len(requests), 2)
                        self.assertEqual(process.call_count, 1)
                        self.assertEqual(config.read_bytes(), before)
        asyncio.run(run())

    def test_truncated_pcm_rejected_before_vad_and_asr(self):
        for channels in (1, 2):
            output = io.BytesIO()
            with wave.open(output, 'wb') as target:
                target.setparams((channels, 2, 32000, 0, 'NONE', 'not compressed'))
                target.writeframes(b'\0\0' * 32000 * channels)
            for missing in (1, 2, 4):
                with self.subTest(channels=channels, missing=missing), \
                     patch('gateway.voice_quality.speech_only', side_effect=lambda audio: audio) as vad:
                    recognizer = Mock()
                    recognizer.transcribe.return_value = '您好，请慢慢说。'
                    with self.assertRaises(SpeechQualityError):
                        validate_cloned_speech(output.getvalue()[:-missing], '您好，请慢慢说。', recognizer)
                    vad.assert_not_called()
                    recognizer.transcribe.assert_not_called()

    def test_truncated_upstream_retries_without_caching_and_recovers(self):
        async def run():
            good = wav()
            with tempfile.TemporaryDirectory() as tmp:
                ref = Path(tmp)/'reference.wav'
                ref.write_bytes(good)
                voice = {'ref_audio_path':str(ref), 'prompt_lang':'zh',
                         'prompt_text':'参考内容', 'validate_speech':True}
                for missing in (1, 2):
                    with self.subTest(missing=missing):
                        requests = []
                        class Response:
                            def __init__(self, content): self.content = content
                            def raise_for_status(self): pass
                        class Client:
                            async def post(self, *args, **kwargs):
                                requests.append(True)
                                return Response(good[:-missing] if len(requests) <= 3 else good)
                        cache = SpeechCache()
                        recognizer = Mock()
                        recognizer.transcribe.return_value = '您好，请慢慢说。'
                        with patch.object(module.app.state, 'client', Client(), create=True), \
                             patch.object(module, 'speech_cache', cache), \
                             patch.object(module, 'cleaned_reference', return_value=str(ref)), \
                             patch.object(module, 'asr_service', recognizer), \
                             patch('gateway.voice_quality.speech_only', side_effect=lambda audio: audio), \
                             patch.object(module, 'process_senior_speech', side_effect=lambda data, **kwargs:data) as process:
                            with self.assertRaises(module.HTTPException) as error:
                                await module.synthesize('您好，请慢慢说。', voice=voice)
                            self.assertEqual(error.exception.status_code, 502)
                            self.assertEqual(len(requests), 3)
                            self.assertFalse(cache.entries)
                            process.assert_not_called()
                            recognizer.transcribe.assert_not_called()
                            self.assertEqual(await module.synthesize('您好，请慢慢说。', voice=voice), good)
                            self.assertEqual(await module.synthesize('您好，请慢慢说。', voice=voice), good)
                            self.assertEqual(len(requests), 4)
                            self.assertEqual(process.call_count, 1)
        asyncio.run(run())

    def test_stream_keeps_salutation_with_following_clause(self):
        async def run():
            text = '爷爷，春天的公园里百花盛开，树木长出嫩绿的新叶。湖面映着蓝天白云，人们沿着小路散步，孩子们在草地上放风筝，到处洋溢着春天的生机。'
            class Response:
                async def __aenter__(self): return self
                async def __aexit__(self, *args): pass
                def raise_for_status(self): pass
                async def aiter_lines(self):
                    for char in text:
                        yield 'data: ' + json.dumps({'choices': [{'delta': {'content': char}}]})
                        await asyncio.sleep(0)
                    yield 'data: [DONE]'
            class Client:
                def stream(self, *args, **kwargs): return Response()
            spoken = []
            async def synth(sentence, **kwargs):
                spoken.append(sentence)
                return b'test audio'
            async def no_local(*args): return None
            with tempfile.TemporaryDirectory() as tmp, \
                 patch.object(module, 'AUDIO', Path(tmp)), \
                 patch.object(module.app.state, 'client', Client(), create=True), \
                 patch.object(module, 'local_reply', no_local), \
                 patch.object(module, 'salutation_for', lambda root: '爷爷'), \
                 patch.object(module, 'synthesize', synth):
                job = {'text': '', 'clips': [], 'error': ''}
                await module.run_chat_job(job, module.ChatRequest(text='介绍春天'), {})
            self.assertFalse(job['error'], job)
            self.assertGreater(len(spoken), 1)
            self.assertTrue(spoken[0].startswith('爷爷，春天'))
            self.assertTrue(all(len(part) >= 12 for part in spoken), spoken)
            self.assertEqual(''.join(spoken), text)
            self.assertEqual(job['text'], text)
        asyncio.run(run())

    def test_coverage_rejects_missing_clauses(self):
        text = '爷爷您刚才说是在济南了，那这边的天气情况是怎样的呢？'
        self.assertGreater(coverage(text, '岩爷，您刚才说是在济南了，那这边的天气情况是怎样的呢'), .9)
        self.assertLess(coverage(text, '那这边的天气情况是怎样的呢'), .75)
        self.assertLess(coverage(text, ''), .75)
        self.assertIsNone(coverage('好的', '好的'))

    def test_real_silence_rejected_before_asr(self):
        class Recognizer:
            def transcribe(self, audio):
                raise AssertionError('Silence must not reach ASR')
        with self.assertRaises(SpeechQualityError):
            validate_cloned_speech(wav(), '爷爷您好，今天想聊些什么呢？', Recognizer())

    def test_chat_preserves_actionable_quality_error(self):
        async def run():
            async def reply(*args): return '爷爷您好，请慢慢说。'
            async def fail(*args, **kwargs):
                raise module.HTTPException(502, '当前音色连续合成不完整，请重新录入清晰音色。')
            with tempfile.TemporaryDirectory() as tmp, \
                 patch.object(module, 'AUDIO', Path(tmp)), \
                 patch.object(module, 'local_reply', reply), \
                 patch.object(module, 'synthesize', fail):
                job = {'text': '', 'clips': [], 'error': ''}
                await module.run_chat_job(job, module.ChatRequest(text='你好'), {})
                self.assertTrue(job['done'])
                self.assertEqual(job['clips'], [])
                self.assertIn('重新录入清晰音色', job['error'])
        asyncio.run(run())

    def test_retries_and_bounded_failure(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                ref = Path(tmp) / 'reference.wav'
                ref.write_bytes(wav())
                voice = {'ref_audio_path': str(ref), 'prompt_lang': 'zh',
                         'prompt_text': '参考内容', 'label': '我的录入音色'}
                requests = []
                class Response:
                    content = wav()
                    def raise_for_status(self): pass
                class Client:
                    async def post(self, url, json):
                        requests.append(dict(json))
                        return Response()
                for failures in (0, 1, 3):
                    requests.clear()
                    calls = []
                    def validate(*args):
                        calls.append(True)
                        if len(calls) <= failures:
                            raise SpeechQualityError('Injected incomplete speech')
                    with patch.object(module.app.state, 'client', Client(), create=True), \
                         patch.object(module, 'speech_cache', SpeechCache()), \
                         patch.object(module, 'validate_cloned_speech', validate), \
                         patch.object(module, 'process_senior_speech', lambda data, **kwargs: data):
                        if failures == 3:
                            with self.assertRaises(module.HTTPException) as error:
                                await module.synthesize('爷爷您好，请慢慢说。', voice=voice)
                            self.assertIn('重新录入', error.exception.detail)
                        else:
                            self.assertEqual(await module.synthesize('爷爷您好，请慢慢说。', voice=voice), wav())
                    self.assertEqual(len(requests), min(failures + 1, 3))
                    self.assertTrue(all(p['text_split_method'] == 'cut0' for p in requests))
                    if failures:
                        self.assertEqual(requests[1]['top_k'], 5)
        asyncio.run(run())


unittest.main()
