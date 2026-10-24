#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
# Select the physical GPU on hybrid graphics; DISPLAY alone can select llvmpipe.
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
if [[ "${1:-}" != '--skip-build' ]]; then bash scripts/build-unity.sh; fi
bash scripts/start-services.sh
export DISPLAY="${DISPLAY:-:1}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"
output=/home/yyy/digital-human/artifacts/validation
mkdir -p "$output/figurine"
client=/home/yyy/digital-human/build/LocalDigitalHuman.x86_64
if pgrep -f "^${client}( |$)" >/dev/null; then
  echo 'Close the running Unity client before validation; single-instance forwarding cannot produce fresh evidence.' >&2
  exit 1
fi
# Keep prior evidence and require this run to create every report and screenshot.
python - <<'ARCHIVE'
from pathlib import Path
from datetime import datetime
import shutil
out=Path('/home/yyy/digital-human/artifacts/validation')
archive=out/'run-history'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
archive.mkdir(parents=True)
for name in ['figurine-startup.json','avatar-acceptance.json','face-pipeline-runtime.json','face-pipeline-input.json','face-pipeline-diffuse.png','figurine']:
    source=out/name
    if source.exists(): shutil.move(str(source),str(archive/name))
(out/'figurine').mkdir()
ARCHIVE
# Player processes deliberately run with graphics; only editor batch commands use -batchmode -quit.
timeout 90 "$client" -screen-width 1920 -screen-height 1080 -screen-fullscreen 1 -logFile "$BASE/logs/figurine-startup.log" -human-startup-self-test "$output/figurine-startup.json"
timeout 300 "$client" -screen-width 1920 -screen-height 1080 -screen-fullscreen 1 -logFile "$BASE/logs/figurine-runtime.log" -human-self-test "$output/figurine"
python scripts/audit-avatar-validation.py
