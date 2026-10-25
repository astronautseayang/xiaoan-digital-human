# 2026-10-24 数字人优化检查

## 最终收尾审查（10月25日）：关键回归及实际服务验证通过

按用户“最后再审查优化一下就结束”的要求，结束持续迭代前检查近期音频输入、
声纹时长边界、WAV完整性、取消清理、对话超时及流式结束逻辑。本轮未复现新的
明确故障，未继续增加功能或改动生产逻辑。git diff --check通过。

直接执行10个回归脚本，共54项unittest通过：ASR完整性4、时长3、取消2、服务15、
声纹配置7、直接对话超时4、对话取消8、流式EOF5、语音缓存5、健康检查1。
健康检查单个测试另含7种状态子场景。证据为logs/stability-20261024/下
final-review-tests.json及final-review-*.log。

实际服务健康脚本退出0，四服务active，网关各项ready=true，离线唤醒idle无错误。
真实录音通过execute_commands=false识别为“小安，今天天气好吗？”，无关怀指令。
普通对话和轮询对话均成功，轮询finish_reason=stop，error为空；两份语音文件
下载并验证全部声明PCM帧，均32000Hz，分别234284/193324字节、3.66/3.02秒。
ASR/声纹/音色/定位配置哈希一致。证据final-review-live.json及final-review-health.log。

原备份目录/home/yyy/备份/digital-human-20261024-2130仍存在；它早于后续优化，
不是本轮最新快照。本轮没有重新复制大体积备份。实际浏览器播放、麦克风硬件及
长时间连续运行未在本轮验证。以上检查证明覆盖范围内通过，不代表不存在所有bug。
完成本次收尾后停止自动持续优化，保留项目当前可用状态与全部测试记录。

## 持续稳定性检查（10月25日）：五秒声纹录入不再因降噪缩短而误拒绝

沿上轮滤镜时长发现继续复现：clean_audio将5秒录音缩短约400个16kHz样本，
SpeakerInput.enroll随后按降噪长度执行五秒下限，正好五秒也被拒绝。现在沿用
项目voice_denoise的长度保持方式，在原滤镜之后添加apad/atrim，以解码帧数
恢复输出长度。超过30秒仍在降噪前拒绝，不通过放宽录入下限解决；补齐的是
尾部静音，不声称恢复滤镜未输出的声音。人声和声纹一致性检查保持原流程。

时长测试新增真实FFmpeg五秒/十秒录入，通过临时SpeakerInput和VAD/embedding替身
隔离线上声纹；4.99/10.2秒拒绝，拒绝后配置字节保持不变。29.9/30秒输出现在
要求精确等于解码采样数，不再仅要求50ms容差。修复前五秒用例报错、两个长度
断言失败，修复后时长3项、完整性4项、声纹配置7项、ASR取消2项共16项通过。
真实噪声、已录入声纹、混合声音、配置持久化及中文流式/TTS综合验证通过。

重启后正常实际录音识别为“小安，今天天气好吗？”，截断WAV仍返回明确提示；
线上请求均execute_commands=false，无关怀指令，四份用户配置哈希不变。健康脚本
退出0，四服务active、网关全就绪、唤醒idle无错误，worker_pid=114158。
没有通过线上声纹录入接口覆写用户声纹；五秒录入边界的证据来自隔离测试。
未验证浏览器实际麦克风。git diff --check通过。
证据：logs/stability-20261024/asr-filter-duration-before.log、
asr-filter-duration.log、asr-filter-integrity.log、asr-filter-profile.log、
asr-filter-cancellation.log、asr-filter-language.log、asr-filter-deployed.json、
asr-filter-health.log。回归以human-gsv-v2环境Python及PYTHONNOUSERSITE=1
PYTHONPATH=.直接执行scripts/test-asr-duration.py、scripts/test-asr-integrity.py、
scripts/test-speaker-profile.py、scripts/test-asr-cancellation.py、scripts/test-speaker-language.py。

## 持续稳定性检查（10月25日）：拒绝数据截断的有限长度WAV

真实FFmpeg复现：两秒PCM16 WAV截去1/2/4/16000字节后仍成功解码，clean_audio
继续返回残留音频；ASGI请求也继续调用识别，可能只处理指令前半段。现在对RIFF/WAVE
逐个检查块长度，跳过元数据及奇数字节填充，声明长度超出实际剩余数据时返回
“录音数据不完整，请重新录制。”，不进入识别和指令执行。解析最多扫描上传字节数。
兼容管道WAV以0xffffffff表示未知data长度；该情况不能凭长度字段证明尾部完整。
WebM/Ogg/MP3沿用原解码行为，本轮不声称检测这些格式的所有损坏。

新增完整性4项回归（截断4种、正常4种格式、元数据/填充和损坏块、接口拒绝及恢复），
时长2项、取消2项共8项通过；真实噪声/声纹/配置持久化及中文流式/TTS综合脚本通过。
正常格式测试包含FFmpeg管道WAV，确保未知长度兼容。修复前有5处断言失败证据。
一次误选的Unity键盘验证脚本因当前Python无gi退出，未启动Unity；与本次音频变更
无关，相关验证使用scripts/test-speaker-language.py，未宣称完成硬件键盘验证。

重启上线后真实截断WAV返回HTTP200、空text及明确提示；下一次正常录音识别为
“小安，今天天气好吗？”。线上测试均execute_commands=false，未执行关怀指令，
ASR/声纹/音色/定位配置哈希不变。健康脚本退出0，四服务active、网关全就绪、
唤醒idle无错误，worker_pid=111808。未验证实际浏览器麦克风硬件。
证据：logs/stability-20261024/asr-integrity-before.log、asr-integrity.log、
asr-integrity-duration.log、asr-integrity-cancellation.log、
asr-integrity-speaker-language.log、asr-integrity-deployed.json、asr-integrity-health.log。
回归使用human-gsv-v2环境及PYTHONNOUSERSITE=1 PYTHONPATH=.直接执行
scripts/test-asr-integrity.py、scripts/test-asr-duration.py、
scripts/test-asr-cancellation.py、scripts/test-speaker-language.py。

## 持续稳定性检查（10月25日）：超长录音明确拒绝，避免静默截断执行

clean_audio原来通过FFmpeg的-t 30静默截断长录音，后续可能仅识别和执行前半段。
现先将音频解码为16kHz单声道float32，最多读取31秒；超过30秒立即返回输入提示，
不进入人声检测、识别或关怀指令。检查后再运行原降噪滤镜。实际验证afftdn会缩短
约25ms，因此必须在降噪前检查，不能直接依赖滤镜输出长度。代价是有效录音增加
一次FFmpeg进程调用。网页和ASR文档增加30秒限制说明；网页仍需用户手动停止录音。

新增真实FFmpeg边界回归：29.9/30秒接受，30.001/30.1/31/35秒拒绝；ASGI验证
超长输入返回HTTP200、空text、明确input_notice，识别和指令函数未调用，锁释放，
后续正常请求成功。时长2项、ASR取消2项、识别服务15项、声纹7项、音质8项共34项
通过，中文输入综合验证脚本通过。原始失败日志中还包含过于精确的长度断言，
发现滤镜缩短后已改为50ms容差；超长录音未拒绝的失败仍证明原问题。

重启网关后真实35秒输入返回“录音超过30秒，请缩短后重新录制。”；正常录音识别为
“小安，今天天气好吗？”。线上识别均使用execute_commands=false，无关怀指令，
ASR/声纹/音色/定位四份配置哈希不变，页面提示已生效。刚重启时健康检查准确返回1，
网关就绪后重新检查退出0，四服务active、ready各项true、唤醒idle无错误，
worker_pid=108022。未验证实际浏览器麦克风硬件。git diff --check通过。
证据在logs/stability-20261024/下：asr-duration-before.log、asr-duration.log、
asr-duration-{cancellation,service,speaker,quality,language}.log、
asr-duration-deployed.json、asr-duration-health-starting.log、asr-duration-health.log。

## 持续稳定性检查（10月25日）：健康脚本按实际就绪和服务状态退出

scripts/health.sh原来HTTP200就打印HTTP OK，不检查/ready正文；curl失败只打印
UNAVAILABLE，systemctl status失败被|| true吞掉，最终仍可能退出0，启动调用方
无法识别故障。现保留端口诊断，额外要求网关JSON对象中的ready严格为布尔true，
明确输出GATEWAY READY/NOT READY；任一端口失败、ready不满足或服务状态失败均
累积health_failed并退出1，同时仍输出其他服务诊断。使用mktemp目录和EXIT清理，
替代固定/tmp文件，避免并发检查相互覆盖。仍是一次检查，启动中尚未就绪也会
返回1，不自动重启服务或重试。start-services.sh可通过其既有严格模式收到失败。

新增脚本回归直接运行生产shell逻辑，仅在临时副本中替换部署环境初始化，
用假curl/systemctl隔离实际服务。覆盖7个场景：正常、ready=false、字符串true、
无效JSON、非对象JSON、端口不可达、服务异常；修复前6异常场景退出0导致失败，
修复后7场景全部通过，且临时目录无遗留文件。bash -n与git diff --check通过。
运行真实bash scripts/health.sh退出0，三个端口HTTP可达，GATEWAY READY，四个服务
active；网关ready各项true、唤醒idle无错误，worker_pid=105681。仅修改运维检查，
未重启服务，未重复对话/音频测试。证据：logs/stability-20261024/下
health-exit-before.log、health-exit.log、health-exit-deployed.log。
回归命令：human-gsv-v2环境Python执行scripts/test-health-check.py；
bash -n scripts/health.sh scripts/start-services.sh；bash scripts/health.sh。

## 持续稳定性检查（10月25日）：部分启动失败回收客户端及数据库

上轮finally仅覆盖yield后的生命周期。继续复现WeatherService/CareEngine/
WakeService构造抛错时客户端未关闭；WakeService失败前还可能已经调度关怀任务，
该任务未运行便取消时无法执行其内部finally，数据库连接也不能依赖它回收。
现从HTTP客户端创建后即进入try/finally，用空任务列表和可选care_task跟踪已创建
资源；先构造全部组件，再调度后台任务。退出时取消已创建任务并等待，显式关闭
已构造关怀组件的SQLite连接，最后沿用原对话/ASR清理和HTTP客户端关闭顺序。
SQLite.close可重复调用，正常run退出已关闭的连接也可安全再次关闭。

另复现CareEngine构造期间reminders.initialize抛OperationalError后，连接仍可查询，
而对象未返回导致外层无法回收。构造函数在数据库打开后增加失败清理，关闭连接并
重新抛出原异常。该分支以真实内存SQLite验证关闭后SELECT报ProgrammingError。
不自动重试启动，不隐藏导致启动失败的异常。

取消/生命周期8项（新增3种构造失败）、关怀17项（新增构造数据库关闭）、
唤醒生命周期6项、ASR取消2项共33项通过。两项新增回归均有修复前失败证据；
客户端关闭仅一次、没有遗留后台任务、原异常身份保留。git diff --check通过。
关怀测试使用临时数据库，没有创建线上提醒。故障注入均为隔离测试。

重启后真实普通对话1.46秒、轮询任务1.38秒完成，finish_reason=stop、error为空。
两份WAV完整PCM校验通过，32000Hz、336684/408364字节、5.26/6.38秒。
四服务active，/ready全就绪，唤醒idle无错误，worker_pid=105681。
未验证浏览器实际播放及麦克风硬件。证据：logs/stability-20261024/下
startup-cleanup-before.log、startup-care-db-before.log、startup-cleanup.log、
startup-cleanup-care.log、startup-cleanup-wake.log、startup-cleanup-asr.log、
startup-cleanup-deployed.json。回归用human-gsv-v2环境Python及PYTHONNOUSERSITE=1
PYTHONPATH=.执行scripts/test-chat-cancellation.py、scripts/test-senior-care.py、
scripts/test-wake-lifecycle.py、scripts/test-asr-cancellation.py。

## 持续稳定性检查（10月25日）：生命周期异常退出仍执行清理

lifespan原来在yield后顺序执行清理；上下文体抛出异常或取消时，异常在yield
处重新抛出，跳过唤醒/心跳/关怀任务回收、对话任务清理及HTTP客户端关闭。
现在将yield置于try/finally，正常退出与异常退出共用原有清理顺序；先等待
后台及对话/ASR任务清理，再关闭客户端，不吞掉原始异常或取消。
该修复覆盖已进入yield后的退出；启动初始化尚未完成前的构造失败不属于本轮验证。

取消回归扩展到7项，新增RuntimeError和CancelledError两子场景，模拟生命周期
体异常并验证三个后台任务全部结束、aclose仅调用一次、__aexit__不抑制原异常。
修复前两子场景均留下后台任务，修复后通过。原并发取消、请求断开、后台尚未
启动取消及关闭期间等待已有清理全部通过。ASR取消2项、原流式稳定性5场景
通过；git diff --check通过。测试使用假客户端/任务，不启动真实关怀提醒。

重启网关后真实普通对话1.58秒、轮询任务1.034秒完成，轮询finish_reason=stop、
error为空。两份WAV完整PCM帧校验通过，32000Hz、393004/199724字节、
6.14/3.12秒。四服务active，/ready全就绪，唤醒idle无错误，worker_pid=104783。
系统日志显示网关正常停止及启动；未向线上生命周期注入异常，未验证实际播放硬件。
证据：logs/stability-20261024/下lifespan-finally-before.log、lifespan-finally.log、
lifespan-finally-asr.log、lifespan-finally-stability.log、lifespan-finally-deployed.json。
回归用human-gsv-v2环境Python及PYTHONNOUSERSITE=1 PYTHONPATH=.执行
scripts/test-chat-cancellation.py、scripts/test-asr-cancellation.py、scripts/test-chat-stability.py。

## 持续稳定性检查（10月25日）：有效结束帧无需等待连接关闭

流式生成原来收到stop/length只记录completed，仍等待下一行或连接EOF；若上游
不发[DONE]且连接保持打开，缓冲尾句不能及时合成，最终可能将有效回答报超时。
现在完成类型及delta字段验证后，处理结束帧携带的最后文字，然后立即退出读取，
通过响应上下文关闭连接并提交缓冲尾部；无content的结束帧同样立即完成。
单次请求只生成一个choice，不需要等待额外usage帧。缺少任何完成信号的EOF
仍报中断，非法结束类型仍拒绝，不放宽已有错误处理。

