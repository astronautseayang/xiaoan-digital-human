"""Audio cleanup must preserve clips still advertised by polling chat jobs."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import httpx

from gateway import app as module


class AudioRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_direct_audio_survives_future_dated_files(self):
        async def local(*args):
            return '您好，测试回答。'

        async def synth(*args, **kwargs):
            return b'complete new audio'

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # A restored directory or a backward wall-clock correction can
            # leave existing files newer than the answer being generated.
            future = time.time() + 86400
            for index in range(201):
                path = root / f'future-{index}.wav'
                path.write_bytes(b'old audio')
                os.utime(path, (future + index, future + index))
            with patch.object(module, 'AUDIO', root), patch.object(module, 'jobs', {}), \
                 patch.object(module, 'local_reply', local), patch.object(module, 'synthesize', synth):
                for _ in range(2):
                    result = await module.chat(module.ChatRequest(text='测试'))
                    path = root / result['audio_url'].split('/')[-1]
                    self.assertTrue(path.exists(), 'Cleanup deleted the response before its URL was returned')
                    self.assertEqual(path.read_bytes(), b'complete new audio')
                self.assertFalse((root / 'future-0.wav').exists(), 'Unprotected excess files were not pruned')

    async def test_storage_failure_is_atomic_and_retryable(self):
        async def local(*args):
            return '您好，测试回答。'

        async def synth(*args, **kwargs):
            return b'complete audio'

        original_write = Path.write_bytes
        original_replace = Path.replace
        for streamed in (False, True):
            for failure in ('write', 'replace'):
                with self.subTest(streamed=streamed, failure=failure), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)

                    def write(path, data):
                        if failure == 'write' and path.parent == root:
                            original_write(path, data[:3])
                            raise OSError('disk full')
                        return original_write(path, data)

                    def replace(path, target):
                        if failure == 'replace' and path.parent == root:
                            raise OSError('replacement denied')
                        return original_replace(path, target)

                    with patch.object(module, 'AUDIO', root), patch.object(module, 'jobs', {}), \
                         patch.object(module, 'local_reply', local), patch.object(module, 'synthesize', synth):
                        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app, raise_app_exceptions=False), base_url='http://test') as client:
                            job = {'text': '', 'clips': [], 'done': False, 'text_done': False, 'error': '', 'created': time.monotonic()}
                            with patch.object(Path, 'write_bytes', write), patch.object(Path, 'replace', replace):
                                if streamed:
                                    await module.run_chat_job(job, module.ChatRequest(text='测试'), {})
                                    self.assertTrue(job['done'])
                                    self.assertTrue(job['text_done'])
                                    self.assertEqual(job['clips'], [])
                                    self.assertIn('音频保存失败', job['error'])
                                else:
                                    response = await client.post('/api/chat', json={'text': '测试'})
                                    self.assertEqual(response.status_code, 503)
                                    self.assertIn('音频保存失败', response.json()['detail'])
                            self.assertEqual(list(root.iterdir()), [], 'Failed publication left an audio file')
                            if streamed:
                                job = {'text': '', 'clips': [], 'done': False, 'text_done': False, 'error': '', 'created': time.monotonic()}
                                await module.run_chat_job(job, module.ChatRequest(text='重试'), {})
                                self.assertTrue(job['done'])
                                self.assertEqual(job['error'], '')
                                self.assertEqual(len(job['clips']), 1)
                                audio_url = job['clips'][0]['audio_url']
                            else:
                                response = await client.post('/api/chat', json={'text': '重试'})
                                self.assertEqual(response.status_code, 200)
                                audio_url = response.json()['audio_url']
                            self.assertEqual((root / audio_url.split('/')[-1]).read_bytes(), b'complete audio')
                            self.assertEqual(len(list(root.iterdir())), 1)

    async def test_cleanup_io_error_does_not_fail_completed_response(self):
        async def local(*args):
            return '您好，测试回答。'

        async def synth(*args, **kwargs):
            return b'audio'

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(module, 'AUDIO', root), patch.object(module, 'jobs', {}), \
                 patch.object(module, 'local_reply', local), patch.object(module, 'synthesize', synth), \
                 patch.object(Path, 'glob', side_effect=PermissionError('cleanup denied')):
                result = await module.chat(module.ChatRequest(text='测试'))
                self.assertTrue((root / result['audio_url'].split('/')[-1]).exists())

    async def test_new_response_does_not_delete_active_or_recent_job_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('active.wav', 'recent.wav', 'expired.wav'):
                path = root / name
                path.write_bytes(b'audio')
                os.utime(path, (1, 1))
            for index in range(200):
                (root / f'new-{index}.wav').write_bytes(b'audio')
            now = time.monotonic()
            jobs = {
                'active': {'done': False, 'created': now-700,
                           'clips': [{'audio_url': '/audio/active.wav'}]},
                'recent': {'done': True, 'created': now,
                           'clips': [{'audio_url': '/audio/recent.wav'}]},
                'expired': {'done': True, 'created': now-700,
                            'clips': [{'audio_url': '/audio/expired.wav'}]},
            }

            async def local(*args):
                return '您好，测试回答。'

            async def synth(*args, **kwargs):
                return b'new audio'

            with patch.object(module, 'AUDIO', root), patch.object(module, 'jobs', jobs), \
                 patch.object(module, 'local_reply', local), patch.object(module, 'synthesize', synth):
                result = await module.chat(module.ChatRequest(text='测试'))
                self.assertTrue((root / 'active.wav').exists(), 'Active response lost its first clip')
                self.assertTrue((root / 'recent.wav').exists(), 'Unexpired polling job lost its clip')
                self.assertFalse((root / 'expired.wav').exists())
                self.assertTrue((root / result['audio_url'].split('/')[-1]).exists())
                self.assertLessEqual(len(list(root.glob('*.wav'))), 202)


if __name__ == '__main__':
    unittest.main()
