#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
/home/yyy/miniforge3/envs/human-gsv-v2/bin/python scripts/download-sensevoice.py
systemctl --user start human-llm human-tts human-gateway human-face
bash scripts/health.sh
