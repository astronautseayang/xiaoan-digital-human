#!/usr/bin/env python3
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

def stream_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(4*1024*1024): h.update(b)
    return h.hexdigest()

url, dest = sys.argv[1:3]
path = Path(dest)
path.parent.mkdir(parents=True, exist_ok=True)
for metadata_attempt in range(1,4):
    metadata_url=url
    if 'huggingface.co/' in url and metadata_attempt>=2:
        metadata_url=url.replace('huggingface.co/','hf-mirror.com/')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({})) if metadata_attempt==3 else urllib.request.build_opener()
    try:
        req=urllib.request.Request(metadata_url,headers={'Range':'bytes=0-0'})
        with opener.open(req,timeout=60) as r:
            cr=r.headers.get('Content-Range','')
            if not cr.startswith('bytes 0-0/'):
                raise RuntimeError(f'Range unsupported: status={r.status} content-range={cr}')
            total=int(cr.split('/')[-1]);assert len(r.read())==1
        break
    except Exception as exc:
        print('METADATA FAILED',metadata_attempt,metadata_url,str(exc),flush=True)
        if metadata_attempt==3:raise
if path.is_file() and path.stat().st_size == total:
    print('EXISTS', path, total, flush=True)
    sys.exit(0)
chunks = Path(str(path) + '.chunks')
chunks.mkdir(exist_ok=True)
block = 4 * 1024 * 1024

def one(index):
    start = index * block
    end = min(total - 1, start + block - 1)
    part = chunks / f'{index:06d}'
    stored_header = Path(str(part)+'.headers')
    stored_text = stored_header.read_text(errors='replace').lower() if stored_header.exists() else ''
    if part.exists() and part.stat().st_size == end - start + 1 and f'content-range: bytes {start}-{end}/{total}' in stored_text:
        return
    for attempt in range(1,4):
        tmp = Path(str(part)+'.tmp')
        header = Path(str(part)+'.headers')
        headers = header.read_text(errors='replace').lower() if header.exists() else ''
        size = tmp.stat().st_size if tmp.exists() else 0
        # Reuse only a prefix accompanied by the exact original range header.
        prefix_ok = f'content-range: bytes {start}-{end}/{total}' in headers
        if size == end-start+1 and prefix_ok:
            tmp.replace(part)
            return
        offset = size if 0 < size < end-start+1 and prefix_ok else 0
        request_start = start + offset
        target = Path(str(part)+'.resume') if offset else tmp
        request_url = url
        extra = []
        if 'huggingface.co/' in url and attempt >= 2:
            request_url = url.replace('huggingface.co/', 'hf-mirror.com/')
            if attempt == 3: extra = ['--noproxy', '*']
        cmd = ['curl','-fsSL','--connect-timeout','20','--max-time','600','--speed-limit','1024','--speed-time','60','-r',f'{request_start}-{end}','-D',str(header),'-o',str(target),*extra,request_url]
        print('DOWNLOAD', index, 'attempt', attempt, 'resume_bytes',offset,'COMMAND',repr(cmd),flush=True)
        rc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        headers = header.read_text(errors='replace').lower() if header.exists() else ''
        valid = f'content-range: bytes {request_start}-{end}/{total}' in headers
        if offset and valid and target.exists():
            with tmp.open('ab') as f, target.open('rb') as src:
                while data:=src.read(1024*1024):f.write(data)
            target.unlink()
            # Normalize the stored header for a subsequent partial resume.
            header.write_text(f'content-range: bytes {start}-{end}/{total}\n')
        if rc.returncode == 0 and valid and tmp.exists() and tmp.stat().st_size == end-start+1:
            tmp.replace(part)
            return
        print('DOWNLOAD FAILED', index, attempt, rc.stderr[-250:], flush=True)
    raise RuntimeError(f'Three attempts failed for chunk {index} of {url}')

count = (total+block-1)//block
print('PARALLEL DOWNLOAD', url, 'destination', dest, 'size', total, 'chunks',count, flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.environ.get('DOWNLOAD_WORKERS', '8'))) as pool:
    list(pool.map(one,range(count)))
partial = Path(str(path)+'.assembling')
with partial.open('wb') as f:
    for i in range(count):
        with (chunks/f'{i:06d}').open('rb') as src:
            while data := src.read(1024*1024): f.write(data)
assert partial.stat().st_size == total
partial.replace(path)
print('FILES CREATED',path,'size',total,'sha256',hashlib.file_digest(path.open('rb'),'sha256').hexdigest() if hasattr(hashlib,'file_digest') else stream_hash(path),flush=True)
