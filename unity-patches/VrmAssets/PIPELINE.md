# 标准 VRM 角色管线（阶段 1）

Unity 2022.3.31f1，URP 14.0.11，UniVRM 0.128.1（tag commit 2911cb72a905ab7d8b0f9e03397235d1c0293714）。

`source deploy-env.sh` 后运行 `bash scripts/build-unity.sh`。安装脚本校验上游发行归档 SHA256，安装本地 UPM 包 com.vrmc.gltf / com.vrmc.vrm；VRM10 包内含 MToon10 URP Shader。两个明确的上游兼容修正由脚本重放：废弃 API 改名为 UnityUrpShaderName；切线 float4 显式取 xyz，消除 Shader 编译隐式截断警告。无关闭警告的编译开关。

测试资产来自 UniVRM 官方仓库 Tests/Models/Alicia_vrm-0.51/AliciaSolid_vrm-0.51.vrm，名称 Alicia Solid，作者 © DWANGO Co., Ltd.，原始 VRM0.51，由 UniVRM 加载时迁移到 VRM1；不是原创角色或最终商业定制资产。完整原始元数据、SHA256 和来源在 model-source.json，独立人物许可在 Alicia-license.html（https://3d.nicovideo.jp/alicia/rule.html）。软件 MIT 许可不能替代人物许可。人物条款允许个人（含非法人团体）的派生创作，约束用途且不可转授权；法人商业用途需单独确认授权。此处作为本地工程基础测试资产，后续可替换为用户自有 VRoid/VRM。禁止暴力、色情等元数据要求随资产保留。

安装脚本将未修改 VRM 放入 Assets/Models，显式选择 URP Importer；向 StreamingAssets 部署同一 VRM 供运行时读取。挂载根 LocalDigitalHuman 的世界位置、旋转、缩放不变。子节点 VrmAvatar_AliciaSolid 按可见网格包围盒等比缩放到 0.9m 高并把鞋底放到地面 Y=-0.57181。保留资产自己的身体比例、原生骨骼、材质与纹理。

VrmAvatarLoader 使用 Vrm10.LoadPathAsync 和 UrpVrm10MaterialDescriptorGenerator。标准 Humanoid Animator 使用无根位移的 Stable Idle；源待机的站姿肌肉曲线固定，Chest/Spine 以 3.5 秒周期轻微呼吸，IK Pass 开启。VrmGrounding 在 OnAnimatorIK 对左右脚进行 0.5m 向下射线支撑检测，接触权重为 1。地面为 layer30 collider；角色为 kinematic Rigidbody+CapsuleCollider。此阶段是固定展示待机，不实现走路/迈步运动控制。

原生 SpringBone 三组涵盖发束、蝴蝶结、辫子与裙摆，使用 VRM 自带 SpringBone 碰撞组；它与 Unity 地面碰撞属于不同系统。uLipSync 的 A/I/U/E/O 映射到 VRM aa/ih/ou/ee/oh，自动眨眼由 VRM blink 表情驱动。VRM runtime 统一应用表情，避免多个脚本直接竞争 BlendShape。

旧身体/脸/头发网格、照片变形、手工骨骼动画与专用 Toon/Outline 代码整体隔离至 unity-patches/Deprecated~，同步脚本不把它们复制进 Unity Assets，构建不调用旧提取器。Python 照片服务保留历史实现，但不再驱动新 VRM 的几何/材质。白色展厅、UGUI、中文对话及 ASR/TTS 网关保留。

运行 `DISPLAY=:1 bash scripts/validate-vrm.sh` 获取本阶段独立构建与运行证据。旧 avatar-acceptance.json 为程序化角色历史，不能用于本阶段验收。

运行时对共享 MToon 材质去重后应用 0.68 展厅亮度校准，避免重复累乘。足部 IK 前三次帧末以实际 BakeMesh 鞋底最低点校准踝偏移；验收直接检查鞋底与地面的几何高差，容限 3mm。
