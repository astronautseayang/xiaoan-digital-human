"""Photo -> MediaPipe face surface + procedural speech morphs for Unity.
Produces an approximate front face, not a metrically accurate full head.
"""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import mediapipe as mp
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('photo', type=Path)
parser.add_argument('--output', type=Path, default=Path('/home/yyy/digital-human/human-code/Assets/LocalPortrait'))
args = parser.parse_args()
image = cv2.imread(str(args.photo))
if image is None:
    raise SystemExit('Cannot read photo: ' + str(args.photo))
h, w = image.shape[:2]
with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=2, refine_landmarks=False, min_detection_confidence=0.5) as detector:
    result = detector.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
if not result.multi_face_landmarks or len(result.multi_face_landmarks) != 1:
    raise SystemExit('Require exactly one clearly visible frontal face')
landmarks = np.array([[p.x, p.y, p.z] for p in result.multi_face_landmarks[0].landmark], dtype=np.float64)
# Normalize face width to 0.16 metres. MediaPipe Z uses the same unit as X.
width = abs(landmarks[454, 0] - landmarks[234, 0])
if width < 0.05:
    raise SystemExit('Face too small or profile view; provide a frontal portrait')
scale = 0.16 / width
vertices = np.column_stack(((landmarks[:, 0] - landmarks[1, 0]) * scale,
                            (landmarks[1, 1] - landmarks[:, 1]) * scale * h / w,
                            -landmarks[:, 2] * scale))
# MediaPipe tessellation contains oriented edges; recover unique triangular faces.
adjacency = {i: set() for i in range(len(vertices))}
for a, b in mp.solutions.face_mesh.FACEMESH_TESSELATION:
    adjacency[a].add(b); adjacency[b].add(a)
triangles = []
for a in adjacency:
    for b in adjacency[a]:
        if b <= a: continue
        for c in adjacency[a] & adjacency[b]:
            if c <= b: continue
            tri = [a, b, c]
            if np.cross(vertices[b] - vertices[a], vertices[c] - vertices[a])[2] < 0:
                tri = [a, c, b]
            triangles.extend(tri)
# Fill the eye openings with the original photo texture; eye animation is not used.
for eye_edges in (mp.solutions.face_mesh.FACEMESH_LEFT_EYE, mp.solutions.face_mesh.FACEMESH_RIGHT_EYE):
    ring_adjacency = {}
    for a, b in eye_edges:
        ring_adjacency.setdefault(a, set()).add(b)
        ring_adjacency.setdefault(b, set()).add(a)
    start = min(ring_adjacency)
    ring = [start]
    previous, current = None, start
    while True:
        following = next(v for v in sorted(ring_adjacency[current]) if v != previous)
        if following == start: break
        ring.append(following)
        previous, current = current, following
    for i in range(1, len(ring) - 1):
        a, b, c = ring[0], ring[i], ring[i + 1]
        if np.cross(vertices[b] - vertices[a], vertices[c] - vertices[a])[2] < 0:
            b, c = c, b
        triangles.extend([a, b, c])
# Deform lips and surrounding soft tissue. Keep topology identical for all morphs.
center = (vertices[13] + vertices[14]) / 2
half_width = np.linalg.norm(vertices[291, :2] - vertices[61, :2]) / 2
rel = vertices - center
weight = np.exp(-((rel[:, 0] / (half_width * 1.8)) ** 2 + (rel[:, 1] / (half_width * 1.4)) ** 2) * 2)
# Explicit inner lip arcs avoid a closed neutral mouth moving as one surface.
upper_inner = {78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308}
lower_inner = {78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308}
direction = np.where(rel[:, 1] >= 0, 0.35, -1.0)
for idx in upper_inner - lower_inner: direction[idx] = 0.35
for idx in lower_inner - upper_inner: direction[idx] = -1.0
shapes = []
for name, opening, horizontal, protrusion in [('A', .022, 1.02, 0), ('I', .006, 1.22, 0), ('U', .010, .65, .007), ('E', .012, 1.16, 0), ('O', .018, .74, .005)]:
    delta = np.zeros_like(vertices)
    delta[:, 0] = rel[:, 0] * (horizontal - 1) * weight * .35
    delta[:, 1] = direction * opening * weight * .28
    delta[:, 2] = protrusion * weight
    shapes.append({'name': name, 'delta': delta.astype(float).ravel().tolist()})
output = args.output
output.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(output / 'portrait.png'), image)
# A single continuous textured surface prevents duplicated face/teeth layers.
from scipy.interpolate import griddata
with mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=0) as segmenter:
    mask = segmenter.process(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).segmentation_mask
