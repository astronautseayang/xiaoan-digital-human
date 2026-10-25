"""Cancellation drops late ASR results and stops generation with its TTS worker."""
import asyncio
import tempfile
import time
from pathlib import Path
from gateway import app as module
from gateway.wake import WakeService

async def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root/'config').mkdir()
        (root/'config/wake.json').write_text('{"keyword":"小安"}')
        began = asyncio.Event()
        async def recognize(*args, **kwargs):
            began.set()
            await asyncio.Event().wait()
        service = WakeService(root, recognize, None, None)
        controls = []
        async def control(data):
            controls.append(data)
        service.control = control
        events = asyncio.Queue()
        service.clients.add(events)
        path = root/'input.wav'
        path.write_bytes(b'audio')
        task = asyncio.create_task(service.audio({'path':str(path)}))
        service.tasks.add(task)
        await began.wait()
        await service.receive_control({'type':'cancel_listen'})
        assert task.cancelled() and not path.exists()
        assert controls == [{'cancel_listen':True}], controls
        assert all(e['type'] != 'transcript' for e in list(events._queue))

        module.AUDIO = root
        tts_started = asyncio.Event()
        tts_cancelled = asyncio.Event()
        class Response:
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            def raise_for_status(self): pass
            async def aiter_lines(self):
                import json
                yield 'data: '+json.dumps({'choices':[{'delta':{'content':'可以先喝一杯温水。然后看看窗外的树木和花草，慢慢走动，舒展一下身体，今天还可以读书听音乐，与家人聊聊生活里的新鲜事，让心情放松。'}}]})
                await asyncio.Event().wait()
        class Client:
            def stream(self,*args,**kwargs): return Response()
        async def synthesize(*args,**kwargs):
            tts_started.set()
            try: await asyncio.Event().wait()
            finally: tts_cancelled.set()
        module.app.state.client = Client()
        module.synthesize = synthesize
        key = 'cancel-test'
        job = {'text':'','clips':[],'done':False,'created':time.monotonic()}
        module.jobs[key] = job
        task = asyncio.create_task(module.run_chat_job(job,module.ChatRequest(text='测试'),{}))
        module.job_handles[key] = task
        await tts_started.wait()
        await module.cancel_chat_job(key)
        assert task.cancelled() and tts_cancelled.is_set()
        assert job['done'] and job['finish_reason']=='cancelled'
        assert not job['clips']
        await module.cancel_chat_job(key)  # repeated click remains harmless
    print('ASR cancellation cleanup, stale transcript suppression, LLM/TTS cancellation and repeated cancellation passed')

asyncio.run(asyncio.wait_for(main(), 10))
