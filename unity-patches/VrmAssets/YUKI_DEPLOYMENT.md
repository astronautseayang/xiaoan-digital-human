# 優希（Yūki）男性角色接入

用户选择 BOOTH「優希（男子キャラ）」替换男性槽位，并将原始 `優希Ver05.vrm` 放入 assets/avatars。
作者商品页：https://booth.pm/ja/items/6266320 （jji-factory）。
原文件/部署文件 SHA256：`34d5273657acebce1fd269df90f056a9e096e73734a0ff9b7955dc0957137ac4`。

原始文件保持不变，male.vrm 为其副本。旧男性桜田史利矢、旧目录和说明保存在
`artifacts/model-backups/fumiriya-before-yuki/`。女性 Alicia 源文件未替换。
同步脚本优先从目录记录的 local_source 获取用户提供的文件并校验 SHA256；在线源仍为作者官方 BOOTH 下载地址，需要用户登录获取。

模型具备标准 Humanoid、五元音、Blink/Blink_L/Blink_R、Joy 与 Fcl_BRW_Surprised。
继续使用现有双实例缓存、男性独立待机/肩宽站姿、呼吸、VRM 眨眼、uLipSync、UpperBody 交互手势和表情注视。
男性 Wave 针对大头比例将 Right Arm Down-Up 调为 .05、Right Forearm Stretch 调为 -.25，手掌外移以减少与头发重叠；女性曲线保持。
優希使用合并的脸/身体材质，无法用材质名区分皮肤、衣服与头发。因此男性禁用照片调色与虹膜贴图，保留作者原始配色和图集；
VRMFaceController 新增 applyProfilePalette 开关，默认开启，優希实例关闭。照片档案仍独立关联并保留表情控制。

## 原始权限

该模型是免费取得的作者自定义授权素材，并非 CC0。原始 VRM 元数据 author=test、allowedUserName=OnlyAuthor、licenseName=Redistribution_Prohibited，
与公开免费商品页的使用范围存在不明确之处。原始权限不做修改；本轮只完成用户提供文件的本地接入测试。
扩大使用范围或分发应用/模型前需核实作者许可，不能将此前桜田史利矢的 CC0 授权沿用到優希。
目录记录保留原始 metadata、商品来源和该限制。

## 验证

构建与双角色切换：scripts/validate-vrm-switch.sh --skip-build。
真实缓存 TTS 与受控文本的口型/动作/表情测试：scripts/validate-interactive-motion.sh --skip-build。
运行结果和截图分别位于 artifacts/validation/vrm-switch 与 artifacts/validation/interactive-motion。

最终男性Wave微调后重新构建和双角色真实TTS缓存动作测试通过：每轮问候各1次，男性/女性谈话手势3/4次，口型、眨眼、抬眉、微笑、注视、结束回归、播放中切换清理均通过。构建0 warnings/0 errors。
