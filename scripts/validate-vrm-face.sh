#!/usr/bin/env bash
set -euo pipefail
source /home/yyy/digital-human/deploy-env.sh >/dev/null 2>&1
set +x
cd /home/yyy/digital-human
stamp=$(date +%Y%m%d-%H%M%S)
if [[ -d artifacts/validation/vrm-stage3 ]]; then
 mkdir -p artifacts/validation/run-history
 mv artifacts/validation/vrm-stage3 "artifacts/validation/run-history/vrm-stage3-$stamp"
fi
if [[ ! -f artifacts/validation/face-stage2/ExportedFaceData/face_params.json ]]; then
 tools/face-env/bin/python face_feature_extractor.py --input assets/photo/woman.png --output_dir artifacts/validation/face-stage2/ExportedFaceData
fi
pkill -f '^/home/yyy/digital-human/build/LocalDigitalHuman.x86_64' || true
bash scripts/build-unity.sh > logs/vrm-face-stage3-build-command.log 2>&1
cp logs/unity-build.log logs/vrm-face-stage3-build.log
export DISPLAY=:1 __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia
timeout 180 build/LocalDigitalHuman.x86_64 -screen-width 1920 -screen-height 1080 -screen-fullscreen 1 -vrm-face-self-test -logFile logs/vrm-face-stage3-client.log > logs/vrm-face-stage3-launch.log 2>&1
python scripts/audit-vrm-face.py
