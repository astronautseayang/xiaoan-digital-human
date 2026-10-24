"""Export the generated portrait as a portable glTF 2.0 mesh with real morph targets."""
import argparse
import json
from pathlib import Path
import struct
import numpy as np
parser=argparse.ArgumentParser()
parser.add_argument('--input',type=Path,default=Path('/home/yyy/digital-human/human-code/Assets/LocalPortrait'))
parser.add_argument('--output',type=Path,default=Path('/home/yyy/digital-human/artifacts/face/photo-face.glb'))
args=parser.parse_args()
face=json.loads((args.input/'face.json').read_text())
blob=bytearray();views=[];accessors=[]
def view(raw,target=None):
 while len(blob)%4:blob.append(0)
 v={'buffer':0,'byteOffset':len(blob),'byteLength':len(raw)}
 if target:v['target']=target
 views.append(v);blob.extend(raw);return len(views)-1
def accessor(array,kind,component=5126,target=34962):
 a=np.asarray(array,dtype='<f4' if component==5126 else '<u2')
 index=view(a.tobytes(),target)
 entry={'bufferView':index,'componentType':component,'count':len(a),'type':kind}
 if component==5126 and kind=='VEC3':entry.update(min=a.min(axis=0).tolist(),max=a.max(axis=0).tolist())
 accessors.append(entry);return len(accessors)-1
vertices=np.asarray(face['vertices'],dtype=np.float32).reshape(-1,3)
triangles=np.asarray(face['triangles'],dtype=np.uint16).reshape(-1,3)
normals=np.zeros_like(vertices)
for a,b,c in triangles:
 n=np.cross(vertices[b]-vertices[a],vertices[c]-vertices[a]);normals[a]+=n;normals[b]+=n;normals[c]+=n
normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-8)
uv=np.asarray(face['uv'],dtype=np.float32).reshape(-1,2);uv[:,1]=1-uv[:,1]
primitive={'attributes':{'POSITION':accessor(vertices,'VEC3'),'NORMAL':accessor(normals,'VEC3'),'TEXCOORD_0':accessor(uv,'VEC2')},'indices':accessor(triangles.ravel(),'SCALAR',5123,34963),'material':0,'targets':[]}
for shape in face['shapes']:
 delta=np.asarray(shape['delta'],dtype=np.float32).reshape(-1,3)
 assert delta.shape==vertices.shape and np.isfinite(delta).all()
 primitive['targets'].append({'POSITION':accessor(delta,'VEC3')})
image_view=view((args.input/'portrait.png').read_bytes())
while len(blob)%4:blob.append(0)
doc={'asset':{'version':'2.0','generator':'Local Digital Human photo surface exporter'},'extensionsUsed':['KHR_materials_unlit'],'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0,'name':'PhotoFace'}],'meshes':[{'name':'PhotoFace','weights':[0.0]*5,'extras':{'targetNames':[x['name'] for x in face['shapes']]},'primitives':[primitive]}],'buffers':[{'byteLength':len(blob)}],'bufferViews':views,'accessors':accessors,'images':[{'bufferView':image_view,'mimeType':'image/png'}],'textures':[{'source':0}],'materials':[{'name':'Portrait','doubleSided':True,'pbrMetallicRoughness':{'baseColorTexture':{'index':0},'metallicFactor':0,'roughnessFactor':1},'extensions':{'KHR_materials_unlit':{}}}]}
raw=json.dumps(doc,separators=(',',':')).encode();raw+=b' '*((-len(raw))%4)
total=12+8+len(raw)+8+len(blob)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_bytes(struct.pack('<4sII',b'glTF',2,total)+struct.pack('<I4s',len(raw),b'JSON')+raw+struct.pack('<I4s',len(blob),b'BIN\0')+blob)
# Check boundaries and the exported target schema on the artifact itself.
data=args.output.read_bytes();assert len(data)==struct.unpack_from('<I',data,8)[0]
parsed=json.loads(data[20:20+len(raw)]);assert len(parsed['meshes'][0]['primitives'][0]['targets'])==5
print('EXPORTED',args.output,'bytes',len(data),'vertices',len(vertices),'morphs',parsed['meshes'][0]['extras']['targetNames'])
