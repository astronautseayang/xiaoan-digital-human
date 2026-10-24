"""478 relative-depth landmarks, normalized identity controls, affine aligned diffuse.
Affine alignment removes roll/scale/translation, not perspective or hidden face regions.
"""
import argparse, base64, json, math, os, tempfile
from pathlib import Path
import cv2
import mediapipe as mp
import numpy as np
MAX_BYTES = 16 * 1024 * 1024

def normalize(value, lo, hi):
    return float(np.clip((value-lo)/(hi-lo), 0, 1))

def extract(data, size=512):
    if not data or len(data)>MAX_BYTES:
        raise ValueError('Photo must be between 1 byte and 16 MiB')
    image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    if image is None: raise ValueError('Cannot decode photo')
    h,w=image.shape[:2]
    if min(h,w)<96 or h*w>32_000_000: raise ValueError('Dimensions must be >=96 and <=32 megapixels')
    scale=min(1.,1600/max(h,w))
    inference=cv2.resize(image,None,fx=scale,fy=scale) if scale<1 else image
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True,max_num_faces=2,refine_landmarks=True,min_detection_confidence=.6) as mesh:
        faces=mesh.process(cv2.cvtColor(inference,cv2.COLOR_BGR2RGB)).multi_face_landmarks
    if not faces or len(faces)!=1 or len(faces[0].landmark)!=478:
        raise ValueError('Exactly one visible face with 478 landmarks is required')
    points=np.array([(v.x,v.y,v.z) for v in faces[0].landmark],np.float64)
    px=points[:,:2]*[w,h]
    distance=lambda a,b: float(np.linalg.norm(px[a]-px[b]))
    fw=distance(234,454)
    if fw<32: raise ValueError('Face is too small')
    eye_aspect=(distance(159,145)+distance(386,374))/max(distance(33,133)+distance(362,263),1)
    eye_spacing=distance(133,362)/fw
    mouth_width=distance(61,291)/fw
    jaw_width=distance(172,397)/fw
    roundness=distance(148,377)/max(distance(172,397),1)
    left,right=(px[33]+px[133])/2,(px[362]+px[263])/2
    axis=right-left; eye_distance=float(np.linalg.norm(axis)); axis/=eye_distance
    vertical=np.array([-axis[1],axis[0]])
    rise=float(np.dot(px[13]-(px[61]+px[291])/2,vertical))
    angle=math.degrees(math.atan2(rise,distance(61,291)/2))
    weights=dict(EyeScale=normalize(eye_aspect,.15,.42),EyeDistance=normalize(eye_spacing,.16,.36),
        SmileDefault=normalize(angle,-12,18),JawWidth=normalize(jaw_width,.55,.90),
        ChinRoundness=normalize(roundness,.14,.32),MouthWidth=normalize(mouth_width,.28,.55))
    src=np.float32([left,right,(left+right)/2+vertical*eye_distance])
    dst=np.float32([[size*.32,size*.38],[size*.68,size*.38],[size*.5,size*.74]])
    affine=cv2.getAffineTransform(src,dst)
    aligned=cv2.warpAffine(cv2.bilateralFilter(image,9,48,7),affine,(size,size),borderMode=cv2.BORDER_REFLECT_101)
    ap=cv2.transform(px.astype(np.float32)[None],affine)[0]
    oval=[i for edge in mp.solutions.face_mesh.FACEMESH_FACE_OVAL for i in edge]
    mask=np.zeros((size,size),np.uint8)
    cv2.fillConvexPoly(mask,cv2.convexHull(ap[oval].astype(np.int32)),255)
    mask=cv2.GaussianBlur(mask,(0,0),size*.018)
    rgba=cv2.cvtColor(aligned,cv2.COLOR_BGR2BGRA); rgba[:,:,3]=mask
    ok,png=cv2.imencode('.png',rgba)
    if not ok: raise ValueError('PNG encode failed')
    cheeks=[dict(x=float(np.clip(ap[i,0]/size,.05,.95)),y=float(np.clip(1-ap[i,1]/size,.05,.95))) for i in (50,280)]
    return dict(schemaVersion=1,sourceWidth=w,sourceHeight=h,landmarkSpace='mediapipe-normalized-relative-depth',
        landmarks=[dict(x=float(x),y=float(y),z=float(z)) for x,y,z in points],blendShapes=weights,
        metrics=dict(eyeAspect=eye_aspect,eyeDistance=eye_spacing,mouthWidth=mouth_width,jawWidth=jaw_width,chinRoundness=roundness,smileAngleDegrees=angle),
        textureWidth=size,textureHeight=size,textureMime='image/png',textureBase64=base64.b64encode(png).decode('ascii'),
        cheekUV=cheeks,upperEyeEdge=float(ap[[159,386],1].mean()/size))

def save(packet,output):
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=output.parent,suffix='.tmp',delete=False) as stream:
        stream.write(json.dumps(packet,ensure_ascii=False,allow_nan=False)); temp=stream.name
    os.replace(temp,output)
    output.with_suffix('.png').write_bytes(base64.b64decode(packet['textureBase64']))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('photo',type=Path)
    parser.add_argument('--output',type=Path,default=Path('artifacts/face/latest.json')); args=parser.parse_args()
    packet=extract(args.photo.read_bytes()); save(packet,args.output)
    print(json.dumps(dict(output=str(args.output),landmarks=len(packet['landmarks']),blendShapes=packet['blendShapes'])))
