#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
systemctl --user start human-llm human-tts human-gateway human-face
python - <<'READY'
import json,time,urllib.request
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(120):
    try:
        with opener.open('http://127.0.0.1:9881/ready', timeout=3) as response:
            if json.load(response).get('ready'):
                break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit('服务尚未就绪，请检查 logs/tts.log、logs/llm.log 和 logs/gateway.log。')
READY
exec bash /home/yyy/digital-human/scripts/run-client.sh "$@"
