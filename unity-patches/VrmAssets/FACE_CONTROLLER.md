# 阶段 3：Unity VRM 脸部参数与材质热刷新

源码 `unity-patches/VrmPipeline/VRMFaceController.cs`，同步至 Unity Assets/Scripts/LocalHuman/VrmPipeline。VrmAvatarLoader 在 VRM 加载后自动挂载到 Vrm10Instance 根，自动缓存 Animator、所有 SkinnedMeshRenderer、皮肤及眼特征材质。编辑器运行模式可从组件右键菜单 `Reload Face Profile (Play Mode)`，或者客户端窗口按 F。testJsonPath 默认指向阶段 2 的实际测试导出，Inspector 可覆盖。启动可传 -face-profile /absolute/path/face_params.json 自动应用，未传时仍按F刷新。

```csharp
var controller = vrmInstance.GetComponent<LocalHuman.VRMFaceController>();
controller.ApplyFaceProfile("/absolute/path/face_params.json");
// 调用必须在 Unity 主线程；LastError 为 null 表示接受，AppliedProfiles 计数增加。
```

## 版本与形变映射

当前安装 UniVRM 0.128.1 的 VRM10 包，加载的 VRM0 模型已迁移为 VRM1。VRMBlendShapeProxy/AccumulateValue/BlendShapeKey 属于旧 VRM0 API，不在当前包中；此实现使用 Vrm10Instance.Runtime.Expression.SetWeight，并由原生 ExpressionMerger 统一融合。默认 applyProfileExpressions=false：照片里的情绪值不作为持续表情应用，以免Joy=1让人物一直闭眼。只有显式设true时才映射Joy→happy，Sorrow→sad，Angry→angry，Fun→relaxed，Surprised→surprised。只接管这组基础情绪，aa/ih/ou/ee/oh 与 blink 仍由现有 uLipSync/眨眼脚本拥有。

其他 key 默认按不区分大小写的 mesh Shape 名匹配；shapeMappings 可显式设置 profileKey→shapeName。自定义权重从 0–1 转成 SetBlendShapeWeight 的 0–100。凡已被 VRM 原生表达式绑定的 Shape，均跳过直接驱动，避免与口型/眨眼/情绪竞争。不存在的控制记录到 UnmatchedControls，不能凭空生成形状键。

Alicia 原始资产没有 EyeSlanted、EyeDistance、JawRound、EyeSize、EyeOpenness 身份形状键。因此实际照片默认改变皮肤/眼贴图（原生Joy需显式启用），但这些身份形变尚无生产资产可驱动。本阶段验证向真实导入网格的临时克隆加入 Stage3JawRound 测试 Shape，实测自定义映射和 0–100 写入；没有修改原始模型或部署测试 Shape。阶段 2 bone_offsets 不在本任务中应用。

0.25 秒使用固定起止值的 SmoothStep+Lerp，使用 unscaledTime，准确到帧到达目标。重复刷新从当前权重开始，不重置到原始值。Update 提交表达式；控制器 LateUpdate(12000) 在原生 VRM LateUpdate(11000) 后写独立 Shape 与材质，避免被表达式材质还原覆盖。新档案未提供的已管理表情/Shape 平滑回到捕获的原始值。

## 材质与纹理

皮肤匹配 skin/face/body/neck，并排除 wear/cloth/hair/eye/lash 等，避免染衣服；feature 匹配 iris/pupil/eye，排除眼白/睫毛。两个 Material[] Inspector 列表可显式覆盖自动识别。当前 Alicia 命中 Alicia_face 与 Alicia_body 两套皮肤和 Alicia_eye 一套特征材质。schema2的skin.base_color/shade_color/shade2_color分别映射基色/一阶/二阶阴影；旧档案回退skin_tint。studioExposure默认改为1，不再重复乘0.68。支持_Color/_BaseColor、_ShadeColor/_1st_ShadeColor以及有对应属性时的_2nd_ShadeColor。当前MToon10只有基色和一阶阴影，Shade2仍导出供三阶ToonShader使用，不能声称当前模型渲染了第三阶。

自动挂载材质伴随组件FaceMorphController，按Renderer材质槽使用MaterialPropertyBlock在VRM原生表达式后应用皮肤/发色色值；hair名称匹配排除wear/accessory，避免给头饰染色。实际MToon10的有效发色属性是_Color/_ShadeColor，同时兼容_BaseColor/_1st_ShadeColor。hair省略/null保留上次发色；RGB必须恰好3个有限0–1数值，非法数据在提交前拒绝。

为了避免原模型金发/桃色贴图与新颜色重复相乘，首次加载palette时生成缓存中性贴图：头发去色、保留亮度细节与Alpha，皮肤仅对温暖、低中饱和像素去色，保留深色线条/高饱和细节。保留UV/ST/法线贴图，原始资产不修改；禁用/销毁恢复原MPB并释放缓存。MPB通过SetVector显式写入线性RGB，当前三灯棚拍使用studioLightNormalization=.55归一化MToon叠加光预算（JSON高亮sRGB不修改），避免直接sRGB写shader造成过曝。首次GPU读回/贴图去色不计入持续帧窗口，重复同资产使用缓存。皮肤材质乘色和MPB同时同步，防止VRM旧MPB颜色覆盖新色。头发提取仍受照片ROI启发式限制。脸diffuse没有直接投射到VRM的不同UV上。

