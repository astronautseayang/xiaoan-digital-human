#!/usr/bin/env python3
"""Exercise real LLM/TTS streaming jobs and transactional reference enrollment."""
import io,json,time,wave
from pathlib import Path
import httpx
ROOT=Path('/home/yyy/digital-human')
out=ROOT/'artifacts/validation/voice-latency';out.mkdir(parents=True,exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:9881',timeout=240,trust_env=False)
def checked(r):
 r.raise_for_status();return r.json()
results=[]
for prompt in ['你好，请用一句话介绍自己。','我今天工作很累，能给我一些放松身心的建议吗？','请介绍如何培养每天阅读的习惯。']:
 start=time.monotonic();old=checked(c.post('/api/chat',json={'text':prompt}));old_time=time.monotonic()-start
 start=time.monotonic();job=checked(c.post('/api/chat/jobs',json={'text':prompt}));first_text=first_audio=None
 while True:
  j=checked(c.get('/api/chat/jobs/'+job['id']));elapsed=time.monotonic()-start
  if j['text'] and first_text is None:first_text=elapsed
  if j['clips'] and first_audio is None:first_audio=elapsed
  if j['done']:break
  time.sleep(.1)
 assert not j['error'] and j['clips'],j
 for clip in j['clips']:
  r=c.get(clip['audio_url']);r.raise_for_status()
  with wave.open(io.BytesIO(r.content)) as w:assert w.getnframes()>0
 results.append({'prompt':prompt,'old_complete_seconds':old_time,'new_first_text_seconds':first_text,'new_first_audio_seconds':first_audio,'new_complete_seconds':elapsed,'job':j})
 (out/'latency.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 print(prompt,old_time,first_text,first_audio,elapsed,flush=True)
# Bad input must leave a known-good voice untouched.
before=(ROOT/'config/voice.json').read_bytes()
r=c.post('/api/voice/enroll',files={'file':('bad.wav',b'not audio','audio/wav')});assert r.status_code==422,r.text
assert (ROOT/'config/voice.json').read_bytes()==before
# Use the existing reference to exercise enrollment without claiming physical mic capture.
reference=json.loads(before)
r=checked(c.post('/api/voice/enroll',files={'file':('reference.wav',Path(reference['ref_audio_path']).read_bytes(),'audio/wav')}))
assert r['transcript'] and r['audio_url']
new_voice=checked(c.get('/api/voice'));assert new_voice['text']=='我的录入音色'
speech=c.post('/api/tts',json={'text':'音色已切换，这是一次真实的语音合成测试。'});speech.raise_for_status()
(out/'enrolled-response.wav').write_bytes(speech.content)
(out/'enrollment.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
checked(c.post('/api/voice/reset'))
assert (ROOT/'config/voice.json').read_bytes()==(ROOT/'config/voice-default.json').read_bytes()
print('Enrollment, ASR transcript, preview, subsequent TTS, invalid-file rollback and default reset passed')
