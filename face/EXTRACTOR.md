# 阶段 2：独立照片参数与材质导出

入口为仓库根目录 `face_feature_extractor.py`，实现位于 `face/face_feature_extractor.py`。独立 CLI，不依赖旧程序角色或正在运行的 HTTP 服务；输出由 Unity VRMFaceController/FaceMorphController 读取。

## 环境与运行

```bash
cd /home/yyy/digital-human
source deploy-env.sh
# 首次安装（推荐 Python 3.10）：
python3.10 -m venv tools/face-env
tools/face-env/bin/python -m pip install -r face/requirements-extractor.txt
source tools/face-env/bin/activate
python face_feature_extractor.py --input me.jpg --output_dir ./ExportedFaceData/
# 项目已有的实际测试照片：
python face_feature_extractor.py --input assets/photo/me.png --output_dir ./ExportedFaceData/
```

MediaPipe 固定 0.10.21，保留 solutions.face_mesh.FaceMesh API。OpenCV 使用 opencv-contrib-python，它包含 opencv-python 的全部基础接口，也是 MediaPipe 的依赖；不要在同一环境叠装两个都提供 cv2 的 wheel。依赖包含 NumPy 1.26.4。当前项目已有 tools/face-env，无须重新创建。

## 输出与单位

- `face_params.json`：UTF-8，schema_version=2（兼容保留 skin_tint），含用户指定的 skin_tint、blendshapes、bone_offsets、texture_path。
- `face_diffuse.png`：512×512 RGBA，眼中心仿射对齐、双边滤波、保护眼/眉/唇后的三阶肤色重映射及面部椭圆遮罩。去除 roll/缩放/平移，不补全侧脸，不是 VRM UV 图集。
- `pupil_accent.png`：256×128 RGBA 虹膜图集，左半为被摄者右眼、右半为被摄者左眼。虹膜关键点裁切，轻微 CLAHE 提升对比，圆形透明遮罩。由源照片有限像素放大，不增加真实细节。
- `--no_pupil` 可跳过虹膜图集，texture_path 为 JSON null；diffuse 仍生成。JSON 中贴图为绝对路径，方便 Unity 从不同工作目录读取。

478 点以 normalized x/y/z 数组导出。x/y 原点在图片左上，z 为 MediaPipe 相对深度，不是米制 3D 扫描。比例在消除头部侧倾后的图像平面计算；明显单眼遮挡/侧脸、多人、无脸、无效图片拒绝。该检查不能覆盖所有大俯仰/遮挡，请使用正面清晰、光照均匀肖像。

| 导出控制 | 测量与映射 |
| --- | --- |
| EyeSize / EyeOpenness | 两组上下眼睑距离/眼裂宽度，双眼平均；0.12–0.40 映射到 0–1。当前 EyeSize 是 EyeOpenness 的别名，供不同 Unity 目标映射选择，避免同时叠加 |
| EyeDistance | 内眦 133–362 距离/全脸 234–454 宽度；0.16–0.36 |
| EyeSlanted | 去侧倾后内外眼角高度差角度，外眼角较高为正；-15°–15°，中性约 0.5 |
| Joy | 嘴角相对上下唇中线的上移量/嘴宽；-0.06–0.12，夹紧 0–1 |
| JawRound | 下颌 13 点按脸宽归一化，二次曲线拟合后求下巴处曲率；0.5–3.5 反向映射，宽圆为高，尖窄为低 |

这些区间是启发式标定，非训练出的身份拟合器。原始 metrics、normalization_ranges、下颌拟合残差保留供审计和后续标定；Joy 达到 1 表示上移量超出当前上界，不代表情绪分类结论。

skin_tint 改在鼻侧至苹果肌四个小区域采样，排除眼/唇/鼻翼，用亮度35–90百分位与主RGB色簇中位数降低阴影与高光影响。source_skin_tint保留原始观测色。toon_skin_palette使用归一化sRGB→HSV：V=min(1,max(.85,V*1.15))，S先夹到.12–.28，再偏向低饱和.12；基色H=350°，Shade1 H=325°/S=.12，Shade2 H=285°/S=.14。这是面向二次元的审美重映射，不宣称恢复真实皮肤反射率。skin含base_color/shade_color/shade2_color，所有RGB数组为sRGB 0–1。

