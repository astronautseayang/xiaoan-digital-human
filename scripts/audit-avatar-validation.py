"""Fail on actual geometry, performance, speech and image evidence; preserve raw frame samples."""
from pathlib import Path
import hashlib
import json
import struct
import re
import base64
root=Path('/home/yyy/digital-human')
out=root/'artifacts/validation'
b=json.loads((out/'avatar-build.json').read_text())
assert b['result']=='Succeeded' and b['warnings']==b['errors']==0
build_log=(root/'logs/unity-build.log').read_text()
assert not re.search(r'warning CS\d+|error CS\d+|Shader (?:error|warning)',build_log,re.I)
g=json.loads((out/'avatar-geometry.json').read_text())
s=json.loads((out/'figurine-startup.json').read_text())
r=json.loads((out/'figurine/unity-runtime.json').read_text())
assert g['passed'] and abs(g['headBodyRatio']-2.5)<.001
for surface in g['surfaces']:
    assert surface['boundaryEdges']==surface['nonManifoldEdges']==surface['degenerateTriangles']==0
assert s['passed'] and s['interactiveFrames']>=180 and len(s['frameMilliseconds'])==s['interactiveFrames']
assert max(s['frameMilliseconds'])<=33 and s['targetFrameRate']==60
assert s['screenWidth']==1920 and s['screenHeight']==1080 and s['renderScale']==1
assert 'NVIDIA' in s['graphicsDevice']
assert s['vSyncCount']==0
assert all(r[k] for k in ['modernPanelValid','panelPasteAndEditPassed','panelSendPassed','studioBackdropValid','studioSsaoActive'])
assert r['wristPoseValid'] and r['continuousGarmentValid']
assert r['minimumPalmInward']>.6 and r['minimumThumbForward']>.6
assert r['maxSkinWeightError']<.00001 and r['blendedGarmentVertices']>100
assert any(x['name']=='ContinuousHoodie' for x in g['surfaces'])
assert r['feetLocked'] and r['footSupportStepPassed'] and r['footSupportLossPassed']
assert r['footIdleFrames']>=240 and r['footSpeechFrames']>=180
assert r['maxFootGapMeters']<.001 and r['maxFootSlideMeters']<.001 and r['maxFootNormalDegrees']<.1
assert r['polishStructureValid'] and r['blinkSpeechIndependent'] and r['completedBlinks']>=2
assert .65<=r['irisWidthRatio']<=.75
assert r['detailStructureValid'] and r['transparentEyeDomes']==2 and r['threeQuarterYawDegrees']==45
assert r['facePipeline']['passed']
assert r['passed'] and r['identitySpeechIndependent'] and not r['error']
assert r['playbackMeasuredFrames']>=180 and max(r['playbackFrameMilliseconds'])<=33
assert r['outlineRenderedFrames']>=180 and all(x>1 for x in r['maxWeights'])
assert r['measuredReplayCount']>0 and r['playbackStarts']==3+r['measuredReplayCount'] and r['voiceRounds']==2
assert len(r['playbackFrameMilliseconds'])==r['playbackMeasuredFrames']
# Inspect rendered pixels, independent of scene material settings.
from PIL import Image
white=Image.open(out/'figurine/neutral.png').convert('RGB')
for xy in [(3800,40),(3800,1000),(3000,100)]:
    assert white.getpixel(xy)==(255,255,255), (xy,white.getpixel(xy))
images=[]
for name in ['neutral','three-quarter','profile','rear','face-detail','garment-detail','hand-detail','blink-closed','interaction-studio','interaction-answer']:
    path=out/f'figurine/{name}.png'
    data=path.read_bytes()
    assert data[:8]==b'\x89PNG\r\n\x1a\n'
    width,height=struct.unpack('>II',data[16:24])
    assert width>=3840 and height>=2160
    images.append(dict(file=str(path.relative_to(root)),width=width,height=height,sha256=hashlib.sha256(data).hexdigest()))
report=dict(wristAndGarment={k:r[k] for k in ['wristPoseValid','continuousGarmentValid','minimumPalmInward','minimumThumbForward','maxSkinWeightError','blendedGarmentVertices']},pureWhitePixelsVerified=True,facePipeline=r['facePipeline'],studio={k:r[k] for k in ['modernPanelValid','panelPasteAndEditPassed','panelSendPassed','studioBackdropValid','studioSsaoActive','backdropVertices','backdropRoughness','keyIntensity','fillIntensity']},feet={k:r[k] for k in ['feetLocked','footLockMode','footIdleFrames','footSpeechFrames','maxFootGapMeters','maxFootSlideMeters','maxFootNormalDegrees','footSupportStepPassed','footSupportLossPassed']},passed=True,build=b,polishStructureValid=r['polishStructureValid'],blinkSpeechIndependent=r['blinkSpeechIndependent'],completedBlinks=r['completedBlinks'],irisWidthRatio=r['irisWidthRatio'],detailStructureValid=r['detailStructureValid'],transparentEyeDomes=r['transparentEyeDomes'],garmentDetailRenderers=r['garmentDetailRenderers'],threeQuarterYawDegrees=r['threeQuarterYawDegrees'],geometry=g,startupFrames=s['interactiveFrames'],startupMaxMilliseconds=s['maxInteractiveFrameMilliseconds'],startupP95Milliseconds=s['p95InteractiveFrameMilliseconds'],speechFrames=r['playbackMeasuredFrames'],measuredReplayCount=r['measuredReplayCount'],playbackStarts=r['playbackStarts'],voiceRounds=r['voiceRounds'],speechMaxMilliseconds=r['playbackMaxFrameMilliseconds'],speechP95Milliseconds=r['playbackP95FrameMilliseconds'],outlineRenderedFrames=r['outlineRenderedFrames'],images=images,graphicsDevice=s['graphicsDevice'],renderScale=s['renderScale'],displayRefreshHz=s['displayRefreshHz'],targetFrameRate=s['targetFrameRate'],vSyncCount=s['vSyncCount'],scope='Measured ready-state startup and sustained cached speech replay, 1920x1080 with a 60 fps software cap; desktop refresh rate recorded separately. 4K offline screenshot capture and engine/window initialization are outside timing windows.')
# Snapshot the exact applied photo packet; later uploads cannot replace this run's evidence.
packet_bytes=(root/'artifacts/face/latest.json').read_bytes()
packet=json.loads(packet_bytes)
assert len(packet['landmarks'])==478
(out/'face-pipeline-input.json').write_bytes(packet_bytes)
diffuse=base64.b64decode(packet['textureBase64'],validate=True)
(out/'face-pipeline-diffuse.png').write_bytes(diffuse)
python_report=json.loads((out/'face-pipeline-python.json').read_text())
assert python_report['passed'] and python_report['blendShapes']==packet['blendShapes']
report['facePipelinePython']=python_report
report['faceInput']={'packet':'artifacts/validation/face-pipeline-input.json','packetSha256':hashlib.sha256(packet_bytes).hexdigest(),'diffuse':'artifacts/validation/face-pipeline-diffuse.png','diffuseSha256':hashlib.sha256(diffuse).hexdigest()}
(out/'avatar-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
