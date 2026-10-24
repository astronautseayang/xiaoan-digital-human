# 照片特征服务与程序化头部热更新

源码入口为 `face/face_feature_pipeline.py`、`face/face_feature_service.py` 和 `unity-patches/AvatarPipeline/`。当前照片路径为 `assets/photo/me.png`，照片及生成的 Base64/贴图不提交 Git。

## 部署与使用

```bash
cd /home/yyy/digital-human
source deploy-env.sh
# 当前 tools/face-env 已安装依赖；新环境参见 requirements-feature.txt。
bash scripts/install-face-service.sh
# CLI：同时写出 latest.json 和 latest.png。
tools/face-env/bin/python face/face_feature_pipeline.py assets/photo/me.png
# HTTP：原始 PNG/JPEG 字节，不是 multipart/form-data。
curl --noproxy '*' --fail --data-binary @assets/photo/me.png \
  -H 'Content-Type: image/png' http://127.0.0.1:9882/features \
  -o artifacts/face/upload-response.json
```

服务监听 `127.0.0.1:9882`；`GET /health` 检查服务，`GET /latest` 获取完整数据包，`GET /revision` 返回原子 JSON 文件的修改版本。客户端启动加载最新包，之后每2秒检查小型版本响应，仅版本变化时读取贴图并更新。外部 CLI 或 HTTP 换照片后，不需要重建 Unity 或重启客户端。启动/停止脚本包含 human-face 服务。

Unity 组件也提供 `StartCoroutine(controller.UploadPhoto(bytes))`、`StartCoroutine(controller.FetchLatest())` 和主线程 `controller.ApplyJson(json)`。`LastError` 暴露请求/数据错误；错误输入保留已加载的形象。备用模型在设置公开的眼骨/颌骨引用后、首次加载前调用 `Rebind()` 捕获静态基准。

## 数据与映射

v1 JSON 包含 `schemaVersion`、`sourceWidth/Height`、478个 `landmarks:{x,y,z}`、`blendShapes` 对象、原始几何 `metrics`、`textureBase64`、`textureWidth/Height=512`、`textureMime=image/png`、两个 `cheekUV` 和 `upperEyeEdge`。UV 为 Unity 左下原点；landmarks 为 MediaPipe 左上原点、归一化相对深度，不是米制扫描结果。

| 参数 | 比率/角度 | 当前启发式归一化区间 |
| --- | --- | --- |
| EyeScale | 双眼平均眼高/眼宽，33/133/362/263及159/145/386/374 | .15–.42 |
| EyeDistance | 内眼角133–362 / 脸宽234–454 | .16–.36 |
| SmileDefault | 眼轴校正后嘴角61/291相对上唇13的上扬角 | -12–18° |
| JawWidth | 下颌172–397 / 脸宽 | .55–.90 |
| ChinRoundness | 下巴148–377 / 下颌172–397 | .14–.32 |
| MouthWidth | 嘴角61–291 / 脸宽 | .28–.55 |

权重先裁剪到0–1；这些是可调的几何启发式，未训练人群统计模型。当前程序头部设置`centeredShapes=true`，以.5为模型静态中点，映射到-100…100的双向身份 BlendShape；普通外部模型保持默认false，直接映射到0…100。眼睛实体另随身份比例/间距调整；嘴角与嘴宽使用独立 Identity 通道，A/I/U/E/O 的增量不变。`1-exp(-smoothing*deltaTime)` 作为 Mathf.Lerp 系数，完成收敛后停止写入，避免叠加偏移。缺少头部Shape时支持眼骨位置/缩放与颌骨宽度/高度备用变形；备用精度取决于模型实际绑定的骨骼及权重。

## 材质与几何边界

双眼中心构造相似仿射对齐，双边滤波抑制肤质噪声，脸椭圆羽化生成RGBA diffuse。它修正roll/scale/translation，不会恢复被遮挡的侧脸，也不是无光照反照率反演；建议正面单人、均匀光照、自然表情。照片光照残留通过低强度相对肤色调制减弱。

当前Head增加六个专用形变，仍使用原数学闭合拓扑和保留的MeshFilter审计；渲染改为独立SkinnedMeshRenderer。头部高度不因这些横向/局部形变变化，2.5头身基准保持。程序眼睛/嘴巴附近压低照片纹理贡献，避免双眼/双嘴。shader仅在正脸皮肤区域采样，往颈部/后脑淡出；脸颊5×5双侧采样取通道中位数同步全身 `_BaseColor`，头部用独立MaterialPropertyBlock绑定 `_BaseMap`/`_MainTex`，不污染共用皮肤材质。换图销毁前一张运行时Texture2D。

HairSlot挂在Head下。现有五束刘海与后发是同一个闭合隐式网格，故微调共用根节点Y（限幅-4…8mm），而不是拆开闭合网格；每次依据静态基准和眼上缘计算，不累计。更换为拆分发型后可将fringeRoot绑定到独立刘海根。

## 验证

```bash
tools/face-env/bin/python scripts/test-face-features.py
DISPLAY=:1 bash scripts/validate-avatar.sh
```

Python测试真实照片、478点、0–1权重、512RGBA、12°旋转、无脸/无效输入和HTTP请求。Unity测试真实上传、纹理绑定、全身肤色、发型父级、重复换图、平滑过渡、六参数两端和无Shape骨骼备用路径，并继续执行五口型、独立眨眼、脚锁地、中文ASR/TTS、闭合网格、原始帧时和4K截图回归。最新具体成绩见RESUME.md和本次报告；不得引用旧运行成绩替代新版本验收。
