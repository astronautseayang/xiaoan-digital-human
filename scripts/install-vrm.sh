#!/usr/bin/env bash
set -euo pipefail
cd /home/yyy/digital-human
if [[ ! -f tools/univrm-0.128.1/Assets/VRM10/package.json ]]; then
 archive=$(mktemp)
 curl -fL --retry 3 https://codeload.github.com/vrm-c/UniVRM/tar.gz/refs/tags/v0.128.1 -o "$archive"
 echo "c5bb683b13aeade345428e9644f762387fbf23d90d35cc8d1e8eb74688355fc9  $archive" | sha256sum -c -
 mkdir -p tools/univrm-0.128.1
 tar -xzf "$archive" --strip-components=1 -C tools/univrm-0.128.1
 rm "$archive"
fi
python - <<'PY'
from pathlib import Path
import json,shutil,hashlib
p=Path('human-code/Packages/manifest.json');j=json.loads(p.read_text())
j['dependencies'].update({'com.vrmc.gltf':'file:../../tools/univrm-0.128.1/Assets/UniGLTF','com.vrmc.vrm':'file:../../tools/univrm-0.128.1/Assets/VRM10'})
p.write_text(json.dumps(j,indent=2)+'\n')
patch=Path('tools/univrm-0.128.1/Assets/VRM10/Runtime/IO/Material/URP/Import/Materials/UrpVrm10MToonMaterialImporter.cs')
patch.write_text(patch.read_text().replace('MToon10Meta.URPUnityShaderName','MToon10Meta.UnityUrpShaderName'))
shader=Path('tools/univrm-0.128.1/Assets/VRM10/MToon10/Shaders/vrmc_materials_mtoon_forward_vertex.hlsl')
shader.write_text(shader.read_text().replace('MToon_TransformObjectToWorldDir(v.tangentOS)', 'MToon_TransformObjectToWorldDir(v.tangentOS.xyz)'))

PY
python scripts/sync-avatar-assets.py
