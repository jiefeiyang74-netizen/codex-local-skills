# geometry-1.0 director

图片题转分镜前，先依据 references/narration-preparation.md 的核图规则确认目标区域块数、边界及对应约束；可见填充须与已验算的目标区域一致，不能用整圆填充或示意多边形冒充契约未支持的精确扇形、弓形或区域差。先检查实时契约，只在明确支持时规划相应对象与动作；没有原音频时只交无时间的视觉规划，不生成虚构 at/duration。

先读取实时 contract.geometry、references/geometry.md 和真实 analyze 输出，再写纯 JSON。不得输出 Python、按字数分配时间、借 generic4.3 假称支持。保持完整原稿和实际音频时长；canvas 由项目明确指定，不把单次偏好改成全局偏好。

## 图形语义规划

对重要概念和推导，先判断什么数量关系需要看见，再选真实数量模型，例如长宽与面积、数轴位置与区间、整体与等分；不能只把公式出现或高亮当作图形解释。在项目现有规划记录中简述变量与图形量的对应、适用条件、守恒量（若无则说明变化规律），以及变换前后各表示什么；这些说明不新增 schema 字段。

模型适合且口播顺序允许时，先让图形发生有数学意义的分割、移动、比较或重组，再把观察对应到算式。运动全过程须保持所声明的约束；取等或极值须对应可达到的图形状态。单次数值演示只能说明该实例，不能替代一般结论的符号推导或覆盖适用范围的数学论证。

不要求每句配图，不用装饰图或无关运动充数。自然无法几何化、图形会误导或增加理解负担时，保留清晰代数并在规划中说明选择。图形服务锁定稿与音频，不为配图擅改措辞、顺序、时长或提前显示答案；节奏受限时缩减模型复杂度。

## 数学语义短句与视线引导

以承担数学信息的短句为单位规划，不机械逐字闪烁，也不要求问候或连接词都有动画。指认点、边、角、相等关系、变换及结论时，先让绘图区出现对应变化，再按同一解释顺序展开卡片推导；卡片变字不能代替左图（竖版为上图）的语义动作。动作服从锁定稿及实际音频，不改稿凑动画、不借后文提前显示答案。

在项目现有语义规划记录中为每个这类短句登记：spoken anchor（原文片段、句内出现序号及真实 token 依据）、object IDs（含被比较对象）、focus group（一个主要焦点，比较对象可成一组）、appearance（何时首次出现及何种可见变化）、hold（理解关系所需的可读停留）、restore（何时恢复临时强调、保留哪些结构标记），并映射到具体动作索引。以上是规划记录项，不是新增 storyboard/action 字段；动作审计仍使用实时契约字段。无真实音频时仅规划语义次序，不伪造时间。

| 口播语义 | 对应绘图区动作与边界 |
| --- | --- |
| 点或端点指认 | 指向对应可见 point 及可读点名；短脉冲可用 highlight，不移动点或缩放字形制造注意力。小点在实际峰值帧中色差不足时，可用现有 circle 的空心小圆环作短暂点名提示，在原声学时窗内 reveal、短停留并 hide 退出；圆环仅引导注意，不作为数学构造圆，不残留、不挤动后文，须核对实际出现及消失帧。 |
| 边、延长线或辅助线 | 新线使用 reveal(style:"draw")，端点定义决定方向；已有边使用契约支持的强调，不反复重画或 reveal 隐藏对象来冒充强调。 |
| 角及角关系 | 先识别顶点、两射线和内外角，再显示/强调相应 angle、right_angle 或有数学依据的 sector；不得用整片三角形高亮代替指定角。 |
| 相等、全等及对应 | 两边或两角作为同一 focus group 对比，条件成立后显示 ticks/角标；结构性标记可保留，临时强调需恢复，不能把颜色本身当数学证明。 |
| 旋转、平移、缩放等变换 | 使用契约对应的派生点及 set_parameter、translate_copy 等真实动作；保留来源与对应关系，验证中间态，不能只闪烁终态或移动推导卡。 |
| 推理结论 | 先聚焦支撑结论的对象及关系，再在实际结论声学窗显示卡片完整式；保持足够稳定阅读帧，不提前亮出答案。 |

focus 对象必须是口播语义对应的最小完整组，同一时段只保留一个主要焦点；相等关系可同时选两个对象成组，比较也可含多个必要 IDs，但它们须共同服务当前关系，不允许给整张图套大框充数。已隐藏或尚未引入的对象不得因聚焦、强调或恢复而变可见；先按口播 reveal，再使用需要可见对象的动作。动作不可超出当前时窗或重叠预算；相邻语义短句过密时减少装饰和过渡，不靠拖长音频或删去核心对应关系解决。

