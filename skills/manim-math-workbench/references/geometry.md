# geometry-1.0 独立声明式分支

此分支不调用 generic4.3 normalize/renderer，不执行用户 Python。实时 `contract.geometry` 列出实现字段。数学使用本地 math2d，文字使用 Text，无 TeX。未知字段、动作、引用、循环依赖、非有限数、重叠事件或数学检查失败直接拒绝。

## 圆与圆周运动（capability geometry-1.1）

协议继续兼容 `geometry-1.0`，实时 contract 增加独立能力版本。`circle` 对象使用 `center` 点 ID 与正数 `radius`，可设置 `color`、`stroke_width`、`dashed`、`fill_opacity`。以 `reveal` 的 `style: "draw"` 绘制真实圆。

`move_on_circle` 动作字段为 `at`、`duration`、`type`、`point`、`circle`、`angle`。`point` 必须是自由点且当前位于所引用圆上；`angle` 是弧度增量，正值逆时针、负值顺时针，绝对值不超过 8π。动作按真实旋转参数逐帧更新，原有投影、边线与点名同步跟随；禁止将普通直线 move 串联后声称圆周运动。圆心不得依赖正在运动的点。可以在动作之间移动圆心，但下一次圆周运动前，动点必须已位于新圆周上。

通用示例见 `examples/circle_projection.json`。该示例仅说明协议，示例中的动作秒数不能替代用户真实音频锚点。三角形应用中仍须检查共线退化点，不得把不可取的极限端点描述为已取到的最大值或最小值。

## 可复用流程

首次 `setup → contract → analyze → Codex JSON → preview → 真实画面人工审阅 → final`。使用 setup 输出的 RuntimeConfig，无需原作者硬盘路径或模型 API key。

```powershell
scripts/video.ps1 analyze -Request request.json -JobDir output -RuntimeConfig runtime.json
scripts/video.ps1 run -Request request.json -Storyboard storyboard.json -JobDir output -RuntimeConfig runtime.json -Quality preview
scripts/video.ps1 run -Request request.json -Storyboard storyboard.json -JobDir output -RuntimeConfig runtime.json -Quality final
```

request 保留 problem/narration/audio_path；增加 alignment_path、action_audit_path，final 可指定 visual_review_path。相对路径按 request 所在目录解析。analyze 使用已有本地音频分析/缓存，仅导出原始 token 时间为 geometry 锚点；不使用按字数插值的 script_points。run 没有 alignment_path 时分析一次，但仍需有动作审计附件才能渲染。已有合格附件直接复用，不重新识别。

