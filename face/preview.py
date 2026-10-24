"""Software preview of generated face surfaces and viseme deformation."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
root=Path('/home/yyy/digital-human')
folder=root/'human-code/Assets/LocalPortrait'
data=json.loads((folder/'face.json').read_text())
vertices=np.array(data['vertices']).reshape(-1,3)
uv=np.array(data['uv']).reshape(-1,2)
triangles=np.array(data['triangles']).reshape(-1,3)
texture=np.array(Image.open(folder/'portrait.png').convert('RGB'))
size=360
views=[]
for label,delta in [('Neutral',np.zeros_like(vertices))]+[(s['name'],np.array(s['delta']).reshape(-1,3)) for s in data['shapes']]:
 v=vertices+delta
 xy=np.column_stack((size/2+v[:,0]*size/.29,size/2-v[:,1]*size/.29))
 canvas=np.full((size,size,3),(30,36,46),dtype=np.uint8)
 # Order far-to-near, matching the +Z orthographic Unity camera.
 for indices in triangles[np.argsort(v[triangles,2].mean(axis=1))]:
  p=xy[indices];x0,y0=np.maximum(np.floor(p.min(axis=0)).astype(int),0);x1,y1=np.minimum(np.ceil(p.max(axis=0)).astype(int),size-1)
  if x1<x0 or y1<y0:continue
  matrix=np.vstack((p.T,np.ones(3)))
  if abs(np.linalg.det(matrix))<1e-7:continue
  xx,yy=np.meshgrid(np.arange(x0,x1+1),np.arange(y0,y1+1))
  bary=np.linalg.solve(matrix,np.stack((xx.ravel(),yy.ravel(),np.ones(xx.size))))
  mask=(bary>=-1e-5).all(axis=0)
  coords=uv[indices].T@bary
  tx=np.clip((coords[0]*texture.shape[1]).astype(int),0,texture.shape[1]-1)
  ty=np.clip(((1-coords[1])*texture.shape[0]).astype(int),0,texture.shape[0]-1)
  canvas[yy.ravel()[mask],xx.ravel()[mask]]=texture[ty[mask],tx[mask]]
 panel=Image.fromarray(canvas);ImageDraw.Draw(panel).text((10,10),label,fill='white');views.append(panel)
out=Image.new('RGB',(size*3,size*2))
for i,panel in enumerate(views):out.paste(panel,((i%3)*size,(i//3)*size))
path=root/'artifacts/face/viseme-preview.png';out.save(path);print(path)
