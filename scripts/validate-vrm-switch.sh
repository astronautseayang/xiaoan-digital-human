#!/usr/bin/env bash
set -euo pipefail
cd /home/yyy/digital-human
source deploy-env.sh >/dev/null 2>&1
set +x
stamp=$(date +%Y%m%d-%H%M%S)
if [[ -d artifacts/validation/vrm-switch ]]; then
 mkdir -p artifacts/validation/run-history
 mv artifacts/validation/vrm-switch "artifacts/validation/run-history/vrm-switch-$stamp"
 for log in logs/avatar-switch-client.log logs/avatar-switch-launch.log logs/avatar-switch-unity-build.log; do
  [[ ! -f "$log" ]] || cp "$log" "artifacts/validation/run-history/vrm-switch-$stamp/"
 done
fi
for avatar in man woman; do
 tools/face-env/bin/python face_feature_extractor.py --input "assets/photo/$avatar.png" --avatar "$avatar" > "logs/face-$avatar-extract.log" 2>&1
done
pkill -f '^(build/|/home/yyy/digital-human/build/)LocalDigitalHuman.x86_64' || true
python - <<'PYWAIT'
import subprocess,time
for _ in range(40):
 if subprocess.run(['pgrep','-f','^(build/|/home/yyy/digital-human/build/)LocalDigitalHuman.x86_64'],stdout=subprocess.DEVNULL).returncode: break
 time.sleep(.25)
else: raise SystemExit('Previous client has not stopped')
PYWAIT
if [[ "${1:-}" != --skip-build ]]; then
 DISPLAY=:1 bash scripts/build-unity.sh > logs/avatar-switch-build.log 2>&1
fi
cp logs/unity-build.log logs/avatar-switch-unity-build.log
export DISPLAY=:1 __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia
timeout 300 build/LocalDigitalHuman.x86_64 -monitor 1 -screen-width 1920 -screen-height 1080 -screen-fullscreen 1 -vrm-switch-self-test -logFile logs/avatar-switch-client.log > logs/avatar-switch-launch.log 2>&1
python - <<'PY'
import json
from pathlib import Path
j=json.loads(Path('artifacts/validation/vrm-switch/runtime.json').read_text())
assert j['passed'],j['error']
for s in j['samples']:
 assert len(s['rawFrames'])>=180 and max(s['rawFrames'])<=33
 print(s['avatar'],len(s['rawFrames']),s['maxFrameMs'],s['soleGap'])
print('Runtime switching, UI raycasts, continuous audio, rollback and model profiles passed')
PY
python scripts/audit-vrm-switch.py
