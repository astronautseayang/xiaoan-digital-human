# 本地离线唤醒与简化界面

## 运行方式

`human-gateway.service` 启动一个独立唤醒子进程，使用 Sherpa-ONNX 中英双语 3M Zipformer int8 关键词模型。常驻阶段不运行 Whisper、LLM 或 TTS。麦克风由 PulseAudio `parec` 单独持有，16kHz 单声道、80ms 音频块、一个推理线程、能量门控加首音预留。检测“小安”后通过本地 WebSocket 通知 Unity，播放独立柔和提示音、点头微笑并看向镜头，进入后续语音采集。

当前部署环境为 `/home/yyy/miniforge3/envs/human-gsv-v2`，增加依赖 `sherpa-onnx==2.0.0`、`websockets==16.1.1`；系统需 `pulseaudio-utils` 提供 `parec`。原有 NumPy、FFmpeg、ASR 和聊天服务继续使用。

模型来源：[Sherpa-ONNX 官方 kws-models release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/kws-models)，文件 `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2`，解压至 `models/wake/`。选择 int8 encoder/joiner 与普通 decoder。模型和运行音频未纳入 Git；复制部署时需一并下载模型。模型就位后可断网运行，不使用云端识别。

```bash
cd /home/yyy/digital-human
PYTHONNOUSERSITE=1 /home/yyy/miniforge3/envs/human-gsv-v2/bin/python -m pip install sherpa-onnx==2.0.0 websockets==16.1.1
systemctl --user restart human-gateway
curl http://127.0.0.1:9881/api/wake/status
```

## 配置与状态

`config/wake.json` 配置默认麦克风、关键词文件、能量阈值、输入增益和超时。修改后重启网关。`pulse_source` 默认 `@DEFAULT_SOURCE@`，可用 `pactl list short sources` 查询并指定实际设备。`speech_rms=0.004` 是启用语音门控的原始 RMS 阈值，需结合房间底噪调节；`kws_input_gain=2.0` 只影响关键词推理，不改变录音响度。

关键词在 `config/wake-keywords.txt`，使用该模型 tokens 中的声母、韵母与声调形式，例如 `x iǎo ān :1.5 #0.25 @小安`。修改唤醒词时同时修改 JSON 的 `keyword` 与关键词文件，不能只改显示文字。当前同时检测“救命”“跌倒”“胸口疼”“知道了”，并接入原有关怀服务；无需叫“小安”即可触发这些待机关键词。确认绑定语音开始时的事件 ID，避免旧录音关闭新告警。

- `GET /api/wake/status` 返回 `ready/state/keyword/error/worker_pid`；`/health` 与 `/ready` 也包含唤醒快照。原有聊天就绪判定保留，唤醒不可用时仍能点击麦克风手动录音。
- `WS /ws/wake` 首先发送 `status`，后续发送 `wake`、`level`、`state`、`transcript`。
- 唤醒事件示例：`{"type":"wake","keyword":"小安","state":"listening"}`。
- 客户端每 250ms 发送 `{"type":"control","enabled":true,"suppress":false}`，另支持 `{"type":"manual_listen"}`。客户端不能伪造服务端唤醒事件。
- 提示音保护窗口为 450ms；随后连续 5 秒未检测到超过阈值的声音，返回 `idle`，原因 `silence_timeout`。光圈与波形在约 400ms 内淡回待机。说话后 700ms 静音结束一句，连续录音最多 15 秒。
- 录音交现有本地 ASR，文字经 WebSocket 交 Unity 自动对话。错误返回可重试提示；麦克风子进程异常时 3 秒后重启，Unity WebSocket 断开后 2 秒重连。

## 界面、镜头和渲染

主界面保留近景角色、右侧 72 号时钟、底部 44 号高对比字幕，以及可点击的语音呼吸光圈。待机、在听、在想、在说话分别显示大字状态，活动状态为明亮水绿色；拾音或播放强度驱动波形。唤醒时字幕显示“我在听，您请说”。

右上角“设置”展开抽屉，收纳文字输入、粘贴、刷新、男女角色、音色录入/恢复、重播、大音量开关、唤醒监听开关及署名。点击关闭或抽屉外区域收起。关怀弹窗出现时抽屉隐藏。

`PortraitImporter` 使用胸部至头部近景机位，32°视角；暖主光、暖补光和轮廓光，降低主光阴影强度。静态 16px 反射球提供环境反射，不增加实时反射渲染或 Bloom。光圈/波形由 UGUI 网格绘制，无位图、额外相机或每帧数组分配。

## 资源指标与实际边界

本机实际物理麦克风待机采样 20.149 秒：唤醒子进程约单核 0.3% CPU、采集进程 0.2%、网关 0.4%，唤醒子进程 RSS 约 82MB，见 `artifacts/validation/offline-wake/live-cpu.json`。这是当前电脑上的测量值；5% 目标针对常驻唤醒阶段，不包含被唤醒后 ASR、LLM、TTS 或 Unity 渲染，其他硬件需重新测量。

没有声学回声消除。普通播报、手动录音和音色录入期间暂停关键词识别，防止扬声器声音自行唤醒或确认卡片，因此这些期间也无法靠后台关键词检测求助；卡片按钮和原有手动入口仍可用。客户端控制消失 3 秒后解除播放抑制。识别流关闭开关也会关闭待机求助词监听。

能量门控是轻量阈值检测，持续环境噪声可能延迟静音退出或造成误触发，轻声、方言和短促唤醒也可能漏检。提供可点击光圈作为手动入口。已用清晰的中文合成音频做集成验证，仍需在实际老人、麦克风与扬声器摆放环境下检查误唤醒率、漏检率和听感。不得把关键词模块当作独立生命安全监护设备。

