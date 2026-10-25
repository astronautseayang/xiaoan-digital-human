# 中文语音识别（SenseVoice-Small）

## 实际入口与依赖

本项目没有 backend.py；实际后端是 `gateway/app.py`。主识别原为
Faster-Whisper base/tiny，此次替换为 `gateway/asr_service.py` 中的 FunASR
`AutoModel`，模型为阿里开源 `iic/SenseVoiceSmall`。离线唤醒词继续使用独立
Sherpa 关键词模型，不把持续麦克风声音送入大模型。Faster-Whisper 的
Silero VAD 工具继续用于前置人声检测，不再执行 Whisper 主识别。

```bash
cd /home/yyy/digital-human
PYTHONNOUSERSITE=1 /home/yyy/miniforge3/envs/human-gsv-v2/bin/python -m pip install -r config/asr-requirements.txt
PYTHONNOUSERSITE=1 PYTHONPATH=. /home/yyy/miniforge3/envs/human-gsv-v2/bin/python scripts/download-sensevoice.py
```

固定 FunASR 1.4.16、ModelScope 1.40.2，沿用 Torch/Torchaudio 2.6 CUDA 配对和
现有推理环境约束。首次下载约 937 MB，保存在 `models/asr/SenseVoiceSmall`。
脚本并发分块、有限重试、检查 HTTP Range、文件大小及 SHA256，完成后原子写清单。
下载中断不会把未完成模型视为缓存。完整缓存启动时在本地验证，无需联网。

## 输入输出与推理

`POST /api/asr` 继续使用 multipart 字段 `file`，保留 `care_commands`、
`care_event_id`，返回 `text`、`raw_text`、`corrected`，拒绝输入时保留
`input_notice`、`care_command`。客户端调用和后续 `/api/chat`、`/api/chat/jobs`
保持兼容；识别不会自行提交重复聊天。

单次录音最长 30 秒，按解码后的音频长度检查。超长录音返回 HTTP 200、空 `text`
及 `input_notice=录音超过30秒，请缩短后重新录制。`，不继续识别或执行指令。
网页显示时长提示，录音仍需用户手动停止。解码最多读取前 31 秒以判断超限，
在降噪之前检查时长，避免滤镜略微缩短音频后漏过边界。
降噪输出按解码后的帧数补齐/裁齐，保持录音时长，避免正好五秒的声纹录入
因滤镜缩短约25ms而被误判为不足五秒。声纹录入仍需通过人声及一致性检查。

WAV 中声明了长度的数据块必须完整，截断文件返回空 `text` 和
`input_notice=录音数据不完整，请重新录制。`，不识别剩余片段。
兼容管道生成的 WAV 使用 `0xffffffff` 表示未知数据长度；这种输入无法仅凭
长度字段判断是否缺失尾部。WebM、Ogg、MP3 继续使用原解码流程。

网页录音采用 `POST /api/asr?execute_commands=false`：继续做输入声纹检查及
指令语境纠错，只把识别文字填入可编辑输入框，不自动触发紧急求助或关怀确认。
`execute_commands` 默认 `true`，保留离线唤醒等现有入口行为。
该选项与录入音色使用的 `care_commands=false` 不同，后者同时跳过声纹验证和
指令纠错。网页转写后的“发送”仍使用普通对话流程，不代替专用关怀确认入口。

- WAV 保留原接口，也接受文件名 `.pcm`/`.raw` 或 Content-Type `audio/pcm`、
  `audio/x-pcm` 的 16 kHz、16-bit little-endian、单声道 PCM 缓冲。这里处理
  一次话语的音频缓冲，并非 WebSocket 实时逐帧 ASR。原本地麦克风话语缓存不变。
- FFmpeg 降噪/重采样 → 人声检测/已录入声纹验证 → 整段增益 → SenseVoice →
  清理语言/情绪/声音事件标签 → 简体中文 → 指令语境纠错 → 原对话管线。
- `language=zh`，`use_itn=true`，由模型输出中文标点和数字规范化；不插入情绪表情。
- 使用 CUDA 优先；没有 CUDA 或初始化/推理 CUDA 失败时回退 CPU。推理由锁串行，
  每次话语使用独立 cache，不把上一段声音的解码状态带入下一段。
- CPU 普通推理失败默认重试一次，最终返回 503 中文错误，不伪造识别文字。
  静音/杂音/非目标声纹仍走原输入拒绝流程。
- 网关启动时加载模型；`/ready` 增加 `asr`，加载失败则不会报告完全就绪。
  `GET /api/asr/status` 查看实际设备、缓存、模型加载和热词支持能力。

## 配置与热词能力

