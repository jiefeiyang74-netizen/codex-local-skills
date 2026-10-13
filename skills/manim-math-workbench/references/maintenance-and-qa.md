# 维护与验收

## 分发边界

白名单执行核心位于 `assets/engine/v3/`（generic 音频、分镜与渲染）及 `assets/engine/geometry/`（声明式数学、校验与渲染）；导演提示词位于 `assets/engine/prompts/`。不复制原应用 server、网页、虚拟环境、用户历史、音视频、缓存或密钥。

当前包 runner 版本、storyboard schema、capability 版本都由 `contract` 输出并写入 manifest。源码来自现有工作台的对应版本；`rendering.py` 的字体查找仅保留 Windows 环境探测，不依赖某个用户的绝对路径。接口或执行行为变化时同步能力版本、contract 与示例，并运行相关回归和真实渲染；只改文档/导演提示词时检查加载、规则冲突及代表场景，不为凑验收重跑无关长片或虚增能力版本。

来源提交与许可实际状态见 [来源与分发边界](provenance.md)。当前运行入口固定加载包内引擎，并使用隔离 Python 启动；验收仍须核对实际加载路径，不能仅凭文字判断隔离成立。封包必须以已通过验收的安装版源码为准，不能取同名旧副本或旧 ZIP。

## 真实验收

运行时版本以 contract 为准。geometry-1.0 是协议名，不等于 capability 版本；能力从 1.1 的圆、1.2 的参数数轴扩展到 1.3 的二次函数，新增能力须保留旧能力回归。圆对象和真实圆周运动的验证必须包括运动中间帧守半径、顺逆时针、投影及线段和标签同帧更新、连续动作状态，以及无效圆周起点的拒绝。实际产出仍须通过音频、媒体和视觉验收；数学单测或能力测试片不能替代用户本期成片验收。

geometry 关键帧提取覆盖圆周运动中间帧、每条动作结束及章末稳定帧，并增加公式切换中帧。自动抽帧仍需主代理实际查看，不自动标记视觉通过。

geometry 结论式验收须从锁定口播稿建立应显示清单，逐条核对其在对应真实声学窗内完整、稳定、可读地出现；等号、负号、括号及两侧各项须同时在场，不能只验证已显示式子的代数正确性而漏掉从未完整出现的结论式。hide/text_transform 等过渡后，须安排被隐藏符号的恢复，并在下一次替换或隐藏前留出足够的连续稳定帧；按实际输出帧率及帧量化核对恢复完成至再次变化的帧数，再从当前真实视频记录稳定首末帧、帧数及可读性证据，不能只凭动作存在、正 duration 或过渡闪帧判通过。声学锚不足、完整式缺席或稳定阅读时间不足均为待修复项，不借下一条结论的画面补算覆盖，也不编造时码或延长原音频。

完整验收按实际显示时段检查所有可见固定点和动点的标签、坐标刻度标签及其黑底 mask 与主几何的避让；局部修复按下文限定复验范围，但受影响画面内的邻近标签、角弧和线条仍须一起核对。数值 bbox 仅作筛查，不能代替真实帧。

媒体片尾校验以已解码的原音频采样数为时钟，保留源容器时长供诊断；MP3 文件头可能带编码填充或版本相关估算差异，不能据此误判高清缺帧。帧连续性与音频完整性仍逐帧/逐采样解码检查，不放宽真实截断的闸口。

runner 0.1.1 修正首次公式的动作回执：`board_opening` 覆盖实际 FadeIn 开始至结束，并去掉首次展示后多余的强调脉冲。此前 `board_reference` 回执记录的是淡入之后的强调动作；不能把该回执与 Whisper 估计相减，宣称存在或改善了约 0.34 秒的真实逐词延迟。

同步测量应分别记录动画开始/完成、媒体中首次可见帧及其亮度阈值、Whisper 估计锚点和人工语义标注。淡入的首次可见时刻取决于像素阈值，视频还有一帧量化误差；波形能量只能定位全句或声音活动起点，不能作为每个词的真值。没有人工逐词标注时，只报告可观察现象和估计之间的差异，不宣称精确逐词同步误差。

最低证据分三层：

1. `contract`/Python 静态检查：接口和源码可加载，不证明 Manim 渲染。
2. `smoke`：合成音频通过真实低清 Manim 渲染，检查 preview 有音频流、低清稳定帧无问题；其 timing 明确为 `synthetic_fixture`，不证明 Whisper。
3. 用户任务：真实音频经过本机 Whisper；generic 检查 `alignment_passed=true`，geometry 检查 analyze/对齐附件的真实 token、输入绑定及动作审计验证结果，不要求不存在的同名字段。低清验收通过后才允许 final；用 PyAV/FFprobe 等证据核对视频分辨率、帧率和音频流。尚未查看真实当前帧时，`visual_review` 保持未审查。

失败 attempt 必须保留 `manifest.json`、报告和日志；低清失败不许用参数绕过。只在用户明确选择并且产品后续定义了安全的 `allow-preview-fail` 策略时，才另行设计例外，本版本默认没有该开关。

## 常见故障

