#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
for port in 8080 9880 9881; do
  case "$port" in 8080) endpoint=health;; 9880) endpoint=openapi.json;; 9881) endpoint=ready;; esac
  if curl -fsS --max-time 5 "http://127.0.0.1:$port/$endpoint" -o /tmp/human-health-$port.json; then
    printf 'PORT %s HTTP OK\n' "$port"
    if [[ "$port" != 9880 ]]; then cat /tmp/human-health-$port.json; fi
  else printf 'PORT %s UNAVAILABLE\n' "$port"; fi
done
systemctl --user --no-pager status human-llm human-tts human-gateway human-face || true
