"""Local denoising, speech validation and an explicitly enrolled input speaker.

Speaker verification rejects a mixed/nonmatching recording; it does not separate
overlapping voices. Never learn identity from an arbitrary background utterance.
"""
import json
from pathlib import Path
import subprocess
import threading

import numpy as np


class InputRejected(ValueError):
    pass


def clean_audio(data):
    try:
        result = subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', 'pipe:0',
        '-af', 'highpass=f=90,lowpass=f=7400,afftdn=nr=10:nf=-45:tn=1',
        '-ar', '16000', '-ac', '1', '-t', '30', '-f', 'f32le', 'pipe:1'],
            input=data, capture_output=True, timeout=20, check=True)
    except (subprocess.SubprocessError, OSError) as exc:
        raise InputRejected('录音无法读取，请重新录制清晰语音。') from exc
    audio = np.frombuffer(result.stdout, dtype='<f4').copy()
    if not len(audio) or not np.isfinite(audio).all():
        raise InputRejected('没有听到清晰的人声，请靠近麦克风再说一次。')
    return audio


def speech_only(audio):
    from faster_whisper.vad import get_speech_timestamps, VadOptions
    spans = get_speech_timestamps(audio, VadOptions(
        threshold=.6, min_speech_duration_ms=250, min_silence_duration_ms=350,
        speech_pad_ms=100))
    speech = np.concatenate([audio[s['start']:s['end']] for s in spans]) if spans else np.empty(0, np.float32)
    if len(speech) < 16000 * .35:
        raise InputRejected('没有听到清晰的人声，请靠近麦克风再说一次。')
    return speech


class SpeakerInput:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'config/input-speaker.json'
        self.model_path = self.root / 'models/speaker/campplus.onnx'
        self.extractor = None
        self.lock = threading.RLock()

    def profile(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {'enabled': False, 'embedding': []}

    def status(self):
        with self.lock:
            p = self.profile()
            return {'available': self.model_path.is_file(), 'enrolled': bool(p['embedding']),
                    'enabled': bool(p['enabled']), 'text': '只接收已录入的声音' if p['enabled'] else '尚未开启声音识别限制'}

    def save(self, profile):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(profile, ensure_ascii=False))
        temporary.replace(self.path)
        self.path.chmod(0o600)

    def enable(self, enabled):
        with self.lock:
            p = self.profile()
            if enabled and (not p['embedding'] or not self.model_path.is_file()):
                raise InputRejected('请先录入您的识别声音，再开启只听我的声音。')
            p['enabled'] = enabled
            self.save(p)
            return self.status()

    def embedding(self, speech):
        if not self.model_path.is_file():
            raise InputRejected('声音识别模型尚未就绪，请稍后重试。')
        if self.extractor is None:
            import sherpa_onnx
            config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=str(self.model_path), num_threads=2, provider='cpu')
            self.extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        stream = self.extractor.create_stream()
        stream.accept_waveform(16000, speech)
        stream.input_finished()
        if not self.extractor.is_ready(stream):
            raise InputRejected('语音太短，请完整说一句话。')
        vector = np.asarray(self.extractor.compute(stream), dtype=np.float32)
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm < 1e-6:
            raise InputRejected('没有提取到清晰声音，请重新录入。')
        return vector / norm

    @staticmethod
    def windows(speech):
        # Check local windows as well as the full clip; a matching first speaker
        # must not authorize a second speaker's appended command.
        width, stride = 32000, 16000
        if len(speech) <= width:
            return [speech]
        starts = list(range(0, len(speech)-width+1, stride))
        if starts[-1] != len(speech)-width:
            starts.append(len(speech)-width)
        return [speech[s:s+width] for s in starts]

    def enroll(self, data):
        audio = clean_audio(data)
        if not 5 <= len(audio)/16000 <= 10.1:
            raise InputRejected('请单独录制五到十秒，期间不要让其他人说话。')
        speech = speech_only(audio)
        if len(speech) < 16000*3:
            raise InputRejected('清晰人声不足三秒，请在安静环境重新录入。')
        with self.lock:
            vector = self.embedding(speech)
            if any(float(self.embedding(w) @ vector) < .55 for w in self.windows(speech)):
                raise InputRejected('录音中的声音不一致，请您单独重新录入。')
            self.save({'enabled': True, 'embedding': vector.tolist(), 'threshold': .55, 'window_threshold': .45})
            return {**self.status(), 'text': '识别声音已录入，已开启只听我的声音。'}

    def prepare(self, data, *, verify=True):
        speech = speech_only(clean_audio(data))
        with self.lock:
            profile = self.profile()
            if verify and profile['enabled']:
                if len(speech) < 16000*.8:
                    raise InputRejected('语音太短，暂时不能确认是您的声音，请完整说一句。')
                reference = np.asarray(profile['embedding'], dtype=np.float32)
                scores = [float(self.embedding(w) @ reference) for w in self.windows(speech)]
                if float(self.embedding(speech) @ reference) < profile.get('threshold', .55) or min(scores) < profile.get('window_threshold', .45):
                    raise InputRejected('声音与录入不匹配，或有其他人说话，请您单独再说一次。')
        return speech