扩展EOF回归到5项，新增stop带末尾文字、length带末尾文字、stop空delta后
永久等待3个子场景。修复前3种均被外层2秒超时中止，修复后全部通过，验证
末尾文字完整、截断标志和结束原因正确，全部正常/异常场景的响应上下文均关闭。
取消6项、原结束原因/TTS失败脚本、重复输出脚本通过。git diff --check通过。
故障为本地流模拟，未人为挂起线上模型连接。

重启后真实普通对话1.37秒、轮询任务1.281秒完成；轮询finish_reason=stop且
error为空。两WAV完整PCM帧校验通过，32000Hz、336684/321324字节、
5.26/5.02秒。四服务active，/ready全就绪，唤醒idle无错误，worker_pid=104203。
未验证浏览器实际播放或麦克风硬件。证据：logs/stability-20261024/下
finish-socket-before.log、finish-socket.log、finish-socket-finish.log、
finish-socket-cancellation.log、finish-socket-repetition.log、finish-socket-deployed.json。
回归用human-gsv-v2环境Python及PYTHONNOUSERSITE=1 PYTHONPATH=.执行
scripts/test-chat-stream-eof.py、scripts/test-chat-finish.py、scripts/test-chat-cancellation.py、
scripts/test-chat-repetition.py。

## 持续稳定性检查（10月25日）：合成后PCM完整性与缓存保护

synthesize对语音后处理结果原来只检查WAV头的帧数大于零，没有读取PCM核对。
本地故障注入复现：正常文件头后截去1/2/4字节，单声道和双声道共6种结果
均被/api/tts返回200，可能进入成功缓存或后续对话音频发布。现在在缓存前
读取声明帧，核对实际字节数等于帧数×声道数×采样字节数；空或截断结果返回
502“语音处理失败，请检查服务日志”，不写成功缓存。该检查针对后处理产物，
不声称发现线上ffmpeg实际产生过这种损坏，也不替代语音内容质量校验。

扩展缓存回归到5项，新增6种截断子场景均验证TTS/普通对话502、流式任务报错
且无clip、无坏音频缓存；恢复完整数据后TTS成功且第二次复用缓存。修复前
新增6子场景失败，修复后通过。音质8项、关怀16项、普通对话总超时4项通过，
合计33项。音质称呼分句测试的旧模拟只发送content后EOF，补上[DONE]使其符合
已实施的流式完成协议；断流行为仍由独立EOF回归覆盖，未放宽生产校验。
git diff --check通过。关怀测试使用临时目录/SQLite，没有创建线上提醒。

重启网关后真实普通对话和轮询任务完成，轮询finish_reason=stop且error为空。
两个WAV完整PCM帧校验通过，32000Hz、386604/334124字节、6.04/5.22秒。
四服务active，/ready全就绪，唤醒idle无错误，worker_pid=103558。
未验证实际浏览器播放及麦克风硬件。证据：logs/stability-20261024/下
processed-wav-before.log、processed-wav-cache.log、processed-wav-quality.log、
processed-wav-care.log、processed-wav-timeout.log、processed-wav-deployed.json。
回归用human-gsv-v2环境Python及PYTHONNOUSERSITE=1 PYTHONPATH=.执行
scripts/test-speech-cache.py、scripts/test-voice-quality.py、scripts/test-senior-care.py、
scripts/test-chat-direct-timeout.py。

## 持续稳定性检查（10月25日）：普通对话增加全流程总时限

普通对话此前仅依赖HTTP客户端每次调用180秒超时；模型、中文改写与语音合成
可累计超过网页240秒等待上限，等待voice_lock本身也无截止时间。现在普通
对话以asyncio.wait_for复用CHAT_TIMEOUT_SECONDS=180作为全流程时限，包含
本地回复、模型生成、中文改写、语音排队与合成；到期取消协程并返回504及
“本次回答等待超时，请重试。”，不发布迟到音频。客户端取消继续传播，不转成504。
总时限为异步协作取消；已交给线程的处理或上游已收到的推理不保证立即终止，
已发生的本地命令副作用不回滚，不自动重试请求。

新增4项回归覆盖模型挂起、语音锁排队、两个未单独超时阶段累计超时及父请求
取消。前三项均验证无音频文件、取消清理和随后请求成功。修复前累计耗时仍
返回200、模型/锁等待被外层测试超时中止；修复后4项通过。模型响应4项、
音频保留4项，以及原流式稳定性5个场景通过（TTS失败、模型失败、总超时、
初始化失败、WAV处理与串行推理重叠）。git diff --check通过。

重启网关后真实普通对话1.2秒完成，轮询任务0.874秒完成且finish_reason=stop、
error为空。两份WAV完整PCM帧校验通过，32000Hz、262444/193324字节、
4.1/3.02秒。四服务active，/ready全就绪，唤醒idle无错误，worker_pid=102712。
超时采用本地模拟，不向线上服务注入故障；未验证浏览器实际播放和麦克风硬件。
证据：logs/stability-20261024/下direct-timeout-before.log、direct-timeout.log、
direct-timeout-model.log、direct-timeout-audio.log、direct-timeout-stability.log、
direct-timeout-deployed.json。回归以human-gsv-v2环境Python及PYTHONNOUSERSITE=1
PYTHONPATH=.执行scripts/test-chat-direct-timeout.py、scripts/test-model-response.py、
scripts/test-audio-retention.py、scripts/test-chat-stability.py。

## 持续稳定性检查（10月25日）：普通对话校验模型结束原因

普通对话及中文改写共用的completion_text原来只检查文字，模型返回过滤、
工具调用或非法finish_reason且带非空文字时，可能将部分回答当作正常结果播出。
现在先检查choice对象，再校验结束原因；仅接受stop、length或缺失/null，
其他原因统一返回502“大模型返回格式异常”，不合成语音、不创建音频文件。
中文改写遇到同类异常继续使用已有中文兜底。length仍按原兼容行为接受，
本轮没有为普通对话新增截断提示。

模型响应4项、中文输出4项、流式EOF与字段4项共12项回归通过；模型异常覆盖
原11种结构及新增8种结束原因，正常stop/length/null和缺失原因兼容通过。
修复前新增异常原因测试失败，修复后通过；choice=null继续返回502，避免新增
属性访问导致500。git diff --check通过。重启网关后真实普通对话及轮询任务
成功，轮询finish_reason=stop、error为空。两个WAV完整PCM帧校验通过，
32000Hz、403244/249644字节、6.3/3.9秒。四服务active，/ready全就绪，
唤醒idle无错误，worker_pid=102013。未验证浏览器实际播放或麦克风硬件。
证据：logs/stability-20261024/下completion-reason-before.log、completion-reason.log、
completion-reason-language.log、completion-reason-stream.log、completion-reason-deployed.json。
回归命令：human-gsv-v2环境Python配合PYTHONNOUSERSITE=1 PYTHONPATH=.执行
scripts/test-model-response.py、scripts/test-output-language.py、scripts/test-chat-stream-eof.py。

## 持续稳定性检查（10月25日）：流式字段类型与结束原因验证

复现finish_reason=True/数字/容器或未知原因可能标成成功并污染任务字段，
content=False/0/空容器被or空串静默吞掉；正常终帧delta=null却触发属性错误。
现在校验流式payload对象、delta对象、content字符串；缺失/null delta按空对象，
缺失/null content按空串，其他类型返回中文格式异常。finish_reason仅接受
当前文字/语音链路支持的stop/length或未结束null；content_filter/tool_calls及
未知/非字符串原因报未正常完成，不将它们当作已完成文本。字段校验在写入
任务结束状态及提交缓冲前执行。未添加工具调用能力，也未假称过滤后文本完整。

扩展EOF回归4项通过，新增14个异常字段子场景（7种原因、5种content、2种delta），
以及角色帧、用量帧、null content/null delta兼容；原断流、3种完成信号、
后续重试测试通过。原完成原因/TTS失败及重复输出脚本通过。git diff --check
通过。异常输入为本地流模拟，没有修改线上模型返回。重启网关后真实普通与
轮询对话成功，轮询finish_reason=stop且error为空；两个WAV下载完整PCM帧校验
通过，32000Hz、330284/212524字节、5.16/3.32秒。四服务active，/ready全就绪，
唤醒idle无错误，worker_pid=101455。
证据：logs/stability-20261024/下chat-stream-fields-before.log、chat-stream-fields.log、
chat-stream-fields-finish.log、chat-stream-fields-repetition.log、chat-stream-fields-deployed.json。
回归命令：human-gsv-v2环境Python配合PYTHONNOUSERSITE=1 PYTHONPATH=.执行
scripts/test-chat-stream-eof.py、scripts/test-chat-finish.py、scripts/test-chat-repetition.py。

## 持续稳定性检查（10月25日）：流式连接EOF不能冒充回答完成

复现流式响应只有部分content便EOF，既无finish_reason又无[DONE]时，原逻辑
仍合成缓冲尾部、标记任务无错误，客户端可能把不完整回答加入历史。现在流式
分支记录明确完成信号，只有finish_reason或[DONE]才能在连接结束后提交尾部；
缺少信号报“回答传输中断，请重试”，继续执行原有任务与TTS清理。已经发送的
流式片段不可能撤回，本轮防止将未确认尾部继续合成及将整个任务误报成功。
兼容显式[DONE]但无reason、reason=stop/length后直接EOF；已有[DONE]立即结束
语义保留。本轮不宣称验证所有finish_reason值或流式JSON字段类型。

新增EOF测试2项，修复前部分回答误报成功失败，修复后验证错误、缓冲尾部无
音频、后续新任务可成功，以及3种正常完成信号；原完成原因/TTS失败脚本、
取消6项及重复输出回归通过。git diff --check通过。中断采用本地流式模拟，
未中断线上LLM连接。重启网关后普通/轮询实际对话成功，轮询finish_reason=stop、
error为空；两WAV下载完整PCM校验通过，32000Hz、399404/412204字节、6.24/6.44秒。
四服务active，/ready全就绪、唤醒idle无错误，worker_pid=100930。
证据：logs/stability-20261024/下chat-eof-before.log、chat-eof.log、
chat-eof-finish.log、chat-eof-cancellation.log、chat-eof-repetition.log、chat-eof-deployed.json。
回归命令：human-gsv-v2环境Python配合PYTHONNOUSERSITE=1 PYTHONPATH=.执行
scripts/test-chat-stream-eof.py、scripts/test-chat-finish.py、
scripts/test-chat-cancellation.py、scripts/test-chat-repetition.py。

## 持续稳定性检查（10月25日）：迟到取消不改写已结束任务结果

复现DELETE在后台已经完成时仍无条件将finish_reason改成cancelled，成功、截断、
超时、重复输出或普通生成错误均可能被迟到停止请求改写，影响后续轮询诊断。
现先检查job.done；已结束则返回原接口确认结构，不改任务任何字段。活动任务
继续走原取消、shield等待和幂等清理；过期检查先执行，过期任务仍404。

新增本地ASGI回归修复前成功等终态被改写，修复后取消6项、过期3项、音频4项
共13项通过。新增覆盖6种终态×有无已完成handle，共12子场景，各连续DELETE
两次并GET验证完整原始结果不变，包含原错误、文本和音频列表。原请求断开、
并发取消、后台启动前取消及服务关闭清理回归通过。git diff --check通过。
重启网关后普通对话和轮询任务实际完成；对该已完成任务连续取消两次均200，
每次轮询与取消前完整JSON一致，finish_reason保持stop。两份WAV实际下载完整PCM
校验通过，均32000Hz、230444字节、3.6秒。四服务active，/ready全就绪，
唤醒idle无错误，worker_pid=100404。失败终态由隔离测试验证，未制造线上模型故障。
证据：logs/stability-20261024/下chat-terminal-before.log、
chat-terminal-cancellation.log、chat-terminal-expiry.log、chat-terminal-audio.log、
chat-terminal-deployed.json。回归命令：PYTHONNOUSERSITE=1 PYTHONPATH=. 配合
human-gsv-v2环境Python执行scripts/test-chat-cancellation.py、
scripts/test-chat-expiry.py、scripts/test-audio-retention.py。

## 持续稳定性检查（10月25日）：未来文件时间不能误删当前回答音频

复现音频目录有201份未来mtime文件时，普通chat生成的新音频会排序到最旧，
本次prune在返回URL前删掉它，产生成功回答但音频404。备份恢复或系统时间
回拨可造成这种文件时间关系；此前只保护轮询任务音频，没有明确保护当前
普通回答。现在prune_chat_audio接受当前文件名并加入本次保护集合，chat保存
成功后传入文件名，保证本次清理不会删除即将返回的音频。原有轮询保护保留。
本轮只保证当前响应不被自己的清理误删，后续回答的清理仍按原保留规则执行，
没有承诺所有历史重播永久有效。未来mtime场景可能额外保留当前受保护文件。

专项回归修复前确认新文件被删除，修复后连续两次回答的当前文件均存在、
内容完整，且多余无保护旧文件仍被清理。音频保留/保存4项、过期3项、取消5项
全部通过；使用临时目录设置文件mtime，未修改系统时钟或线上音频。既有部分
写入、替换失败、清理访问失败及轮询音频保留测试通过。git diff --check通过。
重启网关后实际普通对话和轮询对话成功无错误，两个WAV下载按完整PCM帧数验证，
32000Hz、277804/249644字节、4.34/3.9秒。四服务active，/ready全就绪，
唤醒idle无错误，worker_pid=99816。线上没有注入未来时间文件，异常边界由本地
受控目录测试验证。
证据：logs/stability-20261024/下audio-clock-before.log、audio-clock-retention.log、
audio-clock-expiry.log、audio-clock-cancellation.log、audio-clock-deployed.json。
回归命令：PYTHONNOUSERSITE=1 PYTHONPATH=. 配合human-gsv-v2环境Python分别执行
scripts/test-audio-retention.py、scripts/test-chat-expiry.py、scripts/test-chat-cancellation.py。

## 持续稳定性检查（10月25日）：轮询任务过期与音频保护一致

