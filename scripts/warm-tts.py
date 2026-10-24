#!/usr/bin/env python3
"""Warm the real speech path after the supervised TTS process starts."""
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import wave

ROOT = Path('/home/yyy/digital-human')
client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
started = time.monotonic()
try:
    for attempt in range(120):
        try:
            with client.open('http://127.0.0.1:9880/openapi.json', timeout=1):
                break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(.5)
    else:
        raise RuntimeError('TTS did not become available within 60 seconds')
    voice = json.loads((ROOT / 'config/voice.json').read_text())
    payload = {
        **{key: voice[key] for key in ('ref_audio_path', 'prompt_lang', 'prompt_text')},
        'text': '你好，很高兴和你交流。', 'text_lang': 'zh',
        'media_type': 'wav', 'streaming_mode': False,
        'text_split_method': 'cut5', 'batch_size': 1,
        'parallel_infer': False, 'use_cuda_graph': False,
    }
    request = urllib.request.Request('http://127.0.0.1:9880/tts',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with client.open(request, timeout=90) as response:
        data = response.read()
    with wave.open(io.BytesIO(data)) as audio:
        assert audio.getnframes() > 0
    report = {'passed': True, 'seconds_including_startup': round(time.monotonic() - started, 3)}
except Exception as exc:
    report = {'passed': False, 'error': str(exc)}
path = ROOT / 'artifacts/validation/voice-latency/tts-warmup.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(report, indent=2) + '\n')
print('TTS startup warmup: ' + json.dumps(report), flush=True)
