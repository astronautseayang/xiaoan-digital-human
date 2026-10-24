"""Use SHA-verified pinned UPM archives from the deployment's local cache."""
import hashlib
import json
from pathlib import Path
root=Path('/home/yyy/digital-human');manifest=root/'human-code/Packages/manifest.json'
original=root/'config/unity-manifest.original.json'
if not original.exists():original.write_bytes(manifest.read_bytes())
data=json.loads(original.read_text())
lock=json.loads((root/'human-code/Packages/packages-lock.json').read_text())['dependencies']
for name,entry in lock.items():
    if entry['source']!='registry':continue
    version=entry['version'];cache=root/'tools/upm-cache'
    metadata=json.loads((cache/f'{name}-{version}.json').read_text())
    archive=cache/f'{name}-{version}.tgz'
    assert hashlib.sha1(archive.read_bytes()).hexdigest()==metadata['shasum'],name
    package=cache/f'{name}@{version}'
    description=json.loads((package/'package.json').read_text())
    assert description['name']==name and description['version']==version
    data['dependencies'][name]=f'file:../../tools/upm-cache/{name}@{version}'
manifest.write_text(json.dumps(data,indent=2)+'\n')
print('MODIFIED',manifest,manifest.read_text())
