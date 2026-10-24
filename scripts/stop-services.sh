#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
systemctl --user stop human-client.service 2>/dev/null || true
systemctl --user stop human-face human-gateway human-tts human-llm
sync
printf 'Digital human services stopped; model files and configuration retained.\n'
