"""Lightweight, fixed-gain speech leveling; no resampling or time processing."""
import audioop
import io
import math
import wave


def normalize_speech(data: bytes, *, reject_quiet: bool = False) -> bytes:
    """Level active speech to -20 dBFS RMS, with -1 dBFS peak headroom.

    Ignore pauses using 50 ms windows within 20 dB of the strongest window.
    One gain per clip preserves natural dynamics and never pumps up each pause.
    Limit boost to 40 dB and leave effectively silent output alone. This is
    level correction, not denoising or a guarantee that input contains speech.
    """
    with wave.open(io.BytesIO(data), 'rb') as source:
        params = source.getparams()
        if params.sampwidth != 2 or params.comptype != 'NONE':
            raise ValueError('音量处理需要 PCM16 WAV')
        pcm = source.readframes(params.nframes)
    if not pcm or len(pcm) != params.nframes * params.nchannels * 2:
        raise ValueError('Empty or truncated WAV')
    window_bytes = max(1, params.framerate // 20) * params.nchannels * 2
    levels = [(audioop.rms(pcm[i:i + window_bytes], 2),
               len(pcm[i:i + window_bytes]) // 2)
              for i in range(0, len(pcm), window_bytes)]
    strongest = max(level for level, _ in levels)
    # Below about -66 dBFS there is too little signal to boost reliably.
    if strongest < 16:
        if reject_quiet:
            raise ValueError('未录到足够清晰的声音，请检查麦克风或靠近后重新录制')
        return data
    active = [(level, count) for level, count in levels
              if level >= max(16, strongest * 0.1)]
    rms = math.sqrt(sum(level * level * count for level, count in active)
                    / sum(count for _, count in active))
    peak = audioop.max(pcm, 2)
    gain = min(32768 * 0.1 / rms, 32767 * 10 ** (-1 / 20) / peak, 100.0)
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setparams(params)
        target.writeframes(audioop.mul(pcm, 2, gain))
    return output.getvalue()