hair_palette用10号额头点、152号下巴点估计向上方向，沿脸宽比例向上及横向多点采样，排除脸椭圆、过亮/近白背景与亮度极端，再取主色簇。hair导出base_color/shade_color，阴影轻微偏冷。无可靠区域时hair=null，Unity保留原发色；quality含采样数/方法/限制。该方法是几何ROI启发式，不是头发语义分割，暗背景、帽子及遮挡仍可能误采；白发或头顶裁切可能弃权。使用头顶完整、背景干净的人像效果更可靠。

bone_offsets 是脸宽单位的建议偏移，非米。眼距中性为 0.26，偏移限制 ±0.04；假设 Unity 局部 +X 指向被摄者左侧，LeftEye/RightEye 为人物自身左右。Unity 接入时应乘角色脸宽，并转换到目标眼骨父空间；不要直接作为米制 localPosition。该阶段只生成数据，没有对 VRM 实际应用骨骼或材质。标准 VRM 不保证具有 EyeSlanted/JawRound 等形状键，后续需按资产能力映射。

## 验证

```bash
source deploy-env.sh
tools/face-env/bin/python face_feature_extractor.py --input assets/photo/me.png --output_dir artifacts/validation/face-stage2/ExportedFaceData
tools/face-env/bin/python scripts/test-face-extractor.py
```

实际照片 478 点、六权重范围、RGB 色值、RGBA 两类贴图、可选虹膜关闭、重复推理一致性、几何侧倾 17°/缩放不变性及无脸/多人/损坏/缺失输入拒绝均测试。结果在 artifacts/validation/face-stage2/acceptance.json，日志 logs/face-stage2-extract.log 和 logs/face-stage2-tests.log。MediaPipe 底层会输出反馈张量/投影相关 warning，原始日志保留；这些不是 Python 异常，也不是 Unity 构建报告。

照片、完整关键点 JSON 和生成贴图不提交 Git。最新色彩联动构建与实际渲染结果见RESUME.md顶部及vrm-stage3/acceptance.json；历史第二阶段记录不能代替当前Unity验收。

## schema 3：照片笑意与神态

新增 `expression`，四项都是有限的0–1数值：`smile_degree`、`eye_smile_left`、`eye_smile_right`、`mouth_open`。旧blendshapes保留兼容。`expression_features`先沿两眼中心连线消除侧倾，再计算嘴角平均高度与13/14唇中线的相对差/嘴宽（Smile Arc），以.005–.14归一化；嘴宽/脸宽在.30–.48提供至多25%的佐证，开口本身不会被当作笑意。唇内缘垂直间隙/嘴宽以.015–.40归一化为开口量。

左右眼分别以两组上下眼睑距离/眼裂宽度计算EAR，用经验中性参考.34与压缩区间0–.16估计笑眼，再乘笑意，避免单独闭眼被误判为笑。Left/Right均指人物自身左右。无中性参考照时，天然窄眼与表情挤压无法可靠区分；此值是几何启发式，不是卧蚕重建或情绪分类。metrics包含Smile Arc、嘴宽/脸宽、开口/嘴宽、左右EAR和经验基准；open_smile_candidate仅表示张嘴笑候选，不能证明原照片牙齿可见。

当前实际me.png输出expression约为：笑意1.0、左笑眼.2331、右笑眼.1460、开口.4908。输出保留左右差异，不为了满足示例数字而强制眯眼。Python回归增加实际笑照、无笑闭口、单独闭眼不产生笑意、17°侧倾与等比缩放不变性。

### 男女独立缓存

`python face_feature_extractor.py --input assets/photo/man.png --avatar man`
和 `python face_feature_extractor.py --input assets/photo/woman.png --avatar woman`
分别写入 `artifacts/validation/face-stage2/man/`、`woman/`，JSON 带 `avatar_id`。
显式 `--output_dir` 仍可覆盖输出目录。照片只生成该角色的颜色/可用特征参数，
不会从单照生成新的 VRM 几何。模型关联固定为 man→male.vrm、woman→female.vrm；
运行时拒绝把带 woman 标记的档案关联到 man，反之亦然。
