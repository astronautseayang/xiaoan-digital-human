"""Reject damaged recordings instead of recognizing their remaining prefix."""
import asyncio
import runpy
from pathlib import Path
import subprocess
import struct
import unittest
from unittest.mock import patch

import httpx
from gateway import app as module
from gateway.speaker_input import clean_audio, InputRejected

recording = runpy.run_path(str(Path(__file__).with_name('test-asr-duration.py')))['recording']


class IntegrityTests(unittest.IsolatedAsyncioTestCase):
    def test_truncated_wav_is_rejected(self):
        data = recording(2)
        for missing in (1, 2, 4, 16000):
            with self.subTest(missing=missing), self.assertRaises(InputRejected):
                clean_audio(data[:-missing])

    def test_valid_recording_formats_remain_supported(self):
        data = recording(2)
        for codec, container in (('pcm_s16le', 'wav'), ('libopus', 'webm'),
                                 ('libvorbis', 'ogg'), ('libmp3lame', 'mp3')):
            with self.subTest(container=container):
                encoded = subprocess.run([
                    'ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', 'pipe:0',
                    '-c:a', codec, '-f', container, 'pipe:1'], input=data,
                    capture_output=True, timeout=10, check=True).stdout
                self.assertAlmostEqual(len(clean_audio(encoded)) / 16000, 2, delta=.1)

    def test_metadata_chunks_are_skipped_and_truncation_still_rejected(self):
        data = recording(2)
        # A padded odd-length chunk before data must not shift parsing.
        metadata = b'JUNK' + struct.pack('<I', 3) + b'abc\0'
        with_metadata = data[:36] + metadata + data[36:]
        with_metadata = with_metadata[:4] + struct.pack('<I', len(with_metadata) - 8) + with_metadata[8:]
        self.assertGreater(len(clean_audio(with_metadata)), 16000)
        for broken in (with_metadata[:-2], data[:36] + b'JUNK' + struct.pack('<I', 100) + b'abc'):
            with self.subTest(length=len(broken)), self.assertRaises(InputRejected):
                clean_audio(broken)

    async def test_bad_upload_never_reaches_inference_and_next_request_recovers(self):
        with patch('gateway.speaker_input.speech_only', side_effect=lambda audio: audio), \
             patch.object(module.asr_service, 'transcribe', return_value='您好。') as recognize, \
             patch.object(module, 'handle_care_text') as command, \
             patch.object(module, 'asr_lock', asyncio.Lock()), \
             patch.object(module, 'asr_tasks', set()):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://test') as client:
                response = await client.post('/api/asr', files={
                    'file': ('broken.wav', recording(2)[:-16000], 'audio/wav')})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['text'], '')
                self.assertIn('数据不完整', response.json()['input_notice'])
                recognize.assert_not_called()
                command.assert_not_called()
                self.assertFalse(module.asr_lock.locked())
                response = await client.post('/api/asr?execute_commands=false', files={
                    'file': ('valid.wav', recording(2), 'audio/wav')})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['text'], '您好。')
                recognize.assert_called_once()
                command.assert_not_called()
                self.assertFalse(module.asr_lock.locked())
                self.assertFalse(module.asr_tasks)


if __name__ == '__main__':
    unittest.main()