强调必须落为实时 contract 支持且运行器执行的动作。geometry-1.9.2 的 `highlight` 可选 `style:"emphasis"`，同一 `ids` 组执行颜色与线宽脉冲（峰值线宽1.45倍），不缩放坐标/字形，不改透明度、遮罩和层位，结束恢复原样式；省略 style 保持旧颜色脉冲行为。paper_guided 的新脉冲峰值深绿 #244F46，classic_black 的该可选动作峰值为 #FFD166；不能承诺它自动保留比较对象各自红蓝色。经典黑底分镜复用语义规则时保留既有色体系与默认 highlight，不因新规则强制采用此 opt-in 脉冲，更不套用 paper 的颜色或卡片层次。只选择已可见 IDs；隐藏引用被 schema 拒绝，运行器也防御性跳过，不由本动作揭示。需要同时强调结构刻痕时将其 ID 显式放入同组。

例如 `{"type":"highlight","style":"emphasis","ids":["edge_a","edge_b"],"at":12.3,"duration":0.6}` 表示一个比较组；这里的时间仅为字段示例，生产时须替换为本句真实音频锚点和可用时窗。此动作在 duration 内强调并回落，不是持续样式开关；随后 `hold` 保持的是恢复后的场景，不是峰值。需要较长读图时，按声学窗安排合适脉冲时长和恢复后停留，并让已揭示的结构标记维持关系。

`focus` 是框选，`focus(ids:[])` 清除框，不能冒充对边/角的直接强调或底图压暗。不要添加未声明的 emphasis、opacity、z_index、appearance 或 restore 字段；也不存在可随意调用的独立 restore 动作。三层外观使用已支持的对象样式、显示顺序及主题执行；缺能力按 Skill 的已授权扩展流程处理，不能把导演文字当执行能力。逐项核对强调后的可见性、颜色、线宽、填充和焦点状态，结构标记保留与临时强调恢复分别验收。

### 题设随口播建立

念题设时按口播顺序逐条在绘图区建立所念对象：念到点就出现该点及点名，念到线段、函数图像或区域就在当时画出，念到数值或相等、垂直、平行等关系就在当时标上数值或关系标记；后文再提到已出现对象时，用上表方式在其声学窗内突出。不要在第一帧把全部题设一次画满让观众自己找点。题图必须先完整出现时（如复杂原题图），在规划记录中说明理由，并仍按口播逐项指认。规划记录逐条登记条件原文、对象 IDs 和出现/突出动作；沿用实时契约已有的 reveal/highlight 等动作，不新增字段。

## 动作与状态

同一句口播描述两个对象的关联增减时，先明确每个指代所对应的对象及被描述的量，并确定同一连续动作路径上两者各自的单调方向与适用区间；拆成多个动作也须沿该路径接续，不能在后半句反向或复位，导致当前指代对象的变化与动词相反。沿用动作前、中、后及衔接处的检查，逐动作核对被叙述对象的量值变化方向；涉及等量增减时，还须核对同一段运动内两者的变化量大小相等、符号相反。参数单调不代表被叙述量单调，须检查实际对象量；数学等式或守恒关系成立不能替代上述语义核对。

只用 contract 声明的对象、动作、checks。点定义隐藏但参与计算；reveal 决定可见性。所有 at 是绝对音频秒，duration 显式且不可重叠，章首预算留给标题过渡。逐条在 action_audit_path 附件登记真实 token 锚点。没有可靠锚点时明确待听审，不伪造精度。

重复的“等于”“这里”“取一份”等锚词，必须按所在句、局部上下文和句内出现顺序消歧。例如同一句第二次“等于”对应第二个局部事件，不能任选同名 token，更不能借下一句的同名词触发。逐条核对原稿句段与原始 ASR segment/token；字符识别有差异时，用对应局部中文词组定位，审计保留原 token、所在句/segment、出现顺序及语义判断说明，并明确字母等识别不确定性，不以数学推断改写 ASR。若仍不能确认，标为待听审，不自动换到别句。token/附件哈希绑定只证明引用数据一致，不能单独判定语义锚点正确或音画同步通过；同步仍需结合实际音频、动作及画面审阅。

用 derive/constrain 描述反射、投影、平移和实时求交；被约束点不可直接 move，移动自由依赖点。不要用两个端点线性插值冒充沿动态直线交点运动。checks 用真实长度/共线/垂直/射线关系，失败修 JSON 或明确能力缺口。

当实时 contract 声明圆与圆周动作时（自 geometry-1.1 引入，后续兼容），使用 circle(center,radius) 画圆，使用 move_on_circle(point,circle,angle) 做真实圆周运动；angle 为有符号弧度增量，动点必须从圆周上开始且为自由点，圆心不能依赖该动点。投影继续用 derive.project，由动点实时带动。不能把沿弦的 move 或折线片段当作沿圆运动。非退化三角形的圆周极限位置若导致三点共线，动点只趋近端点，最终区间排除端点。

