"""Verify noise reduction without sacrificing speech energy or source recordings."""
import io
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import numpy as np
from gateway.voice_denoise import denoise_speech, cleaned_reference, trim_reference, NOISE_FILTER, REFERENCE_PROFILE


def sample():
    rate = 32000
    t = np.arange(rate * 4) / rate
    audio = np.random.default_rng(42).normal(0, .002, len(t))
    voiced = (t >= 1) & (t < 3)
    audio[voiced] += (.1 * np.sin(2 * np.pi * 220 * t[voiced])
                      + .025 * np.sin(2 * np.pi * 660 * t[voiced]))
    data = io.BytesIO()
    with wave.open(data, 'wb') as w:
        w.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        w.writeframes((audio * 32767).astype('<i2').tobytes())
    return data.getvalue()


def read(data):
    with wave.open(io.BytesIO(data)) as w:
        return w.getparams(), np.frombuffer(w.readframes(w.getnframes()), '<i2') / 32768


class DenoiseTests(unittest.TestCase):
    def test_truncated_pcm_is_rejected_before_dsp(self):
        original = sample()
        for damaged in (original[:44], original[:-100], original[:-1]):
            for process in (denoise_speech, trim_reference):
                with self.subTest(size=len(damaged), process=process.__name__):
                    with patch('faster_whisper.vad.get_speech_timestamps', return_value=[]):
                        with self.assertRaises(ValueError):
                            process(damaged)

    def test_truncated_source_never_becomes_a_valid_reference_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'reference.wav'
            damaged = sample()[:-100]
            source.write_bytes(damaged)
            with patch('faster_whisper.vad.get_speech_timestamps', return_value=[]):
                with self.assertRaises(ValueError):
                    cleaned_reference(source, root/'cache')
            self.assertEqual(source.read_bytes(), damaged)
            self.assertEqual(list((root/'cache').glob('*.wav')), [])
            # A cache produced by an older version must not authorize a
            # damaged original merely because the derived WAV is complete.
            cache = root/'cache'
            cache.mkdir(exist_ok=True)
            key = hashlib.sha256((NOISE_FILTER+REFERENCE_PROFILE).encode()+damaged).hexdigest()
            (cache/(key+'.wav')).write_bytes(sample())
            with self.assertRaises(ValueError):
                cleaned_reference(source, cache)

    def test_reference_trim_keeps_internal_pauses_and_respects_minimum(self):
        source = sample()
        params, original = read(source)
        spans = [{'start': 8000, 'end': 16000}, {'start': 48000, 'end': 56000}]
        with patch('faster_whisper.vad.get_speech_timestamps', return_value=spans):
            trimmed_params, trimmed = read(trim_reference(source))
        self.assertEqual(trimmed_params.nframes, params.framerate * 3)
        np.testing.assert_array_equal(trimmed, original[16000:112000])
        for spans in ([], [{'start': 16000, 'end': 32000}]):
            with patch('faster_whisper.vad.get_speech_timestamps', return_value=spans):
                self.assertEqual(trim_reference(source), source)

    def test_reduces_noise_and_preserves_voiced_energy_and_duration(self):
        source = sample()
        params, before = read(source)
        after_params, after = read(denoise_speech(source))
        self.assertEqual(params, after_params)
        def db(audio): return 20 * np.log10(np.sqrt(np.mean(audio ** 2)))
        for pause in (slice(16000, 32000), slice(112000, 128000)):
            self.assertLess(db(after[pause]), db(before[pause]) - 6)
        voice = slice(48000, 80000)
        self.assertLess(abs(db(after[voice]) - db(before[voice])), 1)
        self.assertLess(np.max(np.abs(after)), .891)

    def test_cached_copy_preserves_original_and_refreshes_on_content_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'reference.wav'
            original = sample()
            source.write_bytes(original)
            first = cleaned_reference(source, root / 'cache')
            self.assertEqual(source.read_bytes(), original)
            self.assertNotEqual(Path(first), source)
            with patch('gateway.voice_denoise.denoise_speech', side_effect=AssertionError('cache missed')):
                self.assertEqual(cleaned_reference(source, root / 'cache'), first)
            # A replaced recording at the same path must not reuse stale audio.
            source.write_bytes(denoise_speech(original))
            self.assertNotEqual(cleaned_reference(source, root / 'cache'), first)

    def test_damaged_cache_is_rebuilt_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'reference.wav'
            original = sample()
            source.write_bytes(original)
            with patch('gateway.voice_denoise.denoise_speech',return_value=original),patch('gateway.voice_denoise.trim_reference',side_effect=lambda data:data):
                target = Path(cleaned_reference(source,root/'cache'))
                for damaged in (b'', b'broken WAV', original[:44], original[:-100]):
                    with self.subTest(size=len(damaged)):
                        target.write_bytes(damaged)
                        with patch('gateway.voice_denoise.denoise_speech',return_value=original) as denoise:
                            self.assertEqual(cleaned_reference(source,root/'cache'),str(target))
                            denoise.assert_called_once()
                        self.assertEqual(target.read_bytes(),original)
                        self.assertEqual(source.read_bytes(),original)
                        self.assertEqual(list((root/'cache').glob('*.tmp')),[])

    def test_failed_rebuild_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'reference.wav';source.write_bytes(sample())
            with patch('gateway.voice_denoise.trim_reference',side_effect=lambda data:data):
                target=Path(cleaned_reference(source,root/'cache'))
                target.write_bytes(b'broken')
                with patch('gateway.voice_denoise.denoise_speech',side_effect=RuntimeError('Injected DSP failure')):
                    with self.assertRaises(RuntimeError):cleaned_reference(source,root/'cache')
                self.assertEqual(list((root/'cache').glob('*.tmp')),[])
                repaired=Path(cleaned_reference(source,root/'cache'))
                params,_=read(repaired.read_bytes())
                self.assertGreater(params.nframes,0)


unittest.main()