`config/asr.json` 可配置 `device`（auto/cpu/cuda/cuda:0）、cpu_threads、
retries（0～2）、hotwords、use_itn。设备配置更改后重启网关。
热词可通过 `GET /api/asr/config`、`PUT /api/asr/config` 读写；PUT 仅更新热词，
例如 `{"hotwords":["定位","杭州","提醒","吃药","闹钟","义乌市"]}`，即时生效。

**SenseVoice-Small 本身不支持原生 hotword 解码/声学偏置。** 本实现不把一个会被
忽略的参数宣称为声学热词；状态明确返回 `native_hotword_bias=false`、
`hotword_mode=context_correction`。配置用于识别后的受限指令词纠偏：
在有时间的提醒语句中可按“提醒”热词修正同音关键词；自定义城市使用“义乌市”
这样的名称加入定位/天气城市候选。仅配置“吃药”等词不会强制替换普通聊天或
提醒事项，以免篡改用户实际说的内容。真正的声学热词偏置需要换用支持该功能的
Paraformer/其他后端；这里保留了统一配置入口。

城市同音歧义继续询问；模型升级不能保证所有口音、噪声、同音字都识别正确。

## 服务启动与离线验证

实际 systemd 用户服务通过
`~/.config/systemd/user/human-gateway.service.d/sensevoice.conf` 调用
`scripts/start-gateway.sh`：先准备/验证缓存，再启动网关。`scripts/start-services.sh`
也准备该缓存。首次启动缺缓存时需联网下载；已缓存后：

```bash
cd /home/yyy/digital-human
PYTHONNOUSERSITE=1 PYTHONPATH=. /home/yyy/miniforge3/envs/human-gsv-v2/bin/python scripts/download-sensevoice.py --offline
systemctl --user restart human-gateway
```

Ubuntu 终端直接验证文件（仅转写，不执行定位/提醒或提交聊天）：

```bash
cd /home/yyy/digital-human
PYTHONNOUSERSITE=1 PYTHONPATH=. /home/yyy/miniforge3/envs/human-gsv-v2/bin/python scripts/verify-asr.py artifacts/validation/sensevoice/command-1.wav --expected '定位到杭州'
```

替换文件路径可验证本人录音；`--expected` 可选，提供时输出忽略标点后的字符错误率。
数字 ITN（例如“三”与“3”）可能被该简单指标记为不同字符，需同时查看原文。
该命令关闭声音身份限制以便验证测试文件，但保留降噪和人声检测；常规客户端
仍执行已录入声纹验证。多人同说时不提供声源分离。

## 回归验证

`scripts/test-asr-service.py` 覆盖中文/ITN 参数、标签清理、CUDA 初始化/推理回退、
CPU 重试上限、PCM/WAV 包装、离线缺缓存、受限热词、配置 API 与 503 错误。
`scripts/test-input-logic.py`、`scripts/test-conversation-context.py`、
`scripts/test-reminders.py` 验证识别下游纠错、上下文和不含编号的提醒管理。
提醒引用通过上轮成功确认的时间+事项在数据库中匹配唯一记录；含糊时询问。
内部数据库 ID 保留，列表和 TTS 均不播报；列表按时间排序，可说“取消第一个提醒”。

## 本机部署实测（2026-10-24）

网关已通过 systemd 重启，线上 `/ready` 的 ASR、TTS、LLM、care、wake 均就绪，
`/api/asr/status` 为 `sensevoice`、`cuda:0`、`loaded=true`。完整缓存通过
`download-sensevoice.py --offline` 的 SHA256 校验；独立 CPU 加载与识别也已跑通。

使用同一批本地 TTS 合成音频比较（不是本人麦克风准确率评估）：

| 参考语句 | 原 Whisper 输出 | SenseVoice 输出 |
| --- | --- | --- |
| 定位到杭州 | 定位到杭州。 | 定位到杭州。 |
| 定位到苏州 | 定位到苏州。 | 定位到苏州。 |
| 一分钟后提醒我喝水 | 一分钟后,替醒我喝水。 | 一分钟后提醒我喝水。 |
| 今天下午三点提醒我吃药 | 今天下午,我三点提醒我吃药。 | 今天下午我三点提醒我吃药。 |
| 杭州明天天气怎么样 | 杭州明天天气怎么样? | 杭州明天天气怎么样？ |

第四条仍有插入字，不能据此声称彻底解决所有识别错误。GPU 模型推理单次约
0.025～0.135 秒（不含预处理与网络）；CPU 的杭州样本加载加识别约 1.16 秒，
该数据仅代表此次本机测试。线上 WAV 与原始 PCM 接口分别验证了杭州和一分钟
喝水指令；验证调用不执行提醒或定位。完整结果位于
`artifacts/validation/sensevoice/sensevoice-results.json`、`deployed-status.json`。

真实识别/简体输出回归通过，11 项离线唤醒测试及手动中断回归通过。