使用 File.ReadAllBytes+Texture2D.LoadImage 加载 PNG，替换 _MainTex，并兼容 _BaseMap。相对路径按 JSON 所在目录解析；缺失/空/null texture_path 保留当前图。存在但损坏的 PNG 拒绝整份档案；解析/数值/颜色/贴图错误通过 LastError 与 VRM_FACE_REJECTED 记录，保留当前目标。仅接受 <=16MiB、每边<=4096、<=16MP 的 PNG；当前阶段 2 正好输出 PNG。

Stage 2 是双虹膜 atlas，Alicia 双眼共享/镜像整张眼 UV，直接绑定会每眼出现双虹膜。useSingleIrisTile 默认开启：当 profile 的 pupil_layout 声明 256x128 并匹配尺寸时，以 _MainTex_ST 的 X 缩放 .5 采样第一枚虹膜，双眼使用同一虹膜。自有角色已适配双眼 atlas 时可关闭；精准左右眼独立纹理/遮罩和 UV 烘焙属于资产适配，当前不重新生成角色网格。其他普通图片保持原材质 ST。皮肤和权重平滑过渡，眼纹理在解码后一次替换。

材质来自运行时 GLTF 实例，为此角色独有，不克隆以免破坏 VRM 原生材质绑定；纹理由组件拥有，换图销毁旧图，禁用/移除恢复原始色/纹理/ST/独立 Shape 及管理的表情，销毁时释放纹理。重新启用后需再次 ApplyFaceProfile。

## 实际验证

先 source deploy-env.sh，运行 `DISPLAY=:1 bash scripts/validate-vrm-face.sh`。脚本停止正常客户端、完整真实构建（batchmode/quit/900秒）、启动专用运行测试并审计。结束后可 `DISPLAY=:1 bash scripts/open-client.sh` 恢复正常客户端。

报告独立写入 artifacts/validation/vrm-stage3，构建日志 logs/vrm-face-stage3-build.log，客户端日志 logs/vrm-face-stage3-client.log。测试新增schema2肤色基色/冷阴影、实际三套头发材质槽MPB色值、中性贴图绑定、越界发色拒绝；涵盖真实阶段 2 JSON/PNG、自动发现、0.25秒过渡中值和终点、过渡中断、自定义 Shape、脸身色值、贴图与 ST 绑定、缺失贴图保留、坏 JSON/颜色/越界/缺失文件/坏 PNG 拒绝、口型/眨眼输入隔离及卸载恢复。

240 原始帧窗口包含小 JSON 重读与多次 Shape/肤色过渡；不包括初次 PNG 解码、模型加载和 4K 读回，不是 ASR/TTS 性能测试。保存真实照片档案生效的全身与睁眼局部两张 4K 图。原始照片 Joy=1 对应 Alicia 闭眼笑；阶段3专用测试显式启用情绪映射覆盖原接口，正常客户端默认忽略照片情绪。阶段4增加真实照片Joy=1加载后仍睁眼、眨眼后完全睁开的回归与独立截图。

## schema 3：独立照片表情通道

`VRMFaceController.ApplyFaceProfile`对expression四个字段逐项验证数值/有限性/0–1范围；完整解析及PNG检查成功后才交给同根FaceMorphController，非法expression保持上一档案。新字段优先于旧blendshapes.Joy，防止重复叠加。旧字段默认仍不驱动情绪；明确启用applyProfileExpressions的旧API回归继续保留。

FaceMorphController使用固定起止值SmoothStep+Vector4.Lerp在.3秒内过渡，新档案从当前值接续。当前VRM0资产经UniVRM导入为VRM10，Joy对应happy。Alicia的happy绑定eye_smile和笑眉，直接持续happy会闭眼，因此优先使用资产已有区域形状：mouth_smile/Fcl_MTH_Smile（.75倍）、mouth_ornerUp/CornerUp（.25倍）、笑眉（.3倍）；无区域笑嘴时回退保守的.2倍happy。Alicia不含Fcl_MTH_Smile别名，但有实际mouth_smile；没有生成新的角色网格或牙齿。眼弯形状最多22%，共同眼形状用左右笑眼均值，支持独立左右名称时分别映射；当前Alicia只有共同eye_smile，不能声称实现独立左右几何。该上限是当前资产的保守绑定，不保证任意第三方模型无需调校。

照片aa基线=.65×mouth_open×smile_degree。LocalAvatarLipSync是五元音的唯一常规写入者，aa=clamp(speechAa+photoAa×(1-maxSpeechVowel))；语音强时降低照片开口，停止后恢复笑嘴开口，I/U/E/O不叠加照片口型。笑嘴、笑眉和笑眼在VRM原生LateUpdate后一次合成；原生绑定权重加区域增量，非原生绑定每帧直接设置，避免累计漂移。自然blink保持随机2–4秒/220ms，照片笑眼不写blink。禁用恢复形状/材质；有照片开口时，静音的正确状态是回到照片aa基线。

本通道可呈现微张露齿笑，牙齿可见程度取决于资产已有几何；不推断不存在的苹果肌、卧蚕或牙齿形状。当前Alicia没有独立苹果肌上提Shape，不能保证复刻真人开怀笑的全部脸颊细节。阶段4验收检查实际笑嘴权重、最终笑眼上限、0.3秒过渡中值与终点、非法档案不改变状态、原生网格加法、语音五元音与静音恢复、眨眼重新睁开，并输出4K近景与眨眼图。
