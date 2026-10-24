#!/usr/bin/env bash
set -Eeuo pipefail
cd /home/yyy/digital-human
export PYTHONNOUSERSITE=1
export PYTHONPATH=/home/yyy/digital-human
asr_python=/home/yyy/miniforge3/envs/human-gsv-v2/bin/python
# Complete SHA256-verified local caches do not contact the network.
"$asr_python" scripts/download-sensevoice.py
exec "$asr_python" -m uvicorn gateway.app:app --host 127.0.0.1 --port 9881
