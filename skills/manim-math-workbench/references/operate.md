# 运行流程

## 1. 准备本地环境

本 Skill 面向 Windows x64。Codex 先检查已有环境，再在包目录执行以下命令；检查通过时无需重复下载。用户不必逐条操作：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -CheckOnly
```

首次安装会联网下载锁定依赖，无需预装 Python、Node 或 Git。默认环境为 `%LOCALAPPDATA%\ManimMathWorkbench`，默认配置为其中的 `runtime.json`。需要至少 5 GB 可用空间及系统微软雅黑，不需要 TeX。指定其他磁盘时，setup 与后续命令使用同一个目录，例如：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -RuntimeDir 'D:\数学工具 Runtime'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\video.ps1 contract -RuntimeDir 'D:\数学工具 Runtime'
```

上述 D 盘路径只是用户可替换的安装位置示例。若 setup 使用 `-ConfigPath 'D:\数学工具 Runtime\custom.json'`，后续 launcher 使用 `-RuntimeConfig 'D:\数学工具 Runtime\custom.json'`。`-RuntimeConfig` 优先于 `-RuntimeDir`。所有后续 contract、smoke、run 均须传入同一个自定义运行目录或配置，不能漏传而误用默认环境。运行环境迁移后在新位置重新执行 setup 刷新配置；Skill 源码本身从包内加载引擎，不引用原工作台。

至少 5 GB 是环境准备预算，下载临时文件、渲染缓存和成片另计。网络不可达、哈希错误与写入权限不足应分别说明；真实权限缺口要给出失败命令和最小人工操作，不无条件要求管理员权限。不得导入他人的 runtime 配置或 API 密钥。

setup 生成的 runtime config 至少包含以下路径（示意值，不能直接运行）：

```json
{
  "python_exe": "C:/path/to/python.exe",
  "ffmpeg_exe": "C:/path/to/ffmpeg.exe",
  "whisper_exe": "C:/path/to/whisper-cli.exe",
  "whisper_model": "C:/path/to/ggml-small.bin"
}
```

锁定版本为 Python 3.13.15、Manim 0.19.0、PyAV 13.1.0 和 Pillow 12.3.0；完整下载信息见 `assets/runtime-lock.json`。不要把本机 config、模型、用户音频或日志复制进可分发包。

## 2. smoke 闸门

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\video.ps1 smoke `
  -JobDir '.\smoke-output'
```

smoke 会生成非私人合成 WAV、小型分镜，并调用真实 Manim 低清渲染。它必须在报告里看到 `passed=true`、`has_audio=true`；`timing_source=synthetic_fixture` 是人工 script points，只验证音轨封装和渲染，不能当作 Whisper 对齐证据。失败 attempt 保留，不手工改成成功。

## 3. 题目、逐字稿和音频

收集与本次音频对应的完整稿及必要题设。知识梳理型视频不强求单道练习题，可用主题与定义条件填写 problem；不要为了凑材料编造原题。转写噪声及用户授权的补全按 [录音稿准备](narration-preparation.md) 处理。

