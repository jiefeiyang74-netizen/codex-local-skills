# Manim 数学视频工作台

Windows x64 本地数学动画 Skill：根据题目、完整逐字稿和对应音频，用受约束的 JSON 分镜驱动数学验算、音频对齐、真实对象动作与 Manim 渲染。Codex 负责规划和检查，本机执行器负责渲染；无需另配付费分镜 API。黑底、黄色标题，不烧录底部旁白字幕。

## 能做什么

- 从题目或稿件准备录音稿，按每段最多 500 字符交付可复制块和编号 TXT；成片配套锁定完整稿。
- 可选抖音单视频输入：本地抓取与转写、保留来源音频，再整理稿件；配音仍由使用者提供。只处理使用者有权处理的素材。
- generic 分支支持既有公式与等份动作；geometry 分支支持声明式几何、圆周/旋转、二次与反比例函数、圆锥曲线、扇形/弓形、动态参数及圆柱/圆锥侧面展开等受支持动作。
- 真实音频对齐、逐动作审计、先有声预览再正式导出，保存旧 attempt、恢复编辑所需输入、报告和中间片段。
- geometry 支持分镜中的横/竖屏画布与原生高清规格；无明确规格时默认 1080×1440、60 fps。generic 默认固定 1080×1440，不能静默代替 4K。
- 明确 `production_profile: "long_lesson"` 可启用最长 4 小时、512 章、12000 动作的有界预算；这属于输入预算，不保证任意机器能完成最大规模任务。
- 配套双封面工作流由宿主支持的图片生成工具完成，不是本机渲染器内置生图功能。

支持范围以 `contract` 的实际字段和能力版本为准，不保证任意题型、任意动画或无人检查的自动正确性。

## 安装 Skill

