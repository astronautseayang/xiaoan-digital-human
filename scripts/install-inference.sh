#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
export no_proxy=localhost,127.0.0.1,.tsinghua.edu.cn
python -m pip install --no-deps wheelhouse/torch-*.whl wheelhouse/torchaudio-*.whl wheelhouse/torchvision-*.whl wheelhouse/nvidia_*.whl wheelhouse/triton-*.whl wheelhouse/sympy-*.whl
python -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple --find-links wheelhouse -c config/runtime-constraints.txt torch==2.6.0 torchaudio==2.6.0 torchvision==0.21.0
python -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple --find-links wheelhouse -r config/inference-requirements.txt
python -m pip check
python - <<'PY'
import torch
print('TORCH',torch.__version__,'CUDA',torch.version.cuda)
assert torch.cuda.is_available()
x=torch.randn(256,256,device='cuda');y=x@x
torch.cuda.synchronize();assert torch.isfinite(y).all().item()
print('CUDA COMPUTATION PASSED',torch.cuda.get_device_name(0))
PY
python -m pip freeze > logs/runtime-packages.txt
