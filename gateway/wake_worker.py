"""Offline microphone owner: one-thread int8 KWS, bounded VAD and wake recording.

stdout is a JSON-lines protocol; diagnostic output belongs on stderr.
"""
import collections
import json
import io
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
import wave

import numpy as np
from gateway.speech_activity import SpeechActivity
from gateway.speaker_input import SpeakerInput, InputRejected

RATE = 16000
BLOCK = 1280  # 80 ms, no busy polling


def make_spotter(root, config):
    import sherpa_onnx
    model = root / config['model_dir']
    suffix = 'epoch-13-avg-2-chunk-8-left-64'
    return sherpa_onnx.KeywordSpotter(
        tokens=str(model / 'tokens.txt'),
        encoder=str(model / f'encoder-{suffix}.int8.onnx'),
        decoder=str(model / f'decoder-{suffix}.onnx'),
        joiner=str(model / f'joiner-{suffix}.int8.onnx'),
        keywords_file=str(root / config['keywords_file']),
        num_threads=config.get('num_threads', 1), max_active_paths=2,
        num_trailing_blanks=1, provider='cpu')


class Listener:
    def __init__(self, root, config, emit, speech_detector=None):
        self.root, self.config, self.emit = root, config, emit
        self.spotter = make_spotter(root, config)
        self.stream = self.spotter.create_stream()
        self.speech_detector = speech_detector if speech_detector is not None else SpeechActivity()
        self.mode = 'idle'
        self.enabled = config.get('enabled', True)
        self.suppressed = False
        self.care_id = ''
        self.utterance_care_id = ''
        self.clock = 0.0
        self.last_voice = -100.0
        self.last_hit = -100.0
        self.wait_until = 0.0
        self.started = 0.0
        self.speech_started = False
        self.speech_detector.reset()
        self.recording = []
        self.pre = collections.deque(maxlen=3)
        self.kws_active = False
        self.last_level = 0.0
        self.speaker_input = SpeakerInput(root)
        self.keyword_audio = collections.deque(maxlen=50)

    def reset(self, reason=''):
        self.mode = 'idle'
        self.recording.clear()
        self.pre.clear()
        self.speech_started = False
        self.speech_detector.reset()
        self.spotter.reset_stream(self.stream)
        self.kws_active = False
        self.emit({'type': 'state', 'state': 'idle', 'reason': reason})

    def control(self, data):
        if data.get('manual_listen') and self.enabled and not self.suppressed and self.mode == 'idle':
            self.mode = 'listening'
            self.utterance_care_id = self.care_id
            self.wait_until = self.clock + .45
            self.started = self.wait_until
            self.speech_started = False
            self.speech_detector.reset()
            self.recording.clear()
            self.pre.clear()
            self.emit({'type': 'wake', 'keyword': self.config['keyword'], 'state': 'listening'})
        if data.get('finish_listen'):
            self.finish_listening()
        if data.get('cancel_listen'):
            self.reset('manual_cancel')
        if data.get('resume'):
            self.reset()
        old_enabled, old_suppressed = self.enabled, self.suppressed
        self.enabled = data.get('enabled', self.enabled)
        self.suppressed = data.get('suppress', self.suppressed)
        self.care_id = data.get('care_event_id', self.care_id)
        if (not self.enabled and old_enabled) or (self.suppressed and not old_suppressed):
            # Speaker output and manual recordings must not wake or acknowledge themselves.
            if self.mode != 'processing':
                self.reset('paused')

    def finish_listening(self, reason="manual_finish"):
        # Closing a capture window commits exactly its buffered samples once.
        if self.mode != 'listening':
            return
        if not self.recording or sum(map(len, self.recording)) < RATE * .25:
            self.reset('empty_recording')
            return
        folder = self.root/'artifacts/wake-input'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (uuid.uuid4().hex + '.wav')
        pcm = np.clip(np.concatenate(self.recording), -1, 1)
        with wave.open(str(path), 'wb') as out:
            out.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            out.writeframes((pcm*32767).astype('<i2').tobytes())
        self.mode = 'processing'
        self.recording.clear()
        self.pre.clear()
        self.emit({'type': 'state', 'state': 'thinking', 'reason': reason})
        self.emit({'type': 'audio', 'path': str(path), 'care_event_id': self.utterance_care_id})

    def feed(self, samples):
        self.clock += len(samples) / RATE
        now = self.clock
        if not self.enabled or self.suppressed or self.mode == 'processing':
            return
        self.keyword_audio.append(samples.copy())
        rms = float(np.sqrt(np.mean(samples * samples)))
        voiced = rms >= self.config['speech_rms']
        if now - self.last_level >= .16:
            self.emit({'type': 'level', 'level': min(1.0, rms * 16)})
            self.last_level = now
        if self.mode == 'listening':
            if now < self.wait_until:
                return  # clear the local chime before opening the speech window
            voiced = self.speech_detector(samples)
            if not self.speech_started:
                self.pre.append(samples.copy())
                if voiced:
                    self.speech_started = True
                    self.recording.extend(self.pre)
                    self.pre.clear()
                    self.last_voice = now
                elif now - self.started >= self.config['silence_timeout']:
                    self.reset('silence_timeout')
                    return
            else:
                self.recording.append(samples.copy())
                if voiced:
                    self.last_voice = now
                if now-self.last_voice >= self.config['speech_end_silence'] or sum(map(len, self.recording)) >= RATE*self.config['max_speech_seconds']:
                    reason = "max_duration" if sum(map(len, self.recording)) >= RATE*self.config["max_speech_seconds"] else "speech_finished"
                    self.finish_listening(reason)
            return
        # Energy gate keeps a silent room cheap; include pre-roll and trailing
        # blanks, so the gate cannot cut the initial consonant or keyword endpoint.
        if voiced:
            if not self.kws_active:
                self.utterance_care_id = self.care_id
                for previous in self.pre:
                    self.stream.accept_waveform(RATE, np.clip(previous*self.config.get("kws_input_gain",2),-1,1))
                self.pre.clear()
                self.kws_active = True
            self.last_voice = now
        if not self.kws_active:
            self.pre.append(samples.copy())
            return
        self.stream.accept_waveform(RATE, np.clip(samples*self.config.get("kws_input_gain",2),-1,1))
        while self.spotter.is_ready(self.stream):
            self.spotter.decode_stream(self.stream)
            hit = self.spotter.get_result(self.stream)
            if hit and now-self.last_hit > 1.5:
                self.last_hit = now
                self.spotter.reset_stream(self.stream)
                if hit == self.config['keyword']:
                    self.mode = 'listening'
                    self.wait_until = now + .45
                    self.started = self.wait_until
                    self.speech_started = False
                    self.speech_detector.reset()
                    self.recording.clear()
                    self.pre.clear()
                    self.emit({'type': 'wake', 'keyword': hit, 'state': 'listening'})
                else:
                    # Emergency words remain accessible. Acknowledging a medicine
                    # reminder must be verified too, or background speech could clear it.
                    if hit == '知道了' and self.speaker_input.status()['enabled']:
                        data = io.BytesIO()
                        with wave.open(data, 'wb') as out:
                            out.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
                            out.writeframes((np.clip(np.concatenate(self.keyword_audio), -1, 1)*32767).astype('<i2').tobytes())
                        try:
                            self.speaker_input.prepare(data.getvalue())
                        except InputRejected as exc:
                            self.emit({'type': 'state', 'state': 'error', 'error': str(exc)})
                            break
                    self.emit({'type': 'command', 'text': hit, 'care_event_id': self.utterance_care_id})
                break
        if self.mode == 'idle' and now-self.last_voice > .9:
            self.spotter.reset_stream(self.stream)
            self.kws_active = False


def main():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root/'config/wake.json').read_text())
    def emit(data):
        print(json.dumps(data, ensure_ascii=False), flush=True)
    controls = queue.Queue()
    def read_controls():
        for line in sys.stdin:
            try:
                controls.put(json.loads(line))
            except ValueError:
                pass
        controls.put({'shutdown': True})  # main loop closes the capture child
    threading.Thread(target=read_controls, daemon=True).start()
    listener = Listener(root, config, emit)
    command = ['parec', '--device='+config['pulse_source'], '--format=s16le',
               '--rate=16000', '--channels=1', '--raw', '--latency-msec=80',
               '--client-name=DigitalHumanWake']
    capture = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stderr)
    emit({'type': 'state', 'state': 'idle', 'keyword': config['keyword'], 'ready': True})
    try:
        while True:
            while not controls.empty():
                control=controls.get_nowait()
                if control.get("shutdown"):
                    return
                listener.control(control)
            raw = capture.stdout.read(BLOCK * 2)
            if len(raw) != BLOCK * 2:
                raise RuntimeError('本地麦克风输入中断，请检查默认录音设备')
            listener.feed(np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768)
    finally:
        capture.terminate()
        capture.wait(timeout=3)

if __name__ == '__main__':
    main()
