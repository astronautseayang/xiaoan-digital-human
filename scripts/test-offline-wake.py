"""Real offline KWS fixture tests and bounded recording/state regressions."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave

import numpy as np
from gateway.wake_worker import Listener, RATE, BLOCK

ROOT=Path(__file__).resolve().parents[1]

class EnergyDetector:
    def reset(self):
        pass
    def __call__(self, samples):
        return float(np.sqrt(np.mean(samples*samples))) >= .004


class WakeTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'config/wake.json').read_text())
        self.temp=tempfile.TemporaryDirectory()
        self.events=[]
        self.listener=Listener(ROOT,self.config,self.events.append)
        self.listener.root=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def feed(self,data):
        for offset in range(0,len(data),BLOCK):
            self.listener.feed(data[offset:offset+BLOCK])

    def silence(self,seconds):
        self.feed(np.zeros(int(RATE*seconds),dtype=np.float32))

    def fixture(self,name):
        path=ROOT/f'artifacts/validation/offline-wake/{name}.wav'
        if not path.exists():self.skipTest('Run local TTS fixture generation first')
        result=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','f32le','-ar','16000','-ac','1','pipe:1'],capture_output=True,check=True)
        return np.frombuffer(result.stdout,dtype='<f4')

    def test_real_chinese_keyword_and_question_recording(self):
        self.silence(1)
        self.feed(self.fixture('wake-command'))
        self.silence(2)
        self.assertTrue(any(e['type']=='wake' and e['keyword']=='小安' for e in self.events))
        event=next(e for e in self.events if e['type']=='audio')
        with wave.open(event['path']) as f:
            self.assertEqual(f.getframerate(),RATE)
            self.assertGreater(f.getnframes(),RATE*.3)

    def test_unrelated_speech_does_not_wake(self):
        self.feed(self.fixture('negative'));self.silence(2)
        self.assertFalse(any(e['type'] in ('wake','command') for e in self.events))

    def test_five_second_silence_returns_to_idle(self):
        self.listener.control({'manual_listen':True})
        self.silence(5.4)
        self.assertEqual(self.listener.mode,'listening')
        self.silence(.16)
        self.assertEqual(self.listener.mode,'idle')
        self.assertEqual(self.events[-1]['reason'],'silence_timeout')
        self.assertFalse(any(e['type']=='audio' for e in self.events))

    def test_playback_and_disabled_listener_ignore_wake(self):
        for control in ({'suppress':True},{'suppress':False,'enabled':False}):
            self.listener.control(control)
            self.feed(self.fixture('wake-command'));self.silence(1)
        self.assertFalse(any(e['type']=='wake' for e in self.events))

    def test_manual_button_honors_disabled_state(self):
        self.listener.control({'enabled':False})
        self.listener.control({'manual_listen':True})
        self.assertEqual(self.listener.mode,'idle')

    def test_manual_cancel_discards_recording_and_allows_next_wake(self):
        self.listener.speech_detector=EnergyDetector()
        self.listener.control({'manual_listen':True})
        self.silence(.56)
        self.feed(np.ones(BLOCK*4,dtype=np.float32)*.08)
        self.assertTrue(self.listener.recording)
        self.listener.control({'cancel_listen':True})
        self.assertEqual(self.listener.mode,'idle')
        self.assertEqual(self.events[-1]['reason'],'manual_cancel')
        self.silence(2)
        self.assertFalse(any(e['type']=='audio' for e in self.events))
        self.listener.control({'manual_listen':True})
        self.assertEqual(self.listener.mode,'listening')

    def test_finish_submits_only_current_window_once(self):
        self.listener.speech_detector=EnergyDetector()
        self.feed(np.ones(BLOCK*3,dtype=np.float32)*.02)
        self.listener.control({'manual_listen':True})
        self.silence(.56)
        self.feed(np.ones(BLOCK*5,dtype=np.float32)*.08)
        expected=sum(map(len,self.listener.recording))
        self.listener.control({'finish_listen':True})
        self.assertEqual(self.listener.mode,'processing')
        self.feed(np.ones(BLOCK*8,dtype=np.float32)*.2)
        self.listener.control({'finish_listen':True})
        audio=[e for e in self.events if e['type']=='audio']
        self.assertEqual(len(audio),1)
        with wave.open(audio[0]['path']) as f:
            self.assertEqual(f.getnframes(),expected)
            pcm=np.frombuffer(f.readframes(expected),dtype='<i2')
            self.assertLessEqual(pcm.max(),int(.081*32767))
        self.listener.control({'resume':True})
        self.feed(np.ones(BLOCK*3,dtype=np.float32)*.02)
        self.assertEqual(len([e for e in self.events if e['type']=='audio']),1)

    def test_finish_empty_window_returns_idle(self):
        self.listener.control({'manual_listen':True})
        self.silence(.56)
        self.listener.control({'finish_listen':True})
        self.assertEqual(self.listener.mode,'idle')
        self.assertEqual(self.events[-1]['reason'],'empty_recording')
        self.assertFalse(any(e['type']=='audio' for e in self.events))

    def test_maximum_speech_is_bounded(self):
        self.listener.speech_detector=EnergyDetector()
        self.listener.control({'manual_listen':True})
        self.silence(.56)
        data=np.sin(np.arange(RATE*16,dtype=np.float32)*.08)*.08
        self.feed(data)
        self.assertEqual(self.listener.mode,'processing')
        event=next(e for e in self.events if e['type']=='audio')
        with wave.open(event['path']) as f:self.assertLessEqual(f.getnframes(),RATE*15+BLOCK)

    def test_noise_alone_does_not_submit_a_question(self):
        self.listener.control({'manual_listen':True})
        self.silence(.56)
        noise=np.random.default_rng(42).normal(0,.025,RATE*6).astype(np.float32)
        self.feed(noise)
        self.assertEqual(self.listener.mode,'idle')
        self.assertFalse(any(e['type']=='audio' for e in self.events))

    def test_older_speaker_pause_is_preserved_and_auto_submitted(self):
        self.listener.control({'manual_listen':True})
        self.silence(.56)
        self.feed(self.fixture('negative'))
        self.silence(.85)
        self.assertEqual(self.listener.mode,'listening')
        self.feed(self.fixture('negative'))
        self.silence(2)
        self.assertEqual(self.listener.mode,'processing')
        audio=[e for e in self.events if e['type']=='audio']
        self.assertEqual(len(audio),1)
        self.assertTrue(any(e.get('reason')=='speech_finished' for e in self.events))
        with wave.open(audio[0]['path']) as f:
            self.assertGreater(f.getnframes(),len(self.fixture('negative'))*1.5)

if __name__=='__main__':unittest.main()