problem 最多两行，formula.lines 最多三行；独立 text/formula_group 遵循实时 contract 的可见项与字符预算，不套用三行上限。使用 Text 短语并明确拆等式。图形、公式、标题互不遮挡，不添加底部旁白字幕。point 可用 font_size 指定标签字号；文字位置按 canvas 对应画面安全边界校验，字符数和 max_width 仅粗筛，不代表视觉通过。所需模型缺执行能力时，按 SKILL.md 的已有授权规则处理扩展，验证后再使用更新后的 contract；未获覆盖授权或尚未实现时标 unsupported 并暂停依赖动作，不用静态幻灯片替代核心图形行动，也不以临时用户代码绕过契约。

分词公式及长中文说明按同字体、字号的实际 Pango `Text.width/height` 排版，不按字符长度估算。可用 `geometry.glyph_layout.token_row` 测量行布局、`validate_text_state` 检查当前可见稳态的字形 bbox 与调用方指定的语义容器（标题、条件、图形、公式区域）。这是可选创作工具，不增加 schema 字段或自动移动运行中的对象。每次文字替换须同时考虑随后揭示的同排 token；独立小数点按数字基线定位，不能垂直居中成乘点。continuous copy 的源/目标保持相同字形和严格平移关系。测量不能替代真实运动前中后及最终稳态的像素验收。

标签避让须检查反射前、中、后及最优位置，不能只检查起点；带下标的点名不得挤在同向线或等长 ticks 上。进入辅助直角三角形证明时，在切换动作中用 hide（FadeOut）收起不再需要的旧角标、基线、原路线和点名，避免新角度数值压在旧基线上。隐藏只改变可见性，仍被 derive 引用的数学对象保留定义，不随意删除依赖。

小角度或角平分线穿过内置角度数值时，保留不设 label 的 angle 角弧，用独立 text 把数值放到外侧，并用已有细 line 作引线（leader，不新增对象类型或字段）；角弧、数值、引线放在同一 reveal/hide 动作中同步揭示和隐藏。不能把数值硬塞进窄夹角，也不能为避让歪曲真实几何夹角。距离数字同样要检查最终状态及运动途经状态，避免线段穿过文字。

公式不仅检查稳态，还须核对更换中帧：同位置旧式完全退场后新式再出现，新旧字形不得重叠；内容改变由动画完成，沿用原动作预算，不增加总时长。互斥解集或答案须检查从淡入完成到淡出开始的稳定可读窗口，不能仅在过渡中闪现；时间不足优先缩短过渡，不延长原音频。

公式、条件和图形在过渡过程中也须一致。待满足的方程须明确标为目标条件，不能当作运动中已成立的关系；到达满足条件的状态后再显示成立结论。先列出每个状态的参数、可见对象与成立结论；参数变化期间用同时适用的通式，或暂时收起旧结论，等目标状态到达再出现新结论。静态 problem 也要覆盖全章的示例，不能让固定正系数题面陪着负开口图像。正负开口、根数、区间空实等条件交接，先清掉已经不成立的旧结论；不要只检查终态。候选或题面替换时，先按依赖关系让旧交叉积、验算及结论退场，再换输入，按新输入重新计算后显示对应结果；即使旧等式本身仍正确，也不能作为新输入的当前验算，恢复原候选同样遵守此次序。

动态标签只保留解释所需的信息：运动中密集跳动的小数可改为固定符号说明或到位后坐标。调整标签偏移不改数学点。逐个核对点名及动态标签与邻接曲线、斜线、辅助线的关系，不能只查第一个点名。标签背景遮罩虽可防穿字，也会截断邻线；优先调整标签偏移，再从当前真实 MP4 查看原生分辨率局部及运动前中后，确认线条连续，不能以遮罩掩盖布局冲突。

长讲解按知识点拆 chapter，在项目中记录各章目标、对应原稿范围、公式与实际动作。章节不照搬录音分段；秒数来自实际音频，标题过渡占现有预算，不增加停顿。复用同一几何状态或参考曲线说明变化，结论按口播出现。

多方法证明涉及章节交接时，在项目规划或复核记录中列出各章旧辅助线、角标和点名的保留/隐藏/再出现时序，隐藏仍被引用的对象时保留数学定义。涉及多处取等条件时，逐项标明条件对应的可视化状态及实际音频锚点；仅在所有必要条件同时满足且对应讲解到达时显示取等或最优结论，避免沿用上一方法的旧标记造成误读。

