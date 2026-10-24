import httpx,time,json
from pathlib import Path
c=httpx.Client(base_url='http://127.0.0.1:9881',timeout=180,trust_env=False)
r=c.post('/api/chat/jobs',json={'text':'请写一段150字左右的中文短文，介绍春天公园的景色，只输出正文。'});r.raise_for_status();key=r.json()['id'];start=time.monotonic()
while time.monotonic()-start<200:
 r=c.get('/api/chat/jobs/'+key);r.raise_for_status();j=r.json()
 if j['text_done']:
  print('text complete',len(j['text']),j['finish_reason'],j['truncated'],flush=True)
  break
 time.sleep(.2)
assert j['text_done'] and len(j['text'])>80,j
while not j['done'] and time.monotonic()-start<200:
 time.sleep(.5);j=c.get('/api/chat/jobs/'+key).json()
assert j['done'] and not j['error'],j
assert bool(j['truncated'])==(j['finish_reason']=='length')
assert j['clips']
c.get(j['clips'][0]['audio_url']).raise_for_status()
out=Path('artifacts/validation/text-default-voice');out.mkdir(parents=True,exist_ok=True)
(out/'long-answer.json').write_text(json.dumps(j,ensure_ascii=False,indent=2))
r=c.post('/api/tts',json={'text':'你好，我是你的数字人助手，很高兴与你聊天。'});r.raise_for_status();(out/'default-female.wav').write_bytes(r.content)
print('long answer and default reference synthesis passed',j['elapsed_seconds'],flush=True)