检查发现音频清理对已完成且创建超过600秒的任务取消额外保护，但GET仍直接
返回该任务与旧音频地址；只有新建任务才删除过期记录，可能返回已被清理的音频。
现抽取prune_chat_jobs并在新建、轮询、取消入口统一清理已完成的过期记录。
GET/DELETE过期任务返回原有404“对话已过期”；超过期限仍生成中的任务保留，
恰好600秒仍保留。沿用从创建起600秒的既有期限，本轮未改为完成时间计时。
清理仅随任务接口请求发生，没有引入后台清理定时器或固定内存上限。

新增回归修复前轮询未清理记录、过期GET/DELETE未404失败。修复后过期测试3项、
取消清理5项、音频保留/原子保存3项通过。含本地ASGI接口200/404和JSON实际
序列化验证，临时隔离jobs字典、单调时钟，不向线上注入任务或修改线上时钟。
git diff --check通过。重启网关后真实普通对话和轮询任务均完成无错误；两份
WAV下载并按完整PCM帧数验证，32000Hz、346924/358444字节、5.42/5.6秒。
四服务active、/ready全部就绪，唤醒idle无错误，worker_pid=99276。
线上验证正常链路，过期600秒边界使用受控时钟在本地测试，无实际等待十分钟。
证据：logs/stability-20261024/下chat-expiry-before.log、chat-expiry.log、
chat-expiry-cancellation.log、chat-expiry-audio.log、chat-expiry-deployed.json。
回归命令：PYTHONNOUSERSITE=1 PYTHONPATH=. 配合human-gsv-v2环境Python分别执行
scripts/test-chat-expiry.py、scripts/test-chat-cancellation.py、scripts/test-audio-retention.py。

## 持续稳定性检查（10月25日）：成功JSON字段校验与空转写保护

复现HTTP成功但响应缺少字段时，网页先追加undefined等内容，再在历史处理抛错；
缺音频字段可清空草稿和替换旧音频；非字符串ASR先覆盖输入再在trim抛错。
核对实际后端，InputRejected会返回text为空且携带input_notice，原网页会清空
草稿并误提示“识别完成”。新增三组回归在修复前均失败。

现在json封装先确认对象结构：就绪ready必须布尔，对话text/audio_url必须非空
字符串，ASR text必须字符串，验证后才允许调用方改变记录、历史、输入和音频。
空/空白转写保留输入，显示后端非空input_notice，否则提示未识别到有效语音。
既有超长转写、编辑冲突仍按此前规则处理，不改变后端声纹设置或命令执行方式。
本轮验证字段存在及类型，没有宣称校验音频URL指向的资源或所有附加字段。

请求10组、页面/录音15组、历史3组全部通过，新增覆盖10种异常对话正文，
7种异常/空/被拒绝转写和5种异常就绪正文。对话逐例保留原记录、草稿、历史及
旧音频，按钮恢复、计时器清理，后续重试成功；ASR保留草稿并显示正确原因。
git diff --check通过。运行页面200且与本地一致；当前json封装通过原生fetch
实际识别安全测试音频，返回“小安，今天天气好吗？”，execute_commands=false，
无care_command；普通对话与TTS随后成功。音频200、384044字节、RIFF/WAVE标记
正常，定时器残留0。四服务active，/ready全就绪，唤醒idle无错误，刷新页面加载。
异常响应和声纹拒绝分支采用模拟返回；未改线上声纹限制、未制造线上紧急事件。
该线上检查模拟DOM/播放，不等同真实浏览器硬件测试。
证据：logs/stability-20261024/下web-response-fields-before.log、
web-response-fields-timeout.log、web-response-fields-recording.log、
web-response-fields-history.log、web-response-fields-deployed.json。
回归命令：node scripts/test-web-timeout.cjs、node scripts/test-web-recording.cjs、
node scripts/test-web-history.cjs。

## 持续稳定性检查（10月25日）：HTTP错误与非JSON返回提示

复现json封装直接Error(d.detail)：FastAPI的422 detail数组会显示[object Object]；
HTML错误页、空响应先抛JSON解析异常，丢失HTTP状态；错误正文为null还会抛属性
读取异常。现在读取正文仍在原请求总超时内，解析失败时按HTTP状态提示，
成功状态但非JSON正文提示服务返回格式异常。HTTP失败若detail为非空字符串
保留原说明；422结构化详情统一提示检查输入，其余以HTTP状态提示检查服务。
不展示校验详情里可能包含的整段输入，不自动重发。Abort仍交给原超时提示，
所有分支finally清理计时器。对话/ASR原有失败恢复逻辑继续保留输入。

新增两组在修复前因422显示[object Object]失败，修复后请求测试7组、录音15组、
历史3组通过。每条对话/ASR错误组覆盖7种实际Response对象：字符串detail、
结构化422、HTML502、空503、null500、对象detail500、成功状态无效JSON；
验证输入保留、历史不污染、按钮恢复和定时器清理，对话逐例验证随后重试成功。
原连接/正文超时回归仍通过；git diff --check通过。尚未添加成功JSON正文的
各接口字段验证，本轮不宣称所有响应格式异常已覆盖。

运行页面200且与本地一致；执行当前json封装调用实际接口触发无副作用422，
确认显示中文校验提示；随后当前页面普通对话、TTS及音频下载成功，WAV 200、
343084字节、RIFF/WAVE标记正常、定时器残留0。四服务active，/ready全部就绪，
唤醒idle无错误。HTML错误页以本地Response模拟，未干扰线上服务；线上检查
使用模拟DOM/播放，不等同真实浏览器测试。刷新页面加载修改。
证据：logs/stability-20261024/下web-http-errors-before.log、
web-http-errors-timeout.log、web-http-errors-recording.log、web-http-errors-history.log、
web-http-errors-deployed.json。回归命令：node scripts/test-web-timeout.cjs、
node scripts/test-web-recording.cjs、node scripts/test-web-history.cjs。

## 持续稳定性检查（10月25日）：麦克风权限等待上限与迟到授权清理

复现getUserMedia始终不返回时，网页busy一直为true、发送和录音按钮一直禁用。
新增权限等待回归修复前因缺少等待上限失败。现在microphone封装30秒等待上限，
超时交由原录音初始化异常路径恢复按钮、保留草稿并提示处理浏览器权限后重试。
请求正常授权或拒绝均清除计时器。超时后的原getUserMedia仍挂接完成处理：
迟到授权立即停止该请求的全部轨道，不创建MediaRecorder、不上传、不改页面状态；
迟到拒绝被消费，不影响已恢复页面。新请求拥有自己的计时器和过期标记，
旧授权不会停掉新录音的轨道。浏览器权限弹窗本身不能由此代码强制关闭，
实际getUserMedia未被取消；若一直不结算，关联处理仍待浏览器完成。

页面/录音15组、请求超时5组、历史3组通过。新增覆盖权限超时后按钮与草稿恢复，
新录音开始后旧授权到达只停止旧轨道，以及迟到拒绝、普通授权/拒绝清理计时器。
使用模拟时钟触发30秒边界，未实际等待30秒，也未宣称真实浏览器权限测试。
git diff --check通过。运行页面200且与本地一致，当前脚本+原生fetch实际普通
对话成功，WAV下载200、197164字节、RIFF/WAVE标记正常，定时器残留0。
四服务active，/ready全就绪，唤醒idle无错误；刷新页面加载修改。
证据：logs/stability-20261024/下web-permission-before.log、
web-permission-recording.log、web-permission-timeout.log、web-permission-history.log、
web-permission-deployed.json。回归命令：node scripts/test-web-recording.cjs、
node scripts/test-web-timeout.cjs、node scripts/test-web-history.cjs。

## 持续稳定性检查（10月25日）：超长转写与发送长度恢复

确认ChatRequest.text最多2000 Unicode字符，而textarea的maxlength不能限制程序
填入的ASR结果。原页面超长转写仍显示“点击发送”，发送后接口422；后端结构化
校验错误还可能显示为[object Object]。本轮在进入busy/请求前检查trim后字符数，
超过2000字时明确提示缩短且保留输入；未截断或自动分次发送，避免改变指令。
ASR填入超长转写时同步提示长度限制，完整转写仍可编辑。与用户草稿冲突时继续
走前轮保留草稿、显示转写的路径。计数用Array.from，与Python按Unicode字符
计数一致；原HTML手动输入maxlength仍按浏览器UTF-16计数，本轮没有调整它。

新增两组回归修复前失败：超长转写错误提示、2001个表情仍发请求；修复后页面/
录音12组、超时5组、历史3组全部通过。验证2001字转写完整保留、阻止请求、
按钮可用、编辑缩短后正常发送，以及2000/2001表情边界与首尾空格处理。
git diff --check通过。对运行接口发送无副作用的超长请求，实际返回422；执行
当前服务页面脚本确认同样超长输入在请求前拦截，缩短为普通问候后实际对话与
语音下载成功。页面200且等于本地，音频200、236844字节、RIFF/WAVE标记正常，
定时器残留0。四服务active、/ready全就绪，唤醒idle无错误，刷新页面加载修改。
长转写采用模拟ASR返回，未运行真实超长录音；线上检查采用模拟DOM/播放，
不代表真实浏览器设备测试。通用结构化错误显示仍可后续独立改善。
证据：logs/stability-20261024/下web-input-limit-before.log、
web-input-limit-recording.log、web-input-limit-timeout.log、web-input-limit-history.log、
web-input-limit-deployed.json。回归命令：node scripts/test-web-recording.cjs、
node scripts/test-web-timeout.cjs、node scripts/test-web-history.cjs。

## 持续稳定性检查（10月25日）：异步回答和转写保留用户新草稿

复现两处输入丢失：发送后仍可编辑输入，但回答成功会无条件清空；录音权限、
录制或识别等待期间编辑后，转写成功会无条件替换。新增两组回归修复前均失败。
现在记录操作启动时输入原文及input事件版本，完成时仅在二者均未变化时清空
已发送输入或填入转写。编辑后改回原文也保留，避免仅比较字符串误判用户意图；
原文比较额外保护没有触发input事件的程序赋值。未编辑时保留原有操作方式。
转写与新草稿冲突时保留草稿，将完整识别文本写入上方记录并说明未覆盖，
使用textContent展示，不自动发送或执行转写命令。发送请求和历史仍记录原问题。

录音/页面10组、超时5组、历史3组通过。新增覆盖等待回答期间编辑和改回原文，
以及权限等待、录音、识别上传期间编辑及识别期间改回原文，验证转写可查看、
草稿完整保留、按钮恢复。既有正常识别填入和正常发送清空回归继续通过。
git diff --check通过。运行页面200且与本地一致；当前脚本通过原生fetch发起真实
普通对话，在等待中写入新草稿，回答完成后草稿保持完整。音频200、236844字节、
RIFF/WAVE标记正常，定时器残留0。四服务active，/ready全就绪、唤醒idle无错误。
静态页面刷新加载；模拟DOM/媒体的回归与线上网络验证不代表真实浏览器硬件测试。
转写记录需用户手动复制到输入框，本轮没有新增自动合并，以免改变指令语义。
证据：logs/stability-20261024/下web-draft-before.log、web-draft-recording.log、
web-draft-timeout.log、web-draft-history.log、web-draft-deployed.json。
回归命令：node scripts/test-web-recording.cjs、node scripts/test-web-timeout.cjs、
node scripts/test-web-history.cjs。

## 持续稳定性检查（10月25日）：就绪检查迟到覆盖操作提示

复现页面初始/ready请求晚返回时覆盖用户操作提示：旧成功、失败或超时响应
均可覆盖录音、识别、播放或错误状态，仅判断busy也无法保护已完成的识别结果。
现在状态提示统一通过setStatus更新版本；就绪检查记住启动版本，仅当此后没有
任何新提示时才展示结果。麦克风权限等待、实际录音也明确展示状态，启动操作
立即使先前就绪检查失效。没有交互时仍正常显示服务就绪或就绪检查超时。

新增回归修复前在迟到响应覆盖权限等待提示时失败。修复后录音8组、超时5组、
历史3组通过。覆盖权限等待、录音中、识别中、识别完成、录音错误下的迟到
成功/失败响应，以及对话中/播放完成后的迟到响应和录音中的就绪检查超时。
测试执行实际页面脚本；git diff --check通过。
运行页面200且与本地一致，当前脚本配合原生fetch实际对话成功，WAV下载200、
303404字节、RIFF/WAVE标记正常，请求定时器残留0；四服务active，/ready全就绪，
唤醒idle无错误。静态页面刷新加载。测试采用模拟DOM、设备、播放；实际网络
检查不等同于真实浏览器权限和硬件测试。本轮保护就绪请求，不宣称解决所有
媒体事件之间的状态时序问题。
证据：logs/stability-20261024/下web-status-before.log、web-status-recording.log、
web-status-timeout.log、web-status-history.log、web-status-deployed.json。
回归命令：node scripts/test-web-recording.cjs、node scripts/test-web-timeout.cjs、
node scripts/test-web-history.cjs。

## 持续稳定性检查（10月25日）：结束录音同步异常恢复

新增回归复现MediaRecorder.stop()同步抛错：原分支在设置busy之后直接调用，
异常逃逸会让发送、录音一直禁用。现在捕获同步异常，复用该录音会话的错误
清理路径，释放麦克风、清除当前录音引用、恢复按钮并显示失败原因。
同一会话ended标记同时屏蔽迟到的数据、停止和错误事件，避免部分音频上传，
也避免旧会话影响新录音。保留用户输入，可重新开始录音。

录音5组、请求超时4组、历史3组回归通过；新增用例在修复前抛出cannot stop，
修复后验证资源释放、按钮恢复、重试和旧事件隔离。git diff --check通过。
运行页面200且与本地一致；当前页面脚本通过原生fetch实际普通对话成功，
WAV下载200、225324字节、RIFF/WAVE标记正常，定时器残留0。
四服务active，/ready全部就绪，唤醒idle无错误。静态页面刷新即可加载。
异常回归采用模拟MediaRecorder；线上检查模拟DOM/播放，不代表真实设备或
浏览器权限测试。检查中另观察到初始就绪响应可能覆盖操作状态，待后续单独处理。
证据：logs/stability-20261024/下web-stop-failure-before.log、web-stop-failure.log、
web-stop-timeout.log、web-stop-history.log、web-stop-deployed.json。
回归命令：node scripts/test-web-recording.cjs。

