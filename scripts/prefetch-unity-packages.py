"""Cache pinned UPM registry archives with registry SHA1 validation."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request
root=Path('/home/yyy/digital-human')
cache=root/'tools/upm-cache';cache.mkdir(exist_ok=True)
lock=json.loads((root/'human-code/Packages/packages-lock.json').read_text())['dependencies']
def fetch(item):
    name,entry=item
    if entry['source']!='registry':return
    version=entry['version']
    for attempt in range(1,4):
        try:
            with urllib.request.urlopen(f'https://packages.unity.com/{name}',timeout=90) as r:meta=json.load(r)
            dist=meta['versions'][version]['dist']
            archive=cache/f'{name}-{version}.tgz'
            if not archive.is_file() or hashlib.sha1(archive.read_bytes()).hexdigest()!=dist['shasum']:
                with urllib.request.urlopen(dist['tarball'],timeout=180) as r:raw=r.read()
                assert hashlib.sha1(raw).hexdigest()==dist['shasum'],name
                archive.write_bytes(raw)
            destination=cache/f'{name}@{version}'
            if not (destination/'package.json').is_file():
                with tarfile.open(archive,'r:gz') as tar:
                    for member in tar.getmembers():
                        path=Path(member.name)
                        assert path.parts[0]=='package' and '..' not in path.parts and not member.issym() and not member.islnk()
                    tar.extractall(cache/f'.extract-{name}')
                (cache/f'.extract-{name}/package').rename(destination)
            metadata={'name':name,'version':version,**dist,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
            (cache/f'{name}-{version}.json').write_text(json.dumps(metadata,indent=2))
            print('UPM VERIFIED',json.dumps(metadata),flush=True)
            return
        except Exception as exc:
            print('UPM FAILED',name,attempt,repr(exc),flush=True)
            if attempt==3:raise
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(fetch,lock.items()))
print('ALL PINNED REGISTRY PACKAGES VERIFIED',flush=True)
