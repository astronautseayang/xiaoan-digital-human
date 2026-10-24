# 对话动作与表情驱动

## 打招呼挥手（2026-10-24）

唤醒回应改为约2.8秒的右手挥手：抬手、张开手掌、左右摆动三次、放下，
保留各角色避开头发的抬臂参数，手腕摆幅增至0.28并配合轻微前臂转动。
唤醒窗口保持动作层，静音时也能完整回应；结束自然退回待机。
播报首句出现您好/你好/欢迎/早上好/上午好/中午好/下午好/晚上好/早安/晚安等
问候时固定挥手，每轮最多一次；同句存在疼痛、求助等严肃词时抑制问候挥手。
仍按实际音频开播触发，尚未开播的生成文字不会触发手势。

验证包含双角色唤醒挥手、唤醒后归位、问候固定挥手、扩展问候词、严肃语句抑制，
以及原有口型/眨眼/眯眼笑/动作切换检查。唤醒截图为
`artifacts/validation/interactive-motion/{man,woman}-wake-wave.png`。

## 眯眼笑（2026-10-24）

保留原有动作，新增独立 `InteractionEyeSmile` 渐变通道：男性使用
`Fcl_EYE_Joy` / `Fcl_MTH_Joy`，女性使用 `eye_smile` / `mouth_smile`。
眼睛与嘴角分别混合，不使用整体 Joy 覆盖口型。相同 mesh/index 的多路表情
先求和再写一次，避免照片表情与互动笑容重复叠加。原生眨眼和语音口型继续工作。

待机初次等待7～12秒，之后每9～15秒出现约1.8秒的轻柔眯眼笑；收音、思考、
音色录入及关怀提醒期间暂停。问候、开心、感谢、鼓励、陪伴等词句在实际播报时
触发约1.9秒笑容，间隔至少5.5秒。疼痛、难过、求助和否定开心等词优先抑制，
并推迟之后的待机笑容12秒。中断与角色切换立即清理互动通道。

表情按本地词句规则选择，不新增模型情绪分类；句内位置按音频进度估算。
重播从 `SpeechSubtitleTrack.CurrentSpeech` 读取当前原始片段及其进度，
不会提前使用完整回答后半段的情绪。复杂否定、反话等表达仍可能需要扩展规则。

`scripts/validate-interactive-motion.sh` 增加双角色待机/说话笑眼、实际眼部mesh、
严肃语句抑制、合并重播片段切换、手动中断和切换清理检查；截图和报告保存在
`artifacts/validation/interactive-motion/`。测试使用缓存真实TTS与受控语义文本，
用于验证表情驱动，未验证逐词音画对齐。

`AvatarInteractiveMotion` 与 `AudioSource` 同驻场景根节点。`LocalHumanDemo` 将 TTS
片段的文本和音频成对入队，在 `PlayChecked` 即将调用 `AudioSource.Play()` 前交给
`PrepareSpeech`。组件确认音频实际播放后才触发动作，下载或文字显示不会抢先挥手。
完整回答重播复用完整文本；`BeginUtterance` 重置每轮问候去重。

`InteractiveMotionBuilder` 在构建时为男女控制器生成独立的 `Interaction` Override 层，
各自从原有待机姿势制作 Humanoid muscle 动画。`UpperBody` AvatarMask 只开启头、双臂和手指，
排除根节点、髋、双腿/足部IK、Spine/Chest，以保留原有站距、脚底定位与3.5秒呼吸。
动作没有下颌、眼睛及 BlendShape 曲线，口型由 uLipSync、眨眼由原有 VRM 控制器继续驱动。
状态包含 Rest、Wave、Nod、Emphasize、Explain、Listen；writeDefaultValues=false。
切换使用 CrossFadeInFixedTime(0.25s)，避免把0.25误当成随片长变化的 normalized duration。

你好/您好/嗨/欢迎/hello 每轮最多触发一次挥手或点头，并以低权重激活 VRM10 happy
（VRM0 Joy 迁移后的预设）。正常讲话3～6秒选一个手势，相邻手势不重复，动作持续约2.8秒，
收手后等待下一动作。播放结束覆盖层0.4秒退到0，表情同步回落。切换角色时清空旧角色
层权重、互动表情与注视目标，正在播放的音频继续，新角色重新淡入。

`FaceMorphController` 将互动微笑与已有照片表情合并；happy最大约0.144，避免原始Joy完全闭眼。
抬眉使用 Alicia 的 eyeblow_up / VRoid 的 BRW_Surprised 局部形状，与原生表情合并后相加，
不占用 aa/ih/ou/ee/oh、blink 或 lookAt 表情。问号/感叹号触发0.7秒脉冲，逗号/冒号触发
0.4秒轻脉冲。标点位置按当前片段音频进度与字符比例估计，未使用强制对齐，不保证逐字同步。
VRM LookAt 目标在说话时渐变向相机聚焦，标点处短暂加强聚焦，结束还原原目标。

验证：`DISPLAY=:1 bash scripts/validate-interactive-motion.sh` 构建并运行两个角色的
真实 TTS 缓存音频与受控文本测试：不开播不挥手、问候去重、3～6秒手势、实际骨骼变化、脚底漂移、
表情/抬眉mesh、口型与眨眼并行、结束回归、播放中切换清理。证据
`artifacts/validation/interactive-motion/runtime.json` 及两个角色问候截图。
测试音频来自 artifacts/validation/voice-latency/gpu-same-text-1.wav，缺失时需先生成真实TTS样本。
标点文本为测试夹具，不能将本测试视为语音逐字对齐验证。实际TTS/UI/ASR链路另运行 `scripts/validate-vrm-integration.sh --skip-build`。


2026-10-23 双角色运行验证通过：男性22秒3次谈话手势、女性22秒4次，
每轮问候各1次；间隔范围3.767～5.802秒。两个角色脚部漂移均小于0.001毫米；
happy峰值0.144、眉形实际mesh峰值18/100；口型与自然眨眼继续工作。
不开播不触发问候、结束回待机、播放中切换旧角色状态清理均通过。
此测试使用缓存TTS与受控文本，不能代表真实音频与文本逐字匹配；
实际对话链路以 vrm-stage4 的验收记录和客户端日志为准。

最终真实 TTS/UI/ASR 集成通过：问候1次、谈话手势2次，结束动作/表情释放通过，
五个元音、自然眨眼、照片表情合并与脚底定位通过。缓存真实音频重播采样282帧，
最大17.662ms、超33ms为0；该帧采样不含网络/ASR/TTS生成、模型加载和截图读回。
构建 Succeeded，0 warnings / 0 errors。