## 持续稳定性检查（10月25日）：网页长会话历史边界与超长工具回答

检查发现网页仅在发送时slice(-10)，内存history仍不断push，且将任意长度回答
存为assistant消息。接口Message.content最多4000字，超长工具回复会污染后续请求，
连续返回校验错误。用临时SQLite填入120项提醒，实际查看提醒工具返回6258字；
实际ChatRequest验证产生string_too_long，证明问题不只存在于模拟返回。
新增页面回归修复前两组失败（30轮保留60消息、超长回答后仍发送旧历史）。

现每次成功后只保留最新10条消息（5个完整问答对）。若回答超过4000 Unicode字符，
完整显示回答但清空操作上下文，避免下一次请求422，也避免仅丢掉超长一轮后
把更早的提醒错误当作“刚才”。不截断回答内容或在半个编号/事项处构造上下文。
代价是超长回答后的省略追问可能需要重新说明；页面显示记录保留完整，显示区域
本身仍未做虚拟化或条数限制，不据此宣称整个页面内存有固定上限。

历史3组回归通过，覆盖30轮、超长提醒回答后继续发送、旧上下文清空和4000个
非BMP字符不误判；网页超时4组、录音4组通过。执行页面脚本验证JS语法，
git diff --check通过。临时提醒数据库随测试删除，未操作线上提醒。
服务GET / 200且与本地页面一致；通过当前脚本+Node原生fetch真实普通对话成功，
WAV下载200、405804字节，RIFF/WAVE标记正常，请求定时器残留0。
该线上检查使用模拟DOM/播放，未宣称真实浏览器播放或长工具TTS合成测试。
四服务active，/ready全部就绪，唤醒idle无错误；页面刷新加载新逻辑。
证据：logs/stability-20261024/下`web-history-before.log`、`web-history.log`、
`web-history-timeout.log`、`web-history-recording.log`、`web-history-tool-evidence.json`、
`web-history-deployed.json`。回归命令：`node scripts/test-web-history.cjs`。

## 持续稳定性检查（10月25日）：网页请求总等待上限与按钮恢复

处理前轮待办：网页fetch没有客户端超时，连接或响应正文一直不返回时，
普通发送/识别的finally不能执行，busy与按钮可一直锁住。新增延迟网络及假时钟
回归执行实际页面脚本，修复前对话和ASR两组均因无等待上限失败。
json请求统一使用AbortController，就绪10秒、ASR120秒、普通对话240秒；
定时器保持到正文解析完成，finally始终清理。到期显示“请求等待超时，请检查服务状态。”，
不自动重试，防止重复有状态操作；普通网络错误继续原样传递。

超时4组回归通过，包含就绪初始检查、普通对话/识别连接和正文各自卡住、成功及
网络错误定时器清理；验证输入保留、失败回答不入历史、按钮恢复、signal已取消。
原网页录音4组回归通过。执行页面脚本同时验证JS语法，git diff --check通过。
超时测试采用模拟fetch与假时钟，没有真实等待2/4分钟；前端取消等待不保证
后端工作停止，也不会回滚超时前已完成的提醒等操作。

运行服务返回页面200且与本地文件字节一致；另外通过Node原生fetch执行当前页面
脚本的普通发送，真实LLM/TTS回答成功，WAV下载200、384044字节、RIFF/WAVE标记正确，
请求定时器残留0，按钮恢复、输入清空。该检查模拟DOM和播放，仅验证真实网络及
页面请求流程，未宣称真实浏览器播放或完整PCM检查。四服务active，/ready全就绪，
唤醒idle无错误。静态页面已即时提供，原有页面刷新即可加载。
证据：logs/stability-20261024/下`web-timeout-before.log`、`web-timeout.log`、
`web-timeout-recording.log`、`web-timeout-deployed.json`。
回归命令：`node scripts/test-web-timeout.cjs`、`node scripts/test-web-recording.cjs`。

## 持续稳定性检查（10月25日）：网页编辑式转写不自动执行关怀命令

追踪网页识别请求时发现，页面显示“识别完成，点击发送”，但调用/api/asr默认
会执行handle_care_text，可能在用户编辑或发送之前创建紧急求助事件或确认关怀。
进一步核对确认该即时处理仅涉及emergency/ack，不是定时提醒创建；不能将它
描述为所有提醒都会重复执行。网页也未展示接口返回的关怀执行结果。

新增execute_commands布尔查询参数，默认true保留原调用行为；网页显式传false，
只禁止关怀执行，继续保留原有声纹验证和指令语境纠错。没有直接使用
care_commands=false，以免同时跳过声纹和纠错。网页发送仍走普通对话，不替代
专用关怀命令接口；离线唤醒继续使用默认自动处理。

新增接口回归覆盖只转写/默认命令/音色录入三种组合，验证调用次数和verify参数；
修复前execute_commands=false仍调用处理函数，断言失败。
修复后ASR15项、取消2项、网页录音4组通过；网页测试同时断言上传URL显式禁用执行。
编译及git diff --check通过。所有求助文本均在隔离测试用mock处理函数，未在线上
创建求助或确认事件。ASR.md补充参数区别及网页流程说明。

网关重启后，以execute_commands=false真实识别天气问句，200返回
“小安，今天天气好吗？”，不含care_command；识别配置哈希未变，页面200且与
当前文件字节一致。四服务active，/ready全部就绪，唤醒idle无错误。
证据：logs/stability-20261024/下`web-asr-execution-before.log`、`web-asr-execution.log`、
`web-asr-execution-page.log`、`web-asr-execution-cancel.log`、`web-asr-execution-deployed.json`。
本轮优先修复识别阶段的状态修改；网页请求缺少超时仍作为后续待处理项。

## 持续稳定性检查（10月25日）：网页录音运行时错误及迟到事件隔离

继续检查MediaRecorder运行中设备故障。页面没有error处理，不能及时释放流、
提示失败；随后到达的最终dataavailable/stop还会把部分数据上传识别。
新增故障回归在修复前失败（error发生后麦克风停止次数仍为0）。
现每次录音用ended标志约束结束流程，error先标记结束、释放流、恢复按钮并提示
“录音失败”；随后旧session的数据/停止事件直接忽略。正常stop仅执行一次上传。
这样用户故障后立刻重录时，旧事件不会清空新录音的状态或启动额外识别。

网页录音脚本4组回归全部通过，覆盖前轮初始化/授权/识别边界，以及本轮运行中
error→释放→重录→旧data/stop的交错顺序，验证无部分上传、原输入保留、
新录音按钮保持“结束录音”。测试执行真实页面脚本并模拟浏览器媒体API；
没有拔出实体麦克风，也没有真实浏览器驱动，因此不将模拟结果描述为硬件验证。
git diff --check通过。GET / 返回200且字节与当前页面相同，/ready全部就绪、
四服务active，唤醒idle无错误。静态文件即时提供，已有页面需刷新。
尝试下载MDN MediaRecorder error说明时网络读取超时，未将该下载作为验证依据。
证据：logs/stability-20261024/下`web-recorder-error-before.log`、
`web-recorder-error.log`、`web-recorder-error-deployed.json`。

## 持续稳定性检查（10月25日）：网页录音并发控制与麦克风释放

检查就绪显示及网页入口时，发现麦克风授权和ASR上传期间没有busy保护；
录音器构造或start失败未停止已获得的麦克风流，重播按钮还能在录音期间启动播放。
新增Node VM测试执行实际HTML中的脚本，模拟DOM、MediaRecorder、媒体流及延迟网络，
修复前三组场景全部失败。现等待授权即锁定操作，录音中仍可结束录音；
停止后在ASR完成或失败前锁定发送/录音/重播，finally恢复按钮。
录音器初始化失败释放流并允许重试；录音与识别期间禁止重播。
每次录音用闭包保存独立chunks和session.mimeType，避免依赖可被下一次录音覆盖的全局值。

三组回归通过，包含构造/start两种失败及重复重试、授权等待重复点击、识别成功/失败、
麦克风停止次数、上传内容与恢复按钮。通过实际脚本执行同时校验JS语法，
git diff --check通过。测试模拟浏览器API，不代表真实设备权限弹窗或实际声卡测试。
服务GET / 返回200、text/html，返回字节与修改后的页面完全一致；
静态页面按请求读取，无需重启网关，已打开的页面需要刷新加载新脚本。
真实录音fixture经/api/asr?care_commands=false返回200“小安，今天天气好吗？”，
识别配置哈希未变。四服务active，/ready全部就绪，唤醒idle无错误。
证据：logs/stability-20261024/下`web-recording-before.log`、`web-recording.log`、
`web-recording-asr-deployed.json`、`web-recording-page-deployed.json`。
回归命令：`node scripts/test-web-recording.cjs`。

## 持续稳定性检查（10月25日）：自然问候与避免重复称呼

上轮真实对话出现“你好您”。检查发现没有直接把“你好”变成该短语的规则，
因此不能断言是称呼替换造成，可能来自模型原始输出。另以固定输入复现选择
“爷爷”时“您好，爷爷！”会被重复加前缀成为“爷爷，您好，爷爷！”。
新增问候检查及分段场景后，修复前6处断言失败。
现仅修复句首明确独立称呼：中性“你好您/您好，您”整理为“您好”；选中家庭称呼时，
“您好，爷爷/奶奶”整理为“所选称呼，您好”，避免再加一次前缀。
使用后续标点或结尾边界，保留“您好，您的家人”“您好，爷爷的花”及非句首叙述。
不改正文中正常的您，也不声称能修复所有模型措辞问题。

称呼9项、提醒14项、对话上下文13项全部通过。新增普通对话验证显示文本和传入
TTS文字相同，分段场景验证称呼只出现一次且合成文字拼接等于显示文字。
编译及git diff --check通过，选择称呼测试均使用临时配置。
重启后真实普通对话200、1.69秒，分段任务1.291秒结束且无错误，
两次均自然以“您好！”开头。取回32kHz WAV长6/5.42秒，PCM完整。
线上companion.json及voice.json哈希未变；四服务active，/ready全部就绪，唤醒idle。
线上随机模型响应验证正常问候链路，具体错误问候修复由固定输入回归证明。
证据：logs/stability-20261024/下`greeting-address-before.log`、`greeting-address.log`、
`greeting-address-reminders.log`、`greeting-address-context.log`、`greeting-address-deployed.json`。

## 持续稳定性检查（10月25日）：中文改写函数独立防御无效返回值

上一轮已在模型响应入口拒绝无效正文，本轮进一步独立测试chinese_reply本身：
rewrite返回None、数字、列表、字典或bytes时，strip/简繁处理在try范围外抛异常。
这是函数边界的防御缺口；当前线上模型入口已经有上一轮校验，不能据此宣称
现网仍可通过相同模型响应复现500。新增4项回归，修复前5个子场景异常。
现检查rewrite输出为字符串，并将strip及中文归一化放入已有异常兜底范围。
继续让CancelledError向上传播，避免取消被当成中文改写失败吞掉。

新增4项、模型响应3项通过；覆盖空白/残留英文/非文本兜底，正常繁体与数字保留、
原中文及常用英文词无需请求模型、调用失败与取消传播。
说话人/中文集成脚本通过，包括实际本地声纹、噪声/混合声音拒绝、临时声纹持久化、
分段中文显示与TTS文本。声纹测试使用临时目录，不修改线上声纹。
编译及git diff --check通过。

重启后真实普通与分段对话成功，耗时1.22/1.364秒；取回32kHz WAV，
3.46/5.42秒，PCM完整。此线上检查验证正常对话基础链路；异常rewrite回调与
取消传播由隔离测试证明。四服务active，/ready全部就绪，唤醒idle无错误。
证据：logs/stability-20261024/下`output-language-before.log`、`output-language.log`、
`output-language-model.log`、`output-language-speaker.log`、`output-language-deployed.json`。

## 持续稳定性检查（10月25日）：校验模型正文与中文改写异常兜底

检查模型返回格式，复现content为null、数字、数组、对象时，普通对话调用strip
产生未处理500，中文改写在原有异常捕获范围外再次处理无效内容，不能正常兜底。
新增3项回归，前两项各覆盖11种异常返回，修复前共4处失败、4处异常。
统一通过completion_text读取并校验非空字符串，再用于普通对话和中文改写；
不符合约定的正文转502“ 大模型返回格式异常 ”，中文改写由已有捕获流程返回
中文兜底提示。拒绝将结构化内容或数字直接当正文播报。

新增3项通过，验证坏响应不调用TTS、不生成文件，合法正文及翻译继续正常。
回答完成/截断/TTS失败脚本、重复检测脚本、中文综合脚本全部通过；
中文综合脚本含实际ASR“小安，今天天气好吗？”以及简繁转换、分段文本、本地拼音。
编译及git diff --check通过。分段流已有异常收尾逻辑，本轮未修改流解析约定。

网关重启后真实普通对话200、1.64秒，分段任务1.206秒结束且error为空；
取回32kHz WAV分别5.8和4.98秒，PCM长度与声明帧数相符。
/ready全就绪，四服务active，唤醒idle无错误。线上只验证正常真实响应，
异常模型格式通过隔离测试注入，不改线上模型配置。
证据：logs/stability-20261024/下`model-response-before.log`、`model-response.log`、
`model-response-finish.log`、`model-response-repetition.log`、
`model-response-chinese.log`、`model-response-deployed.json`。

## 持续稳定性检查（10月25日）：对话音频原子发布与存储故障恢复

复现普通对话与轮询分段对话直接写最终WAV的问题：磁盘部分写入失败会留下
不完整文件，普通接口返回未处理500，分段任务仅提示通用生成失败。
新增回归在修复前四个子场景失败，覆盖两条路径的部分写入及替换失败。
现统一通过save_chat_audio先写同目录独立临时文件，再原子替换为最终WAV；
只有发布成功才返回音频地址或追加clips。存储OSError转为明确的503保存失败说明，
分段任务保留同一说明并正常结束，finally尝试清理临时文件。

