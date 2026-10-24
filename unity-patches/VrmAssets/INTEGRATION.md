# 阶段 4：VRM 语音、待机与展厅集成

当前版本 Unity 2022.3 / URP14 / UniVRM0.128.1 使用 VRM10 API。VRM0 的 BlendShapePreset.A/I/U/E/O 对应 VRM1 ExpressionPreset.aa/ih/ou/ee/oh，不同时挂载旧 VRMBlendShapeProxy 或直接写脸部网格的第二套 uLipSyncBlendShape。

LocalHumanDemo 与 LocalAvatarLipSync/uLipSync 共用同一个 AudioSource，播放真实 GPT-SoVITS WAV。uLipSync 分析 A/I/U/E/O 后，通过 VRM 原生表达式绑定定位实际脸部 SkinnedMeshRenderer。指数平滑系数18；音频停止或分析超过150ms未更新时，目标回零，避免陈旧数据造成持续张嘴。

VrmAvatarLoader.BindAvatar 对本实例导入的非 mouth/blink/lookAt 表情将 OverrideMouth 和 OverrideBlink 设为 none。其目的是让阶段3持续的Joy等表情不抑制程序口型和眨眼；不修改磁盘VRM或全局表达式工厂。VRM原生MorphTargetBindingMerger逐项加法合成表情与五元音/眨眼，VRMFaceController只在其后写未被VRM表情占用的独立身份Shape及材质。没有额外直接写共享形状键的竞争脚本。照片参数默认applyProfileExpressions=false，不将启发式Joy永久映射为资产闭眼笑。需要持续情绪时显式启用该选项；启用后资产原有闭眼笑语义仍成立。

LocalAvatarLipSync 独立维护随机2.5–5秒的眨眼起始间隔，闭合/展开共220ms：55ms SmoothStep闭合、25ms闭眼、140ms SmoothStep展开；与语音状态无关。暂停时间缩放不影响此计时。禁用时移除分析监听并清空自己拥有的五元音与blink。BlinkCount/LastBlinkStarted/LastBlinkInterval/BlinkWeight提供运行时观测。

Stable Idle固定根部与下半身，Chest/Spine Front-Back进行3.5秒微幅呼吸，OnAnimatorIK保持双脚锁地。VRM原生18条/66关节SpringBone由正常骨骼动画驱动，保留模型自带碰撞组；当前测试资产没有抽绳，不凭空添加或声称验证不存在的服饰节点。

相机SolidColor/#FFFFFF，纯白连续地面/后墙保留；人物脚下圆盘已移除，地面接收暖主光 Soft Shadows（强度 .35），URP 接触 SSAO 半径 .03、强度 .32；主光强度 .95、补光 .48、轮廓光 .3。左上角UGUI圆角16卡片、白色18%透明背景/35%细边、深色文字、浅色胶囊输入与图标按钮保持原布局。

完整复验：先source deploy-env.sh，再DISPLAY=:1 bash scripts/validate-vrm-integration.sh。脚本保留旧证据至run-history、实际重建、1920×1080 NVIDIA运行；输出vrm-stage4/runtime.json与独立acceptance.json。检查实际原生合成后网格权重、默认忽略照片Joy时的五元音、眨眼与睁眼静息权重、正常呼吸的关节变化、脚锁、UI屏幕射线/剪贴板/编辑/发送/重播、一轮文本TTS和真实音频ASR→TTS、持续缓存语音原始帧时及4张4K（包含睁眼与自然闭眼对照）。实际物理麦克风和桌面输入法仍需人工设备交互；自动测试不伪称操作了物理设备。

计时窗口包括缓存GPT-SoVITS真实语音播放及逐帧原生权重/网格/脚锁检查；模型加载、网络/推理、首次档案PNG加载与4K读回不在该窗口。阶段3关于Alicia缺少身份Shape、bone_offsets尚未应用及眼图UV适配的限制继续适用。

照片表情更新：schema3 expression由FaceMorphController处理，区域笑嘴/笑眉与受限笑眼保留虹膜可见。LocalAvatarLipSync合成照片aa基线与实时语音，停播回到照片开口而非强行闭嘴；完整规则和资产限制见FACE_CONTROLLER.md末尾。阶段4新增photoSmileApplied、expressionSmooth、expressionInvalidSafe、expressionDuration、maxSmileEyeWeight、photoExpression审计项。photoEmotionIgnored表示旧Joy不持续施加，explicit expression仍会生效；maxRestingLidWeight检查blink专用Shape，maxSmileEyeWeight另行约束笑眼，二者不能互相替代。


## 对话动作与表情（2026-10-23）

已接入 `AvatarInteractiveMotion`：UpperBody Override 动作层、0.25秒交叉淡入、
问候挥手/点头及 happy 微笑、3～6秒谈话动作池、按音频片段进度估计的标点抬眉/注视。
底层站姿/Chest-Spine呼吸、足部IK、uLipSync与VRM眨眼独立保留。
配置、表情权重合并、测试入口与限制详见 [INTERACTIVE_MOTION.md](INTERACTIVE_MOTION.md)。
