#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
# Select the physical GPU on hybrid graphics; DISPLAY alone can select llvmpipe.
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
client=/home/yyy/digital-human/build/LocalDigitalHuman.x86_64
if [[ ! -x "$client" ]]; then
  echo 'Unity 客户端尚未构建。激活 Unity 许可证后运行 bash scripts/build-unity.sh。'
  exit 1
fi
curl -fsS --max-time 5 http://127.0.0.1:9881/ready
exec "$client" -screen-width 1280 -screen-height 720 -screen-fullscreen 0 -logFile /home/yyy/digital-human/logs/unity-client.log "$@"