音频保留3项（含4个故障子场景）、对话取消5项及对话稳定性脚本全部通过；
继续验证活跃/近期任务音频保留、清理失败不影响响应、模型/TTS失败与超时收尾。
故障解除后普通请求与新分段任务都能生成完整文件，故障场景无最终或临时残留。
编译、git diff --check通过。若文件系统同时拒绝删除，清理仍只能记录警告；
原子替换保护文件可见性，不代表断电持久化保证。

已重启网关并真实请求两种对话接口：普通响应1.68秒，分段任务1.351秒结束且无错误；
取回两段32kHz WAV，时长5.76/5.26秒，声明帧数与PCM实际长度一致。
/ready全部就绪，四服务active，唤醒idle无错误。故障注入仅在临时目录执行。
证据：logs/stability-20261024/ 下`chat-audio-storage-before.log`、
`chat-audio-storage.log`、`chat-audio-storage-stability.log`、
`chat-audio-storage-cancellation.log`、`chat-audio-storage-deployed.json`。

## 持续稳定性检查（10月25日）：损坏参考录音不能补静音后进入缓存

核对录入归一化已有截断检查，进一步复现参考录音降噪和裁剪路径缺少相同保护：
只剩WAV头、尾部丢失100字节或一个字节的录音仍可能被接受，降噪按头部声明
长度补静音后可生成格式完整的缓存。新增两项回归修复前六处断言失败。
现统一读取并核对声明帧数×通道数×采样宽度与实际PCM长度，拒绝空或截断输入；
降噪、裁剪及cleaned_reference缓存查询前均检查，防止旧版本已生成的完整缓存
掩盖损坏原录音。保留有效录音的降噪、裁剪、内容哈希缓存与原文件不变行为。

降噪7项、语音质量8项、音量5项回归通过，编译与差异检查通过。
新增检查覆盖截断输入、原录音不变、不创建损坏来源缓存，以及旧缓存存在时仍拒绝。
有效音频回归继续使用真实FFmpeg验证噪声、能量和时长；故障输入均为临时测试数据。
网关已重启：/ready全部就绪，四服务active，唤醒idle无错误；默认音色TTS200，
32kHz单声道4.14秒WAV，声音配置哈希未变。线上检查验证默认音色基础服务，
损坏录音及缓存边界由隔离回归验证，未在线上切换音色或破坏参考文件。
证据沿用本次持续检查目录logs/stability-20261024/：`reference-truncation-before.log`、
`reference-truncation.log`、`reference-truncation-quality.log`、
`reference-truncation-level.log`、`reference-truncation-deployed.json`。

## 持续稳定性检查：音色录入存储失败返回明确503

检查录音上传与异常清理，复现创建参考目录、参考音频部分写入、试听音频
部分写入和配置替换失败时，录入接口返回未处理500。新增接口回归修复前
四个子场景失败。参考目录创建移入已有事务式录入清理范围，存储OSError
转换为带保存失败说明的503，保留原有finally回滚及取消处理。
更新原有直接调用测试，确认新的HTTPException状态503，并继续验证旧音色不变、
参考/试听/临时配置均清理；新增接口测试还验证故障解除后可成功重新录入。

音色录入5项、声音配置4项、语音质量8项通过，编译与差异检查通过。
故障注入、音色切换均在临时目录，线上未调用录入或重置接口。
已重启网关：/ready全部就绪，四服务active，唤醒idle无错误。
线上仍为默认小男孩·小安，真实TTS200，32kHz单声道4.92秒WAV，声音配置
哈希未变。若存储系统同时拒绝清理，原有清理逻辑只能记录日志，仍可能残留文件。
证据：logs/stability-20261024/ 下 `enrollment-storage-before.log`、
`enrollment-storage.log`、`enrollment-storage-config.log`、
`enrollment-storage-quality.log`、`enrollment-storage-deployed.json`。

## 持续稳定性检查：天气缓存临时文件权限与失败清理

继续检查含位置信息的天气缓存落盘，复现部分写入、原子替换失败时残留
weather-cache.tmp，临时文件在写入后chmod前权限0664。
新增两项回归修复前三处失败。缓存现用每次独立的临时路径，先创建0600
文件再写数据；finally尝试清理，不影响原有落盘失败仅记录警告的行为。
回归验证写入/替换失败后正式缓存字节不变、无临时文件，当前请求和内存缓存
仍使用最新天气；解除故障后可保存，重启服务对象仍可离线读取更新数据。
若删除也被系统拒绝，仍可能残留私有临时文件；未增加断电持久性保证。

天气31项、对话上下文13项通过，编译与差异检查通过。
已重启网关：/ready全部就绪、四服务active、唤醒idle无错误；真实ASR200，
识别“小安，今天天气好吗？”，ASR配置哈希未变。
实际/api/weather返回200，stale=false、cached=false，新落盘缓存权限0600，
查询前后位置配置字节一致。故障注入仅在临时目录，线上请求验证正常刷新路径。
证据：logs/stability-20261024/ 下 `weather-cache-storage-before.log`、
`weather-cache-storage.log`、`weather-cache-storage-context.log`、
`weather-cache-storage-deployed.json`、`weather-cache-storage-online.json`。

## 持续稳定性检查：定位配置私有写入与存储失败提示

检查天气服务错误恢复，复现手动/自动定位在临时写入中断和替换失败时
返回未处理500并残留临时文件；位置临时文件在写入后、chmod前权限为0664。
新增两项回归修复前五处失败：四个接口故障组合与一处写入时权限检查。
位置保存现每次创建独立0600临时文件再写数据，原子替换后继承私有权限，
finally尝试清理；存储OSError转换为WeatherStorageError，手动/自动接口返回503，
语音/文字定位命令返回明确保存失败提示，城市查询失败仍为原有422。
测试验证原文件字节不变、无临时文件残留、命令不虚报成功，
解除故障后可保存新城市且权限0600。若系统拒绝清理仍可能残留私有临时文件。

天气29项、对话上下文13项及对话稳定性脚本通过，编译与差异检查通过。
所有位置写入和故障注入都在临时目录，未在线上修改城市或触发自动定位。
已重启网关，/ready全部就绪，四服务active，唤醒idle无错误；
线上位置读取200仍为手动上海，读取前后位置文件字节一致；真实ASR200，
识别“小安，今天天气好吗？”，ASR配置哈希未变。
证据：logs/stability-20261024/ 下 `location-storage-before.log`、
`location-storage.log`、`location-storage-context.log`、`location-storage-chat.log`、
`location-storage-deployed.json`、`location-storage-read.json`。

## 持续稳定性检查：照护音频完整写入后再发布

复现CareEngine.render直接覆盖正式wav：写入中途OSError后留下截断文件，
已有可用音频也被破坏。新增含四种子场景的回归修复前四处失败，
覆盖首次生成/已有音频与部分写入/替换失败组合。
现写每次独立的临时文件，完整写入后同目录原子替换正式wav，
finally尝试删除临时文件，清理失败只记录日志。数据库ready更新位于替换成功后。
回归验证失败时状态failed、已有文件字节不变/首次生成无正式文件、
无临时文件残留，解除故障后重试成功且URL与内容正确。
这不提供断电持久性保证；若删除临时文件也被系统拒绝，仍可能残留临时文件。

照护16项、提醒14项、对话取消5项通过，编译与差异检查通过。
已重启网关：/ready全部就绪、四服务active、唤醒idle无错误。
真实ASR200，识别“小安，今天天气好吗？”，ASR配置哈希未变；
真实TTS200，返回32kHz单声道4.34秒WAV，声音配置哈希未变。
文件故障仅在临时目录注入，线上未制造照护事件；线上TTS验证合成依赖正常，
原子发布与错误恢复由隔离回归验证。
证据：logs/stability-20261024/ 下 `care-audio-atomic-before.log`、
`care-audio-atomic.log`、`care-audio-atomic-reminders.log`、
`care-audio-atomic-cancellation.log`、`care-audio-atomic-deployed.json`、
`care-audio-atomic-tts.json`。

## 持续稳定性检查：启动音频恢复遇到写锁后可继续

针对上一轮注明的启动恢复边界，复现活动卡片需要恢复音频时，
启动UPDATE遇到另一连接BEGIN IMMEDIATE写锁，调度run直接退出。
新增真实双连接回归修复前失败：Startup database lock stopped scheduler。
启动恢复现移入OperationalError重试循环，在锁释放后继续恢复，
用已启动音频ID集合避免部分恢复后重试时重复合成；完整扫描后释放集合。
保持每张卡片启动时仅恢复一次，TTS失败不会在后续每秒循环反复请求。

新增两项回归：启动前持锁，释放后同一调度任务完成音频恢复；
恢复第一张卡片后再持锁，且第一张TTS失败，释放后仅恢复第二张，
验证两张各合成一次，第一张failed、第二张ready。仅临时数据库与受控音频替身。
照护15项、提醒14项、对话取消5项通过，编译与差异检查通过。
已重启网关，/ready全部就绪、四服务active、唤醒idle无错误；
真实ASR200，识别“小安，今天天气好吗？”，ASR配置哈希未变。
持续写锁仍会延迟恢复；本次处理run中的启动恢复，不包含构造阶段建表失败、
数据库损坏或永久存储故障。未在线上制造数据库锁或照护事件。
证据：logs/stability-20261024/ 下 `care-startup-lock-before.log`、
`care-startup-lock.log`、`care-startup-lock-reminders.log`、
`care-startup-lock-cancellation.log`、`care-startup-lock-deployed.json`。

## 持续稳定性检查：照护调度从临时数据库写锁中恢复

检查照护后台任务生命周期，复现另一个SQLite连接持有写事务时，
调度tick抛出OperationalError，run直接退出并关闭数据库，后续提醒停止。
新增真实双连接回归修复前失败：Temporary database lock stopped scheduler。
循环现捕获sqlite3.OperationalError，回滚未提交事务、记录错误，
保留原有一秒间隔后重试；正常关闭取消仍走finally清理任务及数据库。
回归通过BEGIN IMMEDIATE持有临时库写锁，验证任务存活，释放锁后同一任务
恢复调度，目标事件恰好一条且音频ready。测试设busy_timeout=0以快速触发故障；
生产仍沿用现有SQLite等待超时。持续存储故障仍会导致提醒延迟或错过有效窗口，
此修改不保证故障期间按时送达，也未扩展启动恢复阶段或数据库损坏的处理。

照护13项、提醒14项、对话取消5项回归通过，编译和差异检查通过。
锁冲突只在临时数据库制造，未锁定线上数据库或发送线上照护事件。
已重启网关，/ready全部就绪，四服务active，唤醒idle无错误；
真实ASR返回200并识别“小安，今天天气好吗？”，ASR配置哈希未变。
证据：logs/stability-20261024/ 下 `care-db-lock-before.log`、
`care-db-lock.log`、`care-db-lock-reminders.log`、
`care-db-lock-cancellation.log`、`care-db-lock-deployed.json`。

## 持续稳定性检查：小数钟点不能截取为整数时间

继续检查提醒时间边界，复现“明天8.5点”被截取为5点、
“明天8点30.5分”被截取为08:30，且小数尾部进入任务内容。
新增回归修复前十个子场景失败，覆盖半角/全角小数点、小数小时、
小数分钟、冒号时间及“提醒我”前后两种语序。
时钟整数匹配现检查紧邻前后的小数部分，拒绝部分匹配并提示整数小时与分钟；
未添加小数钟点换算。合法的1.5小时相对时长沿用原实现，
任务“测量1.5升水”在两种语序下仍按明天08:00保存。

提醒14项、对话上下文13项、照护12项回归全部通过；编译和差异检查通过。
所有提醒测试均使用临时数据库，未向线上创建测试提醒。
网关已重启，/ready全部就绪，四服务active，唤醒idle且无错误。
真实ASR返回200，识别“小安，今天天气好吗？”，线上ASR配置哈希未变。
时间边界由隔离测试验证，线上检查验证服务恢复及基础识别。
证据：logs/stability-20261024/ 下 `reminder-decimal-before.log`、
`reminder-decimal.log`、`reminder-decimal-context.log`、
`reminder-decimal-care.log`、`reminder-decimal-deployed.json`。

## 持续稳定性检查：提醒时间中的秒数不能静默丢弃

复现“提醒我明天8点30分20秒关火”“提醒我明天八点三十分零五秒关火”
和“提醒我明天8点30秒关火”错误保存为08:30，秒数或秒字进入任务内容。
新增回归修复前有三处断言失败。解析时现检查紧跟时钟表达式的秒数后缀，
明确提示暂不支持秒且不写入提醒；保持原有分钟精度，不擅自取整。
覆盖时间在“提醒我”前后、数字/中文秒数、冒号时间；同时验证
“提醒我明天8点做三十秒伸展”等正常任务仍能按08:00保存。

提醒13项、对话上下文13项、照护12项测试通过，编译及git diff --check通过。
提醒测试使用临时数据库，未在线上创建提醒。
已重启网关，/ready全部就绪，四服务active，唤醒idle无错误；
真实ASR返回200并识别“小安，今天天气好吗？”，ASR配置哈希未变。
线上检查验证基础服务恢复，秒数边界由隔离回归覆盖。
证据：logs/stability-20261024/ 下 `reminder-seconds-before.log`、
`reminder-seconds.log`、`reminder-seconds-context.log`、
`reminder-seconds-care.log`、`reminder-seconds-deployed.json`。

## 持续稳定性检查：ASR请求取消后底层线程仍须保持串行

检查线程中的FFmpeg/识别调用后，复现/api/asr在等待asyncio.to_thread时取消请求，
async with asr_lock立刻退出，但线程继续音频处理，后续请求可并发进入预处理。
受控线程回归修复前断言失败：工作线程未结束时ASR锁已经释放。
现先取得锁，再创建并保留独立工作任务，shield使请求取消不取消该任务；
任务实际结束的回调才释放锁并观察异常，取消请求立即退出且不会解释或执行迟到文本。
在等待锁期间取消的请求不创建工作线程。关闭流程也等待登记的ASR任务后再关闭共享客户端。
此修复不强制终止Python线程或FFmpeg；后续请求需等待已有线程结束，
FFmpeg保留原有20秒超时，模型推理仍受已有后端行为约束。

