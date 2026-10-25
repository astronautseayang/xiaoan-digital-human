"""Measured speech loudness normalization and clarity, including short utterances."""
import io
import json
import math
import os
import subprocess
import wave
from gateway.audio_level import normalize_speech
from gateway.voice_denoise import denoise_speech

CLARITY_FILTER = ('equalizer=f=2450:t=o:w=1.4:g=2.5,'
                  'acompressor=threshold=0.125:ratio=3:attack=15:release=180:makeup=1.4')


def process_senior_speech(data, *, denoise=False):
    if denoise:
        data = denoise_speech(data)
    data = normalize_speech(data)
    ffmpeg = os.environ.get('HUMAN_FFMPEG', 'ffmpeg')
    # Measure after EQ and compression. A single dynamic loudnorm pass can
    # attenuate very short phrases, so apply the measured correction explicitly.
    measured = subprocess.run([
        ffmpeg, '-hide_banner', '-nostats', '-i', 'pipe:0', '-af',
        CLARITY_FILTER + ',loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json',
        '-f', 'null', '-'], input=data, capture_output=True, timeout=30, check=True)
    diagnostic = measured.stderr.decode('utf-8', errors='replace')
    stats = json.loads(diagnostic[diagnostic.rfind('{'):diagnostic.rfind('}')+1])
    integrated, peak = float(stats['input_i']), float(stats['input_tp'])
    gain = min(-16-integrated, -1.5-peak, 30) if math.isfinite(integrated) and math.isfinite(peak) else 0
    result = subprocess.run([
        ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', 'pipe:0', '-af',
        CLARITY_FILTER + f',volume={gain:.6f}dB,alimiter=limit=0.891:level=false,apad=pad_dur=0.22',
        '-ar', '32000', '-ac', '1', '-c:a', 'pcm_s16le', '-f', 'wav', 'pipe:1'],
        input=data, capture_output=True, timeout=30, check=True)
    # ffmpeg's pipe WAV uses an unknown-length header; rewrite it for Unity.
    with wave.open(io.BytesIO(result.stdout), 'rb') as source:
        pcm = source.readframes(source.getnframes())
        params = source.getparams()
    target = io.BytesIO()
    with wave.open(target, 'wb') as output:
        output.setparams(params._replace(nframes=0))
        output.writeframes(pcm)
    return target.getvalue()
