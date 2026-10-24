"""Run from the project root: PYTHONPATH=. python scripts/test-audio-level.py."""
import asyncio
import audioop
import io
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from fastapi import HTTPException, UploadFile
from gateway.audio_level import normalize_speech
from gateway import app as gateway


def tone(amplitude, seconds=6, silence=0):
    frames = [int(amplitude * math.sin(2 * math.pi * 220 * i / 16000))
              if i >= silence * 16000 else 0 for i in range(int(seconds * 16000))]
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(struct.pack('<' + 'h' * len(frames), *frames))
    return output.getvalue()


def pcm(data):
    with wave.open(io.BytesIO(data), 'rb') as wav:
        return wav.getparams(), wav.readframes(wav.getnframes())


class Levels(unittest.TestCase):
    def test_quiet_normal_loud_converge(self):
        for amplitude in (100, 300, 6000, 32000):
            source = tone(amplitude)
            params, raw = pcm(normalize_speech(source))
            self.assertEqual(params, pcm(source)[0])
            self.assertAlmostEqual(audioop.rms(raw, 2), 3276.8, delta=30)
            self.assertLessEqual(audioop.max(raw, 2), 29204)

    def test_pauses_do_not_inflate_gain(self):
        normalized = normalize_speech(tone(300, silence=4))
        _, raw = pcm(normalized)
        self.assertEqual(audioop.max(raw[:4 * 16000 * 2], 2), 0)
        self.assertAlmostEqual(audioop.rms(raw[4 * 16000 * 2:], 2), 3276.8, delta=30)

    def test_peak_headroom(self):
        params, raw = pcm(tone(100))
        raw = struct.pack('<h', 32000) + raw[2:]
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setparams(params)
            wav.writeframes(raw)
        self.assertLessEqual(audioop.max(pcm(normalize_speech(output.getvalue()))[1], 2), 29204)

    def test_silence_and_invalid(self):
        for data in (tone(0), tone(10)):
            self.assertEqual(normalize_speech(data), data)
            with self.assertRaises(ValueError):
                normalize_speech(data, reject_quiet=True)
        with self.assertRaises((wave.Error, EOFError)):
            normalize_speech(b'bad file')

    def test_enrollment_uses_normalized_reference_and_rolls_back(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / 'voice.json'
                config.write_text('{"original": true}')
                audio = root / 'audio'
                audio.mkdir()
                async def asr(file, care_commands=True):
                    self.assertFalse(care_commands)
                    self.assertGreater(audioop.rms(pcm(await file.read())[1], 2), 3200)
                    return {'text': '这是测试参考声音。'}
                async def synth(text, voice):
                    self.assertGreater(audioop.rms(pcm(Path(voice['ref_audio_path']).read_bytes())[1], 2), 3200)
                    return tone(4600)
                with patch.multiple(gateway, ROOT=root, VOICE_FILE=config, AUDIO=audio,
                                    asr=asr, synthesize=synth):
                    result = await gateway.enroll_voice(UploadFile(file=io.BytesIO(tone(100))), text='')
                    self.assertTrue((audio / Path(result['audio_url']).name).is_file())
                    saved = config.read_bytes()
                    references = set((root / 'assets/reference/enrolled').iterdir())
                    async def fail(*args, **kwargs):
                        raise HTTPException(502, 'test failure')
                    with patch.object(gateway, 'synthesize', fail):
                        with self.assertRaises(HTTPException):
                            await gateway.enroll_voice(UploadFile(file=io.BytesIO(tone(100))), text='清晰的参考内容')
                    self.assertEqual(config.read_bytes(), saved)
                    self.assertEqual(set((root / 'assets/reference/enrolled').iterdir()), references)
        asyncio.run(run())


unittest.main()
