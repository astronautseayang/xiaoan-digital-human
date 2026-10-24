"""Offline C# compilation against editor assemblies. Does not replace a licensed Unity import/build."""
from pathlib import Path
import subprocess
root=Path('/home/yyy/digital-human')
data=root/'tools/unity/Editor/Data'
refs=list((data/'NetStandard/ref/2.1.0').glob('*.dll'))
if not refs: refs=list((data/'NetStandard/ref').rglob('*.dll'))
refs+=list((data/'Managed/UnityEngine').glob('*.dll'))
refs+=list((data/'NetStandard/compat/2.1.0/shims/netfx').glob('*.dll'))
template=data/'Resources/PackageManager/ProjectTemplates/libcache/com.unity.template.universal-2d-2.1.2/ScriptAssemblies'
refs+=[p for p in template.glob('*.dll') if not p.name.startswith('Assembly-CSharp')]
refs+=list((root/'human-code/Assets').rglob('*.dll'))
# Avoid two references with the same assembly filename.
refs=list({p.name:p for p in refs}.values())
sources=sorted((root/'human-code/Assets').rglob('*.cs'))
response=root/'logs/unity-source-check.rsp'
response.write_text('\n'.join(['-nologo','-target:library','-unsafe+','-nostdlib+','-langversion:9.0','-define:UNITY_EDITOR,UNITY_EDITOR_LINUX,UNITY_STANDALONE_LINUX,UNITY_2022_3,UNITY_2022_3_OR_NEWER,UNITY_2022_2_OR_NEWER,UNITY_2021_3_OR_NEWER,ENABLE_UNITY_COLLECTIONS_CHECKS',f'-out:"{root}/artifacts/validation/UnitySourceCheck.dll"',*[f'-r:"{p}"' for p in refs],*[f'"{p}"' for p in sources]]))
cmd=[str(data/'NetCoreRuntime/dotnet'),str(data/'DotNetSdkRoslyn/csc.dll'),'@'+str(response)]
print('COMMAND',cmd,'sources',len(sources),'references',len(refs),flush=True)
subprocess.run(cmd,check=True)
print('OFFLINE C# SOURCE CHECK PASSED; actual Unity project compilation/build still requires activation.',flush=True)
