"""Exercise upstream token exhaustion and TTS failure without a long live generation."""
import asyncio,json,tempfile
from pathlib import Path
from gateway import app as module
class Response:
 def __init__(self,reason):self.reason=reason
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
 def raise_for_status(self):pass
 async def aiter_lines(self):
  yield 'data: '+json.dumps({'choices':[], 'usage':{'completion_tokens':0}})
  for choice in [{'delta':{'content':'这是完整测试内容。'},'finish_reason':None},{'delta':{},'finish_reason':self.reason}]:
   yield 'data: '+json.dumps({'choices':[choice]})
  yield 'data:[DONE]'
  # The completion marker ends the job even if the HTTP peer keeps the
  # connection open; do not wait for a socket timeout after a valid answer.
  await asyncio.Event().wait()
class Client:
 def __init__(self,reason):self.reason=reason
 def stream(self,*args,**kwargs):
  assert kwargs['json']['max_tokens']==512
  return Response(self.reason)
async def run():
 with tempfile.TemporaryDirectory() as directory:
  module.AUDIO=Path(directory)
  for reason,fail in [('stop',False),('length',False),('stop',True)]:
   module.app.state.client=Client(reason)
   async def synth(*args,**kwargs):
    if fail:raise RuntimeError('Expected test failure')
    return b'test audio'
   module.synthesize=synth
   job={'text':'','clips':[],'done':False,'text_done':False,'error':'','truncated':False}
   await asyncio.wait_for(module.run_chat_job(job,module.ChatRequest(text='测试'),{}),2)
   assert job['done'] and job['text_done'],job
   assert job['truncated']==(reason=='length'),job
   assert bool(job['error'])==fail,job
 print('Normal stop, token-limit notice and TTS failure completion passed')
asyncio.run(run())
