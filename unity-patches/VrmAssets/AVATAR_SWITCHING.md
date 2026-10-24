# 男女 VRM 运行时切换

男性采用桜田史利矢 / Sakurada Fumiriya，原作者 VRoid Project / pixiv，CC0 1.0。
VRM 镜像：https://opengameart.org/content/vroid-studio-cc0-models
可编辑源文件：https://booth.pm/en/items/3094418 （选择桜田史利矢）。
授权来源与原始 VRM metadata 见 `Fumiriya-license.html` 和 `avatar-catalog.json`。
镜像 ZIP 和解压后的 VRM 分别固定 SHA256，构建下载时先校验压缩包，再读取指定成员并校验模型。
女性继续使用 Alicia Solid，© DWANGO Co., Ltd.，许可见 Alicia-license.html。
原 Seed-san 模型已备份到本机 artifacts/model-backups/seed-san。

`scripts/sync-avatar-assets.py` 按 catalog 中来源 URL 和 SHA256 下载缺少的
模型，已有文件也必须通过校验；构建时复制至 Assets/Models 与 StreamingAssets/Avatars。
照片缓存分别打包为 Profiles/man 与 Profiles/woman，贴图路径改为相对路径。

客户端默认 woman，支持 `-avatar man`。卡片按钮“男性/女性”热切换；
“刷新照片”重读当前档案，F 键亦重读当前模型对应档案。重新处理照片后再刷新即可。
本机 artifacts 缓存优先，缺少时读取随构建打包的档案。
`-face-profile PATH` 可显式指定初始档案，但 avatar_id 必须匹配。

男性独立使用 RelaxedMaleIdle 控制器：肩部向后微沉，手臂自然落于侧前方，
肘部和手指轻屈；脚部 IK 将双脚支撑点展开至肩宽。女性继续使用 StableIdle，
原始男女 VRM 文件均不修改。两者 Chest/Spine 叠加 3.5 秒微幅呼吸，
VRM blink 按 2.5～5 秒随机间隔眨眼（55ms 闭合、25ms 保持、140ms 展开）。
Alicia 的眉毛使用脸部图集中的独立金色区域；调肤色时对该区域保留深色眉形，
避免肤色乘色让眉毛近乎不可见。该 UV 区域仅适用于当前 Alicia_face 材质。

启动遮罩下依次准备男女两个实例，完成 Humanoid、Shader、档案校验、
场景尺寸/脚部配置和16帧实际渲染预热后再开放交互。男女实例各导入一次；
切换时启用目标并暂停旧角色，失败保留当前实例；并发切换被拒绝。
AudioSource、UI、相机和根 Transform 保留，uLipSync 引用改绑到新实例。
未修改档案的切换复用已解码的贴图和面部状态；档案变更后仍可重读。
缓存最多两个角色，增加常驻内存并将首次准备移到启动阶段，未显示角色不运行动画、物理或表情更新。
预热失败时保留已加载角色并允许之后重试，重试首次加载不保证无长帧。

照片虹膜贴图依赖模型 UV。桜田史利矢保留原作眼部贴图，避免照片虹膜覆盖
不兼容的眼线、高光和虹膜 UV；其肤色、发色与表情仍使用男性档案。
身份形状键仍受资产实际提供项限制，不生成替代网格。

运行 `DISPLAY=:1 bash scripts/validate-vrm-switch.sh` 完整构建并检查实际 UI 射线点击、
4 次换人、每次按钮点击耗时及紧随其后的30个帧间隔（均须<33ms）、
口型目标重绑、连续音频保留、两实例复用及档案不重复解码、错误角色/档案回退、
男女各 240 原始帧、脚底接触、SpringBone 链及 4K 全身/脸部/UI 截图。
音频保留测试使用合成连续音，不能替代实际 ASR/TTS 验收。

场景已移除圆盘，运行时以双脚中点定位并将鞋底直接贴合 Y=-0.57181 的地面。
柔和主光投影和 URP 接触 SSAO 提供接地效果；暖主光、补光与轮廓光降低面部过亮。
每个角色另观察 720 帧，检查 Chest/Spine 运动、完整闭眼/睁眼及眨眼间隔，男性检查肩宽站距。独立稳态测试在切换后显式 GC、180 帧预热后取 240 帧；
失败性能窗口也保留在 run-history，不能把通过窗口解释为从启动起没有长帧。

实际主屏 DP-4 为 1920×1080@60Hz；自动验收指定 monitor 1，避免落到
1024×768 的副屏。客户端保留 vSyncCount=0、targetFrameRate=60；尝试垂直同步后长帧增加，已恢复原配置。
