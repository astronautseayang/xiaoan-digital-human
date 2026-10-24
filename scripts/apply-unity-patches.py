from pathlib import Path
import re, shutil,subprocess
root=Path('/home/yyy/digital-human');project=root/'human-code'
files={
 'LocalHumanStartup.cs':'Assets/Scripts/LocalHuman/LocalHumanStartup.cs',
 'VoiceRecognizerModel.cs':'Assets/Scripts/VoiceRecognition/VoiceRecognizerModel.cs',
 'VoiceTTS.cs':'Assets/Scripts/VoiceSynthesis/VoiceTTS.cs',
 'LLM.cs':'Assets/Scripts/LLM/LLM.cs',
 'LLMLogic.cs':'Assets/Scripts/Logics/LLMLogic.cs',
 'LocalHumanDemo.cs':'Assets/Scripts/LocalHuman/LocalHumanDemo.cs',
 'PortraitImporter.cs':'Assets/Scripts/LocalHuman/Editor/PortraitImporter.cs',
 'LocalAvatarLipSync.cs':'Assets/Scripts/LocalHuman/LocalAvatarLipSync.cs',
}
# Refuse to patch an incomplete checkout.
assert (project/'Assets/Scripts/Logics/LLMLogic.cs').is_file(),'Unity checkout not ready'
tracked=subprocess.check_output(['git','-C',str(project),'ls-tree','-r','--name-only','HEAD'],text=True).splitlines()
voice_paths=[p for p in tracked if p.endswith('/VoiceRecognizerModel.cs')]
assert len(voice_paths)==1,voice_paths
files['VoiceRecognizerModel.cs']=voice_paths[0]
for name,target in files.items():
 dst=project/target;dst.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(root/'unity-patches'/name,dst)
 print('MODIFIED',dst)
cfg=project/'Assets/Resources/LLMConfig.asset'
s=cfg.read_text();s=re.sub(r'^  url:.*$', '  url: http://127.0.0.1:8080/v1/chat/completions',s,flags=re.M)
s=re.sub(r'^  model:.*$', '  model: local-qwen',s,flags=re.M)
s=re.sub(r'^  key:.*$', '  key: ""',s,flags=re.M)
cfg.write_text(s)
print('MODIFIED',cfg,'url=local, model=local-qwen, key=empty')

# Runtime GameApp does not use NUnit; remove its accidental test-only import.
app=project/"Assets/Scripts/Manager/GameApp.cs"
raw=app.read_bytes();app.write_bytes(raw.replace(b"using NUnit.Framework;",b""))
print("MODIFIED",app,"removed unused NUnit test import")

# Sync only active sources. Archive is deliberately outside Unity compilation.
active=project/'Assets/Scripts/LocalHuman'
for old in [active/'AvatarPipeline',active/'LocalHumanMotion.cs',active/'LocalHumanValidation.cs',active/'Editor/ChibiBodyBuilder.cs']:
 if old.is_dir(): shutil.rmtree(old)
 elif old.exists(): old.unlink()
for src in sorted((root/'unity-patches/AvatarPipeline').rglob('*')):
 if src.is_file():
  dst=project/'Assets/Scripts/LocalHuman/AvatarPipeline'/src.relative_to(root/'unity-patches/AvatarPipeline')
  dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
  print('MODIFIED',dst)

# Unity 2022 renamed ListView events. Fix the cached pinned package API usage rather than suppress warnings.
searcher=root/'tools/upm-cache/com.unity.searcher@4.9.2/Editor/Searcher/SearcherControl.cs'
if searcher.exists():
 raw=searcher.read_bytes()
 raw=raw.replace(b'm_ListView.onItemsChosen +=',b'm_ListView.itemsChosen +=').replace(b'm_ListView.onSelectionChange +=',b'm_ListView.selectionChanged +=')
 searcher.write_bytes(raw)
 print('MODIFIED',searcher,'Unity 2022 ListView event names')

for src in (root/"unity-patches/VrmPipeline").rglob("*"):
 if src.is_file():
  dst=project/"Assets/Scripts/LocalHuman/VrmPipeline"/src.relative_to(root/"unity-patches/VrmPipeline")
  dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)

# Remove the archived renderer feature before Unity's OnValidate runs on a clean checkout.
renderer=project/'Assets/Settings/Windows Pipeline Asset_Renderer.asset'
text=renderer.read_text()
for match in list(re.finditer(r'^--- !u!114 &(\d+)\n(?:(?!^--- ).)*?m_Name: Figurine Inverted Hull\n(?:(?!^--- ).)*',text,re.M|re.S)):
 text=text.replace(match.group(0),'').replace('  - {fileID: '+match.group(1)+'}\n','')
text=text.replace('  - {fileID: 0}\n','')
features=re.search(r'  m_RendererFeatures:\n((?:  - .*\n)*)',text)
if features:
 import struct
 ids=re.findall(r'fileID: (-?\d+)',features.group(1))
 mapping=''.join(struct.pack('<q',int(value)).hex() for value in ids)
 text=re.sub(r'^  m_RendererFeatureMap:.*$', '  m_RendererFeatureMap: '+mapping,text,flags=re.M)
renderer.write_text(text)
