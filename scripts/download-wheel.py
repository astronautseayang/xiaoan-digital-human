import hashlib,json,os,subprocess,sys,urllib.request
from pathlib import Path
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
tags=list(sys_tags());root=Path('/home/yyy/digital-human')
for specification in sys.argv[1:]:
 name,version=specification.split('==')
 with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=45) as response:data=json.load(response)
 candidates=[]
 for f in data['urls']:
  if f['packagetype']!='bdist_wheel':continue
  wt=parse_wheel_filename(f['filename'])[3]
  rank=min((i for i,t in enumerate(tags) if t in wt),default=999999)
  if rank<999999:candidates.append((rank,f))
 assert candidates,specification
 f=min(candidates,key=lambda pair:pair[0])[1]
 dest=root/'wheelhouse'/f['filename']
 env=dict(os.environ,DOWNLOAD_WORKERS='6');env['no_proxy']=env.get('no_proxy','')+',.tsinghua.edu.cn'
 subprocess.run([sys.executable,str(root/'scripts/parallel-download.py'),f['url'].replace('https://files.pythonhosted.org/','https://pypi.tuna.tsinghua.edu.cn/'),str(dest)],check=True,env=env)
 h=hashlib.sha256()
 with dest.open('rb') as stream:
  while block:=stream.read(4*1024*1024):h.update(block)
 assert h.hexdigest()==f['digests']['sha256']
 print('WHEEL VERIFIED',dest,flush=True)
