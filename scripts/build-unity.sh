#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
# Select the physical GPU on hybrid graphics; DISPLAY alone can select llvmpipe.
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
editor=/home/yyy/digital-human/tools/unity-international/Editor/Unity
if [[ ! -x "$editor" ]]; then echo 'Unity Editor is not installed yet'; exit 1; fi
bash scripts/install-vrm.sh
python scripts/apply-unity-patches.py > logs/apply-figurine.log
export DISPLAY="${DISPLAY:-:1}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"
export HUMAN_BUILD_PATH=/home/yyy/digital-human/build/LocalDigitalHuman.x86_64
timeout 900 "$editor" -batchmode -quit -force-glcore -job-worker-count 4 -projectPath /home/yyy/digital-human/human-code -buildTarget Linux64 -executeMethod LocalHuman.Editor.PortraitImporter.BuildLinux -logFile /home/yyy/digital-human/logs/unity-build.log
