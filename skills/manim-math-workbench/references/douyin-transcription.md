# 抖音链接作为数学视频的输入入口

数学视频上下文中，用户给出抖音 URL 或完整分享文本，即触发本输入适配，无需另说“提取”。只处理本次提供的输入；没有新链接时，不取历史私人视频来证明成功。

连续流程：

1. 原样提交 URL/完整分享文本，先 health；服务未运行才启动 Node，工作目录为配置中的 `outputs/douyin-web`。`POST /api/jobs` 的 JSON 字段是 `shareText`，不要截掉分享文案或只保留链接。轮询 `GET /api/jobs/{id}` 到 `done`；`queued/running` 继续等待，`failed/error` 报具体错误，轮询超时保留任务 ID，可续查而非重复创建。
2. 提供原始 `transcript.txt`、保留的源音频路径及 transcript/audio 下载链接。提取稿保留为输入证据，不直接覆盖成改写稿。源音频角色固定为参考原素材，不自动当成改写后正式旁白。
3. 沿用 `narration-preparation.md` 的数学验算与稿件处理规则；涉及原创发布时原创重构，用户明确轻改、保留原稿等要求优先。ASR 同音字、数字和符号需核查，不能把识别误字当数学结论。
4. 本入口的目标是准备用户录音：处理后的完整稿内部保存，录音阶段默认仅交付每段硬上限 500 字符的可复制分段稿；用户显式要求完整稿时可例外交付。主动运行 `scripts/split_narration.py` 分段，只分段、不在分段时改稿，无需用户再次要求分段。
5. 用户自行生成配音并发回，核对对应锁定稿；等待配音期间可做不依赖音频的验算/语义分镜，但不能用原视频音轨假装新版稿件的配音。
6. 收到实际配音后沿用工作台分析、分镜、真实预览、正式动画/视频、双封面流程。最终交付配套完整锁定稿；成片阶段不再附分段稿。此适配不替代视频/画面/音频 QA。

## 调用

在 Skill 目录，Codex 可执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\douyin_transcribe.ps1 -ShareTextFile '完整分享文本.txt' -OutputDir '本期项目\douyin-inputs'
# 或：-ShareText '用户本次给出的完整 URL/分享文本'
```

输入文件为 UTF-8。不要把文本拼成 shell 命令；参数通过临时 JSON 传入 Node，退出删除临时请求。健康服务存在且配置缺失时，只采用其 health 路径和可用 Node，不安装完整便携环境；未知服务或缺依赖拒绝新建任务。health 的 `ok:true` 仅表示 HTTP 服务可访问，必须另检查 dyt/FFmpeg/Whisper/helper/model 就绪及 `small` 默认。

输出是 JSON，含 `jobId`、`transcriptPath`、`sourceAudioPath`、下载 `links`、`configPath` 和下一阶段。每个任务独立目录，另有 `job-receipt.json`、`job-status.json`。下载地址仅在对应服务存活时有效，文件路径可长期保存。

```powershell
.\scripts\douyin_transcribe.ps1 -JobId '任务ID' -ConfigPath '回执中的配置路径' -OutputDir '原输出目录'
.\scripts\douyin_transcribe.ps1 -HealthOnly
```

轮询超时不杀死用户服务/任务；用回执续查。便携服务单任务最长 2 小时，超时停止该任务进程树并保留日志，报 `failed`/`error.type=timeout`。任务串行，重启时把未完成任务标成 interrupted，不自动再次抓取。旧服务任务元数据仅在内存中，重启后已有任务可能无法通过 ID 查询，已有本地文件仍保留。

旧服务只识别 `v.douyin.com` 短链；完整 `www.douyin.com/video/...` URL 自动走独立的便携服务配置（默认主端口加一），不会修改/重启旧服务。独立端口被未知程序占用时拒绝接管；按回执中的 `configPath` 续查该独立任务。

## 便携安装及本机复用

```powershell
.\scripts\douyin_setup.ps1
.\scripts\douyin_setup.ps1 -CheckOnly
# 非默认位置：
.\scripts\douyin_setup.ps1 -RuntimeDir 'D:\LocalTools\ManimDouyin' -ConfigPath 'D:\LocalTools\ManimDouyin\config.json' -Port 18787
# 采用已经正常运行的小模型旧服务，路径由本机 Codex 探测，不写入分发：
.\scripts\douyin_setup.ps1 -ExistingServiceDir '本机现有项目\outputs\douyin-web'
```

默认配置 `%LOCALAPPDATA%\ManimMathWorkbench\douyin\config.json`，runtime、任务、模型全在包外。`-ExistingServiceDir` 只在其健康接口能报告依赖时采用该服务的真实 dyt/helper/model 等路径，不下载、不编译、不 npm 安装；后续停服由入口在原目录启动。便携安装优先复用 `ManimMathWorkbench/runtime.json` 的 FFmpeg/Whisper/小模型；small SHA-256 必须匹配锁文件，错误不退回 base 或云。

Windows x64，系统 PowerShell 5.1+；Node>=20 和 Go>=1.24 可复用，也可显式 `-NodeExe/-GoExe`。缺失时下载锁定的官方 ZIP 并核验 SHA-256。构建仅 Go 标准库，不依赖 Git/Cobra/云 API。仅准备 Node 可用 `-NodeOnly`。npm 使用固定 lockfile/integrity，不运行 lifecycle scripts；已有相同 npm lock 和模块时跳过安装，已有相同 Go 源身份及二进制时跳过构建。锁下载 `.partial` 通过校验才替换；失败配置不标为成功。首次网络下载可能较大，已有模型不重复下载。

浏览器优先系统 Edge/Chrome；缺失时用锁定 Playwright 的固定 Chromium revision 下载到包外。只启动全新临时上下文，不读取登录 profile/cookies，不自动登录或绕付费/验证码。网络抓取仍受抖音页面、风控和 CDN 变更影响；CDN/重定向域名白名单不匹配即失败，需基于新证据维护，不放宽为任意 URL。便携服务仅 127.0.0.1，拒绝跨源 POST 与非回环 Host，不适合作公网服务。

## 验收与发布边界

本源码发行版包含维护测试和合成 fixture 源码；测试运行目录、媒体、编译产物和日志必须留在包外。

- `node --test tests/douyin_api.test.mjs`：真实 Node HTTP 服务 + 明示 mock 下游；覆盖 queued/running/done/failed、worker timeout 分类、客户端 timeout/续查、UTF-8 分块、重启与依赖拒绝。不是抖音抓取或 ASR 成功。
- 编译 `tests/douyin_worker_fixture.go` 到包外临时 exe，设置 `DOUYIN_MOCK_DYT` 后运行上述测试，额外覆盖真实子进程超过 128 KiB 日志及中文音频路径保留。
- `tests/douyin_real_fixture.ps1 -ConfigPath <便携配置> -EvidenceDir <包外目录>`：现场 Windows 中文 TTS 生成短语音，真实 local CLI/FFmpeg/whisper.cpp small zh、真实 API 和音频下载/hash 比对；媒体输入被替换成本地 fixture，不访问抖音。
- 接口 mock 和合成 fixture 不证明真实抖音新作品端到端成功。本机隔离测试也不是第二台全新 Windows 验收；首次空机器网络引导需另验。

公开源码包括 `scripts/douyin*`、`assets/douyin/` 源码/锁文件/许可、通用维护测试及本文；不包含已编译 fixture、真实媒体或测试运行产物。禁止发布运行配置、用户路径、runs、cookies、媒体、密钥、node_modules 或现有项目整体。来源与依赖许可见 `assets/douyin/NOTICE.md`；第三方原版权和许可证必须保留。