alignment 可用带 metadata 的 anchors 附件，或包含 anchors/units[].words 的分析文件。必须有 source_audio_sha256、canonical_narration_sha256、本地 Whisper 来源、原始 token id/text/start/end/time_source。canonical：utf-8-sig 解码、CRLF→LF、strip、UTF-8 哈希。时间范围必须合法。此绑定证明文件一致性，不证明 ASR 内容或词级精度；内容核对按[锁定稿音频规则](narration-preparation.md#锁定稿生成音频来源确认替代逐词追问)分流；满足前提时，低置信度或识别错字仅作非阻断记录，句界与动作时序仍用真实音频自动校验，不能声称小于 0.2 秒精度。

analyze 优先复用 request.alignment_path，其次复用绑定音频/稿件哈希的 geometry 缓存，再复用旧分析中真实 token；仅无可复用分析时调用已安装本地 Whisper。新分析的 numeric_matches 使用包内整数等值规则（30↔三十、10↔十），字母与下标角色独立匹配，M/N 不替换；数值时间取整段原始 token 的并集，不拆词、不为缺失数字插值。无效 token 可保留明确的 null 时间，但不能用于 action audit。analysis_report 单独记录来源、有效 token 数和 asr_launched，内容确认方式按上述来源规则记录，不把 ASR 当作人工听审。

上述来源规则同样适用于 director 提示词中的“待听审”：满足锁定稿前提时，不转成逐词人工确认门槛；内容疑点记为非阻断，缺失或歧义时间锚记为技术待修并补真实证据。有效锚、动作审计及媒体/视觉验收要求保持不变。

动作审计 JSON（附件，不改变 storyboard schema）：

```json
{"source_audio_sha256":"实际音频哈希","canonical_narration_sha256":"实际稿件哈希","alignment_sha256":"实际附件哈希","actions":[{"chapter_id":"c1","action_index":0,"at":0.6,"anchor_ids":[12]}]}
```

每条动作必须登记且 at 与分镜一致。at 落在所选真实 token 包络之外时，必须额外提供 reviewed_by/reason/evidence，说明为何需要提前出现、过渡或静止；不能按字数制造时间。

## 冻结结构和预算

顶层 schema_version/title/audio_duration/narration/chapters，可选 canvas:{width,height,fps:60}；本期横屏必须明确写入项目 canvas，geometry 当前无 canvas 时为 1920×1080。preview 长边≤720、不放大、偶数尺寸、30fps；常见比例精确保留，特殊比例允许不足2像素取整。final 原生按 canvas。新项目先按[用户导出偏好](operate.md#用户导出偏好与像素验收)解析，已有 canvas 不被本机偏好覆盖。旧分支默认不变。

chapter: id/title/start/end/world_bounds/problem/objects/actions/checks；可选 plot_rect、formula_rect，均为 [cx,cy,width,height]。首章从 0 开始，末章覆盖音频尾（仅允许尾帧舍入）；章间空隙保留前章画面。章首留出约 0.5–0.8 秒供标题转换，不后移绝对时钟。formula.lines 最多 3 行，problem 最多 2 行；独立 text/formula_group 使用实时 contract 的文本预算，不套用三行上限。预算只是粗筛，不能代替人工画面验收。

objects/action/check 字段见实时 contract；完整样例见 examples/geometry_minimal.json。定义初始隐藏，reveal 才出现。constrain:{at,duration,type:"constrain",point,derive} 将自由点动画移到派生位置后绑定，derive 支持 reflect/project/translate/intersect；随后只能移动其自由依赖点，不能直接 move 已约束点。schema 对运动采样求解并在章末真实计算 checks；采样不是连续区间数学证明。

## 渲染与人工门槛

当前采用整片受控入口，12 小时上限并持续写 manim.session.log；尚未按章缓存。相同 spec、engine 源码、音频、对齐及动作审计哈希和 quality 可复用已验证视频。交付 MP4 固定 AAC：源音轨已是 AAC 时可 stream-copy，其他音轨只做一次 AAC 编码；原音频只读，不改速、不裁切。解码全部帧检测损坏/帧间距，验证声道、采样率、尺寸、帧率、时长；抽取至少 24 帧及重要运动中间帧和 contact sheets。 preview/final 的媒体全帧校验与关键帧收集共用一次视频解码，抽帧完成后仍校验至视频尾；源音频和输出音轨继续分别全解码。抽帧时间、JPEG/拼图及报告字段沿用既有语义，成片不重编码；失败可保留诊断帧，但不得标记通过。

新分支的真实视频路径读取当前 manifest.artifacts.video，quality 区分 preview/final；不假设旧分支的 artifacts.preview/final。输出尺寸以实际媒体验证结果为准，不能只凭 CLI 或 canvas 声称渲染质量。

验收同时检查数学语义与视觉缺陷。先对照[图形语义规划](../assets/engine/prompts/geometry_director.md#图形语义规划)，核对实际画面的变量映射、适用条件、守恒或变化规律、变换前中后与算式的对应，确认一般结论有相应论证；再检查下列可读性与连续性问题。数学正确不能抵消遮挡，画面无瑕疵也不能证明模型解释成立；两者均满足才能判定通过。

真实画面复核应覆盖以下易漏项：

- 标签在反射前、中、后和最优位置均须可辨认；带下标点名不能与同向线、等长 ticks 重叠。
- 转入辅助直角三角形证明时，用切换动作中的 hide（FadeOut）收起不用的旧角标、基线、原路线及点名，避免新角度数值压在旧基线上。隐藏对象仍可参与 derive；保留其数学定义和依赖关系，不以删除依赖代替显示切换。
- 逐一查看角度弧、数值、垂直符号、辅助线和文字之间的相互遮挡。bounds、字符数及 max_width 检查仅是粗筛，不能证明排版可读。 角度标签还须在实际高清原生尺寸的局部帧中，检查数值及度数符号与自身角弧的间距，以及数值与度数符号的可辨关系；避开线段并不等于通过，不得因贴弧或重叠造成度数误读。
- 公式不仅检查稳态，还须核对更换中帧：同位置旧式完全退场后新式再出现，新旧字形不得重叠；内容改变由动画完成，沿用原动作预算，不增加总时长。
- 小角度或角平分线穿过内置数值时，angle 不设 label、只保留角弧；用独立 text 在外侧标数值，以已有细 line 作引线（leader），三者用同一 reveal/hide 动作同步出现和隐藏，无需新增引擎字段。不得把数值硬塞进窄夹角，或为避让改变真实夹角。距离数字也须检查最终位置和运动途经状态，避免线段穿字。
- 每个答案完成后的稳定画面、每章末稳定帧必查，并核对重要运动前、中、后。当前自动通用抽样未必覆盖这些时刻；从实际 manifest.artifacts.video 所指 MP4 补取所需帧，记录实际时间和帧文件，按可读文字的尺寸审阅。contact sheet 只作定位索引，不得仅看小拼图判视觉通过。

preview manifest 的 local_validation.passed 只表示自动本地检查，不包含上述人工复核。主代理实际审阅关键帧、必要补帧及视频运动后，在 preview attempt 旁保存 visual_review.json；evidence 登记实际查看的帧文件及哈希，notes 说明对应时间、遮挡检查与音画关系：

```json
{"status":"passed","identity":"从preview manifest复制","preview_sha256":"从preview manifest复制","reviewer":"实际审阅者","reviewed_at":"实际ISO时间","evidence":[{"path":"keyframes/实际查看的帧.jpg","sha256":"实际文件哈希","time":12.5}],"notes":"实际检查到的布局、公式、几何运动及音画关系；示例时间不可直接复制"}
```

未看画面不得生成 passed。final 要求匹配 preview 与完整证据哈希；final 自己的 visual_review 仍为 not_reviewed，需对最终画面另行验收。可在 final attempt 旁保存独立 `visual_review_final.json`，绑定该 manifest.identity、video_sha256、实际帧证据与审阅范围；这是交付记录约定，不是额外 runner 自动闸门。高清不能沿用低清截图证明画面通过。具体证据复用与故障诊断见 [维护与验收](maintenance-and-qa.md)。

最终复核记录示意（实际审阅后填写，不把占位值当通过证据）：

```json
{"status":"passed","identity":"从final manifest复制","video_sha256":"从final manifest复制","reviewer":"实际审阅者","reviewed_at":"实际ISO时间","evidence":[{"path":"keyframes/实际高清帧.jpg","sha256":"实际文件哈希","time":12.5}],"scope":"实际覆盖的章节、运动及音频核对范围","notes":"发现的问题、修复及剩余限制"}
```

规划与复核中的状态交接、静态题面适用范围和标签遮罩规则见 [geometry director](../assets/engine/prompts/geometry_director.md)。这些规则同时检查变化过程中仍成立的条件，不只验收最终图形。


## geometry-1.2：参数数轴与区间（兼容1.1圆）

chapter 可选 `parameters`：最多16个合法id到有限数值的映射。端点只接受有限数、开端 `"-inf"`/`"+inf"`，或严格 `{ "parameter": "a", "scale": 2, "offset": 1 }` 仿射对象；不接受表达式代码、不使用eval。

`number_line` 必填 id/type/variable/range/start/end；range是递增的有限两数，start/end引用同高度、从左到右的自由point。可选ticks（最多21个窗内唯一刻度）、color、font_size。数值映射全程线性，不能以挪动端点冒充参数变化。

`interval` 必填 id/type/axis/left/right/left_closed/right_closed，可选lane（轴的世界坐标竖直偏移）、label、empty_label、color、stroke_width。left>right为空；相等仅双闭为单点，半开或双开为空。空状态清除线与全部端帽，可显示empty_label。窗外有限端点只做延伸箭头，不在裁切边界伪造开闭端帽。无穷端永不开闭实点。

`set_parameter` 必填at/duration/type/parameter/value；同一ValueTracker线性变化同步派生所有引用区间端点，不能独立移动某个端点。动作结束写回精确目标值。

`merge_intervals` 必填at/duration/type/sources/target。2至8个可见源与隐藏目标必须引用同一axis；校验真实并集等于target，且必须连通。接点双开造成缺点，不允许合为单区间。最少0.4秒：80%时间只竖向平移至目标lane，20%淡出源（含内部端帽/旧标签）并淡入完整目标；结束只有target拥有可见区间。number_line刻度不属于区间端帽，允许保留。

检查支持 `interval_state`（interval/empty及可选left/right/left_closed/right_closed）、`interval_subset`（subset/superset/expected，空集包含为真且严格核对相等边界开闭）、`interval_union`（sources/target）。

导演约束：区分集合元素轴x与参数轴a；同轴多轨共用刻度。标题/题面分行可读，短区间两端帽必须可辨，必要整体放大轴但不制造非线性假刻度。端点公式用固定说明区，避免短区间标签挤压。空集口播到达之前完成收缩，字幕不替代图解。动作使用真实音频锚点，不能按字数估时。未人工看过的帧不能声明visual passed。


带源内置Text的merge_intervals采用同一duration内15%标签原位淡出、65%整体竖移、20%几何交接。提前锁定源更新器，不对Text子对象执行FadeOut；目标标签随目标交接出现。无源Text仍80%/20%。schema对可能有标签的源检查30/60fps每阶段至少2帧，runtime按实际fps与当前时钟再检查；不足明确拒绝，不能溢出总预算。

## 公式 token 与连续数字副本（可选扩展）

text 可选 formula_group，ID 为 [A-Za-z][A-Za-z0-9_]{0,63}。每一步可见的未分组 text 数量 + 不同 formula_group 数量不得超过6；每组可见项≤24、可见 text 总量≤48、总字符≤200。未分组旧分镜仍最多6项。分组只用于预算，不自动排版或整体变换；只将同一表达式的 token 分一组，不能将整屏随意合为一组绕过限制。

translate_copy 可选 style:"continuous"，只允许可见 text 来源→隐藏 text 目标：内容、font_size（默认28）、color（默认#FFFFFF）、max_width（默认9）一致。目标位置必须等于来源画面位置 + vector × world→plot 的 scale；位置与字形几何由运行时再验。使用 TransformFromCopy 全不透明平移，保留来源，无字形变换；期间暂停目标 updater，完成后恢复。多对副本共享 vector；位移不同则拆动作。省略style仍使用原淡入路径。

根号用现有 point+line；局部求值先hide旧局部再reveal新局部，题干及未变项保持，不调用formula整式换页。禁止为复制偷偷改变字号、内容、颜色或适配宽度。边界/碰撞/运动前中后画面仍须验收。音频未准备时只交付无时间的规划草案；不得将草案声称为可运行分镜。

## geometry-1.3：二次函数曲线与特征

`coordinate_axes` 使用章节 `world_bounds` 的数学坐标；可指定 `x_ticks`、`y_ticks`、`font_size`、`color`、`grid`。不随某一条曲线重新缩放。根与截距不在窗口内时保持不可见，不钳到窗口边缘。

`quadratic` 必填 `id/type/a/h/k`，表示 `y=a(x-h)^2+k`；可选 `color/stroke_width/dashed`。a、h、k 只接受有限数或 `{parameter,scale,offset}`；不执行字符串表达式。复用 `set_parameter` 连续改变参数，曲线按同一状态计算。a 必须全程非零；若正负开口需要切换，用两个非零函数的显示切换，不能跨过 a=0 仍称二次函数。

`quadratic_feature` 必填 `id/type/curve/kind`；kind 支持 `vertex/axis/roots/y_intercept/point`。point 还需 `x`（同样受限的有限数或仿射参数），每帧按 `(x,f(x))` 求值，不能以直线移动冒充曲线上运动。可选 `color/show_label/label/font_size/label_offset`；axis 无标签。标签偏移使用画面单位，数学点位置不受影响。特征不是旧 point 类型，不能用于旧线段的点引用。

曲线采用精确三次 Bezier 表示，并在世界坐标窗口解析裁剪；分离的两支不能错误连接，裁剪处不创建数学交点。roots 使用不同实根：Δ>0 两点，Δ=0 一点，Δ<0 零点。动态对象原子更换子对象，不能在根消失后遗留旧点。

`quadratic_state` 检查 curve，选填 `vertex/roots/y_intercept/coefficients/tolerance`，至少一个期望值；coefficients 为 `[a,b,c]`。`quadratic_point` 检查单点 feature 与 `value:[x,y]`。完整字段以实时 contract 为准。可复用示例 `examples/quadratic_motion.json` 的时间只是合成能力样例，不能替代用户实际音频。

导演约束：同组开口宽窄比较必须固定坐标尺度；平移必须保持 a 不变，从同一参考原图说明位移。y=x²+1 直接下移1只回到y=x²，不会到y=x²-1；上下各1的示例分别从原图副本开始。一般式/顶点式/交点式的恒等改写不改变图像。三种Δ状态可连续改变k，让根真实合并后消失。交点式须说明实根条件；数学结论按对应口播出现。

验收包括实际运动前中后、根的两/一/零状态、负开口、标签与坐标刻度关系、平移与裁剪。每条 set_parameter 增加中间帧抽取；仍须查看真实画面，自动抽样及单测不能代替本期媒体与视觉复核。

## geometry-1.4：扇形与弓形

`sector` 与 `circular_segment` 必填 `id/type/center/radius/start_angle/sweep_angle`；center引用point，半径有限且0<radius≤10000。角度均为度：从+x轴开始，start_angle可为任意有限值，sweep_angle为逆时针正向扫角，严格0<sweep_angle<360。拒绝NaN、无穷、零半径和退化扫角；与move_on_circle的弧度参数不同。

sector由圆弧和两条半径闭合；circular_segment由同一圆弧和端点弦闭合，扫角超过180度表示大弓形。可选color/stroke_width/dashed/fill_opacity，默认填充透明度0.35。原生Sector/Arc平滑曲边，不以粗多边形近似。reveal支持draw/fade，hide隐藏；move圆心point会连带平移区域，半径和相对角度不变；不存在remove动作或半径/角度参数动画。沿用普通translate_copy的既有生命周期，continuous仍只支持text；reflect_copy仍只支持point。

runtime快照curved_regions记录世界坐标圆心、弧端点、半径及area；θ为扫角弧度，扇形面积r²θ/2，弓形面积r²(θ−sinθ)/2，后者含大弓形。不是任意布尔区域相减，也未新增area check或表达式AST。

面积拆解用sector、已有polygon三角形、circular_segment和reveal/hide/move等动作组合；先确认阴影目标边界与块数，实际区域交接和三角形移动应可见，不以文字变化代替拆解。小于180度时可用扇形减圆心三角形解释；大于180度需按有向面积或补形解释，不能一律减去无向三角形面积。示例仅为合成能力规划；没有原音频先交稿，不编词时轴。


## 反比例函数与受约束动点（geometry-1.5）

声明 `{"id":"c","type":"reciprocal","k":2}` 绘制原生 y=k/x。k 与动点 x 接受有限非零数值，或既有严格 `{parameter,scale,offset}` 仿射标量；不接受表达式或 Python。对象支持 color、stroke_width、dashed、tolerance、branch。branch 可选 both（默认）、positive_x、negative_x，严格按数学x正负选支，与k符号或屏幕位置无关。逐支绘制用两个同k对象分别设positive_x/negative_x，再依次reveal(style:"draw")；示例见 examples/reciprocal_branches.json。branch只控制曲线显示，不改变on_reciprocal的函数定义或已有动点约束；规划时应让动点x与所显示分支一致。

动点复用 point：`{"id":"P","type":"point","derive":{"type":"on_reciprocal","curve":"c","x":{"parameter":"x","scale":1,"offset":0}}}`。使用 set_parameter 改变 x；现有 project、reflect、line、polygon 可引用 P 并逐帧联动。move 仍只允许自由点。k、x 动画始终非零且不能变号；换符号请用另一曲线或章节，不穿越渐近线。省略branch时两支都显示；选支不改变曲线与两坐标轴在数学上无交点的性质。

每支独立解析裁剪到 world_bounds，以三次 Hermite/Bézier 平滑细分；最大竖直近似误差 tolerance 默认 0.001 世界单位，可设 1e-8～0.05，超出 8192 段或浮点表示范围明确拒绝。控制点凸包限制在视窗与同一象限，绝不跨 x=0 连线。极小 k 的描边在有限像素下仍可能靠近或覆盖坐标轴；按画幅选可辨认比例，数学无交点不代表像素描边永不接触。

示例 examples/reciprocal_motion.json 包含正负 k 两章、同支动点、投影矩形、参数变更和 hide/reveal；可运行但合成能力测试不证明原音频同步。矩形面积为 |k|。曲线关于原点、y=x、y=-x 对称（两坐标轴不是其对称轴）。沿用既有 canvas/4K 设置，不为本能力变更全局画幅。


## 坐标轴数字标签偏移（可选 label_offsets）

`coordinate_axes.label_offsets` 是从 `origin` 或 `x:<数值>` / `y:<数值>` 到 `[dx,dy]` 的映射。轴键须对应同对象已声明的 `x_ticks` / `y_ticks`；数值采用普通十进制 canonical 写法：整数不带 `.0`，不带加号、前导零、尾随小数零或指数形式，负零归为 `0`。不能用显示文本的三位有效数字舍入值代替真实刻度值。零刻度仍不单独显示数字，原点 O 使用 `origin`。

每个 offset 是相对于真实刻度点/原点的完整二维画面单位偏移（覆盖默认值，不是叠加量），两分量必须有限且绝对值≤1.5，未知 key 拒绝。省略映射或某 key 时保留原默认：x 数字 `[0,-0.27]`、y 数字 `[-0.3,0]`、O `[-0.23,-0.25]`。不改变坐标轴、刻度位置、网格、函数或世界坐标；数字黑底与层级保留。标签在图窗外仍不凭空生成。设计时避开函数线、点名及其他标签，真实预览检查文字与背景框，不能通过删除全部背景或移动数学刻度来掩盖遮挡。


## Derived points on quadratics

Use `{"id":"Q","type":"point","derive":{"type":"on_quadratic","curve":"f","x":{"parameter":"t","scale":1,"offset":0}}}` for a reusable point on quadratic `f`. Exactly `type/curve/x` are allowed; x is finite numeric or the existing exact affine scalar. Coefficients a/h/k may also use affine parameters, with a nonzero throughout transitions. Change t using `set_parameter`; do not move a derived point directly. Multiple points can share t with different scale/offset, and existing project/intersect/line/polygon/circle/right_angle dependencies follow per frame. `quadratic_feature` remains a render object, not a point reference. Parameters/updates keep their existing +/-10000 bounds; world_bounds clips the graph, not the mathematical x-domain. No expression strings or arbitrary code. See `examples/quadratic_derived_points.json` for a synthetic fixture.


## 受约束旋转点（point.derive.rotate）

`{"id":"Q","type":"point","derive":{"type":"rotate","source":"P","center":"O","angle":{"parameter":"theta","scale":1,"offset":0}}}` 使用已有点 P、O；angle 是有限度数或严格的 parameter/scale/offset 仿射标量，正逆时针、负顺时针（不同于 move_on_circle 的弧度）。位置每帧为 center+R(angle)*(source-center)，源点、圆心移动时实时联动。静态角度也保留依赖；center 可等于 source，但不得形成循环。未知字段、表达式字符串、非有限值、无效点引用均拒绝。

用 set_parameter 改 theta；多个副本点共享角度和圆心，再用 line/polygon 引用副本点即可刚性旋转整条边或三角形，标签同步跟随。不要对派生点使用 move，也不要用直线插值冒充旋转；reveal 后旋转副本可保留原图。既有参数范围 [-10000,10000] 不变。合成样例 examples/rotation_points.json 只验证能力，不证明语音同步或 TTS。


## Single current chapter heading
Optional top-level `heading_mode` accepts `standard` (legacy default) or `chapter`. In chapter mode, the only top heading is the warm-yellow current chapter title. Repeating the same title across subscenes preserves it; changing titles transitions at the existing chapter boundary without adding time. The global spec title remains metadata. Existing problem lines remain optional.


## 圆锥曲线与切向投影（capability 1.6.0）

`type:conic` 必填 `id,kind,center`。`kind` 为 ellipse/hyperbola/parabola；center 是固定 `[x,y]`，不是点 ID，坐标绝对值≤10000。ellipse/hyperbola 必填固定正数 a,b（1e-6..10000）；parabola 仅填非零有符号 p（绝对值同范围），局部方程 y²=4px。暂不支持旋转和形状参数动画。其他形状的字段严格拒绝。

hyperbola 必填固定 branch=positive_x/negative_x/both；显示两支时独立绘制，不连线。可选 color/stroke_width/dashed/tolerance；tolerance 是世界坐标下折线与真实曲线的误差上限，默认 .001，范围 1e-8..05，8192 段预算，超限拒绝。先解析求视口边界对应的参数区间，再逐区间采样；视口不限制数学动点，离屏点仍按真实方程计算。

点 `derive={type:on_conic,curve:id,t:scalar}`；hyperbola 动点额外必填单支 branch=positive_x/negative_x，必须属于曲线显示支路。ellipse/parabola 禁止 branch。scalar 仅为有限数或严格 `{parameter,scale,offset}`，章节须声明参数，无表达式执行。相对 center，ellipse P=(a cos t,b sin t)，t 为弧度；hyperbola P=(sign*a cosh t,b sinh t)；parabola P=(pt²,2pt)。动点 t 的绝对值上限分别为 10000/12/10000；整条可见曲线的裁剪不受此动点预算截断。

切向端点 `derive={type:conic_tangent,source:P,scale:scalar}`，source 必须直接引用 on_conic 点，计算 P+scale*P′(t)，scale 绝对值≤10000，允许负数及零。它不是单位切向量；不会自动乘 dt/dtime。需要表示实际速度时，由分镜显式设置 scale，并遵守下述播放时间方向规则；固定正 scale 仅表示沿参数增加方向的切向示意，不能自动视为实际速度。set_parameter 逐帧更新动点、切向端点及下游投影、旋转、线和标签。参数过渡沿用原审计动作，snapshot 包含 conics 和实际 end_state；新增模块由现有 engine_hash 的 geometry/*.py 自动纳入身份。

线可写 `{id:v,type:line,a:P,b:T,kind:segment,arrow:true}`，arrow 必须为布尔值，仅允许 segment；零长度稳定为空，后续参数变化可重新出现。超出视口的线段先裁剪，箭头在裁剪端点表示方向，不应把它解释为真实端点仍在屏内。draw reveal 支持曲线和箭头。

投影复用 `{type:project,source:T,line:[P,A]}`，得到投影端点 H；向量 PH 的符号随切向变化，H=P 时箭头为空。复用 `{type:rotate,source:T,center:P,angle:180}` 得反向切向端点；angle=90 得法向端点。内角射线应旋转正确的源端点。两条非正交轴上的正交投影通常不能相加还原原向量，不得当作向量分解。


### 参数切向与实际速度的导演规则

以播放时间 τ 为自变量，实际速度 V=dP/dτ=P′(t)·dt/dτ。讲解“速度方向”时，切向箭头的有向系数必须与 dt/dτ 同号；t 递减时不能仍用固定正 scale 的参数切向箭头冒充回程速度。t 若由 affine scalar 给出，应按实际 t 的变化判断符号，而不是只看被更新参数的增减。若箭头长度表示速度大小，还须按 dt/dτ 的大小及明确的统一显示倍率设置，不能仅保证方向。

优先安排单调一程运动，在需要验算的参数锚点落定，避免为重复演示增加未解释的回程。确需回程时，同步切向 scale 符号及全部依赖投影、方向标签；已有 project 应引用同一切向端点，不能保留去程投影。当前动作串行，不能假设两个 set_parameter 自动同时执行：若无法在转向处保持速度语义一致，应先隐藏速度及投影箭头，明确标为“复位”，完成参数复位和符号设置后再开始下一程。

冻结静态验算帧只表示所选位置的参数切向，或明确标注“冻结运动瞬间的速度示意”；不能宣称画面中的静止点仍具有非零真实速度。若按当前播放时间解释，停留时 dt/dτ=0，真实速度为零；不能把静态正 scale 当作静止时的实测速度。恢复运动时重新核对方向及投影符号。

验收须检查去程、转向/复位、回程及静态验算帧的叙述与箭头语义；坐标、切线导数或端态验算正确，并不自动证明实际速度方向正确。本规则是分镜/文档约束，不改变 conic_tangent 的引擎定义，也不赋予其自动感知播放速度的能力。

通用例子：`examples/conic_motion.json`。针对性测试：`tests/test_conic.py`；真实无声验收入口：`tests/render_conic_smoke.py --output <包外目录>`，不代替本期真实音频、动作锚点及最终画面验收。
# Provider WordBoundary 音轨验证（edge-word-evidence-1）

`geometry.pipeline.validate_alignment(..., ffmpeg=trusted_runtime_path)` 现在接受显式
`source=edge_tts_word_boundary`。这是独立于 local Whisper 的来源分支，不把 provider
事件标成 Whisper，不改变外部录音的原有 Whisper 校验。只有同次生成音频的原始
WordBoundary 证据可用；另一条同文本、同长度或同音色的录音不能复用这些时间。

alignment 包含 `source_audio_sha256`、`canonical_narration_sha256`、实际解码 `duration`、
`provider_manifest:{path,sha256}` 和完整 `anchors`。manifest 版本为
`edge-word-evidence-1`，包含：

- `narration`、`concat_audio`、`final_audio` 三个 `{path,sha256}` 文件引用；
  canonical hash；可信调用方 FFmpeg 的 `ffmpeg_sha256`；
  `parameters:{voice,rate,pitch,volume,boundary:"WordBoundary"}`；
  `transform:{kind:"atempo",factor}`（当前单次 factor ∈[0.5,2]）。
- `clip_count` 与顺序 `clips`；每段唯一 `id`、锁稿 UTF-8 原字节半开范围
  `source_byte_start/end`、`concat_start_sample`，以及 `text/encoded_audio/pcm/raw_events/sdk_events`
  文件引用。`pcm_info` 包含 PCM SHA256、samples、sample_rate、channels。
- 每段 `generation` 保存原请求身份、同一组参数和 text/encoded_audio/raw_events/sdk_events
  的 SHA256。它是本地捕获来源声明及身份链，不是服务端签名证明。

raw JSONL 每行保存 `raw_utf8` 服务 Metadata JSON 和 `sdk_offset_compensation_ticks`。
逐个原始 `Metadata[].Type=WordBoundary` 与 SDK JSONL 的 text/offset/duration 核对；
当前版本明确拒绝非零内部补偿、非 WordBoundary，以及有解码器 signaled padding/skip 的
情况，不猜测补偿或声学延迟。允许未发音标点／空白无词时间；汉字、数字、字母和数学运算符
必须由原词精确覆盖。无法支持的字符或事件必须保留为错误，不能补造时间。

验证实际重解码每段 encoded_audio 对比缓存 signed-16 PCM，按样本顺序哈希验证无插入的
concat PCM，再用可信运行环境 FFmpeg 重放唯一整轨 atempo，比对 final PCM 与实际长度。
临时 PCM 遵守调用进程 TEMP/TMP，不覆盖输入；不会执行附件提供的 shell 命令或下载工具。

anchor ID 为 `clip_id:raw_line:raw_event`（索引从0开始），保留 text、原 Offset/Duration ticks、
clip_id、raw_line/raw_event、source_char_start/end，以及 canonical 稿的 script_char_start/end。
source/time_source 都是 `edge_tts_word_boundary`。start/end 必须等于
`(concat_start_sample/sample_rate + original_ticks/1e7)/factor`；词保持完整，不给词内字符造时间。
这只是原始 provider 时钟的名义 tempo 映射，atempo 局部波形并非线性逐样本映射；仍须独立听审／
声学抽样和有声 preview QA，不能声明逐样本同步或自动 visual passed。

provider action audit 也必须显式声明 source；每项提供 canonical 稿精确
`script_char_start/end`、`anchor_text` 和全部相交原词 `anchor_ids`，不允许缺数学词、换词、
乱序或拿无关附近词补证据。动作起点须在对应完整词包络内，动作结束最多容许一帧量化误差；
不能用任意 reviewed_by/reason 覆盖越界。Whisper 的旧来源／空 token／review 规则保持不变。

离线回归：`tests/test_provider_word_alignment.py`（可信 FFmpeg/FFprobe 在 PATH；TEMP/TMP 指向
选定工作盘）。合成 fixture 只测合同及拒绝路径，不能当作真实 provider 认证或本期同步通过。
源码变化会改变 engine_hash，必须建立新 preview identity，旧 preview 不可放行新 final。



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