- 缺 Python/Manim/PyAV/Pillow：重新指定 runtime config 或让环境安装流程完成，不在 runner 中静默替换为估时字幕。
- 缺 FFmpeg：先在 setup/doctor 阶段修复可执行路径；不要把剪辑软件目录硬编码进包。
- Whisper 返回低匹配：保留 alignment 报告，按[锁定稿音频规则](narration-preparation.md#锁定稿生成音频来源确认替代逐词追问)区分内容来源与时间对齐。满足前提时，ASR 同音/漏识别本身不触发重录、反复追问或阻挡渲染；真实时间锚不足仍须修复自动对齐，不伪造通过。有证据证实整段缺失、损坏或重大内容错配时，处理受影响部分。
- 分镜 validator 拒绝：根据具体字段/状态错误修 JSON；不要删除 `unsupported_requirements` 或放宽校验。
- render 失败：查看 attempt 的渲染日志；保持旧 attempt 和输入不变，可修复后新建 attempt 重跑。

本地运行可以使用 stdlib `unittest` 检查 contract、示例分镜规范化和编译；真正的完成口径仍然是当前环境的低清/高清渲染和当前真实画面复查，不是测试片或旧报告。

记录测试机、独立目录、运行时位置、实际源码 hash、真实语音 alignment、音视频流参数和视觉复查结果；本机独立目录验证不等于第二台全新 Windows 验证。核心未稳定前不冻结源码，不提前封 ZIP。核心稳定后从已测源码创建干净 staging，包含新增文档与来源许可，再封包并独立解压逐文件比对 hash；私密材料和验证音频只留在包外验收目录。

geometry capability 1.3 增加二次函数图像、参数变化及顶点/轴/根/截距/曲线动点。新增数学与拒绝路径测试，以及12秒合成无声真实渲染只作为能力证据；用户成片仍须原音频对齐、低清有声验收和匹配的高清导出。

## 已授权的能力补齐

从当前实际安装版新建隔离候选副本，并记录代码哈希；不能从前一次任务的旧 candidate 覆盖更新的能力。先列出缺失的对象/动作/数学状态，再把最小通用实现接到 schema、数学模型、runtime、导演提示词与可执行示例。题目数字、音频路径、单次构图留在项目。

验证新能力的数学边界、拒绝路径和受影响旧能力，再用小型真实动画检查运动中间态、依赖特征、标签和末态。合成音频或无声能力测试只证明已检查的能力，不能替代本期有声预览。通过后备份并同步实际安装版与已知分发源码，以相同已测源码继续本期制作。安装、渲染或验收失败时保留已完成的分镜和分析，只修受影响环节；不要重复调用付费分镜服务或重写已批准的稿件。

## 画面证据与复核成本

- 帧检查覆盖章节末稳定画面、关键结论落定、重要运动前中后及条件交接。证据记录视频身份、实际时间、帧路径/哈希和检查内容；记录工具只整理证据，不能把自动抽帧视为已经审阅。
- 委派检查时明确章节/时间范围，汇总实际看过的帧和未决项；局部通过不泛化为全片每帧通过。自动全帧解码证明媒体完整性，也不等于逐帧视觉审阅。
- 一处标签修复后，视觉复验仅覆盖受影响显示时段的前、中、后及相关过渡，连同邻近标签、角弧和线条检查；其余帧与已实际审过的帧哈希相同时，保留并引用旧通过证据、注明来源，不重复整片目检。证据不匹配或影响范围扩大时再扩查；新 MP4 的必要媒体完整性验收仍保留。新 preview/final 证据各自绑定当前视频 SHA-256、manifest.identity、帧哈希与实际时间，不得跨质量或版本混用。
- 每次人工听审都记录实际播放媒体的 SHA-256、所听片段起止时间、核对结论与未覆盖范围；多个片段分别登记。局部听审、ASR 或全帧/全采样解码均不能推断全片已听审，不得把计划播放范围记为实际已听范围。
- 批量图片中疑似标题消失或文字缺失时，先单独打开该帧，并从 manifest 指向的 MP4 复取同一时间核对。查看工具显示、缓存和真实视频故障分开定位；未在原视频复现前，不修改引擎或扩大成整片重渲染。
- 数学/布局修复完成后再高清；环境、执行器和输入未变且有效检查已通过时不反复跑同一验证。最终如实报告媒体检查、视觉抽查和音频核对各自覆盖范围。

## 可编辑项目与技能分发

成片项目包含恢复所需的 request、storyboard、alignment、action audit、原音频及验收证据，输入路径可相对项目解析。纯 Skill 包不带本期媒体或私人材料。两者均从当前已测源码制作，文件清单与哈希可追溯；验证压缩包可解压且内容一致。打包成功不等于另一台机器已运行验证，也不扩大复制或对外分享私人音频的授权。

## MP4 封装与当前作业 partial 保留

geometry 的交付 MP4 固定 AAC：源音轨已是 AAC 时 copy，WAV/PCM 等编码 AAC；不得以“FFmpeg 接受 PCM”作为兼容交付依据。原音频只读，不用 shortest、截时或重采样掩盖尾差。改封装时用短合成 WAV 真渲染 preview，保存源/输出解码采样时钟、首尾 PTS、AAC priming 与尾部 padding 证据，运行原 media_validate；编码填充不等于旁白可裁短。

geometry 和 generic/v3 的本包渲染使用 attempt 内 retain_partials.cfg（max_files_cached=-1、flush_cache=False），只保留当前作业，不改用户全局配置。media/partial_index.json 保存各目录、concat 顺序、片段哈希、帧数来源及累计帧区间；原 partial 和 concat 清单不自动清理。失败渲染仍保留已生成文件；尚未完成 concat 时不能承诺完整索引。

索引的容器帧数不是逐帧解码证明，也不自动复用或拼接。局部 `-n` 片段只有在与完整时轴的对应帧预算、边界状态及连接处时钟一致时才可复用；不一致则按完整时轴重渲染，不得用 trim 补偿帧差、伪造同步。以后局部微修须核对输入/引擎/画幅身份，真实解码受影响片段及连接处的帧数、帧率和连续时钟，检查原生局部画面、邻线及过渡，再对新 MP4 运行完整 media_validate 和音频首尾验证。保留缓存不恢复以前已被删除的片段；清理旧 attempt 另按用户授权执行。

## 文字与符号运动路径验收

文字/符号的 move、text_transform 或复制位移动画不能只验起终点。至少覆盖动作起点、运动中间、终点及最靠近已有公式项的时段，检查完整字形边界与当时可见公式、标签的占用区；发现交叉时增加相邻连续帧，或进行局部路径包围盒筛查。保存当前视频SHA/identity、实际帧时间和碰撞判断；若没有适用的自动检查，逐项列人工帧证据与未覆盖范围。途经点、层位、透明度均不能替代真实中间帧复核。抽样包围盒及单个路线fixture只证明其检查范围，不是通用自动视觉无碰撞证明。


## geometry-1.7.0：动态扇形与可展侧面

动态sector沿用度数和严格仿射标量；0为空、360为圆盘，旧静态sector/circular_segment保持兼容。cylinder_net/cone_net仅实现有限正尺寸的侧面，用set_parameter驱动unfold∈[0,1]；cone_net与conic分离。解析定义、字段和测量语义以实时contract及geometry导演提示词为单一接口依据。

此扩展的聚焦验收须对实际XYZ函数在p=0/.25/.5/.75/1做独立有限差分，验证第一基本形式、积分面积、闭合缝和终态边界，不能只核metadata。圆锥按实际b=1-(1-β)(1-p)²验证末段连续性；圆柱检查p=1解析极限及近终点稳定性。schema须拒绝非有限、布尔、越界、未知字段及表达式；覆盖初态和set_parameter终态（仿射输入及允许区间均凸，因此区间内线性过渡有效）。渲染回归覆盖sector半径/起角/扫角更新、0/90/360、空态再次出现及旧静态区域；display_scale须核对实际渲染坐标缩放及内蕴度量不变。

用包外短合成音轨fixture检查起、中、末真实PNG、网格与轮廓，保存加载路径、源码/视频/帧SHA-256及media_validate完整解码结果；timing_source明确为synthetic_fixture。局部扩展验收不替代本期主视频preview、音频对齐或最终ready状态。不迁移旧输出，不重新安装ASR或重复无关全套smoke。


## geometry-1.8.0: bounded long lessons

Only an explicit top-level `production_profile: "long_lesson"` enables duration <=14400 seconds,
chapters <=512 and total actions <=12000. Missing profile or `"standard"` keeps the original
7200 seconds / 100 chapters / 3000 actions. Unknown, null, boolean or object profiles are rejected.
All per-chapter object/action/check/parameter/text limits, mathematical/lifecycle checks,
real audio-token/audit requirements and complete media/visual QA stay unchanged.
The declaration survives normalization, compiled Scene spec, render identity and reports;
preview/final cache identities cannot cross profiles. Render timeout remains 43200 seconds
and failure is reported without trimming audio, accelerating narration or omitting actions.
Long lessons release prior chapter text caches and spool numeric snapshots per chapter,
then stream the same JSON report structure. This is one continuous existing renderer,
not enabled parallel chapter rendering or boundary cache reuse. Synthetic tests are only
capability evidence, not production audio/visual acceptance.


## geometry-1.8.1 Whisper 来源与动作审计

真实 Whisper alignment 必须携带原 full-json 文件路径与SHA，逐token验证原raw对象/文本/时间与null；仅source字符串不能通过。派生alignment需provenance_sources与token.origin，逐采样验证PCM来源和整数frameoffset，原对齐与raw文件保留。动作audit必须绑定源稿范围和原文；trigger_evidence提供真实cue的source/token配对，motion_window单独声明同句或紧接解释句的真实证据窗。后文不能借作前文启动词，review字符串不能绕过同cue前序动作与有界窗口。synthetic_fixture只供单测显式参数，生产runner不开启。合法旧Whisper缓存有原raw_evidence可复用，旧动作audit需补真实source/trigger/window，不复跑未变ASR。
