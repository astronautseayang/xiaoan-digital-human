"""Stage 4 actual build and native expression/voice/physics integration audit."""
import hashlib,json,re
from pathlib import Path
from PIL import Image
root=Path('/home/yyy/digital-human');out=root/'artifacts/validation/vrm-stage4'
r=json.loads((out/'runtime.json').read_text());b=json.loads((root/'artifacts/validation/avatar-build.json').read_text())
assert b==dict(warnings=0,errors=0,result='Succeeded'),b
assert r['passed'] and not r['error'],r
assert r['interactiveGreetings']>=1 and r['interactionReleased']
assert r['voiceEnrollment'] and r['voiceReset'] and r['answerAutoScroll']
assert r['firstTextSeconds'] >= 0 and r['firstAudioSeconds'] > 0
assert r['frames']==len(r['rawFrames'])>=180 and max(r['rawFrames'])<=33 and r['over33']==0
assert all(v>.001 for v in r['vowelMax'])
assert r['blinkIdle']>=2 and r['blinkSpeech']>=1 and all(2.5<=v<=5.04 for v in r['blinkIntervals'])
assert r['photoSmileApplied'] and r['expressionSmooth'] and r['expressionInvalidSafe']
assert .3 <= r['expressionDuration'] < .35 and r['maxSmileEyeWeight'] < 23
assert r['photoEmotionIgnored'] and r['eyesReopen'] and r['maxRestingLidWeight']<.01
assert r['chestMotion']>.01 and r['springMotion']>.01 and r['maxMorphError']<.02 and r['maxProfileError']<.001
for name in ['vrm-integration-stage4-build.log','vrm-integration-stage4-client.log']:
 text=(root/'logs'/name).read_text(errors='replace')
 assert not re.search(r'(^Shader (warning|error)|warning CS\d|error CS\d|^.*Exception:|VRM_LOAD_FAILED)',text,re.M),name
images=[]
for path in sorted(out.glob('*.png')):
 im=Image.open(path).convert('RGB');assert im.size==(3840,2160)
 assert not any(a>230 and b<35 and c>230 for a,b,c in im.get_flattened_data())
 if path.name=='studio.png':
  assert all(im.getpixel(p)==(255,255,255) for p in [(10,10),(3800,10),(3800,2000)])
 images.append(dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
assert len(images)==4
r.update(build=b,images=images,scope='1920x1080 raw intervals during cached real GPT-SoVITS replay, native expression/mesh and grounding checks included. Model load, network/ASR/TTS generation, initial profile/PNG decode and 4K readback excluded. Native breathing plus UpperBody interactive gestures; no injected spring torque. Legacy photo Joy is ignored; bounded speech-driven happy is checked against the interactive smile input; explicit expression smiles use regional mouth/brow and bounded eye curves, with aa opening composed with speech; actual Stage 2 tint/iris loaded; production Alicia still lacks custom identity shapes.')
(out/'acceptance.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:r[k] for k in ['passed','build','frames','maxFrameMs','vowelMax','blinkIdle','blinkSpeech','springMotion','chestMotion']},indent=2))
