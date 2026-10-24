"""Build a closed photo-fitted head and a separate solid hair volume.
Back geometry is estimated; the source supplies frontal identity and hair colour.
Run photo_to_face.py first to regenerate the frontal grid and speech morphs.
"""
from pathlib import Path
import json,cv2,numpy as np,mediapipe as mp
from scipy.interpolate import griddata
root=Path('/home/yyy/digital-human');out=root/'human-code/Assets/LocalPortrait'
photo=cv2.imread(str(root/'assets/photo/me.png'));h,w=photo.shape[:2]
with mp.solutions.face_mesh.FaceMesh(static_image_mode=True,max_num_faces=1) as detector:
 p=np.array([[v.x,v.y,v.z] for v in detector.process(cv2.cvtColor(photo,cv2.COLOR_BGR2RGB)).multi_face_landmarks[0].landmark])
scale=.16/abs(p[454,0]-p[234,0]);cols,rows=161,141
xx,yy=np.meshgrid(np.linspace(0,1,cols),np.linspace(0,1,rows));uv=np.column_stack((xx.ravel(),1-yy.ravel()))
xy=np.column_stack(((xx.ravel()-p[1,0])*scale,(p[1,1]-yy.ravel())*scale*h/w))
face_mask=np.zeros((h,w),np.uint8)
oval=sorted(set(i for edge in mp.solutions.face_mesh.FACEMESH_FACE_OVAL for i in edge))
cv2.fillConvexPoly(face_mask,cv2.convexHull(np.round(p[oval,:2]*[w,h]).astype(np.int32)),255)
face_inside=cv2.resize(face_mask,(cols,rows),interpolation=cv2.INTER_NEAREST).ravel()>0
z=griddata(p[:,:2],-p[:,2]*scale,(xx,yy),method='linear',fill_value=0)
v=np.column_stack((xy,z.ravel()))
def tris(mask):
 t=[]
 for y in range(rows-1):
  for x in range(cols-1):
   a=y*cols+x
   for tri in ((a,a+cols,a+1),(a+1,a+cols,a+cols+1)):
    if all(mask[i] for i in tri):t.append(tri)
 return np.array(t,dtype=int)
def boundary(t):
 edges={}
 for a,b,c in t:
  for u,vv in ((a,b),(b,c),(c,a)):
   key=tuple(sorted((int(u),int(vv))))
   if key in edges:edges[key]=None
   else:edges[key]=(int(u),int(vv))
 return [e for e in edges.values() if e is not None]
# A continuous front joins hair and face without an internal UV or geometry seam.
with mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=0) as seg:
 person=seg.process(cv2.cvtColor(photo,cv2.COLOR_BGR2RGB)).segmentation_mask
small=cv2.resize(photo,(cols,rows));dark=small.max(axis=2)<180
person_small=cv2.resize(person,(cols,rows))>.65
# Face and hair are recognised separately; photographed neck/shoulders are excluded.
mask=(face_inside.reshape(rows,cols)|(dark & person_small)).astype(np.uint8)
mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
mask=(cv2.GaussianBlur(mask.astype(np.float32),(7,7),1.2)>.48).astype(np.uint8)
contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
mask[:]=0;cv2.drawContours(mask,[max(contours,key=cv2.contourArea)],-1,1,-1)
# A rounded cranial surface supports hair; the landmark depth supplies facial relief.
hair_z=-.065+.13*np.sqrt(np.clip(1-(xy[:,0]/.17)**2-((xy[:,1]-.045)/.18)**2,0,1))
face_z=cv2.GaussianBlur(z.astype(np.float32),(7,7),0).ravel()*.95+.025
blend=np.clip(cv2.distanceTransform(face_inside.reshape(rows,cols).astype(np.uint8),cv2.DIST_L2,3).ravel()/7,0,1)
depth=hair_z*(1-blend)+face_z*blend
# Long hair follows the back of the shoulders; its length is not used as a face crop.
fall=np.clip((-xy[:,1]-.075)/.075,0,1);fall=fall*fall*(3-2*fall)
hair_region=~face_inside
depth[hair_region]=depth[hair_region]*(1-fall[hair_region])-.15*fall[hair_region]
# Broader soft cheeks and a shorter lower face while keeping the chin at the shoulder.
# Deform geometry and the corresponding speech deltas together; UV identity stays fixed.
chin=(p[1,1]-p[152,1])*scale*h/w
crown=float(xy[mask.ravel()>0,1].max())
yfactor=(.185-(-.085))/(crown-chin)
cheek=1.08+.065*np.exp(-((xy[:,1]+.025)/.065)**2)
xy[:,0]*=cheek
xy[:,1]=-.085+(xy[:,1]-chin)*yfactor
depth=cv2.GaussianBlur(depth.reshape(rows,cols).astype(np.float32),(15,15),2.4).ravel()
v=np.column_stack((xy,depth));t=tris(mask.ravel()>0)
verts=v.tolist();uvs=uv.tolist();source=list(range(len(v)))
# Split vertices that join separate triangle fans, so extrusion remains manifold.
for vertex in range(len(v)):
 incident=np.where((t==vertex).any(axis=1))[0].tolist()
 remaining=set(incident);groups=[]
 while remaining:
  group={remaining.pop()};todo=list(group)
  while todo:
   j=todo.pop();neighbors=[k for k in remaining if len(set(t[j]) & set(t[k]))>=2]
   for k in neighbors:remaining.remove(k);group.add(k);todo.append(k)
  groups.append(group)
 for group in groups[1:]:
  new=len(verts);verts.append(verts[vertex]);uvs.append(uvs[vertex]);source.append(vertex)
  for j in group:t[j,t[j]==vertex]=new