新增scripts/test-asr-cancellation.py两项通过，覆盖底层线程迟到成功和迟到失败，
检查取消及时返回、线程未结束时锁仍持有、后续处理不重叠、排队取消不启动处理、
不执行迟到照护命令，以及线程结束后任务集清空、锁释放、下一请求成功。
测试用线程事件控制完成时机，仅模型/预处理为替身；接口取消、锁与工作任务走实际代码。
ASR14项、对话取消5项、手动中断回归通过，编译与差异检查通过。
参考已下载的LiveKit任务完成回调模式，针对to_thread无法强制取消的语义保留任务至结束。
已重启网关：/ready全部就绪、四服务active、唤醒idle无错误，真实ASR200，
识别“小安，今天天气好吗？”，线上ASR配置哈希未变。
竞态在隔离测试复现，线上检查验证正常识别，未在线上制造阻塞或取消故障。
证据：logs/stability-20261024/ 下 `asr-cancellation-before.log`、`asr-cancellation.log`、
`asr-cancellation-service.log`、`asr-cancellation-chat.log`、`asr-cancellation-interrupt.log`、
`asr-cancellation-deployed.json`。

## 持续稳定性检查：声纹配置私有写入与保存失败恢复

复现声纹开关与录入接口在临时文件写入中途失败、原子替换失败时返回未处理500并残留文件。
同时save先写临时文件、替换后才chmod，临时文件沿用默认权限；本机复现替换前为0664。
新增两项回归：四个接口故障子场景和一次替换前权限检查，修复前共五处断言失败。
保存现独立创建0600临时文件后才写入声纹，以原子替换继承私有权限，finally尝试清理；
移除替换后的chmod，避免权限设置失败发生在原配置已经改变之后。
开关与录入接口捕获存储OSError返回明确503保存失败提示。
若系统同时拒绝删除临时文件，清理仅记录日志，仍可能残留私有临时文件。

声纹配置7项、ASR14项回归通过，真实本地声纹/VAD及中文输出回归通过，
覆盖噪声拒绝、录入、带噪匹配、不同/混合声音、持久化和中文流式/TTS。
新增接口测试只在临时目录注入故障与受控声音，验证原文件字节不变、无临时文件残留、
状态维持关闭、解除故障后保存成功且权限0600；替换前检查确认声纹已处于0600文件内。
编译与差异检查通过，已重启网关。线上/ready全部就绪，四服务active，唤醒idle无错误；
声纹状态200，保持已录入但限制关闭，配置哈希未变，未在线上录入或切换声纹限制。
真实ASR200，识别“小安，今天天气好吗？”。
证据：logs/stability-20261024/ 下 `speaker-storage-before.log`、`speaker-storage.log`、
`speaker-storage-language.log`、`speaker-storage-asr.log`、`speaker-storage-deployed.json`。

## 持续稳定性检查：称呼设置保存失败与恢复

复现PUT /api/companion/profile在目录访问失败、临时写入中途失败、替换权限失败时
均返回未处理500，后两类故障还会留下临时文件。新增一项含三个故障子场景的接口回归，
修复前三处断言失败。save_salutation现使用每次调用独立临时文件并在finally尝试清理，
接口捕获OSError返回明确503保存失败提示；原配置在替换成功前保持不变。
若系统同时拒绝清理，记录日志且保留原始保存异常，此时仍可能残留临时文件。

称呼6项、对话上下文13项、照护12项回归全部通过，编译与差异检查通过。
新增测试验证三类失败后原配置字节不变、无临时文件、GET仍为原称呼，
解除故障后PUT成功且读取新称呼。故障注入与修改称呼均在临时目录进行。
已重启网关：/ready全部就绪，四服务active，唤醒idle无错误。
线上读取称呼为“您”，真实/api/chat返回200“你好！您最近过得怎么样？”，
下载生成音频200，243244字节、32kHz单声道、3.8秒，核对声明帧数与实际PCM一致。
线上称呼与音色配置哈希未变，未执行线上称呼保存测试。
证据：logs/stability-20261024/ 下 `companion-storage-before.log`、`companion-storage.log`、
`companion-storage-context.log`、`companion-storage-care.log`、`companion-storage-deployed.json`。

## 持续稳定性检查：克隆语音内容校验依赖不可用的明确响应

复现质量校验内部recognizer.transcribe耗尽自身重试后抛ASRUnavailable，
该异常绕过synthesize错误处理，/api/tts返回未处理500。
现单独捕获ASRUnavailable返回503，提示“语音内容校验服务暂时不可用，请稍后重试”，
不把依赖服务故障当作音色不完整重采样，不提示用户重新录入音色。

新增接口回归修复前500断言失败；修复后音质8项、ASR14项、缓存4项全部通过，
编译和差异检查通过。新增回归串联实际WAV解析、质量校验与接口，
仅替换上游TTS、VAD和识别器注入依赖故障，验证一次TTS后503、
不后处理、不缓存、音色配置不变；识别器恢复后相同请求成功且后续可复用缓存。
已重启网关：/ready全部就绪、四服务active、唤醒idle无错误。
线上当前默认音色TTS200，305964字节、32kHz单声道、4.78秒WAV；真实ASR200，
识别“小安，今天天气好吗？”，音色与ASR配置哈希均未变。
依赖故障在临时目录隔离验证，线上未停止识别服务或更改音色。
证据：logs/stability-20261024/ 下 `cloned-asr-unavailable-before.log`、
`cloned-asr-unavailable-quality.log`、`cloned-asr-unavailable-asr.log`、
`cloned-asr-unavailable-cache.log`、`cloned-asr-unavailable-deployed.json`、
`cloned-asr-unavailable-asr-deployed.json`。

## 持续稳定性检查：克隆合成音频截断的检测与有限重试

复现validate_cloned_speech未检查实际PCM字节数与WAV声明帧数是否一致：
奇数字节截断引发numpy未处理ValueError，双声道半帧截断引发reshape异常，
完整帧截断则继续VAD/ASR，可能通过内容检查而进入处理缓存。
新增两项回归包含八个子场景，修复前4处断言失败、4处异常。
现读取PCM后先检查len(pcm)==frames*channels*2，不一致明确抛SpeechQualityError，
进入已有最多三次重试流程，不把损坏数据交给VAD、ASR或后处理。

音质7项、缓存4项、音色录入4项全部通过，编译与差异检查通过。
新增回归覆盖单/双声道缺少1、2、4字节；使用真实质量校验串联synthesize，
检查连续坏响应恰好三次后502、缓存为空、零ASR/后处理调用，
后续完整响应成功并可复用缓存。此处VAD和识别器用受控替身隔离内容判断，
帧解析、截断检查、重试与缓存均走实际代码。
已重启网关：/ready全部就绪，四服务active，唤醒idle无错误；线上默认音色查询与TTS均200，
生成280364字节、32kHz单声道、4.38秒WAV，当前音色哈希未变。
线上检查验证默认音色链路；克隆截断故障在临时目录隔离验证，未切换或录入线上音色。
证据：logs/stability-20261024/ 下 `cloned-truncated-before.log`、`cloned-truncated-quality.log`、
`cloned-truncated-cache.log`、`cloned-truncated-enrollment.log`、`cloned-truncated-deployed.json`。

## 持续稳定性检查：服务关闭不能重复取消正在清理的对话

复现DELETE取消对话后，后台任务进入异步finally清理，此时lifespan关闭流程再次task.cancel，
打断清理。新增真实lifespan隔离回归，修复前断言失败：后台清理任务提前结束。
接口与关闭流程现共用request_chat_cancellation，已标记cancelled的任务不会再次注入取消；
关闭流程对当前任务集取快照，等待这些任务完成后再关闭共享HTTP客户端。
保留取消前尚未启动任务的完成回调，避免未启动任务留下占用中的状态。

取消回归5项全部通过，包含取消请求断开、并发取消、启动前取消、用户取消后关闭、
直接关闭活动任务。关闭回归使用真实lifespan与受控后台任务，以事件和gather观察确认
关闭流程确实到达任务等待处，检查清理未被打断、清理后才关闭HTTP客户端以及任务最终完成。
对话稳定性5场景、手动中断回归通过，编译和差异检查通过。
已重启网关，/ready全部就绪、四服务active、唤醒idle无错误；实际创建对话及并发两次DELETE
均200，最终done/text_done为true、finish_reason=cancelled、无错误。
竞态故障在隔离测试中复现，线上检查验证正常重启和取消；不宣称线上重现了受控清理竞态。
证据：logs/stability-20261024/ 下 `chat-shutdown-before.log`、`chat-shutdown.log`、
`chat-shutdown-stability.log`、`chat-shutdown-interrupt.log`、`chat-shutdown-deployed.json`。

## 持续稳定性检查：热词配置保存失败的清理与恢复

复现PUT /api/asr/config在写入临时文件途中磁盘错误、原子替换权限失败时返回未处理500，
并遗留临时配置。新增一项覆盖两类故障的隔离回归，修复前两处断言失败。
保存现使用每次请求独立的临时文件，捕获OSError并返回明确503保存失败提示，finally尝试清理。
写入或替换失败保留原配置；清理本身失败只记录日志，可能留下临时文件，不覆盖原始保存错误。

ASR 14项和输入逻辑回归全部通过，编译与差异检查通过。新增回归检查部分写入、替换失败、
原配置字节不变、无临时文件残留、失败后GET仍可读，以及解除故障后再次PUT成功，
保留其余配置字段并正确去重、裁剪热词。故障只注入临时目录，未改线上热词或权限。
已重启网关：/ready全部就绪，四服务active，唤醒idle且无错误；真实ASR返回200，
识别“小安，今天天气好吗？”，线上ASR配置哈希未变。
证据：logs/stability-20261024/ 下 `asr-config-storage-before.log`、`asr-config-storage.log`、
`asr-storage-input-logic.log`、`asr-config-storage-deployed.json`。

## 持续稳定性检查：语音缓存键读取参考录音的异常恢复

复现参考文件通过is_file校验后，在speech_key计算内容摘要时发生PermissionError、
FileNotFoundError或IsADirectoryError，异常绕过synthesize其余错误处理，接口抛未处理异常。
新增一项包含三类读取故障的接口回归，修复前三个子场景均异常失败。
现捕获缓存键计算阶段的OSError并返回明确503，提示检查参考录音或恢复默认音色。
失败不调用上游TTS、不写入缓存、不更改音色；文件恢复后下一请求正常合成并缓存成功音频。

语音缓存4项、音色配置4项、音色录入4项全部通过。新增测试经真实speech_key与线程读取
注入三类故障，检查503提示、零上游调用、空缓存、配置字节不变，以及后续成功请求与缓存复用。
编译与差异检查通过，已重启网关。真实音色查询与TTS均200，生成340524字节、
32kHz单声道、5.32秒有效WAV，当前音色配置哈希未变；/ready全部就绪，四服务active。
故障只在临时目录注入，未删除或改变线上参考录音权限。
证据：logs/stability-20261024/ 下 `speech-reference-read-before.log`、`speech-cache.log`、
`voice-config.log`、`voice-enrollment.log`、`speech-reference-read-deployed.json`。

## 持续稳定性检查：恢复默认音色前验证与失败回滚

复现/api/voice/reset先覆盖当前配置再解析默认文件，默认JSON损坏、null/数组或参考录音缺失时，
会把损坏内容写入当前配置或把无效默认音色当成功；替换失败还遗留临时配置。
/api/voice读取损坏JSON会抛未处理异常，空对象却显示正常音色。
新增三项测试，修复前出现2处断言失败、8处异常。

恢复接口现先读取默认内容快照，明确要求对象并用现有音色校验检查字段与参考文件存在，
通过后才原子替换；读/校验失败返回503并保留当前文件，写/替换失败返回503且尝试清理临时文件。
返回标签使用已验证的同一快照，避免替换后重新读取变化中的默认文件。
当前音色查询同样使用音色校验，损坏配置明确503，修复后正常返回。
此处校验配置结构与参考文件存在，不宣称通过存在检查即可证明参考音频内容完整。

音色配置4项、音色录入4项全部通过。测试覆盖五类默认文件不可用、原配置字节不变、
健康默认配置恢复成功、替换权限失败的临时文件清理，以及显示接口损坏后恢复。
编译与差异检查通过，已重启网关；真实音色查询200，标签“默认小男孩 · 小安”，
真实TTS200，262444字节、32kHz单声道、4.1秒有效WAV，当前音色配置哈希未变。
/ready全部就绪，四服务active。重置及损坏配置均在临时目录测试，未重置线上音色。
证据：logs/stability-20261024/ 下 `voice-reset-before.log`、`voice-config.log`、
`voice-enrollment.log`、`voice-reset-deployed.json`。

## 持续稳定性检查：取消请求中断与并发取消不能打断任务收尾

复现对话取消接口等待后台任务清理时，取消HTTP处理任务会通过gather再次取消后台任务；
两个并发取消请求同样重复task.cancel，打断后台finally中的异步资源清理。
新增三项隔离测试修复前其中两项失败。
取消接口现以cancelled状态避免重复注入取消，通过shield保护等待中的后台收尾，
并在后台任务完成回调中更新done/text_done，保证请求中断后仍能释放任务名额。
只有清理完成才标记任务完成，启动前取消也能更新状态；捕获任务字典引用避免等待期间再次查找。

取消专项3项通过，检查请求取消与双请求取消时后台仍在清理、名额未提前释放、
清理完成后正确取消状态，以及任务启动前取消。原有手动打断回归通过；
对话稳定性五场景通过（TTS失败、模型失败、截止时间、初始化失败、WAV处理与串行推理重叠）。
编译与差异检查通过，已重启网关。真实创建对话200、并发两次取消均200，轮询done与text_done
均true、finish_reason=cancelled且无错误，/ready全部就绪，四服务active。
测试对话仅为普通问候，未创建线上提醒或关怀事件。
证据：logs/stability-20261024/ 下 `chat-cancellation-before.log`、`chat-cancellation.log`、
`manual-interrupt.log`、`chat-stability.log`、`chat-cancellation-deployed.json`。

## 持续稳定性检查：唤醒心跳容错与写锁期间进程消失

