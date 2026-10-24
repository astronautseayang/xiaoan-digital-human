"""SenseVoice backend for the existing multipart WAV/PCM ASR gateway."""
import gc
import io
import logging
from pathlib import Path
import re
import threading
import time
import wave
import numpy as np
from gateway.asr_cache import cached, config
from gateway.chinese import simplified
from gateway.speaker_input import InputRejected

log=logging.getLogger('human.asr')

class ASRUnavailable(RuntimeError):
    pass

class ASRService:
    def __init__(self, root):
        self.root=Path(root);self.model=None;self.device=None
        self.lock=threading.RLock();self.last_error='';self.cpu_fallback=False

    def status(self):
        settings=config(self.root)
        return {'backend':'sensevoice','model_id':settings['model_id'],
                'loaded':self.model is not None,'device':self.device,
                'cached':cached(self.root/settings['model_dir']),
                'language':settings['language'],'punctuation':settings['use_itn'],
                'hotwords':settings['hotwords'],'hotword_mode':'context_correction',
                'native_hotword_bias':False,'error':self.last_error}

    def _release(self):
        self.model=None;gc.collect()
        import torch
        if torch.cuda.is_available():torch.cuda.empty_cache()

    def _load(self, settings, force_cpu=False):
        from funasr import AutoModel
        import torch
        folder=self.root/settings['model_dir']
        if not cached(folder):
            raise ASRUnavailable('SenseVoice 模型缓存不完整，请先运行模型下载脚本。')
        requested=settings['device']
        use_cuda=not (force_cpu or self.cpu_fallback or requested=='cpu') and torch.cuda.is_available()
        self.device='cuda:0' if use_cuda else 'cpu'
        torch.set_num_threads(settings['cpu_threads'])
        self.model=AutoModel(model=str(folder),device=self.device,
                             disable_update=True,disable_pbar=True,
                             trust_remote_code=False,ncpu=settings['cpu_threads'])
        log.info('SenseVoice loaded on %s',self.device)

    def warmup(self):
        with self.lock:
            settings=config(self.root)
            if self.model is None:
                try:self._load(settings)
                except Exception:
                    if self.device!='cuda:0':
                        self.last_error='SenseVoice 初始化失败，请检查模型缓存和依赖。'
                        raise
                    log.exception('ASR CUDA initialization failed; falling back to CPU')
                    self.cpu_fallback=True;self._release();self._load(settings,force_cpu=True)

    def transcribe(self, audio):
        if not isinstance(audio,np.ndarray) or audio.ndim!=1 or not len(audio) or not np.isfinite(audio).all():
            raise InputRejected('录音格式不正确，请重新录制。')
        with self.lock:
            settings=config(self.root)
            error=None
            # One bounded ordinary retry, plus a separate CUDA-to-CPU fallback.
            for attempt in range(settings['retries']+2):
                try:
                    if self.model is None:self._load(settings)
                    result=self.model.generate(input=audio.astype(np.float32,copy=False),
                        cache={},language=settings['language'],use_itn=settings['use_itn'],
                        batch_size_s=30,disable_pbar=True,disable_update=True)
                    if not isinstance(result,list) or any(not isinstance(item,dict) or not isinstance(item.get('text'),str) for item in result):
                        raise RuntimeError('ASR returned invalid results')
                    raw=''.join(item['text'] for item in result)
                    if '<|nospeech|>' in raw.lower():raw=''
                    self.last_error=''
                    # Remove SenseVoice event/emotion/language tags without adding emoji.
                    return simplified(re.sub(r'<\|[^|]*\|>','',raw).strip())
                except Exception as exc:
                    error=exc
                    log.exception('SenseVoice inference attempt %s failed',attempt+1)
                    if self.device=='cuda:0':
                        self.cpu_fallback=True;self._release();self.device='cpu'
                        continue
                    if attempt>=settings['retries']:break
                    self._release();time.sleep(.2)
            self.last_error='语音识别暂时不可用，请稍后重试。'
            raise ASRUnavailable(self.last_error) from error


def input_bytes(data, filename='', content_type=''):
    """Accept existing WAV uploads and explicit raw 16k/16-bit/mono PCM uploads."""
    if filename.lower().endswith(('.pcm','.raw')) or content_type.split(';')[0] in ('audio/pcm','audio/x-pcm'):
        if not data or len(data)%2:raise InputRejected('PCM 录音需为16kHz、16位单声道格式。')
        buffer=io.BytesIO()
        with wave.open(buffer,'wb') as out:
            out.setparams((1,2,16000,0,'NONE','NONE'));out.writeframes(data)
        return buffer.getvalue()
    return data
