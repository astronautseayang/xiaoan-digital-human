"""Real-image and HTTP contract checks. Run with tools/face-env/bin/python."""
import base64, io, json, sys, urllib.request, urllib.error
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'face'))
from face_feature_pipeline import extract
root=Path(__file__).resolve().parents[1]
photo=(root/'assets/photo/me.png').read_bytes()
packet=extract(photo)
assert len(packet['landmarks'])==478
assert all(0<=v<=1 for v in packet['blendShapes'].values())
image=cv2.imdecode(np.frombuffer(base64.b64decode(packet['textureBase64']),np.uint8),cv2.IMREAD_UNCHANGED)
assert image.shape==(512,512,4) and image[:,:,3].min()<30 and image[:,:,3].max()>250
for bad in (b'invalid',cv2.imencode('.png',np.full((256,256,3),255,np.uint8))[1].tobytes()):
    try: extract(bad)
    except ValueError: pass
    else: raise AssertionError('Invalid/no-face photo accepted')
source=cv2.imdecode(np.frombuffer(photo,np.uint8),cv2.IMREAD_COLOR)
h,w=source.shape[:2]
matrix=cv2.getRotationMatrix2D((w/2,h/2),12,1)
rotated=cv2.warpAffine(source,matrix,(w,h),borderMode=cv2.BORDER_REFLECT_101)
rolled=extract(cv2.imencode('.png',rotated)[1].tobytes())
# Model inference is not perfectly rotation invariant; allow modest identity jitter.
assert max(abs(rolled['blendShapes'][k]-v) for k,v in packet['blendShapes'].items())<.18
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
request=urllib.request.Request('http://127.0.0.1:9882/features',data=photo,headers={'Content-Type':'image/png'})
remote=json.load(opener.open(request,timeout=30))
assert remote['blendShapes']==packet['blendShapes']
for data,status in ((b'invalid',422),(b'',413)):
    try: opener.open(urllib.request.Request('http://127.0.0.1:9882/features',data=data),timeout=30)
    except urllib.error.HTTPError as error: assert error.code==status
    else: raise AssertionError('Bad HTTP upload accepted')
assert json.load(opener.open('http://127.0.0.1:9882/latest'))['blendShapes']==packet['blendShapes']
report=dict(passed=True,landmarks=478,textureSize=[512,512],invalidInputRejected=True,roll12DegreesPassed=True,httpUploadPassed=True,blendShapes=packet['blendShapes'])
(root/'artifacts/validation/face-pipeline-python.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
