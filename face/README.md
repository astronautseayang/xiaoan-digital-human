# 照片人脸基线

此工具生成带照片纹理的正面三维人脸表面及 A/I/U/E/O 五个口型变形。
MediaPipe 估计深度，口型由程序变形生成。它不提供完整后脑、头发、耳朵或精确侧脸；口腔是简化暗色平面。适用于正面交互原型，需目视检查嘴型和接缝。

用户照片建议：单人正面、闭嘴自然表情、均匀照明、无遮挡。个人照片尚未提供。

生成：

    source /home/yyy/digital-human/deploy-env.sh
    tools/face-env/bin/python face/photo_to_face.py assets/photo/me.jpg

在 Unity 中执行 Local Human → Import portrait and create demo scene。
它会创建独立 LocalDigitalHuman 场景和 Portrait.prefab，绑定本地聊天、录音、音频播放以及仓库自带的 uLipSync。原项目场景的网络代码另有补丁。

脚本生成几何数据并不代表 Unity 编译和显示验证已通过。实际状态请查看部署日志。

导出口型预览与标准 GLB（与 Unity 使用同一组几何数据）：

    tools/face-env/bin/python face/preview.py
    tools/face-env/bin/python face/export_glb.py

输出 `artifacts/face/viseme-preview.png` 与 `artifacts/face/photo-face.glb`。
GLB 包含照片纹理和五个实际 POSITION morph targets；这些程序化口型仍需根据个人照片目视校准。
