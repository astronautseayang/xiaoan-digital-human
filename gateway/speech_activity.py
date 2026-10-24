"""Streaming speech detection using the bundled local Silero V5 ONNX models."""
import numpy as np


class SpeechActivity:
    def __init__(self):
        from faster_whisper.vad import get_vad_model
        self.model = get_vad_model()
        self.reset()

    def reset(self):
        self.pending = np.empty(0, dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.active = False

    def __call__(self, samples):
        self.pending = np.concatenate((self.pending, samples))
        voiced = False
        while len(self.pending) >= 512:
            frame, self.pending = self.pending[:512], self.pending[512:]
            window = np.concatenate((self.context, frame.reshape(1, -1)), axis=1)
            encoded = self.model.encoder_session.run(None, {'input': window})[0]
            output, self.state = self.model.decoder_session.run(
                None, {'input': encoded.reshape(1, 128), 'state': self.state})
            self.context = frame[-64:].reshape(1, -1).copy()
            probability = float(output.reshape(-1)[0])
            self.active = probability >= (.35 if self.active else .5)
            voiced = voiced or self.active
        return voiced