preview 本地检查通过后，逐一检查角度弧、角度数值、垂直符号、辅助线和点名之间的遮挡；文字在 bounds 内不等于排版可读。必须查看每个答案完成后的稳定画面、每章末尾稳定帧，以及重要运动前、中、后。自动通用抽样可能漏掉这些时刻，审阅者应从 manifest 指向的真实 MP4 补帧并按可辨认文字的尺寸查看，记录时间、帧文件与审阅结论；小型 contact sheet 仅作索引，绝不能仅凭小拼图判 visual passed。结合实际运动和音频审阅后，才能登记人工证据导出 final。


## geometry-1.2：参数数轴与区间（兼容1.1圆）

chapter 可选 `parameters`：最多16个合法id到有限数值的映射。端点只接受有限数、开端 `"-inf"`/`"+inf"`，或严格 `{ "parameter": "a", "scale": 2, "offset": 1 }` 仿射对象；不接受表达式代码、不使用eval。

`number_line` 必填 id/type/variable/range/start/end；range是递增的有限两数，start/end引用同高度、从左到右的自由point。可选ticks（最多21个窗内唯一刻度）、color、font_size。数值映射全程线性，不能以挪动端点冒充参数变化。

`interval` 必填 id/type/axis/left/right/left_closed/right_closed，可选lane（轴的世界坐标竖直偏移）、label、empty_label、color、stroke_width。left>right为空；相等仅双闭为单点，半开或双开为空。空状态清除线与全部端帽，可显示empty_label。窗外有限端点只做延伸箭头，不在裁切边界伪造开闭端帽。无穷端永不开闭实点。

`set_parameter` 必填at/duration/type/parameter/value；同一ValueTracker线性变化同步派生所有引用区间端点，不能独立移动某个端点。动作结束写回精确目标值。

`merge_intervals` 必填at/duration/type/sources/target。2至8个可见源与隐藏目标必须引用同一axis；校验真实并集等于target，且必须连通。接点双开造成缺点，不允许合为单区间。最少0.4秒：80%时间只竖向平移至目标lane，20%淡出源（含内部端帽/旧标签）并淡入完整目标；结束只有target拥有可见区间。number_line刻度不属于区间端帽，允许保留。

检查支持 `interval_state`（interval/empty及可选left/right/left_closed/right_closed）、`interval_subset`（subset/superset/expected，空集包含为真且严格核对相等边界开闭）、`interval_union`（sources/target）。

导演约束：区分集合元素轴x与参数轴a；同轴多轨共用刻度。数轴投影/对齐辅助线须依据实际数值到画面的映射及刻度文字、端点符号的实际边界计算分段，在文字与端帽处留出空隙；不能穿过数字，也不能让辅助线穿过空心端点而使其看似实心。区间合并或移动须检查整条运动路径与刻度、文本的碰撞，不能只检查终态；优先将各源区间安排在目标轴同侧的空白区域、保持不同lane，使其移向目标轴时不穿越刻度文字，必要时提前平滑避让刻度及相关文字，且不得让刻度值、端点开闭或其他语义信息凭空消失。标题/题面分行可读，短区间两端帽必须可辨，必要整体放大轴但不制造非线性假刻度。端点公式用固定说明区，避免短区间标签挤压。空集口播到达之前完成收缩，字幕不替代图解。动作使用真实音频锚点，不能按字数估时。未人工看过的帧不能声明visual passed。


带源内置Text的merge_intervals采用同一duration内15%标签原位淡出、65%整体竖移、20%几何交接。提前锁定源更新器，不对Text子对象执行FadeOut；目标标签随目标交接出现。无源Text仍80%/20%。schema对可能有标签的源检查30/60fps每阶段至少2帧，runtime按实际fps与当前时钟再检查；不足明确拒绝，不能溢出总预算。

## 公式 token 与连续数字副本（可选扩展）

同一公式拆成 text tokens 时，初始布局及全部 text_transform 的起点、过渡和终点均须保持整体可读：按实际字形宽度、基线及运算符/括号的自然间距安排位置，不得按画幅宽度平均撒开。改字后重新核对间距；沿用既有先淡出后淡入及路径避让规则，不要求淡出中仍显示旧字。

红色虚线 focus 使用所选对象的 union 外接矩形；若矩形跨越不参与比较的常数或符号，须先以 text_transform 在保持等价关系的前提下动画重排参与项，再聚焦，或按现有单框能力依次分别聚焦。不得用包入无关项的 union 矩形暗示这些项也参与比较；重排前先清除可能误导的旧框。

上述布局与聚焦须在真实 preview 的初始、每次变换后稳定帧及过渡前/中/后审查，核对整式阅读顺序、间距、遮挡和框选语义；仅静态 bounds/碰撞测试通过不能判定视觉通过，证据沿用前述真实帧记录要求。

