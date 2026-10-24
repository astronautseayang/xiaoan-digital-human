import hashlib
import json
from pathlib import Path
root=Path('/home/yyy/digital-human')
base=root/'GPT-SoVITS/GPT_SoVITS/pretrained_models'
for entry in json.loads((root/'logs/hf-model-tree.json').read_text()):
 name=entry['path']
 if entry['type']!='file' or not (name.startswith(('chinese-roberta-wwm-ext-large/','chinese-hubert-base/')) or name in ('gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt','gsv-v2final-pretrained/s2G2333k.pth')):continue
 p=base/name
 assert p.stat().st_size==entry['size'],p
 h=hashlib.sha256()
 with p.open('rb') as f:
  while block:=f.read(4*1024*1024):h.update(block)
 if entry.get('lfs',{}).get('oid'):assert h.hexdigest()==entry['lfs']['oid'],p
 print('VERIFIED',name,p.stat().st_size,h.hexdigest())
