#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
editor=/home/yyy/digital-human/tools/unity-international/Editor/Unity
if [[ ! -x "$editor" ]]; then printf 'Matching international Unity Editor is still downloading.\n'; exit 1; fi
exec "$editor" -projectPath /home/yyy/digital-human/human-code -logFile /home/yyy/digital-human/logs/unity-editor.log
