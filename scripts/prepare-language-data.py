"""Install required English G2P corpora without runtime network downloads."""
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile
root=Path('/home/yyy/digital-human/GPT-SoVITS/runtime/nltk_data')
root.mkdir(parents=True,exist_ok=True)
for category,name in [('corpora','cmudict'),('taggers','averaged_perceptron_tagger'),('taggers','averaged_perceptron_tagger_eng')]:
    target=root/category/name
    if not target.is_dir() or not (root/category/f'{name}.zip').is_file():
        url=f'https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/{category}/{name}.zip'
        for attempt in range(1,4):
            try:
                data=urllib.request.urlopen(url,timeout=60).read()
                archive=zipfile.ZipFile(io.BytesIO(data))
                assert archive.testzip() is None
                for member in archive.infolist():
                    assert not Path(member.filename).is_absolute() and '..' not in Path(member.filename).parts
                (root/category).mkdir(parents=True,exist_ok=True)
                (root/category/f'{name}.zip').write_bytes(data)
                archive.extractall(root/category)
                print('INSTALLED',name,'source',url,'sha256',hashlib.sha256(data).hexdigest())
                break
            except Exception as exc:
                print('FAILED',name,attempt,repr(exc))
                if attempt==3: raise
for p in [root,*root.rglob('*')]:
    p.chmod(p.stat().st_mode & ~0o022)
Path('/home/yyy/digital-human/GPT-SoVITS/GPT_SoVITS/pretrained_models/fast_langdetect').mkdir(exist_ok=True)
import nltk
nltk.data.path.insert(0,str(root))
print('CMU entries',len(nltk.corpus.cmudict.entries()))
print('English tagger',nltk.pos_tag(['hello']))
