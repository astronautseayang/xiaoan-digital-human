#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
export DISPLAY="${DISPLAY:-:1}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"
output=/home/yyy/digital-human/artifacts/validation/unity
mkdir -p "$output"
timeout 300 bash scripts/run-client.sh -human-self-test "$output"
cat "$output/unity-runtime.json"