用户已明确表示音频按本 Skill 提供的锁定稿生成时，依[锁定稿音频规则](narration-preparation.md#锁定稿生成音频来源确认替代逐词追问)记录来源并继续制作；ASR 内容疑点不增加人工听辨门槛，音频完整性与自动对齐检查仍执行。

输入 JSON 至少是：

```json
{
  "title": "可选标题",
  "problem": "题目原文",
  "narration": "音频中实际说出的完整文字",
  "audio_path": "narration.wav"
}
```

`audio_path` 相对于 request.json 所在目录解析，此例表示把原音频放在该输入目录。路径必须指向实际提供的音频。只询问缺少或不一致的材料；不能自行合成旁白替代原音频。

先执行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\video.ps1 contract`，把输出的 schema、动作字段、能力版本、完整导演提示词和完整示例交给 Codex。Codex 直接产出分镜 JSON，无需额外外部分镜 API Key；不要把任意 Python 交给执行器。包内 `assets/examples/smoke_storyboard.json` 是非私人最小示例，不能替代用户题目的规划。

## 4. 预览和成片

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\video.ps1 run `
  -Request '.\input\request.json' `
  -Storyboard '.\input\storyboard.json' `
  -JobDir '.\output\math-video' `
  -Quality preview
```

generic runner 顺序为：缓存/重新运行本机 Whisper 逐字对齐 → `normalize_storyboard` → `apply_audio_timing` → `compile_storyboard` → 真实低清渲染/稳定帧检查。geometry 使用 [独立管线](geometry.md) 的 analyze、动作审计与渲染门槛，不调用上述 generic 编译步骤。音频是唯一主时间轴；对齐失败、低清检查失败或缺少音轨，默认都不能成功。

确认当前 attempt 的真实画面和报告后才 final：generic 查看 `preview_report.json`；geometry 查看 `report.json`，并按其规则保存匹配的 `visual_review.json`。再运行同样的命令并改为 `-Quality final`。按下文导出偏好优先级明确项目最终尺寸，黑底黄标题；高清不会引用不匹配的旧预览。

每次 run 写入 `JOB_DIR/runs/<attempt>/`，包括 manifest、report、request、规范化分镜、音频对齐附件、视频及日志。generic 另有 `storyboard_input.json`、`generated_math_video.py`、`timeline.json`；geometry 使用 `storyboard_normalized.json`、`generated_geometry_video.py`、`keyframes.json` 与动作审计。按实际 schema 和 manifest 读取，缺少另一条管线的文件不等于任务损坏。旧 attempt 保留；输入原件不改。

读取当前 `manifest.json`：geometry 用 `artifacts.video` 配合 quality，generic 用 `artifacts.final` 或 `artifacts.preview`。确认文件存在且可解码，再把实际绝对路径交付用户；不要凭固定文件名或旧 attempt 猜成片位置。原音频长度与语义锚点驱动动作时间，不为了凑时长裁剪、变速或补静音。查看关键帧之外，还需检查关键动作前后的视频片段，不能用一张 contact sheet 证明对象已移动。

## 5. 需要提问或停止的情况

- 必要题设、完整稿或音频缺失且不能由现有材料及授权解决时，只暂停依赖该材料的制作；可先完成验算、建议稿或无时间的视觉规划，不伪造音频秒数。
- 题意或数字角色矛盾：先列出已知条件和影响，按录音稿准备规则处理；不擅自换数迎合答案。
- `unsupported_requirements` 非空、专用渲染器只读、或 contract 未声明所需效果：说明准确缺口，按已有授权决定扩展或询问，不删除拒绝项绕过验证。圆、数轴、二次函数等支持范围以实时 contract 为准，不代表支持任意路径或任意旋转。
- 用户要求分镜修改时，先重新检查受影响对象生命周期和音频锚点；不静默改旁白。对齐与视频缓存按各管线实际绑定校验后复用，geometry 规则见对应参考文档。

## 用户导出偏好与像素验收

创建新项目时，先读取已有本机 `%LOCALAPPDATA%/ManimMathWorkbench/export-preferences.json`（若存在）；该文件只保存用户导出偏好，不含 API 或运行环境设置，不随 Skill 分发。配置结构为 `schema_version:1`、`default_aspect_ratio`、`final_by_aspect_ratio`（画幅字符串映射到 `{width,height,fps}`）。缺失时沿用 Skill 默认；配置无效或执行器不支持时明确说明，不能静默降规格。

优先级：本次明确规格 > 已有分镜 canvas/已验收项目规格 > 本机偏好（仅新项目）> Skill 默认。新项目由 Codex 将解析后的最终尺寸明确写入 geometry 的 canvas；runner 不读取个人偏好、不自动覆盖旧分镜或改音频身份。仅指定画幅时，新项目可选对应偏好；没有对应项时按当前能力明确确定尺寸。单次规格不回写长期偏好。

preview 与 final 使用同一分镜和逻辑画幅：geometry preview 长边不超过720、不放大小画布、偶数像素、30fps；常见比例保持精确比例（3:4 为540×720，16:9为704×396，9:16为396×704），特殊比例允许不足2像素取整并以实际 metadata 为准。final 按 canvas 原生渲染；低清定稿后才导出高清，不把预览放大或插帧称作4K60。最终另核对宽高、帧率、音轨与原生高清关键帧，不能沿用低清视觉通过记录。

generic/v3 当前固定1080×1440@60，没有自定义 canvas/4K 导出接口；本机4K偏好不使该入口获得4K能力。需要4K时仅对 geometry 已支持的内容采用其管线；不能静默用 generic 的1080成片交付为4K，也不能强行迁移不受支持的内容。
