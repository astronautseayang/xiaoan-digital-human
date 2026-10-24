"""Audit actual runtime evidence and create a versioned checksum manifest."""
import hashlib, json, re
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parents[1]
folder=root/'artifacts/validation/vrm-switch'
r=json.loads((folder/'runtime.json').read_text())
b=json.loads((root/'artifacts/validation/avatar-build.json').read_text())
assert b==dict(warnings=0,errors=0,result='Succeeded')
assert r['passed'] and not r['error'],r['error']
assert r['discRemoved']
assert r['imports']==2 and r['cacheReused'] and r['profilePreserved']
assert len(r['switching'])==4 and all(len(t['rawFrames'])==30 and t['maxFrameMs']<33 and t['clickMilliseconds']<33 for t in r['switching'])
assert r['switches']==4 and all(r[k] for k in ['wrongProfileSafe','unknownSafe','audioPreserved','uiReachable'])
assert {s['avatar'] for s in r['samples']}=={'man','woman'}
for s in r['samples']:
    assert len(s['rawFrames'])==240 and max(s['rawFrames'])<=33 and s['over33']==0
    assert s['chestMotion']>.01 and s['spineMotion']>.01 and s['observationSeconds']>=11
    assert len(s['blinkIntervals'])>=2 and all(2.5<=v<=5.05 for v in s['blinkIntervals'])
    assert s['closedEyeFrames']>0 and s['reopenedEyeFrames']>0
    if s['avatar']=='man': assert abs(s['stanceWidth']-s['shoulderWidth'])<.015
    assert s['grounded'] and s['maxFootDrift']<.002 and abs(s['soleGap'])<.005
images=[]
for p in sorted(folder.glob('*.png')):
    im=Image.open(p).convert('RGB')
    assert im.size==(3840,2160),(p,im.size)
    if 'studio' in p.name:
        assert im.getpixel((3800,10))==(255,255,255)
    images.append(dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
assert len(images)==6
log=(root/'logs/avatar-switch-client.log').read_text()
assert not re.search(r'warning CS\d|error CS\d|Shader error|^.*Exception:',log,re.M)
r.update(build=b,images=images,scope='Native 1920x1080 RTX runtime; 240 unfiltered steady frame intervals per avatar, after explicit GC and 180 warmup frames. Includes click duration and 30 immediate frame intervals for each switch. Both models imported once under startup overlay; steady windows exclude startup and 4K readbacks. Audio continuity uses synthetic 180Hz audio; real ASR/TTS is a separate stage4 regression.')
(folder/'acceptance.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
evidence={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [folder/'runtime.json',folder/'acceptance.json',root/'logs/avatar-switch-unity-build.log',root/'logs/avatar-switch-client.log']}
(root/'unity-patches/VrmAssets/accepted-switch.json').write_text(json.dumps(dict(build=b,evidence=evidence,images=images,models=json.loads((root/'unity-patches/VrmAssets/avatar-catalog.json').read_text())),ensure_ascii=False,indent=2)+'\n')
print('Verified actual switching evidence, build 0/0, six 4K images and independent 240-frame windows')
