"""Append deployment-owned source/config files and hashes to deploy.log."""
import hashlib
from pathlib import Path
root=Path('/home/yyy/digital-human')
paths=[root/'deploy-env.sh',root/'DECISIONS.md',root/'RESUME.md']
for folder in ['scripts','gateway','config','services','unity-patches','face']:
 paths.extend(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
with (root/'deploy.log').open('a') as log:
 for p in sorted(paths):
  raw=p.read_bytes();log.write(f'\nAUDIT FILE {p} sha256={hashlib.sha256(raw).hexdigest()} bytes={len(raw)}\n')
  if p.suffix in ['.py','.sh','.cs','.json','.yaml','.html','.md','.txt','.service']:
   log.write(raw.decode('utf-8',errors='replace')+'\n')
print('Audited',len(paths),'deployment-owned files')
