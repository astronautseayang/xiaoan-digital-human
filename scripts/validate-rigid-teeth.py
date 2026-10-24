import json
from pathlib import Path
import cv2,mediapipe as mp,numpy as np
root=Path('/home/yyy/digital-human')
a=cv2.imread(str(root/'assets/photo/me.png'));h,w=a.shape[:2]
with mp.solutions.face_mesh.FaceMesh(static_image_mode=True,max_num_faces=1) as detector:
 points=detector.process(cv2.cvtColor(a,cv2.COLOR_BGR2RGB)).multi_face_landmarks[0].landmark
coords=np.array([[v.x,v.y] for v in points])
ring=[78,191,80,81,82,13,312,311,310,415,308,324,318,402,317,14,87,178,88,95]
mask=np.zeros((h,w),np.uint8);cv2.fillPoly(mask,[np.round(coords[ring]*[w,h]).astype(np.int32)],255)
mask=cv2.dilate(mask,np.ones((5,5),np.uint8))
locked=cv2.resize(mask,(161,141),interpolation=cv2.INTER_NEAREST).ravel()>0
face=json.loads((root/'human-code/Assets/LocalPortrait/face.json').read_text())
maximum=max(float(np.abs(np.array(s['delta']).reshape(-1,3)[:len(locked)][locked]).max()) for s in face['shapes'])
report={'passed':maximum==0,'teeth_vertices':int(locked.sum()),'maximum_teeth_displacement_metres':maximum,'shapes':[s['name'] for s in face['shapes']]}
(root/'artifacts/validation/unity/rigid-teeth.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report));assert report['passed']