麦克风后台持续采样，待机不写录音。仅唤醒后的有声片段临时保存到 `artifacts/wake-input/`，ASR 完成或失败后删除；进程被强制结束时可能留下未清理片段。常规对话与关怀事件沿用现有本地记录策略。

## 验证

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=. /home/yyy/miniforge3/envs/human-gsv-v2/bin/python scripts/test-offline-wake.py
bash scripts/build-unity.sh
# 先关闭已打开的 Unity 单实例窗口，以下测试会打开测试窗口并自动退出
PYTHONNOUSERSITE=1 PYTHONPATH=. /home/yyy/miniforge3/envs/human-gsv-v2/bin/python scripts/validate-offline-wake.py
```

关键词测试使用 `artifacts/validation/offline-wake/wake-command.wav`（“小安。今天天气好吗？”）与 `negative.wav`，缺少音频时仅音频相关测试会 skip，不能把 skip 算作关键词通过。集成测试需要这些本地测试素材、运行中的网关和桌面 DISPLAY=:1；临时创建 PulseAudio 空输出，将 **DigitalHumanWake 自身的采集流** 移到其 monitor 输入，播放真实 WAV 经 KWS、WebSocket、Unity、ASR 和 TTS，最后恢复原设备并卸载测试输出。它不更改系统默认设备、不注入假唤醒事件。

`unity-runtime.json` 是 Unity 验收结果；`websocket-events.json` 为真实事件；`standby/listening/speaking/returned-idle/settings.png` 为截图。运行时参数 `-offline-wake-self-test` 才启用验收组件，普通启动不会自动提问。

## 手动结束对话与两行字幕（2026-10-24）

在听、在想或在说话时，光圈下方显示“结束对话”；点击按钮或再次点击光圈，立即停止本轮录音/播放/互动动作并回到待机。之后可以再次叫“小安”或点击光圈。`cancel_listen` WebSocket 控制清空唤醒录音并取消正在等待的识别任务，取消后的识别结果不会再触发聊天；`DELETE /api/chat/jobs/{id}` 取消本轮 LLM 流与 TTS 队列。紧急关怀卡片继续使用“知道了”确认。

场景背景材质输出纯白，加载背景同为纯白。底部44号文字使用116高的两行可视区域，长回答可滚动，增量文字更新时显示末尾。以1600×900布局基准，设置和时钟整体向左80单位。新增 scripts/test-manual-interrupt.py 验证识别取消/清理、迟到结果抑制与LLM/TTS取消；离线唤醒运行验证增加手动结束、再次唤醒和播报中结束检查。

## 收音窗口语义与视角（2026-10-24 后续调整）

主界面“在听”阶段按钮现在为“结束收音并发送”，再次点击光圈效果相同：`finish_listen` 关闭当前录音，提交窗口内已采集的语音，进入识别/回答阶段。它与丢弃本轮的 `cancel_listen` 不同。无有效语音时结束收音返回待机；重复结束不会重复提交；processing期间后续音频不会写入当前录音。静音自动结束、5秒无语音退出和15秒最长收音继续作为自动结束机制。待机阶段只做关键词检测，不会把待机声音提交为对话输入。回答阶段按钮仍可结束本轮回答。

设置新增“全身”“当前近景”两个视角，使用同一人物和动作，只调整相机，选择写入PlayerPrefs并在下次启动恢复。全身视角将脚部放在字幕上方，当前近景恢复原相机参数。


## 自动收音与银发称呼（2026-10-24）

- 唤醒词仍在本地待机检测；唤醒后的收音窗口增加本地 Silero V5 人声检测，复用 faster-whisper 自带的两个 ONNX 模型，无需下载新模型。仅在收音窗口推理，待机仍使用原关键词能量门控。VAD 使用跨帧状态和 0.5/0.35 双阈值；非人声噪声不再单纯因为音量较大而开启本轮语音。
- 说话后约 1.5 秒无人声自动结束、提交并识别分析，替代原 0.7 秒阈值，为老人语速和句中停顿留出时间。仍可点击“结束收音并发送”提前提交；5 秒无语音返回待机，15 秒录音上限不变。自动提交原因 speech_finished / max_duration，人工提交 manual_finish。结束后不再向该片段追加采样。
- ASR 加入本地人声过滤，保留音量归一化、关怀命令分析和后续聊天/TTS。UI 提示“说完稍等，会自动发送”；设置中的麦克风按钮也走同一唤醒收音入口，音色录入保留原流程。
- 设置“对您的称呼”可在“您 → 爷爷 → 奶奶”之间点击切换，通过 GET/PUT /api/companion/profile 保存至 config/companion.json。未选择时使用“您”，不根据数字人形象或声音猜测老人性别。聊天、唤醒界面、欢迎语和新生成的关怀提醒共用选择；已有提醒不重新生成。聊天提示要求自然称呼、短句、尊重自主选择，不重复堆砌称呼。
- scripts/test-offline-wake.py 新增真实语音中途停顿和噪声测试；scripts/test-companion.py 检查设置持久化、拒绝非法值、两种聊天入口和关怀文字/语音一致。scripts/validate-offline-wake.py --automatic 在桌面端验证无需点击的真实音频全链，并检查三种称呼设置。生产中真人口音、轻声和电视背景声仍需现场使用调试；该逻辑按人声和停顿判断结束，不是语义完整度判断。
