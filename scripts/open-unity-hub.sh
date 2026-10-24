#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
exec /home/yyy/digital-human/tools/unity-hub/root/usr/lib/unityhub/unityhub --disable-setuid-sandbox "$@"
