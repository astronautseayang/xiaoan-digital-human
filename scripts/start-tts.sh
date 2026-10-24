#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
set -e
# Keep CPU preprocessing from oversubscribing the LLM and Unity render threads.
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
cd "$BASE/GPT-SoVITS"
# The upstream configuration can be regenerated with CPU defaults. Select the
# actual inference device on every launch instead of silently keeping that default.
python - <<'PY'
from pathlib import Path
import torch
import yaml
path = Path('GPT_SoVITS/configs/tts_infer.local-v2.yaml')
config = yaml.safe_load(path.read_text())
cuda = torch.cuda.is_available()
config['custom']['device'] = 'cuda' if cuda else 'cpu'
config['custom']['is_half'] = cuda
path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
print(f'TTS inference: device={config["custom"]["device"]}, half={cuda}', flush=True)
PY
# Load reference/text inference caches before the first conversation.
python "$BASE/scripts/warm-tts.py" &
exec python api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.local-v2.yaml