text 可选 formula_group，ID 为 [A-Za-z][A-Za-z0-9_]{0,63}。每一步可见的未分组 text 数量 + 不同 formula_group 数量不得超过6；每组可见项≤24、可见 text 总量≤48、总字符≤200。未分组旧分镜仍最多6项。分组只用于预算，不自动排版或整体变换；只将同一表达式的 token 分一组，不能将整屏随意合为一组绕过限制。

translate_copy 可选 style:"continuous"，只允许可见 text 来源→隐藏 text 目标：内容、font_size（默认28）、color（默认#FFFFFF）、max_width（默认9）一致。目标位置必须等于来源画面位置 + vector × world→plot 的 scale；位置与字形几何由运行时再验。使用 TransformFromCopy 全不透明平移，保留来源，无字形变换；期间暂停目标 updater，完成后恢复。多对副本共享 vector；位移不同则拆动作。省略style仍使用原淡入路径。

根号用现有 point+line；局部求值先hide旧局部再reveal新局部，题干及未变项保持，不调用formula整式换页。禁止为复制偷偷改变字号、内容、颜色或适配宽度。边界/碰撞/运动前中后画面仍须验收。音频未准备时只交付无时间的规划草案；不得将草案声称为可运行分镜。

## geometry-1.3：二次函数曲线与特征

凡函数曲线因显示窗口而被截取（含二次函数、反比例函数），须在画面标明“局部图像”和所讲函数的定义域，并区分题设限制与显示范围；裁剪边缘不是定义域端点，不加伪端点标记。真实 preview 须检查稳定帧及曲线/窗口变化的过渡帧，确认标注持续对应当前函数，裁剪端不会被误读为端点；不能只凭静态边界测试验收。

`coordinate_axes` 使用章节 `world_bounds` 的数学坐标；可指定 `x_ticks`、`y_ticks`、`font_size`、`color`、`grid`。不随某一条曲线重新缩放。根与截距不在窗口内时保持不可见，不钳到窗口边缘。

`quadratic` 必填 `id/type/a/h/k`，表示 `y=a(x-h)^2+k`；可选 `color/stroke_width/dashed`。a、h、k 只接受有限数或 `{parameter,scale,offset}`；不执行字符串表达式。复用 `set_parameter` 连续改变参数，曲线按同一状态计算。a 必须全程非零；若正负开口需要切换，用两个非零函数的显示切换，不能跨过 a=0 仍称二次函数。

`quadratic_feature` 必填 `id/type/curve/kind`；kind 支持 `vertex/axis/roots/y_intercept/point`。point 还需 `x`（同样受限的有限数或仿射参数），每帧按 `(x,f(x))` 求值，不能以直线移动冒充曲线上运动。可选 `color/show_label/label/font_size/label_offset`；axis 无标签。标签偏移使用画面单位，数学点位置不受影响。特征不是旧 point 类型，不能用于旧线段的点引用。

曲线采用精确三次 Bezier 表示，并在世界坐标窗口解析裁剪；分离的两支不能错误连接，裁剪处不创建数学交点。roots 使用不同实根：Δ>0 两点，Δ=0 一点，Δ<0 零点。动态对象原子更换子对象，不能在根消失后遗留旧点。

`quadratic_state` 检查 curve，选填 `vertex/roots/y_intercept/coefficients/tolerance`，至少一个期望值；coefficients 为 `[a,b,c]`。`quadratic_point` 检查单点 feature 与 `value:[x,y]`。完整字段以实时 contract 为准。可复用示例 `examples/quadratic_motion.json` 的时间只是合成能力样例，不能替代用户实际音频。

导演约束：同组开口宽窄比较必须固定坐标尺度；平移必须保持 a 不变，从同一参考原图说明位移。y=x²+1 直接下移1只回到y=x²，不会到y=x²-1；上下各1的示例分别从原图副本开始。一般式/顶点式/交点式的恒等改写不改变图像。三种Δ状态可连续改变k，让根真实合并后消失。交点式须说明实根条件；数学结论按对应口播出现。

验收包括实际运动前中后、根的两/一/零状态、负开口、标签与坐标刻度关系、平移与裁剪。每条 set_parameter 增加中间帧抽取；仍须查看真实画面，自动抽样及单测不能代替本期媒体与视觉复核。

## geometry-1.4：扇形与弓形

`sector` 与 `circular_segment` 必填 `id/type/center/radius/start_angle/sweep_angle`；center引用point，半径有限且0<radius≤10000。角度均为度：从+x轴开始，start_angle可为任意有限值，sweep_angle为逆时针扫角。sector（capability 1.7.0）允许0≤sweep_angle≤360，0为空、360为完整圆盘；radius/start_angle/sweep_angle支持有限数或严格{parameter,scale,offset}，用set_parameter连续驱动，弧与端点逐帧更新。circular_segment保持固定数值且严格0<sweep_angle<360。拒绝NaN、无穷、零半径和越界扫角；与move_on_circle的弧度参数不同。

