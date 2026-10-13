---
name: manim-math-workbench
description: Windows 本地 Manim 数学视频工作台，支持抖音数学视频链接或分享文本输入、录音稿准备、逐字稿音频对齐、分镜编译与真实渲染验收。
---

# Windows 本地数学视频工作台

这个 Skill 是 Windows x64 本地安装版：Codex 负责根据题目、逐字稿和本地能力契约直接规划 `storyboard.json`，分发包负责校验、音频对齐、编译、真实低清验收和可选高清导出。不强制另配第三方付费分镜 API；Codex 自身的账号与使用额度仍按用户现有配置。

当前执行器能力以 `scripts/video.ps1 contract` 的实时输出为准，不保证任意题型或动效。核心效果缺失时先检查会话授权：用户已授权补齐，就按[维护与验收](references/maintenance-and-qa.md)扩展、验证并继续制作，不重复询问；未获覆盖该扩展的授权时，说明具体缺口和可选方案再询问。不得用静态字幕幻灯片冒充所需运动。Skill 不授予额外执行或外部操作权限。

## 首次部署

Codex 在已授权范围内自动准备环境。已有 runtime.json 时先检查配置及可执行文件；缺失或失效才运行 setup。环境与代码未变时复用有效验收，不重复安装或重跑 smoke。首次部署在本 Skill 目录按需使用以下命令，无需用户逐条操作：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -CheckOnly
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\video.ps1 contract
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\video.ps1 smoke -JobDir .\smoke-output
```

无需预装 Python、Node 或 Git。首次 setup 联网下载隔离 Python、Manim/PyAV/Pillow、FFmpeg、whisper.cpp 和本地识别模型，按 `assets/runtime-lock.json` 固定版本并验证指定下载哈希；需 Windows x64、微软雅黑和至少 5 GB 可用磁盘，不安装 TeX。默认运行环境在 `%LOCALAPPDATA%\ManimMathWorkbench`，配置为 `runtime.json`；`video.ps1` 从中读取 Python，不依赖系统 PATH。改安装位置或自定义配置的方法见运行流程。若 smoke 失败，不能把工作台标成可用；先看该 attempt 目录中的 `manifest.json`、`report.json` 和日志。

5 GB 是准备环境的空间预算，渲染缓存和成片另计，不是所有任务的容量保证。下载或执行被当前工具权限阻止时，说明具体失败命令、缺失的网络/目录写入/进程执行权限及最小人工操作；Skill 本身不能提升权限。不要把下载故障泛称为需要管理员权限。安装与验证范围见 [中文安装说明](README.md)。

## 录音稿准备与剪映分段

在数学视频制作上下文中，用户直接给抖音 URL 或完整分享文本，即触发[抖音输入流程](references/douyin-transcription.md)，替代手贴逐字稿，无需再说“提取”。完整链路为：URL/分享文本 → 调用已有本地服务自动提取原稿，保留源音频及服务返回的下载链接/本地路径 → 数学验算与按既有规则原创重构（用户明确轻改、保留原稿等要求优先）→ 主动交付每段≤500字符的录音稿 → 用户自行生成配音并发回 → 本工作台完成音频对齐、动画/视频、双封面及锁定完整最终稿。输入适配应衔接后续制作，不停在下载结果。

提取的源音频用于核对原稿，不自动成为改写后稿件的正式配音；保留来源材料与改写稿、用户回传配音的版本关系。等待配音时继续可独立完成的验算和语义分镜，不擅自生成或替换配音。服务不可用或提取失败时报告具体阻塞及已取得材料，不伪造提取结果；安装或文档检查不等于真实新链接端到端验证。

图片题识读、阴影边界核对与删去无关情境，先按同一参考文档的“图片题：核图、精简题面与口播”处理；不把单题图像或数字写入通用 Skill。

写稿前按[录音稿准备](references/narration-preparation.md)结合当前指令和会话确定原稿保留、纠错轻改或原创重构；他人逐字稿涉及原创发布或搬运担忧时按该规则重构，用户明确只轻改优先。先完成完整稿自查、验算、修改说明和语义分镜；只要本次交稿意图让用户录音或生成音频（包括发稿后等用户回传音频），就主动交付每段≤500字符的可复制块和编号 TXT，不等用户再要求分段，也不能以 `review_ready` 或“审阅稿”标签规避。仅用户明确纯讨论、只审稿或不要做时不强制分段；录音阶段默认面向用户只交分段块和编号 TXT；完整稿内部保留用于校验与对齐，用户明确索要完整版时才另提供。仅纠错不得冒充原创重构定稿。已批稿或提供对应音频不重复询问；已授权改稿后须重新核对音频，保留旧输入。阶段记录及重录边界见同文。剪映录音稿默认每段硬上限 500 字符，运行 `scripts/split_narration.py --input 完整稿.txt --output-dir 分段目录`，规则见 [录音稿准备与剪映分段](references/narration-preparation.md)。分段用于用户录音或生成音频，不自动切分镜或添加片头、片尾、停顿；视频仍按完整稿和实际音频连续对齐。

## 默认生产流程

用户要求“直接生成”时，连续完成以下流程。先利用现有材料和授权消除可解决的疑点；只询问仍影响结果的关键缺口，暂停依赖该答案的步骤，同时继续独立工作：

1. 核对题目、完整稿和音频。若为本 Skill 提供的锁定稿，且用户已明确表示本次音频按该版本生成，按[锁定稿音频规则](references/narration-preparation.md#锁定稿生成音频来源确认替代逐词追问)复用来源声明，保留音频解码、时长完整性及动效自动对齐；跳过逐词人工听辨，ASR 同音或识别不确定不阻挡渲染、不反复追问，仅在证实整段缺失、损坏或重大内容错配时处理。按用户指定的改写幅度及锁定开头处理稿件；用户授权补全题设时注明假设并验算，不把推定当原题。转写疑点先按[录音稿准备](references/narration-preparation.md)核查，不能仅凭 ASR 漏字要求重录。runner 不改稿，原音频只读，不擅自换成 TTS。
2. 运行 `contract`，把当前 schema、动作字段、能力版本和导演提示词交给 Codex；geometry 分镜先按[图形语义规划](assets/engine/prompts/geometry_director.md#图形语义规划)选择解释模型，再写约束 JSON，不写任意 Python。
3. 保存 `request.json` 和 `storyboard.json`，先跑 `preview`；查看可辨认文字的真实关键帧及重要运动前、中、后，contact sheet 只作索引。长视频按知识点分章，仍以原音频为连续时钟。按对应管线记录预览证据后再导出 `final`。
4. 低清预览必须通过且必须有音轨，才能继续高清。按[用户导出偏好与像素验收](references/operate.md#用户导出偏好与像素验收)确定最终规格：本次明确规格优先，保留已有项目 canvas，本机偏好仅用于新项目；均无时沿用3:4、1080×1440、60fps。最终尺寸写入分镜，低清像素与其分离；4K须原生渲染并独立检查高清抽帧和实际媒体参数。generic/v3目前固定1080×1440，不支持4K，不得静默降规格。保留黑底黄标题、公式和图形连续性，不烧录旁白字幕；答案按实际旁白锚点出现，不提前展示。
5. 从当前 attempt 的 manifest/report 读取并核实实际成片路径，交付可点击的绝对路径以及输入、规范化分镜和恢复编辑所需文件。`local_validation` 与 `visual_review` 分开；没有检查当前真实画面时，不能标成 `visual passed`。本机独立目录验证不等于第二台全新 Windows 已验证。 成片交付时，口播稿只提供本次已锁定且与实际录音一致的完整版的本地文件链接或完整正文，不附分段稿。交稿用于用户录音或生成音频时，按[录音稿准备](references/narration-preparation.md)主动提供每段≤500字符的可复制分段，只分段、不改稿；不得在成片后擅自改写为与音频不一致的版本。

6. 默认随成片交付黑板风双封面：从锁定逐字稿提取题目核心，参考已查看图片风格，按[双封面说明](references/video-covers.md)用内置 `image_gen` 逐张生成独立的 3:4 竖版与 4:3 横版（用户可覆盖；不沿用视频比例裁切），检查文字、数学与排版。封面作为侧文件，不改音视频；生图失败先报 video ready、cover pending 和原因并交付有效视频。新成片默认生效，旧片不批量迁移。

外部完成通知仅在约定交付实际达成、对应QA通过，且已有覆盖该消息的明确发送授权、已核实收件人和可用渠道时执行；制作视频不默认授予发消息权限，也不代表已具备通知能力。未实际发送不得称已通知。

## 耗时与渲染策略

- 先校验文本、数学关系、分镜契约与动作锚点，再进入昂贵渲染。音频、脚本和分镜锁定后，正常只做一轮必要预览与一次最终渲染；仅在输入变更、失败或发现问题时修复并复验受影响环节，不重复已有效的检查。
- 有效 ASR、音频对齐和完整成片仅在各自输入、配置及适用执行环境身份一致、证据有效时复用；不能仅凭文件名或旧 passed。最终4K、fps、画布和音轨严格按用户规格，不得为提速静默降级或删除动效；低清预览不得冒充4K最终成片。
- 每阶段记录起止时间、实际耗时和结果；失败保留 attempt 与日志，向用户说明实际失败原因及尚未完成部分，估计耗时不得当作实测。章节并行、严格前缀缓存仍是隔离实验，不得宣称为已启用功能或已保证的提速收益。
- 最终成片仍按第4–5步及[维护与验收](references/maintenance-and-qa.md)完成实际媒体与画面QA；交付末尾只附锁定完整稿链接或全文，不分段，≤500字符分段用于让用户录音或生成音频的交稿环节。

## 可维护入口

- `geometry-1.0` 几何分镜走独立 [geometry 管线](references/geometry.md)，先 `analyze` 读取真实音频锚点，再按 [geometry director](assets/engine/prompts/geometry_director.md) 规划；不得用 generic4.3 冒充几何支持。
- 制作反馈只在有证据且可复用时沉淀：决策写入对应提示词，执行能力写入契约与引擎，已发生的故障写入验收规则；已有规则不重复堆叠，单题数字和私人材料留在项目。运行与改动风险匹配的验证。
- 本期题目、音频和单次画幅偏好留在项目，不自动修改所有用户默认。
- 安装版修改前保留可恢复备份；公开源码修复在隔离候选副本验证后按实际授权同步，不收入私人对话、密钥和媒体。
- 交付区分本期项目修复与已验证的可复用能力，未验证项如实说明。

- `scripts/video.ps1 contract`：输出实际 schema/capability 版本、完整动作字段、导演提示词和可执行示例。
- `scripts/video.ps1 run -Request REQUEST_JSON -Storyboard STORYBOARD_JSON -JobDir JOB_DIR -RuntimeConfig CONFIG_JSON -Quality preview`：真实音频必须走本机 Whisper 逐字对齐；失败即失败，不估时伪造通过。高清用 `-Quality final`。
- `scripts/video.ps1 smoke -JobDir JOB_DIR -RuntimeConfig CONFIG_JSON`：生成非私人正弦 WAV 和小分镜，跑真实低清音轨渲染；报告中的 `timing_source=synthetic_fixture` 只证明封装/渲染，不证明 ASR。
- 每次运行写入 `JOB_DIR/runs/<attempt>/`，不覆盖旧 attempt。geometry 对齐附件按音频、旁白与原始 token 来源校验，可在仅改画面时复用；视频 identity 另绑定分镜、执行器源码、音频、alignment 和动作审计。generic 缓存另校验 engine 版本；按各管线实际校验复用，不因排版失败重做有效 ASR。

安装版恢复编辑直接读取用户保存的 request/storyboard/attempt，按 [分镜与对话编辑](references/director-and-editing.md) 生成新 attempt。只有用户明确要求操作已有网页会话时，才使用其另行安装的原工作台；网页和原应用路径不作为本包依赖。

## 稳定约定

1. 模型只决定受约束的分镜 JSON；本地执行器负责数学状态、动作字段、音频主时钟和真实渲染。
2. 旁白分段必须按原稿连续覆盖，动作锚点必须是该段逐字词组；换数字或改稿必须重新匹配音频。
3. 保留黑底、顶部黄色标题和图形颜色/尺寸/方向连续性；无画幅指定时默认 3:4，用户指定可用 16:9 等支持的画幅，3:4 不是硬性限制。图形初始在其绘图区居中，后续按分镜动作平移；不添加底部旁白字幕，不提前展示答案。
4. 专用渲染器可能是只读路线；实际 `editable_fields` 为空时不声称通用分镜修改生效。
5. 分发包不包含用户历史题目、音视频、缓存、浏览器会话、密钥或整个原应用；`assets/engine` 只保留白名单执行模块和版本化提示词。

按需读取：生产操作见 [运行流程](references/operate.md)，分镜决策见 [分镜与对话编辑](references/director-and-editing.md)，故障、升级和验收见 [维护与验收](references/maintenance-and-qa.md)。

长课显式使用 `production_profile: "long_lesson"`（4小时/512子场景/12000动作有界预算）；默认标准预算不变，数学/音频/画面验收不降低。详见 geometry 参考与实时 contract。
