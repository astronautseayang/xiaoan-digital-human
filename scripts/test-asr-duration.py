"""Long recordings must not silently execute a transcript of only their prefix."""
import io
import tempfile
import unittest
from unittest.mock import patch
import wave

import httpx
import numpy as np
from gateway import app as module
from gateway.speaker_input import clean_audio, InputRejected, SpeakerInput


def recording(seconds):
    samples = (3000 * np.sin(2 * np.pi * 220 * np.arange(int(seconds * 16000)) / 16000)).astype('<i2')
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(samples.tobytes())
    return output.getvalue()


class DurationTests(unittest.IsolatedAsyncioTestCase):
    def test_preprocessing_preserves_limit_and_rejects_longer_recordings(self):
        for seconds in (29.9, 30):
            with self.subTest(seconds=seconds):
                self.assertEqual(len(clean_audio(recording(seconds))), int(seconds * 16000))
        for seconds in (30.001, 30.1, 31, 35):
            with self.subTest(seconds=seconds), self.assertRaisesRegex(InputRejected, '超过30秒'):
                clean_audio(recording(seconds))

    def test_five_second_speaker_enrollment_is_not_rejected_after_filtering(self):
        with tempfile.TemporaryDirectory() as root:
            speaker = SpeakerInput(root)
            with patch('gateway.speaker_input.speech_only', side_effect=lambda audio: audio), \
                 patch.object(speaker, 'embedding', return_value=np.array([1., 0.], dtype=np.float32)):
                for seconds in (5, 10):
                    with self.subTest(seconds=seconds):
                        self.assertTrue(speaker.enroll(recording(seconds))['enrolled'])
                before = speaker.path.read_bytes()
                for seconds in (4.99, 10.2):
                    with self.subTest(seconds=seconds), self.assertRaises(InputRejected):
                        speaker.enroll(recording(seconds))
                    self.assertEqual(speaker.path.read_bytes(), before)

    async def test_long_upload_is_rejected_before_vad_inference_or_commands_and_recovers(self):
        with patch('gateway.speaker_input.speech_only', side_effect=lambda audio: audio) as vad, \
             patch.object(module.asr_service, 'transcribe', return_value='您好。') as recognize, \
             patch.object(module, 'handle_care_text') as command:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://test') as client:
                response = await client.post('/api/asr', files={'file': ('long.wav', recording(35), 'audio/wav')})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['text'], '')
                self.assertIn('超过30秒', response.json()['input_notice'])
                vad.assert_not_called()
                recognize.assert_not_called()
                command.assert_not_called()
                self.assertFalse(module.asr_lock.locked())
                response = await client.post('/api/asr?execute_commands=false', files={'file': ('short.wav', recording(1), 'audio/wav')})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['text'], '您好。')
                recognize.assert_called_once()
                command.assert_not_called()
                self.assertFalse(module.asr_lock.locked())


if __name__ == '__main__':
    unittest.main()