sector由圆弧和两条半径闭合；circular_segment由同一圆弧和端点弦闭合，扫角超过180度表示大弓形。可选color/stroke_width/dashed/fill_opacity，默认填充透明度0.35。原生Sector/Arc平滑曲边，不以粗多边形近似。reveal支持draw/fade，hide隐藏；move圆心point会连带平移区域，半径和相对角度不变；不存在remove动作；sector参数动画按上述set_parameter执行。沿用普通translate_copy的既有生命周期，continuous仍只支持text；reflect_copy仍只支持point。

runtime快照curved_regions记录世界坐标圆心、弧端点、半径及area；θ为扫角弧度，扇形面积r²θ/2，弓形面积r²(θ−sinθ)/2，后者含大弓形。不是任意布尔区域相减，也未新增area check或表达式AST。

面积拆解用sector、已有polygon三角形、circular_segment和reveal/hide/move等动作组合；先确认阴影目标边界与块数，实际区域交接和三角形移动应可见，不以文字变化代替拆解。小于180度时可用扇形减圆心三角形解释；大于180度需按有向面积或补形解释，不能一律减去无向三角形面积。示例仅为合成能力规划；没有原音频先交稿，不编词时轴。


## 反比例函数与受约束动点（geometry-1.5）

声明 `{"id":"c","type":"reciprocal","k":2}` 绘制原生 y=k/x。k 与动点 x 接受有限非零数值，或既有严格 `{parameter,scale,offset}` 仿射标量；不接受表达式或 Python。对象支持 color、stroke_width、dashed、tolerance、branch。branch 可选 both（默认）、positive_x、negative_x，严格按数学x正负选支，与k符号或屏幕位置无关。逐支绘制用两个同k对象分别设positive_x/negative_x，再依次reveal(style:"draw")；示例见 examples/reciprocal_branches.json。branch只控制曲线显示，不改变on_reciprocal的函数定义或已有动点约束；规划时应让动点x与所显示分支一致。

动点复用 point：`{"id":"P","type":"point","derive":{"type":"on_reciprocal","curve":"c","x":{"parameter":"x","scale":1,"offset":0}}}`。使用 set_parameter 改变 x；现有 project、reflect、line、polygon 可引用 P 并逐帧联动。move 仍只允许自由点。k、x 动画始终非零且不能变号；换符号请用另一曲线或章节，不穿越渐近线。省略branch时两支都显示；选支不改变曲线与两坐标轴在数学上无交点的性质。

每支独立解析裁剪到 world_bounds，以三次 Hermite/Bézier 平滑细分；最大竖直近似误差 tolerance 默认 0.001 世界单位，可设 1e-8～0.05，超出 8192 段或浮点表示范围明确拒绝。控制点凸包限制在视窗与同一象限，绝不跨 x=0 连线。极小 k 的描边在有限像素下仍可能靠近或覆盖坐标轴；按画幅选可辨认比例，数学无交点不代表像素描边永不接触。

示例 examples/reciprocal_motion.json 包含正负 k 两章、同支动点、投影矩形、参数变更和 hide/reveal；可运行但合成能力测试不证明原音频同步。矩形面积为 |k|。曲线关于原点、y=x、y=-x 对称（两坐标轴不是其对称轴）。沿用既有 canvas/4K 设置，不为本能力变更全局画幅。


坐标轴刻度数字（不是点名）需要避线时，使用 `coordinate_axes.label_offsets`，key 为对应已声明刻度的 canonical `x:<数值>` / `y:<数值>` 或 `origin`。offset 是相对于真实刻度点/原点的完整画面单位位移，两分量有限且各≤1.5绝对值；不叠加默认偏移，不改世界坐标/轴/刻度。零刻度统一用 `origin` 控制 O。优先垂直于对应轴避让（x 刻度上下、y 刻度左右），避免大幅沿轴移动数字造成数值位置误读；原点 O 保持紧邻原点，必须沿轴错位时用清晰的视觉关联标明所属刻度或原点。保留与所选主题底色一致的数字遮罩，按线和标签的实际位置选择偏移并在真实帧验收；不要把本题数值写入通用实现。

避让范围包括坐标刻度数字、原点 O 及点名，不只字母标签；固定偏移必须覆盖相关运动路径。密集动态场景可仅保留必要刻度，但不得让标签遮罩截断邻线；静态无碰撞不能代替运动过程抽帧验收。


## Derived points on quadratics

