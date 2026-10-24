"""Export landmarks and source image only for editor-time parameter extraction; never build photo geometry."""
from pathlib import Path
import json
import cv2
import mediapipe as mp
root=Path('/home/yyy/digital-human')
im=cv2.imread(str(root/'assets/photo/me.png'))
if im is None: raise ValueError('Missing personal portrait')
with mp.solutions.face_mesh.FaceMesh(static_image_mode=True,max_num_faces=2,refine_landmarks=True,min_detection_confidence=.6) as mesh:
    faces=mesh.process(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)).multi_face_landmarks
if not faces or len(faces)!=1: raise ValueError('Exactly one frontal face required')
p=[dict(x=v.x,y=v.y,z=v.z) for v in faces[0].landmark]
out=root/'human-code/Assets/LocalPortrait/identity-landmarks.json'
out.write_text(json.dumps(dict(points=p,sourceWidth=im.shape[1],sourceHeight=im.shape[0]),indent=2))
print(f'Exported {len(p)} MediaPipe landmarks to {out}')

with mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=0) as segmenter:
    mask=segmenter.process(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)).segmentation_mask
cv2.imwrite(str(out.parent/'identity-foreground.png'),(mask*255).astype('uint8'))
print('Exported foreground confidence mask for safe editor color sampling')
