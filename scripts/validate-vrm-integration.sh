#!/usr/bin/env bash
set -euo pipefail
source /home/yyy/digital-human/deploy-env.sh >/dev/null 2>&1
set +x
cd /home/yyy/digital-human
stamp=$(date +%Y%m%d-%H%M%S)
if [[ -d artifacts/validation/vrm-stage4 ]]; then
 mkdir -p artifacts/validation/run-history
 mv artifacts/validation/vrm-stage4 "artifacts/validation/run-history/vrm-stage4-$stamp"
fi
if [[ ! -f artifacts/validation/face-stage2/ExportedFaceData/face_params.json ]]; then
 tools/face-env/bin/python face_feature_extractor.py --input assets/photo/woman.png --output_dir artifacts/validation/face-stage2/ExportedFaceData
fi
pkill -f '^(build/|/home/yyy/digital-human/build/)LocalDigitalHuman.x86_64' || true
python - <<'PYWAIT'
import subprocess,time
for _ in range(60):
 if subprocess.run(['pgrep','-f','^(build/|/home/yyy/digital-human/build/)LocalDigitalHuman.x86_64'],stdout=subprocess.DEVNULL).returncode: break
 time.sleep(.25)
else: raise SystemExit('Previous client has not stopped')
PYWAIT
if [[ "${1:-}" != --skip-build ]]; then
 bash scripts/build-unity.sh > logs/vrm-integration-stage4-build-command.log 2>&1
fi
cp logs/unity-build.log logs/vrm-integration-stage4-build.log
export DISPLAY=:1 __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia
timeout 300 build/LocalDigitalHuman.x86_64 -monitor 1 -screen-width 1920 -screen-height 1080 -screen-fullscreen 1 -vrm-integration-self-test -logFile logs/vrm-integration-stage4-client.log > logs/vrm-integration-stage4-launch.log 2>&1
python scripts/audit-vrm-integration.py
