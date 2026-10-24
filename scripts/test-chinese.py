"""Check simplified ASR, complete/streamed answers, and local pinyin."""
import asyncio
import importlib.util
import json
import io
from starlette.datastructures import UploadFile
from pathlib import Path
import tempfile
from unittest.mock import patch
import httpx
from gateway import app as module
from gateway.chinese import simplified,pinyin_engine

async def main():
 assert simplified('爺爺，今天天氣很好，請說話。')=='爷爷，今天天气很好，请说话。'
 for spelling,word in [('nihao','你好'),('yeye','爷爷'),('nainai','奶奶'),('jintiantianqihenhao','今天天气很好')]:
  assert pinyin_engine().candidates(spelling)[0]==word
 assert not pinyin_engine().candidates('bad!')
 client=httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test')
 async with client:
  assert (await client.post('/api/input/simplified',json={'text':'請輸入中文'})).json()['text']=='请输入中文'
  assert (await client.get('/api/input/pinyin',params={'text':'nihao'})).json()['candidates'][0]=='你好'
  assert not (await client.get('/api/input/pinyin',params={'text':'x'*65})).json()['candidates']
 spoken=[]
 async def synth(text,**kw):spoken.append(text);return b'audio'
 async def upstream(*args):return {'choices':[{'message':{'content':'爺爺，今天天氣很好，請放心。'}}]}
 with tempfile.TemporaryDirectory() as folder,patch.object(module,'AUDIO',Path(folder)),patch.object(module,'synthesize',synth),patch.object(module,'upstream_json',upstream),patch.object(module,'salutation_for',lambda root:'您'):
  req=module.ChatRequest(text='請用繁體回答',history=[module.Message(role='user',content='今天天氣')])
  assert req.text=='请用繁体回答' and req.history[0].content=='今天天气'
  result=await module.chat(req)
  assert result['text']=='您，今天天气很好，请放心。' and spoken==[result['text']]
  fixture=type('Fixture',(),{})();exec(Path('scripts/test-chat-repetition.py').read_text().split('asyncio.run(run())')[0],fixture.__dict__)
  traditional='爺爺，今天天氣很好，我們可以一起聊聊天。請您慢慢說，我會認真聽您說話。'
  response=fixture.Response(list(traditional));module.app.state.client=fixture.Client(response)
  job={'text':'','clips':[],'done':False,'text_done':False,'error':'','truncated':False};spoken.clear()
  await module.run_chat_job(job,req,{})
  assert job['text']==module.respectful_reply(simplified(traditional),'您') and ''.join(spoken)==job['text'],job
 # Exercise real ASR with existing recorded Chinese fixture.
 with patch.object(module,'handle_care_text',lambda *a:{'care_command':''}):
  audio=Path('artifacts/validation/offline-wake/wake-command.wav').read_bytes()
  result=await module.asr(UploadFile(filename='test.wav',file=io.BytesIO(audio)),care_commands=False)
  assert result['text'] and result['text']==simplified(result['text']),result
  print('ASR:',result['text'])
 print('PASS: simplified ASR/input/answers/stream/TTS text and local pinyin')

asyncio.run(main())
