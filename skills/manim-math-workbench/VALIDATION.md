# 公开源码验证范围

日期：2026-10-13。使用本机已有 Windows x64 隔离运行环境，Python 3.13.15 / Manim 0.19.0；未执行首次完整联网安装，没有使用私人题目、真实旁白、用户媒体或密钥。

| 检查 | 结果与实际范围 |
|---|---|
| Skill 元数据 | `quick_validate.py` 通过；中文 UTF-8 输入使用 Python UTF-8 模式。 |
| 本机环境 | `setup.ps1 -CheckOnly` 通过；只证明已有环境有效。 |
| 实时契约 | runner `0.1.2`，generic schema `4.3`，geometry schema `geometry-1.0` / capability `geometry-1.8.1`。 |
| Python 维护测试 | 首次 143 项：142 通过；1 项因为旧测试固定断言 `geometry-1.6.0` 失败。公开副本将该断言更新为核对 ellipse / hyperbola / parabola 的实际圆锥曲线契约；受影响的 9 项全部复跑通过，其余测试及执行源码未变化。 |
| JavaScript 接口测试 | 7 项通过，2 项因没有已编译的 Go mock worker 而跳过；使用真实本地 HTTP 服务和明确 mock 下游，不访问抖音。 |
| 入口语法 | 5 个 PowerShell 脚本解析无错误，6 个 MJS 文件通过 `node --check`；Python 文件解析及 JSON 文件读取通过。 |
| 真实合成 smoke | preview 成功，360×480、15 fps、5.47 秒，带音轨；`timing_source=synthetic_fixture`，没有 Whisper ASR、高清导出或真实旁白验证。 |
| 合成 smoke 视觉抽查 | 查看 0.68 秒标题、2.00 秒方块出现、5.38 秒稳定末态三个原尺寸关键帧：标题/公式可辨认、方块正常显示、没有底部旁白字幕。只覆盖这三个采样画面，不宣称逐帧目检。 |
| 公开内容 | 白名单源码、通用示例、维护测试与合成 fixture 源码；保留 BabelCloud MIT，另列 FFmpeg 等运行时许可。不含运行配置、媒体、模型、字体、日志、缓存、编译产物、密钥或个人路径。 |

本次运行源码与当前安装版逐文件一致；公开版本改动为 README/来源/许可/验证说明及一个过期测试断言。原安装版没有修改。`PACKAGE-MANIFEST.json` 定位公开副本每个有效文件，Git 提交定位整体版本；ZIP 的解压一致性由仓库级发布检查负责。

未验证范围：第二台全新 Windows、首次完整联网引导、Go 单元测试和上述 2 个 worker fixture、真实新抖音视频抓取、本次真实语音 ASR、完整用户视频视觉/听审、高清导出、封面生成，以及最大预算长课。使用者需要按自己的实际输入、机器、依赖和任务完成相应验收。

测试中出现 Manim 的弃用提示；它们没有导致相关测试或本次 smoke 失败。合成单测与 smoke 不能替代生产任务的数学、音频、媒体完整性和当前真实画面检查。

## 2026-11-01 更新

本次把公开副本同步到当前安装版，并加入一组制作规则修订。没有生成新的 GitHub Release 或 ZIP；`v1.0.0` 发布资产仍对应 2026-10-13 的版本。

| 内容 | 范围 |
|---|---|
| 规则修订（文档与导演提示词） | 配音来源与授权（默认用户回传，已授权时代理用指定工具生成）、题设随口播建立及其逐条验收、首句问句钩子、封面可用图片生成或代码绘制、只交付音效版成片、新增按需参考 `references/account-preferences.md`（单一账号的已确认偏好，不作通用默认） |
| 同步安装版已有能力 | geometry capability `geometry-1.9.7`、runner `0.1.3`：纸面参考字体与步骤框、`highlight` 的 emphasis 脉冲、动效音效后处理 `scripts/add_sfx.py` 及其说明、4:3 布局片段等。这些引擎改动来自此前安装版，不是本次规则修订新写的代码 |

| 检查 | 结果与实际范围 |
|---|---|
| Python 维护测试 | 本机已有隔离环境（Python 3.13.15 / Manim 0.19.0）在公开副本运行 `unittest discover -s tests`：181 项全部通过 |
| 实时契约 | `contract` 报告 runner `0.1.3`、capability `geometry-1.9.7`；geometry 导演提示词按路径引用，新增段落随文件加载 |
| 仓库检查 | `tools/validate_repository.py` 与仓库 `tests` 通过；`RELEASE-FILES.json` 与本文件同目录的 `PACKAGE-MANIFEST.json` 已按当前文件重算 SHA-256 |

未验证范围：本次没有渲染新视频、没有执行动效音效或配音的真实端到端制作，也没有重跑首次联网安装、Go 测试、JavaScript 接口测试或合成 smoke；规则修订的实际效果需要在下一次真实制作中验收。