edges=boundary(t);ids=sorted(set(i for e in edges for i in e));tri=t.ravel().tolist();last={i:i for i in ids}
front_count=len(tri);hair_tri=[];skin_tri=[]
cy=.045
# Dense rounded back avoids the old three large angular bands.
for depth,factor in [(-.075,.998),(-.10,.99),(-.13,.965),(-.16,.92),(-.19,.84),(-.215,.72),(-.235,.56),(-.247,.35),(-.253,.15)]:
 nxt={}
 for i in ids:
  nxt[i]=len(verts);verts.append([float(verts[i][0]*factor),float(cy+(verts[i][1]-cy)*factor),min(depth,verts[last[i]][2]-.004)]);uvs.append([float(np.arctan2(verts[-1][0],verts[-1][2]+.065)/(2*np.pi)+.5),float((verts[-1][1]+.18)/.38)]);source.append(-1)
 for a,b in edges:
  wall=[last[b],last[a],nxt[a],last[b],nxt[a],nxt[b]];tri.extend(wall)
  target=skin_tri if (abs(verts[a][0])<.065 and abs(verts[b][0])<.065 and verts[a][1]<-.04 and verts[b][1]<-.04 and depth==-.12) else hair_tri
  target.extend(wall)
 last=nxt
pole=len(verts);verts.append([0,cy,-.255]);uvs.append([.27,.69]);source.append(-1)
for a,b in edges:
 cap=[last[b],last[a],pole];tri.extend(cap);hair_tri.extend(cap)
data=json.loads((out/'face.json').read_text());data['vertices']=np.array(verts).ravel().tolist();data['uv']=np.array(uvs).ravel().tolist();data['triangles']=tri
for shape in data['shapes']:
 old=np.array(shape['delta']).reshape(-1,3);old[:,0]*=cheek;old[:,1]*=yfactor;shape['delta']=np.array([old[i] if i>=0 else np.zeros(3) for i in source]).ravel().tolist()
data['skinUv']=[float(p[151,0]),float(1-p[151,1])];data['frontTriangles']=tri[:front_count];data['shellHairTriangles']=hair_tri;data['shellSkinTriangles']=skin_tri
data['hairVertices']=[];data['hairUv']=[];data['hairTriangles']=[]
(out/'face.json').write_text(json.dumps(data,separators=(',',':')))
# Landmark-painted cartoon features, with no photographic skin pasted onto the mesh.
# Positions, eye/brow contours and smile derive from this identity, not a generic doll.
original=photo.copy()
skin_rgb=np.array([.86,.68,.56])
photo[:]=np.round(np.array([.15,.10,.075])[::-1]*255).astype(np.uint8)
# Broad hair ribbons use source colour values, simplified to four tonal bands.
blur=cv2.GaussianBlur(original,(31,31),0)
luma=cv2.cvtColor(blur,cv2.COLOR_BGR2GRAY).astype(float)/255
ribbon=np.clip(np.round(luma*5)/5,.10,.65)
for c,k in enumerate([.075,.10,.15]):photo[:,:,c]=np.clip((k*.8+ribbon*.12)*255,0,255)
cv2.fillConvexPoly(photo,cv2.convexHull(np.round(p[oval,:2]*[w,h]).astype(np.int32)),tuple((skin_rgb[::-1]*255).astype(int).tolist()),cv2.LINE_AA)
def smooth_contour(contour):
 from scipy.interpolate import splprep,splev
 pts=np.asarray(contour).reshape(-1,2)
 try:
  curve,_=splprep(pts.T,s=0,per=True)
  return np.round(np.column_stack(splev(np.linspace(0,1,160,endpoint=False),curve))).astype(np.int32)
 except ValueError:return pts.astype(np.int32)
def ring(edges):
 adj={}
 for a,b in edges:adj.setdefault(a,[]).append(b);adj.setdefault(b,[]).append(a)
 start=min(adj);order=[start];last=None;at=start
 while True:
  nxt=next(v for v in adj[at] if v!=last)
  if nxt==start:break
  order.append(nxt);last,at=at,nxt
 return np.round(p[order,:2]*[w,h]).astype(np.int32)
def hull(edges):
 ids=sorted(set(i for e in edges for i in e))
 return cv2.convexHull(np.round(p[ids,:2]*[w,h]).astype(np.int32))
