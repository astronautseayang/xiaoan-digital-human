# 公开源码部署说明

## 1. 边界与外部依赖

仓库不包含私有运行数据、预训练模型、参考音频、脸部照片/档案、Unity 编辑器和角色原文件。请先核对 THIRD_PARTY_NOTICES.md；尤其是原 Unity 工程、Qwen 3B 权重和 VRM 角色的独立许可。

获取外部工程时按声明中的 commit 固定版本：

```bash
git clone https://github.com/LKZMuZiLi/human.git human-code
git -C human-code checkout c40e12f
git clone https://github.com/RVC-Boss/GPT-SoVITS.git GPT-SoVITS
git -C GPT-SoVITS checkout b4570b876f5c086819ba84e3215472733c6a7b70
git clone https://github.com/ggml-org/llama.cpp.git llama.cpp
git -C llama.cpp checkout 7170cad4d02f7907517613931840cbb2367399a3
```

第三方工程下载行为不表示本项目授予其使用权。原始 Unity 工程授权尚待明确，扩大使用或分发前应联系作者。

## 2. 环境与路径

现有脚本含原开发路径 `/home/yyy/digital-human`、Conda 环境 `human-gsv-v2`，以及本机 Unity 编辑器目录。新机器上请先建立 Python 3.10 环境，再运行：

```bash
python scripts/configure-public-paths.py --python-prefix /absolute/path/to/your/python/environment
```

该脚本仅重写当前源码目录中的原机器路径，跳过外部依赖目录和个人数据；修改后请检查 diff。Unity 编辑器需自行安装并激活，按实际路径修改 scripts/build-unity.sh 中的 editor 变量；启动脚本中的 DISPLAY 也需按机器调整。

```bash
python -m pip install -r config/inference-requirements.txt
python -m pip install -r config/asr-requirements.txt
PYTHONPATH=. python scripts/download-sensevoice.py
PYTHONPATH=. python scripts/download-sensevoice.py --offline
```

Torch/CUDA 安装应与显卡驱动匹配；当前约束固定开发时验证过的依赖，不覆盖所有硬件组合。SenseVoice 权重由 ModelScope 下载，完整缓存后不联网。

## 3. 必须自行准备的资源

- 适用许可的 VRM：放入 assets/avatars/male.vrm，更新 unity-patches/VrmAssets/avatar-catalog.json 的 SHA256 和来源；项目原角色文件不随仓库分发，也不会通过空 source 自动下载。
- 男性 face_params.json 档案及其引用纹理：目录见角色 catalog 的 profile 字段。现有历史档案依赖本地验证输出，仓库没有附带个人照片或档案。
- GPT-SoVITS v2 的预训练模型及本人有权使用的参考音频；修改 gateway/default-voice.json，参考音频文本需与录音一致。示例路径指向缺省位置，不附带声音文件。
- 本地 LLM GGUF、唤醒关键词模型、可选 CAMPPlus 声纹模型和相关语言资源。目录和上游参考见 gateway/ 下各模块说明。

scripts/download-models.py 等旧脚本还依赖原 logs 中的下载清单，不能直接当作从零安装程序；应从相应官方模型发布页获取匹配文件。本公开版本没有携带这些本机日志和测试音频。

## 4. 启动和构建

检查并修改 services/ 中的路径和模型参数后安装用户 systemd 服务。网关服务通过 scripts/start-gateway.sh 启动，启动前会验证 SenseVoice 缓存，首次下载请预留足够时间。

Unity 侧先准备依赖软件包，再使用 scripts/build-unity.sh；部分上游包缓存脚本依赖原本机清单，必要时使用 config/unity-manifest.original.json 从 Unity 官方仓库恢复依赖并检查 UniVRM 本地路径。完整客户端从零部署仍需上述第三方素材和档案，不应假设这些资源已在 Git 中。

ASR 可在网关启动后用本人合法录音独立验证：

```bash
PYTHONPATH=. python scripts/verify-asr.py /path/to/test.wav --expected '定位到杭州'
```

该命令仅转写，不执行提醒或定位；会跳过声纹身份验证但保留人声检测。测试 CER 不是广泛准确率保证。