Use `{"id":"Q","type":"point","derive":{"type":"on_quadratic","curve":"f","x":{"parameter":"t","scale":1,"offset":0}}}` for a reusable point on quadratic `f`. Exactly `type/curve/x` are allowed; x is finite numeric or the existing exact affine scalar. Coefficients a/h/k may also use affine parameters, with a nonzero throughout transitions. Change t using `set_parameter`; do not move a derived point directly. Multiple points can share t with different scale/offset, and existing project/intersect/line/polygon/circle/right_angle dependencies follow per frame. `quadratic_feature` remains a render object, not a point reference. Parameters/updates keep their existing +/-10000 bounds; world_bounds clips the graph, not the mathematical x-domain. No expression strings or arbitrary code. See `examples/quadratic_derived_points.json` for a synthetic fixture.


## 受约束旋转点（point.derive.rotate）

`{"id":"Q","type":"point","derive":{"type":"rotate","source":"P","center":"O","angle":{"parameter":"theta","scale":1,"offset":0}}}` 使用已有点 P、O；angle 是有限度数或严格的 parameter/scale/offset 仿射标量，正逆时针、负顺时针（不同于 move_on_circle 的弧度）。位置每帧为 center+R(angle)*(source-center)，源点、圆心移动时实时联动。静态角度也保留依赖；center 可等于 source，但不得形成循环。未知字段、表达式字符串、非有限值、无效点引用均拒绝。

用 set_parameter 改 theta；多个副本点共享角度和圆心，再用 line/polygon 引用副本点即可刚性旋转整条边或三角形，标签同步跟随。不要对派生点使用 move，也不要用直线插值冒充旋转；reveal 后旋转副本可保留原图。既有参数范围 [-10000,10000] 不变。合成样例 examples/rotation_points.json 只验证能力，不证明语音同步或 TTS。

text_transform：items 为 1–48 个 {id, position:[x,y], text?}，仅操作已可见的 text。position 是画布坐标而非世界坐标，必须显式给出；text 可省略（只移动）或提供不超过64字符的短文字。不变项沿用原对象，全部项同一次 play，继承字号、颜色、宽度、typography 和 formula_group，仍受原可见预算限制。后续移动继续使用 text_transform，复制用 translate_copy，隐藏用 hide；原 move 仍只用于自由点。不改变点名、线条或章节初始定义。 快进/前缀缓存未启用，本动作只验证正常串行路径。

text_transform 改字使用旧字淡出至零后完整新字淡入，保持注册ID与原动作预算，不做整段字形揉合；未改字的项仍连续移动。短时改字中间可能变暗，必须检查变换前、中、后及结论稳态，不以终态正确代替中间帧可读性。

text_transform 单项可选 via:[x,y]：在同一动作时长的一半经过该画布坐标，再到position；仅有限且位于安全画布内的坐标，不是表达式。不填仍走直线。途经点不改变对象终态。导演须检查全路径与相邻可见项的避让，不能只验终点。


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


## 可展侧面连续展开（capability 1.7.0）

圆柱使用 `{"id":"S","type":"cylinder_net","radius":1,"height":2,"unfold":{"parameter":"p","scale":1,"offset":0}}`；正圆锥使用 `{"id":"S","type":"cone_net","radius":1,"slant":3,"unfold":{"parameter":"p","scale":1,"offset":0}}`。章节声明 parameters.p=0，reveal 后用原 set_parameter 将 p 连续推至1；允许反向复原。尺寸是固定有限数，范围[1e-6,10000]，圆锥必须slant>radius。unfold是有限数或严格仿射标量，解析值始终在[0,1]；无表达式执行。可选position为固定世界xy偏移（默认[0,0]），display_scale为固定正有限显示倍率（默认1，范围[1e-6,10000]），只缩放投影后的坐标，position不随之缩放；r/h/ℓ与内蕴面积和弧长不变。另可选color/stroke_width/fill_opacity。这是侧面，不含底面；conic仍表示圆锥曲线，不表示圆锥实体。

圆柱按弧长s∈[-πr,πr]、z∈[-h/2,h/2]，k=(1-p)/r，XYZ=(sin(ks)/k,z,(cos(ks)-1)/k)，p=1用解析极限(s,z,0)。正圆锥β=r/ℓ，θ∈[-πβ,πβ]、ρ∈[0,ℓ]，b=1-(1-β)(1-p)²，XYZ=(ρb sin(θ/b),-ρ√(1-b²),ρb cos(θ/b))。b的末段再映射避免突然拍平，仍是同一保度量family。终态分别为宽2πr高h的矩形、半径ℓ且扇角360r/ℓ度的扇形，锥侧面积πrℓ、弧长2πr。

