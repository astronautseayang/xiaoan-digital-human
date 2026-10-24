import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from packaging.requirements import Requirement
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename

root=Path('/home/yyy/digital-human')
out=root/'wheelhouse'
out.mkdir(exist_ok=True)
tags=list(sys_tags())
def metadata(name, version):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=40) as r:return json.load(r)
        except Exception:
            if attempt==2:raise
plan=[('torch','2.6.0'),('torchaudio','2.6.0'),('torchvision','0.21.0')]
torch=metadata('torch','2.6.0')
for text in torch['info']['requires_dist']:
    req=Requirement(text)
    if req.marker and not req.marker.evaluate():continue
    versions=[s.version for s in req.specifier if s.operator=='==']
    if versions:plan.append((req.name,versions[0]))

def one(item):
    name,version=item
    data=torch if name=='torch' else metadata(name,version)
    candidates=[]
    for f in data['urls']:
        if f['packagetype']!='bdist_wheel':continue
        try:
            wt=parse_wheel_filename(f['filename'])[3]
            rank=min((i for i,t in enumerate(tags) if t in wt),default=999999)
            if rank<999999:candidates.append((rank,f))
        except ValueError:pass
    if not candidates:raise RuntimeError(f'No compatible wheel: {name}')
    f=min(candidates,key=lambda x:x[0])[1]
    dest=out/f['filename']
    env=dict(os.environ,DOWNLOAD_WORKERS='6')
    env['no_proxy']=env.get('no_proxy','')+',.tsinghua.edu.cn'
    download_url=f['url'].replace('https://files.pythonhosted.org/', 'https://pypi.tuna.tsinghua.edu.cn/')
    print('WHEEL',name,version,f['size'],flush=True)
    subprocess.run([sys.executable,str(root/'scripts/parallel-download.py'),download_url,str(dest)],check=True,env=env)
    h=hashlib.sha256()
    with dest.open('rb') as stream:
        while b:=stream.read(4*1024*1024):h.update(b)
    assert h.hexdigest()==f['digests']['sha256'],f'Hash mismatch: {dest}'
    print('WHEEL VERIFIED',dest,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:list(pool.map(one,plan))
print('ALL TORCH WHEELS READY',flush=True)
