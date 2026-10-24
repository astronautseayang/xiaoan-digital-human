"""Relocate only the published source snapshot; never traverse model caches."""
import argparse
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--python-prefix',required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[1]
legacy_root='/home/'+'yyy/digital-human'
legacy_python='/home/'+'yyy/miniforge3/envs/human-gsv-v2'
paths=[root/'face_feature_extractor.py']
for folder in ('gateway','face','scripts','unity-patches','docs','services'):
    paths.extend((root/folder).rglob('*'))
for path in paths:
    if not path.is_file() or path.resolve()==Path(__file__).resolve() or path.suffix not in ('.py','.sh','.cs','.json','.md','.service'):continue
    old=path.read_text();new=old.replace(legacy_python,str(Path(a.python_prefix).resolve())).replace(legacy_root,str(root))
    if new!=old:path.write_text(new)
(root/'deploy-env.sh').write_text('set -Eeuo pipefail\nexport PYTHONNOUSERSITE=1\nexport PATH="'+str(Path(a.python_prefix).resolve()/'bin')+':$PATH"\nexport BASE="'+str(root)+'"\ncd "$BASE"\nmkdir -p logs artifacts\n')
print('Configured source paths. Review git diff and set your Unity editor/model paths.')
