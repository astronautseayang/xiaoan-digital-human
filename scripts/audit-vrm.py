from pathlib import Path
import json,hashlib,re
from PIL import Image
root=Path('/home/yyy/digital-human');out=root/'artifacts/validation/vrm-stage1'
r=json.loads((out/'runtime.json').read_text());b=json.loads((root/'artifacts/validation/avatar-build.json').read_text())
assert r['passed'],r
assert b=={'warnings':0,'errors':0,'result':'Succeeded'},b
assert len(r['rawFrames'])>=180 and max(r['rawFrames'])<=33
build=(root/'logs/vrm-stage1-build.log').read_text(errors='replace')
client=(root/'logs/vrm-stage1-client.log').read_text(errors='replace')
assert not re.search(r'(^Shader (warning|error)|warning CS\d|error CS\d|^Exception:|^VRM_LOAD_FAILED)',build,re.M)
assert not re.search(r'(^.*Exception:|^VRM_LOAD_FAILED|^Shader error)',client,re.M)
images=[]
for path in sorted(out.glob('view-*.png')):
 im=Image.open(path).convert('RGB');assert im.size==(3840,2160)
 # Reject characteristic missing-shader magenta; inspect white studio corners independently.
 colors=im.get_flattened_data();pink=sum(1 for red,green,blue in colors if red>230 and green<35 and blue>230)
 assert pink==0,(path,pink)
 if path.name=='view-0.png':assert im.getpixel((30,30))==(255,255,255)
 images.append({'file':path.name,'size':im.size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pinkPixels':pink})
assert len(images)>=8
r['build']=b;r['images']=images;r['scope']='VRM Stage 1. Raw interval at ready idle; excludes load, TTS request, active spring stimulus and 4K readback.'
(out/'acceptance.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:r[k] for k in ['passed','frames','maxFrameMs','maxFootDrift','springChains','springJoints','playbackStarts']},indent=2))
