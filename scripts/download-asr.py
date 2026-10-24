import hashlib
import json
from pathlib import Path
import subprocess
import sys
root=Path('/home/yyy/digital-human')
for entry in json.loads((root/'logs/asr-model-tree.json').read_text()):
    if entry['type']!='file' or entry['path'] not in ('config.json','model.bin','tokenizer.json','vocabulary.txt'):continue
    dest=root/'models/asr/faster-whisper-tiny'/entry['path']
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.is_file() or dest.stat().st_size!=entry['size']:
        subprocess.run([sys.executable,str(root/'scripts/parallel-download.py'),f"https://huggingface.co/Systran/faster-whisper-tiny/resolve/main/{entry['path']}?download=true&deployment=20261022",str(dest)],check=True)
    h=hashlib.sha256(dest.read_bytes()).hexdigest()
    if entry.get('lfs',{}).get('oid'):assert h==entry['lfs']['oid']
    print('ASR VERIFIED',dest,h,flush=True)
