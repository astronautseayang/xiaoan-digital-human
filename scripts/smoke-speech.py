"""Real HTTP checks: direct TTS, gateway TTS, LLM+audio, ASR round trip."""
import io
import json
from pathlib import Path
import time
import wave
import numpy as np
import httpx
root=Path('/home/yyy/digital-human')
voice=json.loads((root/'config/voice.json').read_text())
out=root/'artifacts/validation';out.mkdir(parents=True,exist_ok=True)
report={}
def validate_wav(name,data):
 with wave.open(io.BytesIO(data),'rb') as wav:
  assert wav.getnframes()>0
  duration=wav.getnframes()/wav.getframerate()
  assert .1<duration<120,(name,duration)
  samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768
  rms=float(np.sqrt(np.mean(samples*samples)))
  assert rms>0.001,(name,'near-silent',rms)
  report[name]={'duration_seconds':duration,'sample_rate':wav.getframerate(),'bytes':len(data),'rms':rms}
 (out/f'{name}.wav').write_bytes(data)
 return data
with httpx.Client(timeout=300,trust_env=False) as client:
 start=time.monotonic()
 r=client.post('http://127.0.0.1:9880/tts',json={**voice,'text':'你好，欢迎使用本地数字人。','text_lang':'zh','media_type':'wav','streaming_mode':False,'parallel_infer':False,'use_cuda_graph':False})

 if r.is_error: print('HTTP ERROR',r.status_code,r.text,flush=True)
 r.raise_for_status();validate_wav('tts-direct',r.content)
 r=client.post('http://127.0.0.1:9881/api/tts',json={'text':'今天天气不错。','text_lang':'zh'})

 if r.is_error: print('HTTP ERROR',r.status_code,r.text,flush=True)
 r.raise_for_status();validate_wav('tts-gateway',r.content)
 r=client.post('http://127.0.0.1:9881/api/chat',json={'text':'请用一句话介绍你自己。'})
 r.raise_for_status();chat=r.json();assert chat['text'];report['chat_response']=chat
 r=client.get('http://127.0.0.1:9881'+chat['audio_url']);r.raise_for_status();data=validate_wav('chat',r.content)
 r=client.post('http://127.0.0.1:9881/api/asr',files={'file':('speech.wav',(out/'tts-direct.wav').read_bytes(),'audio/wav')})
 r.raise_for_status();report['asr']=r.json();assert any(word in report['asr']['text'] for word in ['你好','欢迎','歡迎','数字','數字']),report['asr']
 report['elapsed_seconds']=time.monotonic()-start
 report['ready']=client.get('http://127.0.0.1:9881/ready').json();assert report['ready']['ready']
(root/'logs/speech-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
