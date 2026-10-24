#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
printf '%s\n' 'Install verified local PyTorch wheels, then the constrained speech runtime.'
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export no_proxy=localhost,127.0.0.1,.tsinghua.edu.cn
python -m pip install 'setuptools==69.5.1' wheel pybind11
# Re-run with isolated Python paths to install packages mistakenly resolved from user/ROS paths.
python -m pip install --find-links wheelhouse torch==2.6.0 torchaudio==2.6.0 torchvision==0.21.0
cat > config/runtime-constraints.txt <<'EOF'
torch==2.6.0
torchaudio==2.6.0
torchvision==0.21.0
numpy==1.26.4
transformers==4.51.3
huggingface-hub==0.36.0
peft==0.17.1
pytorch-lightning==2.5.1
torchmetrics==1.5.0
gradio==4.44.1
pydantic==2.10.6
EOF
python -m pip install -c config/runtime-constraints.txt -r GPT-SoVITS/requirements.txt
python -m pip install -c config/runtime-constraints.txt 'faster-whisper==1.1.1' 'soundfile' 'uvicorn' 'httpx' 'python-multipart'
python -m pip check
python - <<'PY'
import torch
print('TORCH', torch.__version__, 'CUDA', torch.version.cuda)
assert torch.cuda.is_available()
x=torch.randn(256,256,device='cuda'); y=x@x
torch.cuda.synchronize()
assert torch.isfinite(y).all().item()
print('CUDA COMPUTATION PASSED', torch.cuda.get_device_name(0))
PY
python -m pip freeze > logs/runtime-packages.txt
