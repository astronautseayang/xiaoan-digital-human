"""Real local speaker/VAD tests and Chinese streaming output regression."""
import asyncio
import io
from pathlib import Path
import tempfile
import wave
from unittest.mock import patch
import numpy as np
from gateway.speaker_input import SpeakerInput, InputRejected, clean_audio, speech_only
from gateway.output_language import chinese_reply, has_english
from gateway import app as module

ROOT=Path(__file__).resolve().parents[1]
def wav(audio):
    b=io.BytesIO()
    with wave.open(b,'wb') as w:
        w.setparams((1,2,16000,0,'NONE','NONE'));w.writeframes((np.clip(audio,-1,1)*32767).astype('<i2').tobytes())
    return b.getvalue()
def rejected(call):
    try:call()
    except InputRejected:return
    raise AssertionError('Expected rejected input')

async def main():
    fixture={};exec((ROOT/'scripts/test-chat-repetition.py').read_text().split('asyncio.run(run())')[0],fixture)
    async def rewrite(text):return '爷爷，请放心，我会认真听您说话。'
    for text in ['好的，OK，我知道了。','Hello, how are you?','我觉得OK可以，今天12点52分。']:
        assert not has_english(await chinese_reply(text,rewrite))
    async def invalid(text):return 'English remains'
    assert not has_english(await chinese_reply('unexpected English',invalid))
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'models/speaker').mkdir(parents=True)
        (root/'models/speaker/campplus.onnx').symlink_to(ROOT/'models/speaker/campplus.onnx')
        speaker=SpeakerInput(root)
        rng=np.random.default_rng(1)
        for a in [np.zeros(96000),rng.normal(0,.05,96000),.1*np.sin(np.arange(96000)*2*np.pi*100/16000)]:
            rejected(lambda:speaker.prepare(wav(a)))
        rejected(lambda:speaker.enroll(b'invalid'))
        a=speech_only(clean_audio((ROOT/'artifacts/validation/offline-wake/wake-command.wav').read_bytes()))
        b=speech_only(clean_audio((ROOT/'artifacts/validation/offline-wake/negative.wav').read_bytes()))
        other=speech_only(clean_audio((ROOT/'assets/reference/me.wav').read_bytes()))
        speaker.enroll(wav(np.tile(a,3)))
        assert speaker.status()['enabled'] and 'embedding' not in speaker.status()
        assert len(speaker.prepare(wav(b)))>0
        assert len(speaker.prepare(wav(b+rng.normal(0,.003,len(b)))))>0
        rejected(lambda:speaker.prepare(wav(other)))
        rejected(lambda:speaker.prepare(wav(np.concatenate([a,other]))))
        before=speaker.path.read_bytes()
        rejected(lambda:speaker.enroll(wav(np.zeros(96000))))
        assert before==speaker.path.read_bytes()
        assert speaker.path.stat().st_mode & 0o777 == 0o600
        speaker.enable(False);assert len(speaker.prepare(wav(other)))>0
        for text in ['爷爷，Hello, how are you? '+ '请您放心，我们慢慢聊。今天可以谈谈您的兴趣，也可以聊聊家人。您喜欢散步还是听音乐？我会认真听您说。','EnglishWordWithoutPunctuation'*3,'好的，OK，今天12点52分。']:
            response=fixture['Response'](list(text));module.app.state.client=fixture['Client'](response)
            spoken=[]
            async def synth(text,**kw):spoken.append(text);return b'audio'
            async def upstream(*a):return {'choices':[{'message':{'content':await rewrite('')}}]}
            with patch.object(module,'AUDIO',root),patch.object(module,'synthesize',synth),patch.object(module,'upstream_json',upstream):
                job={'text':'','clips':[],'done':False,'text_done':False,'error':'','truncated':False}
                await module.run_chat_job(job,module.ChatRequest(text='聊聊天'),{})
                assert not job['error'],job
                assert job['done'] and not has_english(job['text']) and spoken
                assert all(not has_english(t) for t in spoken)
    print('PASS: noise rejection, enrolled speaker, noisy matching voice, different/mixed voices, profile persistence and Chinese stream/TTS')

asyncio.run(main())
