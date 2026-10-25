"""Failures/deadlines release both chat tasks; WAV work does not block inference."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import threading
import wave
from gateway import app as module
from unittest.mock import patch


class Stream:
    def __init__(self, fail=False):
        self.closed = False
        self.fail = fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        yield 'data: ' + json.dumps({'choices': [{'delta': {'content':
            '您好，今天可以慢慢喝水。然后看看窗外的花草，和家人聊聊日常，听一段喜欢的音乐，让心情放松下来。'}}]})
        if self.fail:
            raise RuntimeError('Injected model stream failure')
        await asyncio.Event().wait()


async def run():
    module.salutation_for = lambda root: '您'
    with tempfile.TemporaryDirectory() as directory:
        module.AUDIO = Path(directory)
        for scenario in ('tts_failure', 'model_failure', 'deadline'):
            stream = Stream(fail=scenario == 'model_failure')

            class Client:
                def stream(self, *args, **kwargs):
                    return stream

            module.app.state.client = Client()
            stopped = asyncio.Event()

            async def synth(*args, **kwargs):
                try:
                    if scenario == 'tts_failure':
                        raise RuntimeError('Injected speech failure')
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

            module.synthesize = synth
            module.CHAT_TIMEOUT_SECONDS = .05 if scenario == 'deadline' else 180
            job = {'text': '', 'clips': [], 'done': False, 'error': ''}
            await asyncio.wait_for(module.run_chat_job(job, module.ChatRequest(text='你好'), {}), 1)
            assert job['done'] and job['text_done'] and job['error'], job
            assert stream.closed and not job['clips'], job
            if scenario != 'model_failure':
                assert stopped.is_set()
            if scenario == 'deadline':
                assert job['finish_reason'] == 'timeout', job
            assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()], scenario
            print('PASS:', scenario)


async def overlap():
    # Hold request one's WAV processing in a thread: request two must still
    # reach the inference server, while inference calls remain serialized.
    source = io.BytesIO()
    with wave.open(source, 'wb') as wav:
        wav.setparams((1, 2, 32000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\0\0' * 100)
    data = source.getvalue()
    entered = threading.Event()
    release = threading.Event()
    second_request = asyncio.Event()
    calls = 0
    active = 0

    class Response:
        content = data
        def raise_for_status(self):
            pass

    class Client:
        async def post(self, *args, **kwargs):
            nonlocal calls, active
            active += 1
            assert active == 1, 'Concurrent GPT-SoVITS inference'
            await asyncio.sleep(0)
            active -= 1
            calls += 1
            if calls == 2:
                second_request.set()
            return Response()

    def process(value):
        if not entered.is_set():
            entered.set()
            assert release.wait(2), 'WAV processing was not released'
        return value

    module.app.state.client = Client()
    module.process_senior_speech = process
    voice = {'ref_audio_path': __file__, 'prompt_lang': 'zh', 'prompt_text': '你好'}
    one = asyncio.create_task(original_synthesize('你好', voice=voice))
    two = None
    try:
        while not entered.is_set():
            await asyncio.sleep(.001)
        two = asyncio.create_task(original_synthesize('您好', voice=voice))
        await asyncio.wait_for(second_request.wait(), .5)
    finally:
        release.set()
        await asyncio.gather(*[t for t in (one, two) if t], return_exceptions=False)
    print('PASS: WAV processing overlaps serialized inference')


original_synthesize = module.synthesize
async def main():
    await run()
    with patch.object(module, 'salutation_for', side_effect=OSError('Unreadable settings')):
        job = {'text': '', 'clips': [], 'done': False, 'error': ''}
        await asyncio.wait_for(module.run_chat_job(job, module.ChatRequest(text='你好'), {}), 1)
        assert job['done'] and job['text_done'] and job['error'], job
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        print('PASS: initialization failure completes job and releases workers')
    await overlap()

asyncio.run(main())
