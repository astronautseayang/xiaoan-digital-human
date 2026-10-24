"""Audit the actual Stage 3 build/player run, including full raw intervals."""
import hashlib
import json
import re
from pathlib import Path
from PIL import Image, ImageStat
root = Path('/home/yyy/digital-human')
out = root / 'artifacts/validation/vrm-stage3'
r = json.loads((out/'runtime.json').read_text())
b = json.loads((root/'artifacts/validation/avatar-build.json').read_text())
assert b == dict(warnings=0, errors=0, result='Succeeded'), b
assert r['passed'] and not r['error'], r
for key in ['autoMounted','profileAccepted','smoothStart','expressionReached','customShapeReached',
            'skinMatched','textureBound','missingTextureSafe','invalidRejected','interruptionSmooth',
            'restored','lipSyncIsolated','blinkIsolated','toonPaletteMatched','hairMatched','neutralAlbedoBound']:
    assert r[key], key
assert len(r['rawFrames']) == r['frames'] >= 180
assert max(r['rawFrames']) <= 33 and r['over33'] == 0
assert .25 <= r['transitionSeconds'] < .3
for name in ['vrm-face-stage3-build.log','vrm-face-stage3-client.log']:
    log = (root/'logs'/name).read_text(errors='replace')
    assert not re.search(r'(^Shader (warning|error)|warning CS\d|error CS\d|^.*Exception:|VRM_LOAD_FAILED)', log, re.M), name
images = []
for path in sorted(out.glob('*.png')):
    if path.name == 'bad.png':
        continue
    im = Image.open(path).convert('RGB')
    assert im.size == (3840,2160), path
    assert not any(red>230 and green<35 and blue>230 for red,green,blue in im.get_flattened_data()), path
    images.append(dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
assert len(images) == 2
# Fixed Alicia closeup framing: detect both the old dark orange and clipped-white regression.
im = Image.open(out/'feature-open.png').convert('RGB')
w,h = im.size
cheek = ImageStat.Stat(im.crop((int(w*.47),int(h*.50),int(w*.48),int(h*.515)))).mean
assert 210 <= cheek[0] < 250 and 175 <= cheek[1] <= 235 and 180 <= cheek[2] <= 245, cheek
assert cheek[0] > cheek[1]+8 and cheek[2] > cheek[1]+2, cheek
r['renderedCheekSrgb255'] = cheek
r.update(build=b, images=images,
         scope='240 intervals include repeated small JSON reloads and shape/color transitions. Initial PNG decode, model loading and 4K readback excluded. Native lip/blink input ownership tested; no ASR/TTS performance claim.',
         customShapeScope='A test-only shape was added to a clone of the real imported mesh. Production Alicia has no EyeSlanted/EyeDistance/JawRound/EyeSize/EyeOpenness shape targets.')
(out/'acceptance.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({key:r[key] for key in ['passed','build','frames','maxFrameMs','transitionSeconds','skinMaterials','featureMaterials']},indent=2))
