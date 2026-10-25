"""Reject silent or substantially incomplete cloned speech before publishing it."""
from difflib import SequenceMatcher
import io
import math
import re
import wave
import numpy as np
from scipy.signal import resample_poly
from gateway.speaker_input import speech_only, InputRejected


class SpeechQualityError(ValueError):
    pass


def coverage(expected, recognized):
    # ASR punctuation and written numbers differ. Compare Chinese characters;
    # do not interpret generated audio as a user command or verify its speaker.
    expected = ''.join(re.findall(r'[\u4e00-\u9fff]', expected))
    recognized = ''.join(re.findall(r'[\u4e00-\u9fff]', recognized))
    if len(expected) < 6:
        return None
    matches = SequenceMatcher(None, expected, recognized, autojunk=False).get_matching_blocks()
    return sum(m.size for m in matches) / len(expected)


def validate_cloned_speech(data, text, recognizer):
    with wave.open(io.BytesIO(data), 'rb') as wav:
        if wav.getsampwidth() != 2:
            raise SpeechQualityError('合成音频不是PCM16')
        rate, channels = wav.getframerate(), wav.getnchannels()
        frames = wav.getnframes()
        pcm = wav.readframes(frames)
        if len(pcm) != frames * channels * 2:
            raise SpeechQualityError('合成音频数据不完整')
        audio = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
    if not len(audio):
        raise SpeechQualityError('合成音频为空')
    audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != 16000:
        common = math.gcd(rate, 16000)
        audio = resample_poly(audio, 16000 // common, rate // common).astype(np.float32)
    try:
        speech = speech_only(audio)
    except InputRejected as exc:
        raise SpeechQualityError('合成音频没有清晰人声') from exc
    recognized = recognizer.transcribe(speech)
    score = coverage(text, recognized)
    if not recognized.strip() or (score is not None and score < .75):
        raise SpeechQualityError(f'合成内容不完整，文字覆盖率={score}')
