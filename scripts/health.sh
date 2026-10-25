#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
health_failed=0
health_tmp=$(mktemp -d)
trap 'rm -rf -- "$health_tmp"' EXIT
for port in 8080 9880 9881; do
  case "$port" in 8080) endpoint=health;; 9880) endpoint=openapi.json;; 9881) endpoint=ready;; esac
  if curl -fsS --max-time 5 "http://127.0.0.1:$port/$endpoint" -o "$health_tmp/$port.json"; then
    printf 'PORT %s HTTP OK\n' "$port"
    if [[ "$port" != 9880 ]]; then cat "$health_tmp/$port.json"; printf '\n'; fi
    if [[ "$port" == 9881 ]]; then
      if python3 - "$health_tmp/$port.json" <<'PY'
import json
import sys
try:
    with open(sys.argv[1]) as source:
        data = json.load(source)
    ready = isinstance(data, dict) and data.get('ready') is True
except (OSError, ValueError):
    ready = False
sys.exit(0 if ready else 1)
PY
      then
        printf 'GATEWAY READY\n'
      else
        printf 'GATEWAY NOT READY\n'
        health_failed=1
      fi
    fi
  else
    printf 'PORT %s UNAVAILABLE\n' "$port"
    health_failed=1
  fi
done
if ! systemctl --user --no-pager status human-llm human-tts human-gateway human-face; then
  health_failed=1
fi
exit "$health_failed"