复现关怀rows查询一次异常即终止heartbeat任务，后续不再更新care_event_id或释放过期播放抑制；
另复现control在等待写锁期间worker被清理，取得锁后访问self.process.stdin抛AttributeError。
新增两项隔离测试修复前均异常失败。
control现取得写锁后读取并校验进程，固定本次写入所用进程对象。
heartbeat分别隔离关怀查询与控制发送异常，查询失败使用空事件标识，仍尝试释放过期播放抑制，
随后按原有间隔重试；连续同类故障只记录一次，恢复后允许记录后续新故障，避免持续刷日志。
CancelledError保持向上传播，不被重试循环吞掉。

唤醒生命周期6项、WebSocket3项、关怀12项全部通过。
新增测试覆盖等待锁时进程消失、连续两次查询故障与连续两次控制故障后恢复、正确事件标识
与suppress=false、连续故障日志数量和取消退出。编译与差异检查通过，已重启网关。
/ready全部就绪，wake为idle且无错误；真实录音ASR200，文本“小安，今天天气好吗？”，
配置哈希未变，四服务active。数据库与管道故障只在隔离测试注入。
证据：logs/stability-20261024/ 下 `wake-heartbeat-before.log`、`wake-lifecycle.log`、
`wake-socket.log`、`senior-care.log`、`wake-heartbeat-deployed.json`。

## 持续稳定性检查：唤醒录音清理失败不能阻断恢复监听

检查LiveKit异步取消清理参考代码及本地唤醒任务，复现录音unlink抛PermissionError时，
audio的finally提前退出，正常识别与识别异常两条路径均不再发送resume；
取消路径的CancelledError也被清理异常替换。新增三个子场景修复前全部失败。
现将录音删除统一封装为记录OSError日志的清理操作，供任务finally与完成回调使用，
删除失败仍执行现有代次校验和恢复监听逻辑，取消任务保留取消状态且不恢复旧任务监听。
保留完成回调的再次清理机会；持续权限问题仍可能留下临时文件，本轮不宣称已解决磁盘权限本身。

唤醒生命周期4项、WebSocket3项、ASR13项全部通过。新增测试覆盖成功转录、识别异常、
任务取消下的删除失败，验证正确事件、resume指令、任务集合清理和取消状态；
模拟权限恢复后可正常删除文件。编译与差异检查通过，已重启网关。
真实录音ASR返回200、“小安，今天天气好吗？”，/ready全部就绪，wake为idle且无错误，
四服务active，识别配置哈希不变。权限失败仅在临时目录注入，未破坏线上录音目录权限。
证据：logs/stability-20261024/ 下 `wake-recording-cleanup-before.log`、`wake-lifecycle.log`、
`wake-socket.log`、`asr-service.log`、`wake-recording-cleanup-deployed.json`。

## 持续稳定性检查：运行期间ASR配置损坏的就绪状态

复现模型已加载后，配置被写坏、变成数组或删除，/ready仍报告asr=true、ready=true；
实际识别每次读取配置，已无法正常工作。新增隔离接口测试修复前出现三处断言失败。
ASRService新增轻量is_ready校验当前配置并确认模型已加载，/ready使用此结果。
配置不可读或非法时asr与整体ready为false；恢复文件后下一次检查自动恢复。
就绪检查不触发推理、模型重载或模型释放，也不等待推理线程锁。
保留/ready的HTTP200与现有JSON结构，由ready字段表达是否可用。

ASR13项、唤醒生命周期3项、WebSocket3项全部通过。
新增测试覆盖正常→三种配置损坏→恢复→未加载，验证其它依赖仍正常、模型对象保留、
配置恢复后可继续识别。编译与差异检查通过，已重启网关。
线上/ready全部就绪，配置与状态接口200，模型cuda:0且缓存完整；实际录音识别200，
文本“小安，今天天气好吗？”，配置哈希未变，四服务active。
证据：logs/stability-20261024/ 下 `asr-readiness-before.log`、`asr-service.log`、
`wake-lifecycle.log`、`wake-socket.log`、`asr-readiness-deployed.json`。
配置损坏仅在隔离临时目录中验证，未更改线上配置。

## 持续稳定性检查：ASR损坏配置提示与恢复

复现ASR配置为null、数组、非法JSON或文件缺失时，配置读取/状态/热词更新接口抛出
未处理异常；缺失或空model_dir未提前拒绝，cpu_threads和retries误接受布尔值。
此外hotwords缺失虽通过校验，却在状态读取时KeyError。
新增两项测试，修复前出现5处断言失败、8处异常。

配置读取现明确要求对象、非空模型目录与真正整数类型的线程/重试设置；
缺失热词统一归一为空列表。配置与状态接口对读取失败或非法配置返回明确503，
热词更新先验证旧配置，不覆盖损坏文件；识别完成后的热词配置读取同样使用明确错误处理。
修复配置文件后，下一次读取即可恢复，不缓存错误配置或悄悄回落到默认模型设置。

ASR12项、输入逻辑4项、唤醒生命周期3项全部通过。新增隔离测试覆盖八类非法配置、
四类文件损坏/缺失下的三个接口503、原文件保留，以及恢复后的读取/状态/热词更新200。
编译与差异检查通过，已重启网关；实际配置和状态接口200，模型CUDA加载且缓存完整。
真实录音/api/asr?care_commands=false返回200、“小安，今天天气好吗？”，配置哈希未变。
/ready全部组件就绪，四服务active。损坏配置测试只使用临时目录。
证据：logs/stability-20261024/ 下 `asr-config-before.log`、`asr-service.log`、
`input-logic.log`、`wake-lifecycle.log`、`asr-config-deployed.json`。

## 持续稳定性检查：天气与定位超大JSON整数的溢出恢复

复现合法JSON中的10**400在天气math.isfinite、经纬度float转换和缓存时间差计算中
触发OverflowError。此前未纳入错误处理，导致天气请求绕过缓存回退，损坏缓存行还会阻断
WeatherService初始化。新增首批四项测试在修复前出现6处异常。
现于天气刷新、缓存逐行加载、保存位置读取、网络定位和城市候选处理边界捕获数值溢出，
沿用各自的有效缓存回退、跳过坏记录或明确失败提示；不将异常数字强制截断为有效位置。

天气27项与提醒上下文13项全部通过。新增五项测试覆盖：当前与日预报超大数字、
无缓存接口503、有缓存回退且磁盘不变、后续正常请求恢复；三类磁盘坏记录与有效记录共存；
损坏保存位置自动恢复；网络定位失败保留原位置；地理查询跳过异常候选且保留有效候选。
编译与差异检查通过，已重启网关；真实天气接口200，复用正常缓存，保存城市文件哈希未变。
/ready所有组件就绪，四服务active，唤醒worker正常运行。
证据：logs/stability-20261024/ 下 `weather-overflow-before.log`、`weather.log`、
`conversation-context.log`、`weather-overflow-deployed.json`。超大数值注入均在隔离测试中完成。

## 持续稳定性检查：天气数值范围与预报日期一致性

复现上游返回负数/超过100%的湿度或降雨概率、负风速、最高温低于最低温，
以及预报日期重复或乱序时仍被正常发布并写入缓存；同类磁盘坏记录还能覆盖有效记录。
新增三项回归测试，修复前22项测试出现21处断言失败。
统一校验现要求湿度和降雨概率在0至100之间、风速非负、最高温不低于最低温，
预报日期使用标准日期格式并逐日连续。网络结果和启动缓存加载共同使用该校验。
异常刷新使用现有有效缓存并标记stale，不覆盖磁盘缓存；无有效缓存时明确报告天气暂不可用。
不设置任意温度上下限，避免拒绝合法极端天气。

天气22项、提醒上下文13项全部通过，覆盖八类上游异常、刷新回退和坏磁盘记录隔离。
编译与差异检查通过，已重启网关；/ready全部就绪，四服务active。
真实/api/weather返回200，上海三日预报正常且stale=false，保存位置文件哈希未改变。
异常数据均在隔离临时目录与模拟网络中测试，未破坏线上天气缓存。
证据：logs/stability-20261024/ 下 `weather-consistency-before.log`、`weather.log`、
`conversation-context.log`、`weather-consistency-deployed.json`。

## 持续稳定性检查：多句提醒事项引用不能误操作前缀事项

复现同一时间同时设置“喝水”和“喝水。然后散步”后，对后者说“取消这个提醒”或“改成后天8点”，
系统错误取消或替换前者。原因是上下文从工具确认语中提取事项时遇首个句号就结束，
将长事项截成同名短事项，再按时间和事项匹配到错误数据库记录。
修复前新增两个子场景均失败。现匹配工具确认语最终句号，保留事项内部句号和完整事项，
继续按完整时间与事项唯一匹配，不放宽歧义处理。

上下文13项、提醒12项、关怀12项全部通过。新增真实临时SQLite场景检查取消/修改长事项后，
短事项的完整数据库行保持一致；修改后带称呼确认语再接取消，也只操作长事项。
编译和差异检查通过，已重启网关。/ready所有组件就绪，关怀接口200，四服务active。
操作验证全部使用隔离数据库，未向线上写入或取消任何测试提醒。
证据：logs/stability-20261024/ 下 `reminder-reference-before.log`、`conversation-context.log`、
`reminders.log`、`senior-care.log`、`reminder-reference-deployed.json`。

## 持续稳定性检查：参考录音缓存损坏自动重建

复现cleaned_reference仅检查文件存在，空文件、坏WAV、仅头部以及PCM尾部截断均被复用，
导致后续克隆合成持续读取无效参考。新增用例修复前5项测试出现5处失败（含子用例）。
现读取缓存前验证单声道PCM16 WAV、非零帧数及声明帧数对应字节完整；损坏或不可读视为未命中，
从原录音重新降噪并通过临时文件原子替换。已有健康缓存继续复用，原录音不修改。
校验覆盖格式与截断，不宣称检测任意有效PCM内容的变化。

降噪/缓存5项通过，包括四类损坏重建、处理失败后再次重试、正常命中、原录音内容变化刷新，
以及真实FFmpeg降噪能量/时长和裁剪边界验证；语音缓存3项、音色录入4项、语音质量5项回归通过。
编译与差异检查通过，已重启网关，所有就绪检查通过、四服务active。
实际默认音色/api/tts返回200，258604字节、32kHz单声道、4.04秒有效WAV；
损坏参考缓存恢复在临时目录验证，未破坏线上缓存或切换用户音色。
证据：logs/stability-20261024/ 下 `reference-cache-before.log`、`voice-denoise.log`、
`speech-cache.log`、`voice-enrollment.log`、`voice-quality.log`、`reference-cache-deployed.json`。

## 持续稳定性检查：音色录入取消与存储失败清理

专项复现预览合成取消后参考录音残留，以及配置替换失败后参考录音、预览音频、临时配置残留。
修复前3项测试中2项失败。现将参考录音写入、预览合成和写盘、配置原子替换纳入同一提交过程，
只有配置替换成功后才保留文件；finally同时覆盖取消和异常，逐个删除废弃文件，
清理自身失败记录警告且不遮盖原异常。

专项4项通过，覆盖预览取消、合成异常、预览写入部分数据后磁盘失败、配置替换失败与成功路径，
验证失败后旧配置内容不变且无参考/预览/临时文件残留。音色配置1项（多个非法配置样本）通过；
对话稳定性5个场景通过：TTS失败、模型失败、超时、初始化失败、音频处理与串行推理并行。
编译与差异检查通过，已重启网关。全部健康检查就绪，四服务active，音色接口200。
实际config/voice.json的SHA256更新前后一致，仍为“默认小男孩 · 小安”；未向线上提交测试音色。
证据位于logs/stability-20261024/：`voice-enrollment-before.log`、`voice-enrollment.log`、
`voice-config.log`、`chat-stability.log`、`voice-enrollment-deployed.json`。

## 持续稳定性检查：重启修复关怀语音缺失

复现启动恢复只检查pending状态，导致此前合成失败、ready对应文件丢失或为空的有效提醒
一直没有语音。新增混合记录和持续失败样本，修复前12项关怀测试中2项失败。
现启动时检查未确认、未过期的有效事件，pending/failed及ready但音频缺失或为空的记录
重置为pending、清除旧URL并重建；已有有效音频保持原文件，不重复合成。
每次启动恢复仅尝试一次，合成仍失败时保留failed，不在每秒调度循环中重复请求TTS。
启动恢复也纳入run的try/finally，异常退出时回收任务和数据库。

临时SQLite测试同时覆盖pending、failed、缺失、空文件、有效文件、已确认和已过期记录；
验证实际重建文件内容与数据库ready状态，持续失败至少两次tick仍只调用一次合成。
关怀12项、提醒12项、上下文12项通过，编译与差异检查通过，已重启网关。
部署首次探测发生在端口启动前，随后等待就绪并确认/ready全部为true，四服务active，
间隔两秒读取关怀事件接口均200。线上当前无有效关怀事件；恢复场景由隔离测试验证，
未向实际数据库注入提醒。
证据：logs/stability-20261024/ 下 `care-audio-recovery-before.log`、`senior-care.log`、
`reminders.log`、`conversation-context.log`、`care-audio-recovery-deployed.json`。

## 持续稳定性检查：损坏声纹配置拒绝命令并提示恢复

异常样本复现声纹参考向量/阈值包含NaN时比较结果不触发拒绝，错误放行声音；
损坏JSON、字段缺失、维度不符等则引发未处理异常。修复前专项4项出现7处失败和8处错误。
现校验enabled类型、有限非零的一维数值向量、有效阈值，比较前归一化并验证模型向量维度。
无法可靠验证时抛出InputRejected，保留原配置，提示重新录入，禁止执行关怀命令。
显式verify=False的纯转写路径不读取声纹配置，重新录入路径可写入新配置恢复。
声纹状态接口将配置错误返回为422和可操作的提示。

专项5项通过，包括损坏样本、维度不匹配、匹配/不匹配/关闭状态、纯转写和接口命令隔离；
ASR10项及真实声纹/VAD/噪声/混合声纹/中文流与TTS回归通过，编译及差异检查通过。
已重启网关。在线/ready全部就绪，声纹状态200（已录入、当前限制关闭），四个服务active；
纯转写真实录音返回“小安，今天天气好吗？”，未执行关怀命令。
证据：logs/stability-20261024/ 下 `speaker-profile-before.log`、`speaker-profile.log`、
`speaker-language.log`、`asr-service.log`、`speaker-profile-deployed.json`。