for edges in [mp.solutions.face_mesh.FACEMESH_LEFT_EYE,mp.solutions.face_mesh.FACEMESH_RIGHT_EYE]:
 eye=ring(edges);centre=eye.mean(axis=0);eye=smooth_contour(np.round(centre+(eye-centre)*1.055).astype(np.int32))
 cv2.fillPoly(photo,[eye],(235,239,241),cv2.LINE_AA)
 eye_mask=np.zeros((h,w),np.uint8);cv2.fillPoly(eye_mask,[eye],255)
 eye_width=np.ptp(eye[:,0]);radius=max(2,int(eye_width*.205))
 iris=np.zeros_like(photo);iris[:]=photo
 cv2.circle(iris,tuple(np.round(centre).astype(int)),radius,(47,65,82),-1,cv2.LINE_AA)
 cv2.circle(iris,tuple(np.round(centre).astype(int)),max(1,int(radius*.66)),(28,29,32),-1,cv2.LINE_AA)
 cv2.circle(iris,tuple(np.round(centre+[-radius*.25,-radius*.3]).astype(int)),max(1,int(radius*.2)),(248,246,242),-1,cv2.LINE_AA)
 photo[eye_mask>0]=iris[eye_mask>0]
 cv2.polylines(photo,[eye],True,(52,57,66),max(1,int(w*.002)),cv2.LINE_AA)
for edges in [mp.solutions.face_mesh.FACEMESH_LEFT_EYEBROW,mp.solutions.face_mesh.FACEMESH_RIGHT_EYEBROW]:
 brow=hull(edges).reshape(-1,2).astype(float);brow[:,1]=brow[:,1].mean()+(brow[:,1]-brow[:,1].mean())*.48;cv2.fillPoly(photo,[smooth_contour(brow)],(43,48,58),cv2.LINE_AA)
# Retain the person's original smile shape, including the curved inner lip line.
outer=[61,185,40,39,37,0,267,269,270,409,291,375,321,405,314,17,84,181,91,146]
inner=[78,191,80,81,82,13,312,311,310,415,308,324,318,402,317,14,87,178,88,95]
cv2.fillPoly(photo,[smooth_contour(np.round(p[outer,:2]*[w,h]).astype(np.int32))],(113,135,183),cv2.LINE_AA)
cv2.fillPoly(photo,[smooth_contour(np.round(p[inner,:2]*[w,h]).astype(np.int32))],(224,236,243),cv2.LINE_AA)
# A restrained nostril curve makes the fitted nose read without photo shading.
for ids in [[98,97,2],[2,326,327]]:
 cv2.polylines(photo,[np.round(p[ids,:2]*[w,h]).astype(np.int32)],False,(119,150,183),max(1,int(w*.0015)),cv2.LINE_AA)
(out/'skin-palette.json').write_text(json.dumps({'skin_rgb':skin_rgb.tolist(),'style':'landmark-painted features, no photographic skin; same skin tint and shader on face/hands/legs'}))
cv2.imwrite(str(out/'head-texture.png'),photo);(out/'portrait.bytes').write_bytes((out/'head-texture.png').read_bytes())
count={}
for a,b,c in np.array(tri).reshape(-1,3):
 for e in ((a,b),(b,c),(c,a)):
  key=tuple(sorted(map(int,e)));count[key]=count.get(key,0)+1
assert all(c==2 for c in count.values()),'Non-manifold head'
report={'head_closed':True,'head_vertices':len(verts),'boundary_edges':0,'head_min_y':float(np.array(verts)[np.unique(tri),1].min()),'head_max_y':float(np.array(verts)[np.unique(tri),1].max()),'face_depth_metres':float(np.ptp(v[face_inside,2])),'hair_routed_behind_shoulders':True,'anatomical_crown_y':.185,'anatomical_chin_y':-.085,'floor_y':-.49,'anatomical_head_to_total_ratio':2.5,'style':'landmark-fitted rounded chibi with procedural cartoon features, shared matte skin','limitations':'Face fitted from landmarks; cranial and hair volumes are estimated, not a scan of unseen anatomy.'}
(out/'volume-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

# Export the actual fitted volume for independent inspection in Blender or another DCC.
import shutil
export=root/'artifacts/avatar';export.mkdir(parents=True,exist_ok=True)
shutil.copyfile(out/'head-texture.png',export/'head-texture.png')
with (export/'head.obj').open('w') as obj:
 obj.write('mtllib head.mtl\n')
 for x,y,zv in verts:obj.write(f'v {x} {y} {zv}\n')
 for u,vv in uvs:obj.write(f'vt {u} {vv}\n')
 for name,tt in [('photo',data['frontTriangles']),('hair',hair_tri),('skin',skin_tri)]:
  obj.write('usemtl '+name+'\n')
  for a,b,c in np.array(tt).reshape(-1,3)+1:obj.write(f'f {a}/{a} {b}/{b} {c}/{c}\n')
(export/'head.mtl').write_text('newmtl photo\nKd 1 1 1\nmap_Kd head-texture.png\nnewmtl hair\nKd .10 .066 .042\nnewmtl skin\nKd .76 .53 .41\n')
