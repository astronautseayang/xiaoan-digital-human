"""Verified ModelScope files; complete local caches never need a network call."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import shutil
from pathlib import Path
import time
import httpx

FILES = ('configuration.json','config.yaml','am.mvn',
         'chn_jpn_yue_eng_ko_spectok.bpe.model','tokens.json','model.pt')
MODEL_ID = 'iic/SenseVoiceSmall'


def config(root):
    data = json.loads((Path(root)/'config/asr.json').read_text())
    if not isinstance(data, dict):
        raise ValueError('ASR 配置须为JSON对象')
    if not isinstance(data.get('model_dir'), str) or not data['model_dir'].strip():
        raise ValueError('ASR model_dir 须为非空模型目录')
    if data.get('model_id') != MODEL_ID:
        raise ValueError('当前 ASR 后端仅支持 iic/SenseVoiceSmall')
    if data.get('device') not in ('auto','cpu','cuda','cuda:0'):
        raise ValueError('ASR device 必须为 auto/cpu/cuda/cuda:0')
    if data.get('hotword_mode') != 'context_correction':
        raise ValueError('SenseVoice 不支持原生热词解码，请使用 context_correction')
    words=data.get('hotwords',[])
    if not isinstance(words,list) or len(words)>128 or any(not isinstance(w,str) or not 1<=len(w)<=32 for w in words):
        raise ValueError('ASR 热词须为不超过128项、每项1到32字的字符串列表')
    if data.get('language') != 'zh' or not isinstance(data.get('use_itn'),bool):
        raise ValueError('ASR 需要中文 language=zh 和布尔值 use_itn')
    if type(data.get('cpu_threads')) is not int or not 1<=data['cpu_threads']<=16:
        raise ValueError('ASR cpu_threads 须在1到16之间')
    if type(data.get('retries')) is not int or not 0<=data['retries']<=2:
        raise ValueError('ASR retries 须在0到2之间')
    return {**data, 'hotwords': words}


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def cached(folder, verify=False):
    try:
        manifest=json.loads((folder/'cache-manifest.json').read_text())
        return manifest['model_id']==MODEL_ID and all(
            (folder/name).stat().st_size==manifest['files'][name]['size'] and
            (not verify or sha(folder/name)==manifest['files'][name]['sha256']) for name in FILES)
    except (OSError,KeyError,ValueError,TypeError):return False


def ranged_download(url, params, tmp, total):
    block=8*1024*1024
    parts=tmp.with_suffix('.parts');parts.mkdir(exist_ok=True)
    # Reuse complete chunks from an interrupted serial transfer. Full-file
    # SHA256 below still authenticates every reused/downloaded byte.
    if tmp.exists():
        with tmp.open('rb') as source:
            for index in range(tmp.stat().st_size//block):
                part=parts/str(index)
                chunk=source.read(block)
                if not part.exists():part.write_bytes(chunk)
    def chunk(index):
        start=index*block;end=min(total,start+block)-1;part=parts/str(index)
        if part.exists() and part.stat().st_size==end-start+1:return
        for attempt in range(3):
            try:
                with httpx.Client(trust_env=False,follow_redirects=True,timeout=120) as client:
                    r=client.get(url,params=params,headers={'Range':f'bytes={start}-{end}'})
                    r.raise_for_status()
                    if r.status_code!=206 or r.headers.get('content-range')!=f'bytes {start}-{end}/{total}' or len(r.content)!=end-start+1:
                        raise RuntimeError('模型分块响应不正确')
                    part.write_bytes(r.content)
                return
            except (httpx.HTTPError,OSError,RuntimeError):
                if attempt==2:raise
                time.sleep(attempt+1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for index,_ in enumerate(pool.map(chunk,range((total+block-1)//block))):
            if index%16==0:print('ASR model chunks:',index,flush=True)
    with tmp.open('wb') as out:
        for index in range((total+block-1)//block):
            with (parts/str(index)).open('rb') as source:shutil.copyfileobj(source,out)


def ensure(root, offline=False):
    settings=config(root)
    folder=Path(root)/settings['model_dir'];folder.mkdir(parents=True,exist_ok=True)
    with (folder/'.download.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if cached(folder,verify=True):return folder
        if offline:raise RuntimeError('SenseVoice 本地缓存不完整，请先运行 scripts/download-sensevoice.py')
        with httpx.Client(trust_env=False,follow_redirects=True,timeout=60) as client:
            response=client.get(f'https://www.modelscope.cn/api/v1/models/{MODEL_ID}/repo/files',params={'Revision':'master','Recursive':'true'})
            response.raise_for_status()
            entries={f['Path']:f for f in response.json()['Data']['Files'] if f['Path'] in FILES}
        if len(entries)!=len(FILES):raise RuntimeError('模型文件清单不完整')
        def download(name):
            entry=entries[name];dest=folder/name
            if dest.exists() and dest.stat().st_size==entry['Size'] and sha(dest)==entry['Sha256']:return
            error=None
            for attempt in range(3):
                try:
                    tmp=dest.with_suffix(dest.suffix+'.partial')
                    url=f'https://www.modelscope.cn/api/v1/models/{MODEL_ID}/repo'
                    params={'Revision':'master','FilePath':name}
                    if entry['Size']>32*1024*1024:
                        ranged_download(url,params,tmp,entry['Size'])
                    else:
                        with httpx.Client(trust_env=False,follow_redirects=True,timeout=120) as client:
                            response=client.get(url,params=params);response.raise_for_status();tmp.write_bytes(response.content)
                    if tmp.stat().st_size!=entry['Size'] or sha(tmp)!=entry['Sha256']:
                        shutil.rmtree(tmp.with_suffix('.parts'),ignore_errors=True)
                        tmp.unlink(missing_ok=True)
                        raise RuntimeError('模型文件大小或 SHA256 校验失败：'+name)
                    tmp.replace(dest);shutil.rmtree(tmp.with_suffix('.parts'),ignore_errors=True);print('ASR cached:',name,entry['Size'],flush=True);return
                except (httpx.HTTPError,OSError,RuntimeError) as exc:
                    error=exc
                    if attempt<2:time.sleep(attempt+1)
            raise RuntimeError('模型下载失败：'+name) from error
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(download,FILES))
        manifest={'model_id':MODEL_ID,'files':{name:{'size':entries[name]['Size'],'sha256':entries[name]['Sha256']} for name in FILES}}
        tmp=folder/'cache-manifest.tmp';tmp.write_text(json.dumps(manifest,indent=2));tmp.replace(folder/'cache-manifest.json')
        return folder