alpha = cv2.GaussianBlur(np.clip((mask-.25)/.35,0,1),(3,3),0)
alpha *= np.clip((h-1-np.arange(h))[:,None]/75,0,1)
rgba = np.dstack((image,(alpha*255).astype(np.uint8)))
cv2.imwrite(str(output / 'silhouette.png'),rgba)
(output / 'portrait.bytes').write_bytes((output / 'silhouette.png').read_bytes())
# Colour samples are taken from actual skin, hair, highlight and background pixels.
regions = [(int(w*.4),int(h*.45)),(int(w*.35),int(h*.2)),(int(w*.45),int(h*.7)),(10,10)]
palette = [np.median(image[max(0,y-8):y+9,max(0,x-8):x+9].reshape(-1,3),axis=0)[::-1]/255 for x,y in regions]
np.random.seed(1)
colors=image.reshape(-1,3)[::17].astype(np.float32)
# The clothing texture uses original photographic colours in a subtle woven pattern.
cloth=np.zeros((256,256,3),np.uint8)
for y in range(256):
    for x in range(256):
        base=palette[0]*.58+palette[1]*.42
        accent=base*.84+palette[3]*.16 if x%48<3 else base
        factor=.86+.14*((x+y)%4)/3
        cloth[y,x]=np.clip(accent[::-1]*factor*255,0,255)
cv2.imwrite(str(output/'cloth.png'),cloth)
(output/'cloth.bytes').write_bytes((output/'cloth.png').read_bytes())
(output/'palette.json').write_text(json.dumps({'colors':[c.tolist() for c in palette]}))
cols, rows=161,141
xx,yy=np.meshgrid(np.linspace(0,1,cols),np.linspace(0,1,rows))
zz=griddata(landmarks[:,:2],vertices[:,2],(xx,yy),method='linear',fill_value=-.025)
vertices=np.column_stack(((xx.ravel()-landmarks[1,0])*scale,(landmarks[1,1]-yy.ravel())*scale*h/w,cv2.GaussianBlur(zz.astype(np.float32),(11,11),0).ravel()*.14))
triangles=[]
for y in range(rows-1):
    for x in range(cols-1):
        a=y*cols+x
        triangles.extend([a,a+cols,a+1,a+1,a+cols,a+cols+1])
rel=vertices-center
weight=np.exp(-((rel[:,0]/(half_width*1.4))**2+(rel[:,1]/(half_width*.9))**2)*2)
# The photographed teeth are rigid: no morph displacement inside the inner lips.
inner=[78,191,80,81,82,13,312,311,310,415,308,324,318,402,317,14,87,178,88,95]
teeth=np.zeros((h,w),np.uint8)
polygon=np.round(landmarks[inner,:2]*[w,h]).astype(np.int32)
cv2.fillPoly(teeth,[polygon],255)
teeth=cv2.dilate(teeth,np.ones((5,5),np.uint8))
locked=cv2.resize(teeth,(cols,rows),interpolation=cv2.INTER_NEAREST).ravel()>0
weight[locked]=0
shapes=[]
for name,opening,horizontal in [('A',.005,1.01),('I',.0015,1.06),('U',.0025,.94),('E',.003,1.04),('O',.004,.95)]:
    delta=np.zeros_like(vertices)
    delta[:,0]=rel[:,0]*(horizontal-1)*weight
    delta[:,1]=np.where(rel[:,1]>0,.25,-1)*opening*weight
    shapes.append({'name':name,'delta':delta.ravel().tolist()})
data={'vertices':vertices.ravel().tolist(),'uv':np.column_stack((xx.ravel(),1-yy.ravel())).ravel().tolist(),
      'triangles':triangles,'shapes':shapes,'mouthCenter':center.tolist(),'mouthHalfWidth':float(half_width),
      'portraitBounds':[float(-landmarks[1,0]*scale),float((landmarks[1,1]-1)*scale*h/w),float(scale),float(scale*h/w)]}
(output / 'face.json').write_text(json.dumps(data, separators=(',', ':')))
report = {'source_sha256': hashlib.sha256(args.photo.read_bytes()).hexdigest(), 'vertices': len(vertices),
          'triangles': len(triangles) // 3, 'blendshapes': [s['name'] for s in shapes],
          'locked_teeth_vertices':int(locked.sum()),'limitations':'A continuous frontal photo surface with estimated depth, hair silhouette and rigid teeth; no reconstructed back of head.'}
assert all(np.isfinite(np.array(s['delta'])).all() and np.linalg.norm(s['delta']) > 0 for s in shapes)
assert len(triangles) > 2000
(output / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
