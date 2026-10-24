#!/usr/bin/env bash
set -euo pipefail
source /home/yyy/digital-human/deploy-env.sh >/dev/null 2>&1
set +x
cd /home/yyy/digital-human
if [[ -d artifacts/validation/interactive-motion ]]; then
 mkdir -p artifacts/validation/run-history
 mv artifacts/validation/interactive-motion "artifacts/validation/run-history/interactive-motion-$(date +%Y%m%d-%H%M%S)"
fi
pkill -f '^(build/|/home/yyy/digital-human/build/)LocalDigitalHuman.x86_64' || true
python - <<'PYWAIT'
import subprocess,time
for _ in range(60):
 if subprocess.run(['pgrep','-f','^(build/|/home/yyy/digital-human/build/)LocalDigitalHuman.x86_64'],stdout=subprocess.DEVNULL).returncode: break
 time.sleep(.25)
else: raise SystemExit('Previous client has not stopped')
PYWAIT
if [[ "${1:-}" != --skip-build ]]; then bash scripts/build-unity.sh > logs/interactive-motion-build-command.log 2>&1; fi
export DISPLAY=:1 __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia
timeout 150 build/LocalDigitalHuman.x86_64 -screen-width 1280 -screen-height 720 -screen-fullscreen 0 -interactive-motion-self-test -logFile logs/interactive-motion-client.log > logs/interactive-motion-launch.log 2>&1
python - <<'PY'
import json
from pathlib import Path
report=json.loads(Path('artifacts/validation/interactive-motion/runtime.json').read_text())
assert report['passed'],report.get('error')
assert len(report['avatars'])==1
print(json.dumps(report,ensure_ascii=False,indent=2))
PY
