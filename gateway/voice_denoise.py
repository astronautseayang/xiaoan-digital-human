"""Conservative filtering for enrolled voice references and generated speech."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import uuid
import wave

# Filter before loudness boosts. Avoid a hard gate that cuts quiet syllables.
NOISE_FILTER = 'highpass=f=70,lowpass=f=7600,afftdn=nr=10:nf=-45:tn=1'
REFERENCE_PROFILE = 'outer-silence-v1-pad150'


def _complete_wav(data):
    with wave.open(io.BytesIO(data), 'rb') as source:
        params = source.getparams()
        pcm = source.readframes(params.nframes)
    if not pcm or len(pcm) != params.nframes * params.nchannels * params.sampwidth:
        raise ValueError('录音为空或音频数据不完整，请重新录制。')
    return params, pcm


def denoise_speech(data):
    params, _ = _complete_wav(data)
    frames = params.nframes
    # afftdn retains a short analysis window. Restore the original length so
    # references, subtitles and quiet final syllables keep their timing.
    filters = NOISE_FILTER + f',apad=whole_len={frames},atrim=end_sample={frames}'
    result = subprocess.run([
        os.environ.get('HUMAN_FFMPEG', 'ffmpeg'), '-hide_banner', '-loglevel', 'error',
        '-i', 'pipe:0', '-af', filters, '-ac', '1', '-c:a', 'pcm_s16le',
        '-f', 'wav', 'pipe:1'], input=data, capture_output=True, timeout=20, check=True)
    # Write a finite WAV header, also understood by downstream wave readers.
    with wave.open(io.BytesIO(result.stdout), 'rb') as source:
        params = source.getparams()
        pcm = source.readframes(source.getnframes())
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setparams(params._replace(nframes=0))
        target.writeframes(pcm)
    return output.getvalue()


def trim_reference(data):
    """Remove only outer silence, retaining 150ms pads and all internal pauses.

    GPT-SoVITS expects 3–10 seconds; keep the full reference if its detected
    speech region would be too short. Output quality remains checked separately.
    """
    import numpy as np
    from scipy.signal import resample_poly
    from faster_whisper.vad import get_speech_timestamps, VadOptions
    import math
    params, pcm = _complete_wav(data)
    if params.sampwidth != 2 or params.nchannels != 1:
        raise ValueError('参考录音需要单声道PCM16')
    audio = np.frombuffer(pcm, '<i2').astype(np.float32) / 32768
    common = math.gcd(params.framerate, 16000)
    if params.framerate != 16000:
        audio = resample_poly(audio, 16000 // common, params.framerate // common).astype(np.float32)
    spans = get_speech_timestamps(audio, VadOptions(
        threshold=.6, min_speech_duration_ms=250, min_silence_duration_ms=350,
        speech_pad_ms=150))
    if not spans:
        return data
    start = max(0, spans[0]['start'] * params.framerate // 16000)
    end = min(params.nframes, math.ceil(spans[-1]['end'] * params.framerate / 16000))
    if not 3 <= (end - start) / params.framerate <= 10:
        return data
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setparams(params._replace(nframes=0))
        target.writeframes(pcm[start * 2:end * 2])
    return output.getvalue()


def valid_cached_reference(path):
    try:
        with wave.open(str(path), 'rb') as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getnframes() <= 0:
                return False
            # A valid header alone does not detect an interrupted/truncated
            # write. Require every declared PCM frame to be present.
            return len(source.readframes(source.getnframes())) == source.getnframes() * 2
    except (OSError, wave.Error, EOFError):
        return False


def cleaned_reference(path, cache):
    original = Path(path).read_bytes()
    _complete_wav(original)
    key = hashlib.sha256((NOISE_FILTER + REFERENCE_PROFILE).encode() + original).hexdigest()
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f'{key}.wav'
    if not valid_cached_reference(target):
        cleaned = trim_reference(denoise_speech(original))
        temporary = cache / f'{key}.{uuid.uuid4().hex}.tmp'
        try:
            temporary.write_bytes(cleaned)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return str(target)