仓库中的安装目录：[skills/manim-math-workbench](https://github.com/jiefeiyang74-netizen/codex-local-skills/tree/main/skills/manim-math-workbench)。可将下面文字交给 Codex：

> 请从 jiefeiyang74-netizen/codex-local-skills 的 main 分支安装 skills/manim-math-workbench。先发现当前有效的技能目录，保留已有版本的可恢复备份；安装后检查包内源码、准备本机环境，并运行 CheckOnly、contract 与合成 smoke。说明真实验证范围，不上传我的材料。

也可下载源码 ZIP，将本文件所在的整个 `manim-math-workbench` 文件夹复制到有效技能目录。通常为 `$CODEX_HOME/skills`，未设置时为 `~/.codex/skills`，以本机发现结果为准。确保该目录直接包含 `SKILL.md`，避免多套一层同名目录；刷新技能发现或重开任务后确认已加载。

## 首次准备运行环境

需要 Windows x64、PowerShell 5.1+、系统微软雅黑、联网及至少 5 GB 环境空间；临时下载、渲染缓存和成片另计。Skill 本身只含源码；首次 setup 下载隔离 Python、Manim/PyAV/Pillow 等依赖、FFmpeg、whisper.cpp 和本地 small 识别模型，不安装 TeX。具体版本、来源与下载哈希见 `assets/runtime-lock.json`。

在本 Skill 目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -CheckOnly
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\video.ps1 contract
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\video.ps1 smoke -JobDir .\smoke-output
```

默认运行环境位于 `%LOCALAPPDATA%\ManimMathWorkbench`，实际程序路径保存在包外 `runtime.json`；无需依赖系统 PATH。可用 `-RuntimeDir` / `-ConfigPath` 配置安装位置，后续 launcher 用同一 `-RuntimeDir` / `-RuntimeConfig`。迁移环境后重新执行 setup 刷新配置，不能复制别人的运行配置。已有有效环境先检查，再决定是否安装；详见[运行流程](references/operate.md)。

## 制作视频

> 请用 $manim-math-workbench 根据我提供的题目、完整逐字稿和对应原音频制作数学视频。按实际音频安排对象动作；先检查真实预览，再导出成片，并交付可恢复编辑的任务文件。

只有题目或稿件时，先验算、整理稿件和语义分镜，等提供对应配音后再渲染。原稿和原音频不得静默改写或替换。需要录音时主动交付每段≤500字符的可复制块和编号 TXT；分段用于录音，不自动切分镜、增加片头片尾或停顿。

直接运行的基础形式：

```powershell
.\scripts\video.ps1 run -Request .\request.json -Storyboard .\storyboard.json -JobDir .\video-output -Quality preview
# 预览通过并记录真实画面审阅证据后：
.\scripts\video.ps1 run -Request .\request.json -Storyboard .\storyboard.json -JobDir .\video-output -Quality final
```

geometry 的 request 基础字段是 `problem`、`narration`、`audio_path`。可复用对齐附件、动作审计和审阅证据的真实身份校验见[geometry 流程](references/geometry.md)。相对输入路径按 request 所在目录解析。`examples/` 是通用分镜，不含真实旁白或已通过的审阅材料；`assets/examples/` 的合成 smoke 只用于运行检查，不能编造词时间让真实任务通过。

抖音输入另需准备可选本地服务：

```powershell
.\scripts\douyin_setup.ps1
.\scripts\douyin_setup.ps1 -CheckOnly
.\scripts\douyin_transcribe.ps1 -ShareTextFile .\share-text.txt -OutputDir .\douyin-input
```

服务只绑定回环地址，浏览器使用临时上下文，不读取个人 profile/cookies。平台风控、验证码、登录/付费限制、网页或 CDN 变化可能导致抓取失败；不绕过这些边界。说明、续查与测试范围见[抖音输入](references/douyin-transcription.md)。

## 恢复与验证边界

保留 request、storyboard、原音频、alignment、action audit、manifest 与当前视频的审阅记录。修改时新建 attempt，保留旧输出；操作见[分镜与编辑](references/director-and-editing.md)。generic 的成片/预览路径读取 manifest 的 `artifacts.final` / `artifacts.preview`，geometry 读取 `artifacts.video` 并检查 `quality`。

`CheckOnly` 只检查环境；正弦音轨 smoke 只验证本机封装、渲染和音轨，不验证 ASR。数学单测、媒体完整解码、关键帧视觉抽查及旁白核对分别需要对应证据，不能互相替代。本仓库包含维护测试及合成 fixture 源码，不包含私人测试素材、历史视频或证明新机器已可用的旧报告。当前环境验证记录见 [VALIDATION.md](VALIDATION.md)；另一台全新 Windows、首次完整联网安装、真实新抖音作品和最大长课仍需单独验证。

维护测试可在已有依赖的 Python 环境中运行：

```powershell
python -m unittest discover -s tests -p 'test_*.py'
node --test tests/douyin_api.test.mjs
```

部分测试需要 Manim/PyAV/Pillow/NumPy，部分音频测试还需要可发现的 FFmpeg；推荐使用 `runtime.json` 对应的 Python 并将配置中的 FFmpeg 目录加入当前进程 PATH。Go 单元测试在 `assets/douyin/source` 下运行 `go test ./...`。测试中的合成材料只证明其对应范围。

## 许可与来源

作者自有的 Skill 封装、本地工作台抽取执行核心、后续扩展和文档以 [MIT](LICENSE) 发布。第三方 `assets/douyin/source` 保留 [BabelCloud 的 MIT](assets/douyin/source/LICENSE) 及其来源说明；不将第三方源码版权归给本仓库作者。

仓库不携带 Python 环境、模型、字体、Node/Go/FFmpeg/浏览器二进制或 `node_modules`。这些依赖保留各自许可；尤其锁定的 FFmpeg 是 GPL 构建，本仓库 MIT 不覆盖它。若另外发布包含运行环境的便携包，必须另核对许可证、通知及适用对应源码义务。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与[来源记录](references/provenance.md)。
