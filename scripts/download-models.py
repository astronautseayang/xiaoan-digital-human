import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess

root = Path('/home/yyy/digital-human')
target = root / 'GPT-SoVITS/GPT_SoVITS/pretrained_models'
entries = json.loads((root / 'logs/hf-model-tree.json').read_text())
jobs = []
for e in entries:
    p = e['path']
    if e['type'] != 'file':
        continue
    if p.startswith(('chinese-roberta-wwm-ext-large/', 'chinese-hubert-base/')) or p in (
        'gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt',
        'gsv-v2final-pretrained/s2G2333k.pth',
    ):
        jobs.append((p, e['size'], e.get('lfs', {}).get('oid')))

def download(job):
    name, size, oid = job
    path = target / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size == size:
        if oid:
            h=hashlib.sha256()
            with path.open('rb') as stream:
                while block:=stream.read(4*1024*1024):h.update(block)
            assert h.hexdigest()==oid, f'Hash mismatch: {path}'
        print('VERIFIED EXISTING', name, flush=True)
        return
    if size > 8*1024*1024:
        url = f'https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/{name}'
        subprocess.run([__import__('sys').executable, str(root/'scripts/parallel-download.py'), url, str(path)], check=True)
        h=hashlib.sha256()
        with path.open('rb') as f:
            while b:=f.read(4*1024*1024):h.update(b)
        assert path.stat().st_size == size
        if oid: assert h.hexdigest() == oid
        return
    tmp = Path(str(path) + '.part')
    for attempt, host in enumerate(('https://hf-mirror.com', 'https://huggingface.co', 'https://hf-mirror.com'), 1):
        url = f'{host}/lj1995/GPT-SoVITS/resolve/main/{name}?download=true'
        cmd = ['curl', '-fL', '--connect-timeout', '20', '--max-time', '1800', '--speed-limit', '1024', '--speed-time', '60', '-C', '-', '-o', str(tmp), url]
        print('ATTEMPT', attempt, 'COMMAND', repr(cmd), flush=True)
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0 and tmp.stat().st_size == size:
            if oid and hashlib.sha256(tmp.read_bytes()).hexdigest() != oid:
                tmp.unlink()
                continue
            tmp.replace(path)
            print('FILES CREATED:', path, 'bytes=', size, flush=True)
            return
        print('FAILED', name, 'attempt', attempt, result.stderr[-600:], flush=True)
    raise RuntimeError(f'Three attempts failed: {name}')

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(download, jobs))
print('ALL V2 MODEL FILES VERIFIED', flush=True)