执行器沿固定48×8材质网格计算三维解析坐标，做平滑刚体视角旋转、正交投影和深度排序；不是二维线性形变或静态net淡入。最终平面正对镜头，中途屏幕长度会缩短，标注/测量必须声明intrinsic或flattened，不能量投影边长当真实长度。网格用于可追踪示意，不是数值面积测量网格；底面如需出现另行编排，不提前摆出最终net。使用position/world_bounds/plot_rect安排整段运动，保持起、中、末轮廓和网格可读。snapshot.developable_surfaces记录解析尺寸及measurement_space，不代替真实画面验收。


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


## 受约束正比例缩放点（point.derive.scale，geometry-1.9.0）

`derive={"type":"scale","source":"P","center":"O","factor":{"parameter":"s","scale":1,"offset":0}}` 严格只接受 type/source/center/factor。factor 也可为固定有限数，解析后须满足 `0<factor<=10000`；拒绝布尔、非有限值、未知字段及表达式。位置每帧为 `O+factor*(P-O)`，source/center 均须引用点，允许二者相同但禁止依赖循环。固定因子仍跟随源点和中心运动。

一个 set_parameter 可同时驱动多个 scale 点和动态 sector 的 radius；圆盘用 sweep_angle=360。先用 rotate 派生圆心/点，再以其为 scale.source，实现绕中心旋转后整体伸缩；半径同步乘同一因子，不以位移模拟缩放。constrain 可建立该派生关系；派生点禁止直接 move/move_on_circle，依赖中心的圆周运动禁用规则不变。参数初末态均检查，仿射因子的线性中间态仍在正有界区间；source/center 的依赖逐帧重算，边和标签随点更新。通用例子见 examples/scale_points.json；无声能力样例不证明语音同步，不迁移历史输出。

## 已选择的视觉风格

规划前读取项目 `style-selection.json` 和 Skill 的 `references/visual-styles.md`，按 selected_style 应用视觉与讲解规则；未选择的新任务先询问。不得向 strict storyboard 填入 theme/style_profile。paper_guided 的缺口→依据→结论、原位语义色对应、定向辅助线与逐项条件规则以该单一参考为准；使用该项目锁定的一对语义色（例如红/绿；已锁定红/蓝项目沿用），对应边、角、淡填色保持一致。classic_black 保留旧布局和效果；不要因新风格迁移旧项目。


### 独立构图章节（geometry-1.9.4）

章级可选 `presentation:"freeform"` 关闭该章的自动标题和主题白卡，只为自行声明的图元留出构图画布；默认 `standard` 保留原行为。使用已有 text/line/polygon 等原语组织独立片头，细边框及偏移浅影可自行声明为有序多边形，或使用 geometry-1.9.5 的显式 panel；shadow 字段仅对 panel 有效，不增加任意 z_index，也不代表自动纸卡默认带阴影。进入或离开 freeform 时，旧章淡出按当前 scene 的实际绘制次序收集对象，新章自动元素进入共用新章第一个显式动作时窗（含 hold），不额外占用0.5秒。新章无动作时，在章首使用不超过0.5秒且不超出本章的帧量化时窗完成过渡；没有可用帧时立即清理，不能把 opening 留给后章。恢复 standard 时按既有 heading_mode/主题恢复全局或章节标题，纯 standard→standard 的默认过渡保持不变。用真实音频锚点安排动作及原语进入，仍须通过动作审计和实际转场帧核图。不得把此布局选项当作任意代码、数学约束放宽或默认改写所有题图。通用示例 `examples/freeform_chapter.json` 仅为合成线段数据，不包含用户音频或项目路径。


## 纸面参考版式与字段路由

paper_guided 的独立步骤框、字体、标签和阴影参数以 [visual-styles.md](../../../references/visual-styles.md#已确认参考与沿用版式) 为唯一维护说明，不重复另一套默认。用户说“沿用/恢复”时先实际查看可读已确认参考或读取旧分镜，按该节对齐布局、比例、字体、线宽、完整图框、小页眉与紧凑步骤；只有相同配色不算沿用。缺参考不可自行声称复用成功。

4:3 正式证明按该节和 [布局片段](../../../examples/paper_layout_4x3.json) 使用 freeform+steps、显式 panel 与 text；不得退回自动居中大标题、漏左图框或整张大公式卡。模板文字随题替换，text.position 为中心，换字后重新测宽定位。参考参数不是新 contract 字段，不给 JSON 加 align、font_weight、header 或 frame。用户新要求优先，经典黑底、其他画幅及独立片头不机械照搬。

沿用的画面验收须保留同阶段参考/本期截图与区域比例对照，规则与能力缺口交接见同节；不强制额外生图或重配音。已有项目修订需相应明确授权，更新规范不等于迁移旧输出；仅 schema 通过不能宣称视觉通过。
