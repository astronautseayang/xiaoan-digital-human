"""Regression: incremental loops must stop before they build a speech backlog."""
import asyncio
import json
import tempfile
from pathlib import Path
from gateway import app as module


class Response:
    def __init__(self, chunks):
        self.chunks = chunks
        self.consumed = 0
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for chunk in self.chunks:
            self.consumed += 1
            yield 'data: ' + json.dumps({'choices': [{'delta': {'content': chunk}}]})
            await asyncio.sleep(0)
        yield 'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})


class Client:
    def __init__(self, response):
        self.response = response

    def stream(self, *args, **kwargs):
        assert kwargs['json']['repeat_penalty'] > 1
        return self.response


async def run():
    normal = '国内的大模型包括通义千问、文心一言、混元、盘古、智谱清言等。选择时可以比较中文能力、部署成本和使用场景。'
    for text in [normal, '一、准备材料。二、开始操作。三、检查结果。', '哈哈哈哈，好的。']:
        assert not module.has_repetition(text), text
    for text in ['通义十问、' * 20, '这是一个重复的句子。' * 8, 'abcdef ' * 10]:
        assert module.has_repetition(text), text

    with tempfile.TemporaryDirectory() as directory:
        module.AUDIO = Path(directory)
        for text, repeated, single_chunk in [
            (normal, False, False), ('你好。', False, False),
            ('通义十问、' * 80, True, False),
            ('国内的大模型有：' + '通义十问、' * 80, True, True),
            ('这是一个重复的句子。' * 20, True, False),
        ]:
            response = Response([text] if single_chunk else list(text))
            module.app.state.client = Client(response)
            spoken = []

            async def synth(sentence, **kwargs):
                spoken.append(sentence)
                return b'test audio'

            module.synthesize = synth
            job = {'text': '', 'clips': [], 'done': False, 'text_done': False,
                   'error': '', 'truncated': False}
            await asyncio.wait_for(module.run_chat_job(job, module.ChatRequest(text='测试'), {}), 2)
            assert response.closed and job['done'] and job['text_done'], job
            if repeated:
                assert job['finish_reason'] == 'repetition' and job['error'], job
                assert not job['truncated'] and not job['clips'], job
                assert not spoken, spoken
                if not single_chunk:
                    assert response.consumed < len(text), response.consumed
            else:
                assert job['text'] == text and not job['error'], job
                assert ''.join(spoken) == text, spoken

        # A loop after a valid introduction must cancel an in-flight slow TTS
        # task rather than wait for the entire queued answer to be spoken.
        response = Response(list(normal * 2 + '通义十问、' * 80))
        module.app.state.client = Client(response)
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def slow_synth(*args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        module.synthesize = slow_synth
        job = {'text': '', 'clips': [], 'done': False, 'text_done': False,
               'error': '', 'truncated': False}
        await asyncio.wait_for(module.run_chat_job(job, module.ChatRequest(text='测试'), {}), 2)
        assert started.is_set() and cancelled.is_set() and job['done'], job
        assert job['finish_reason'] == 'repetition' and not job['clips'], job

        async def upstream(*args, **kwargs):
            return {'choices': [{'message': {'content': '通义十问、' * 80}}]}

        module.upstream_json = upstream
        try:
            await module.chat(module.ChatRequest(text='测试'))
        except module.HTTPException as exc:
            assert exc.status_code == 502 and exc.detail == module.REPETITION_NOTICE
        else:
            raise AssertionError('Non-streaming endpoint accepted repetition')
    print('PASS: normal text preserved; incremental/batched loops stopped; legacy endpoint protected')


# Isolate the response guard from the installed user address preference.
module.salutation_for = lambda root: '您'
asyncio.run(run())
