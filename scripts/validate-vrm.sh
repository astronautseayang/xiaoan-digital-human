#!/usr/bin/env bash
set -euo pipefail
source /home/yyy/digital-human/deploy-env.sh >/dev/null 2>&1
set +x
cd /home/yyy/digital-human
stamp=$(date +%Y%m%d-%H%M%S)
if [[ -d artifacts/validation/vrm-stage1 ]]; then
 mkdir -p artifacts/validation/run-history
 mv artifacts/validation/vrm-stage1 "artifacts/validation/run-history/vrm-stage1-$stamp"
fi
bash scripts/build-unity.sh > logs/vrm-validation-build.log 2>&1
cp logs/unity-build.log logs/vrm-stage1-build.log
systemctl --user start human-llm human-tts human-gateway
export DISPLAY=:1 __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia
timeout 300 build/LocalDigitalHuman.x86_64 -screen-width 1920 -screen-height 1080 -screen-fullscreen 1 -vrm-self-test -logFile logs/vrm-stage1-client.log

python scripts/audit-vrm.py