## 持续稳定性检查：ASR回退重试和失败模型回收

注入CUDA推理失败后CPU暂时失败，复现GPU回退消耗普通重试预算：retries=1/2时，
原本下一次CPU尝试可恢复，却提前返回不可用。另复现重试耗尽后仍持有失败模型。
现独立计算普通重试剩余次数，CUDA转CPU不消耗该预算；CPU失败后先释放模型，
耗尽后返回不可用，下一请求重新加载，成功后清空错误。

新增恢复、持续失败上限、下一请求恢复验证。修复前9项测试出现2处错误和1处失败；
修复后ASR共10项通过，其中对retries=0/1/2分别验证一次CUDA加retries+1次CPU的上限。
语音输入回归通过（噪声拒绝、声纹匹配/混合声纹拒绝、持久化、中文流/TTS），
输入逻辑4项通过；编译和差异检查通过。故障场景使用隔离模型替身，未故意破坏在线GPU模型。

已重启网关，真实录音经 /api/asr?care_commands=false 识别为“小安，今天天气好吗？”，
未执行提醒等关怀命令。/ready全部就绪，ASR状态loaded/cached为true、device=cuda:0、
error为空，四个服务active。证据位于 logs/stability-20261024/：
`asr-retry-before.log`、`asr-service.log`、`speaker-language.log`、`input-logic.log`、
`asr-retry-live-transcript.json`、`asr-retry-deployed.json`。

## 持续稳定性检查：提醒事项不能改变时间和重复设置

复现“提醒我明天8点记录每天步数”被误设为每日重复、“准备下午的会议”把8点改成20点、
“确认后天行程”推迟一天、“看月亮”和“复习去年笔记”被当成不支持的日期而拒绝等问题。
另复现“提醒我十分钟后记录每天步数”被错误拒绝。新增用例在修复前共出现6处失败。
现对时间在“提醒我”之后的句式，以匹配到的时间结尾为界，时间段负责日期、时段和重复设置，
后面的事项保留原文。时间在“提醒我”之前的句式保留原解析行为。

隔离临时SQLite验证任务原文、实际到期日期时间和daily字段；提醒12项、上下文12项、关怀10项
全部通过。编译和差异检查通过，已重启网关部署。实际 /ready 所有组件就绪，关怀事件接口200，
四个systemd服务均active。未向实际提醒数据库添加测试提醒。
证据：`logs/stability-20261024/reminder-task-time-before.log`、`reminders.log`、
`conversation-context.log`、`senior-care.log`、`reminder-task-time-deployed.json`。

## 持续稳定性检查：关怀历史清理不能中断提醒调度

通过注入旧关怀音频删除权限错误，复现调度循环退出并关闭数据库，导致后续关怀、提醒及
相关接口无法正常工作的故障。现将历史清理独立为 prune_history，逐个处理过期文件；
删除失败记录警告并保留对应数据库行，供后续重试，其他记录继续处理。
历史清理每分钟执行一次，避免持久权限错误每秒输出异常；提醒调度仍每秒执行。

专项验证：注入清理错误后调度继续运行至少两轮，失败记录保留；解除错误后再次清理，
文件与记录均正常删除。另验证过期本地记录删除、近期记录及待重试推送保留。
关怀测试共 10 项、提醒 10 项、上下文 12 项通过；编译与差异检查通过，已重启网关部署。
修复前证据：`logs/stability-20261024/care-cleanup-before.log`；
修复后证据：`logs/stability-20261024/senior-care.log`。
部署后间隔两秒读取关怀事件接口，两次均正常，care 调度和全部服务就绪；四个服务 active。
实际接口证据：`logs/stability-20261024/care-cleanup-deployed.json`。

## 持续稳定性检查：定位与天气异常数据

新增异常样本复现了字符串坐标在查询时触发 TypeError、缓存城市字段类型错误阻止网关初始化、
缺少每日天气描述的记录仍进入缓存、地理编码异常结果触发异常或写入越界/布尔坐标等问题。
现统一校验位置字段并将合法字符串坐标转为浮点数；坏位置按未设置处理。
磁盘缓存逐条校验，坏记录不影响其他有效记录恢复，校验完成前不加入缓存。
地理编码逐个检查候选城市、坐标和时区，保留原有国家筛选与排序；查询失败不覆盖原位置。
网络定位缺少城市名时可使用有效坐标回退；布尔坐标被拒绝，保留已有位置。

天气测试由 12 项扩展为 19 项并全部通过，新增损坏位置恢复、缓存启动隔离、缺失描述拒绝、
异常地理编码不覆盖位置、混合候选筛选、自动定位缺城市及布尔坐标场景。
上下文 12 项回归、编译和差异检查通过，已重启网关部署。
修复前复现日志：`logs/stability-20261024/weather-invalid-before.log`、
`logs/stability-20261024/weather-geocoder-before.log`；修复后日志：`weather.log`。
部署实测 `/api/location`、`/api/weather` 和 `city=上海市` 均返回 200，取得有效天气后，
同城查询命中缓存；保存位置的 SHA256 前后一致。四个服务 active，全部就绪。
证据：`logs/stability-20261024/weather-validation-deployed.json`。

## 持续稳定性检查：唤醒重启隔离旧识别任务

增强异常重启测试后复现：worker 协议出错时旧 ASR 任务仍存活，可能在新一轮交互中返回旧转写，
或发送 resume。现将手动取消、worker 重启和服务退出统一为先递增 generation、再取消并等待
旧音频任务。即使后端忽略取消并返回结果，也不发布旧转写、旧错误或恢复监听指令。
另补齐创建任务后立即取消的边界：协程尚未开始时 finally 不会执行，完成回调负责兜底清理录音，
同时收取异常并移除任务引用。

唤醒生命周期三项测试通过，覆盖重试前进程回收/旧结果隔离、清理被取消后句柄保留、
未执行任务取消后录音清理。手动中断、WebSocket 三项、离线唤醒十一项回归通过；
编译和差异检查通过，已重启网关部署。
证据：`logs/stability-20261024/wake-lifecycle.log`；实际 worker 退出自动恢复记录见
`logs/stability-20261024/wake-worker-recovery.json`。
真实故障恢复：向当前 worker 发送 SIGTERM 后，观察到 ready=false、旧 PID 释放、
新 PID 启动并恢复 idle/ready，全过程约 3.794 秒（单次样本）；最终仅一个 worker 和
一个 parec 录音进程，网关各项就绪。

## 持续稳定性检查：长对话的音频保留

复现：音频目录已有 200 个新文件时，另一回答完成后的清理会删除仍被活动任务、
十分钟有效期内已完成任务引用的早期音频，导致任务返回的下载地址失效。
统一普通聊天和流式聊天的清理逻辑，保留最新 200 个文件，并保护上述任务的引用音频；
已过期任务不再额外保护。清理遇到文件访问/删除错误时记录警告，不影响已经生成的回答。
保护范围内文件可能使总数暂时超过 200；任务到期后可在后续清理中回收。

新增两项专项测试：在超过保留数量时验证活动/近期/过期任务音频的存删行为，
以及注入清理权限错误后回答仍成功。旧实现第一项失败，修复后两项通过。
手动中断测试的任务样本补齐生产环境已有的 created 时间字段。
手动中断、流式完成、聊天稳定性回归通过。
专项证据：`logs/stability-20261024/audio-retention.log`。
天气 12 项回归、编译及差异空白检查通过后重启网关。部署后连续创建并取消 5 个真实聊天任务，
均正常标记 cancelled，随后新对话正常完成且 WAV 下载成功；最终所有就绪项及唤醒正常。
实际服务证据：`logs/stability-20261024/audio-retention-deployed.json`。

## 持续稳定性检查：配置损坏、流式完成与唤醒进程

完整备份位于 `/home/yyy/备份/digital-human-20261024-2130`，本轮修复发生在备份之后。

- 称呼设置损坏、内容不是对象、编码错误时回退为“您”，设置接口仍可修复。
- 聊天初始化读取称呼失败时，任务正确结束并回收子任务，释放并发名额。
- LLM 流兼容空 choices 用量帧、`data:` 后无空格；收到 `[DONE]` 后立即结束读取，
  不再依赖连接关闭，避免回答已完成却等待超时。
- 唤醒 worker 协议异常时先回收旧进程再重试；清理被取消时保留句柄，供最终退出流程继续回收。
- 唤醒 WebSocket 首次状态发送断线也释放订阅；发送或接收任务任一结束即取消并等待另一个任务，
  避免单方向断开后残留会话。三个断线专项测试通过。
- TTS 与流式聊天共用音色配置校验。损坏 JSON、缺失文件、错误字段类型、缺失参考录音
  返回带恢复默认音色提示的 503；校验失败不创建聊天任务。合法的空参考文本仍允许。

参考 LiveKit Agents 的异步取消及等待清理方式，以及 Pipecat 实时管线的分阶段设计，
优先修复本项目任务结束与资源释放问题，未引入框架依赖。
参考地址：https://github.com/livekit/agents 、https://github.com/pipecat-ai/pipecat 。

验证：15 组已有功能回归全部通过（清单见 `logs/stability-20261024/results.json`）；
另通过称呼配置、聊天异常清理、流式完成、唤醒生命周期和音色配置专项测试。
音色校验修改后重新通过缓存、音色质量和聊天相关回归；唤醒修改后通过手动中断及离线唤醒。
编译检查及 `git diff --check` 通过。真实聊天返回一段有效 WAV，首文字 0.178 秒、
首音频 1.579 秒，仅为单次运行记录，不作为性能提升结论。
证据目录：`logs/stability-20261024/`。

最终部署复查：音色校验部署后真实聊天首文字 0.051 秒、首音频 1.438 秒，
正常 stop 并成功下载 WAV（`deployed-chat-final.json`，单次样本）。
WebSocket 清理修复部署后连续 20 次真实连接/接收状态/断开均成功，
最终 LLM、TTS、关怀、ASR 和唤醒均就绪（`wake-reconnect.json`）。

## 本轮已落地

重复语音内存缓存（32条、32MiB、10分钟有效期）。仅保存已处理成功的WAV，
键包含文本、语言、音色配置、参考文件内容摘要。动态聊天和真实工具调用仍正常执行。
实测同句TTS约1.089秒→2.14毫秒→1.84毫秒，仅适用于命中缓存的语音片段。
网关已重启，服务就绪；新缓存3项、原语音质量5项、聊天稳定性4场景通过。
证据 `artifacts/validation/speech-cache/results.json`。

## 建议顺序

| 优先级 | 事项 | 已有证据及改进方向 | 验收方式 |
| --- | --- | --- | --- |
| P1 | 新音色首次合成稳定性（本轮已改善） | 当前参考录音首尾静音影响短句合成；清理副本裁剪外侧静音后，4句×3种子从9/12通过提升到12/12。继续扩大不同录音样本，不能推算所有音色均稳定 | 统计首次通过率、重试率、漏读率与耗时；检查新旧录音 |
| P1 | 录入质量反馈 | enroll目前验证格式/时长、音量和试合成；可加入削波比例、有效人声时长及背景噪声提示，再选择参考段 | 噪声/削波/过短有效人声样本与清晰录音对照，保留原文件 |
| 已完成 | 客户端音频结果结构 | Result.clips已改为独立AudioClipResult[]，解除自递归。Unity构建0警告/0错误，字幕、分段、重播、中断自检通过，正常客户端已恢复，启动日志未出现深度警告 | 证据见artifacts/validation/voice-startup/subtitles.json及unity-subtitles.log |
| P2 | 分阶段性能统计 | 已有首文字/首音频耗时，但缺长期汇总；补充排队、TTS、质量检查、后处理、下载和开始播放统计 | 多轮样本看中位数及95分位，区分首次/缓存/重试 |
| P2 | 城市解析缓存 | 天气结果已有10分钟缓存，但带city查询仍先resolve，resolve每次联网且单次超时8秒 | 相同城市不重复地理查询，国家过滤/不同城市隔离；失败不缓存为成功 |

本轮不将默认音色或新音色的少量成功样本视为稳定性已完全解决。滤波对底噪有效，
模型金属感、削波与混响还需针对具体录音评估。未来外观与口型改进应在语音可靠性之后，
并先测客户端帧率、口型与音频时差，再决定优化范围。

## 本轮继续优化：参考录音首尾静音与客户端结构

参考录音先降噪，再仅裁剪首个人声之前和最后人声之后的静音，两端保留150ms，
中间停顿完整保留。裁剪后不足3秒或超过10秒、未检出人声时保留完整清理副本。
原始参考文件与音色配置不改写，处理配置纳入缓存键。

部署后4条真实/api/tts请求均成功，包括“你好”，耗时0.694～0.953秒；
一次真实流式聊天生成2段，逐段转写覆盖率均100%，首文字4.580秒、首音频6.792秒。
没有受控性能基线，不宣称本轮加速。有限样本不能证明所有偶发无声均已解决。
证据：artifacts/validation/voice-startup/{matrix,deployed,streaming}.json。
后续优先补充录入质量反馈及分阶段性能统计。

## 多轮提醒补全修复

“一个小时后提醒我”→“提醒我吃饭”现可在第二句补全后创建提醒。
修复相对时间漏识别量词“个”、补全事项重复拼接“提醒我”的问题；支持“之后/以后”、
礼貌前缀与时间后置。第二句若明确给出新时间，按新时间执行。
未完成事项前不创建提醒；相对时间从补全创建时起计算。当前会话上一轮完整问答
提供补全信息，其他会话或已经切换的话题不继承时间。
上下文11项、提醒7项、输入纠错4项回归通过，覆盖数据库与完整/流式请求处理。

## 设置页面排版

设置侧栏新增“对话输入/偏好设置”页签，设置按音色、音量与唤醒、形象、称呼、声音识别分组。
标题、导航和底部状态固定，设置主体可滚动；加宽侧栏和输入区，统一按钮尺寸与间距，
为对话操作图标补充文字标签。已构建部署（0警告/0错误），实际验证1280×720与1024×600，
页签切换、设置滚动到底及中文拼音候选显示正常；正常客户端恢复1280×720并展示设置顶部。
截图见artifacts/validation/settings-layout/。
