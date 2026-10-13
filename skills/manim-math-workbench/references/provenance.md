# 来源与分发边界

## 本地工作台与新增实现

`assets/engine/v3` 和 `assets/engine/prompts/animation_director.md` 从作者本地 Manim Prompt Studio 工作台抽取必要执行子集：只保留分镜校验、编译、音频对齐、对象动作和渲染模块，不依赖完整网页工作台。这不是 Manim Community 项目的源码快照，也不代表 Manim 官方认可。

可追溯的本地工作台 Git HEAD 为 `f69e5f89292047a9e9c3f63b0658ab0c825f57c4`；本地仓库无远程上游，历史作者标识为 workbench-admin。该提交只定位抽取基线，不代表本仓库全部文件的精确版本。Skill 封装、独立 geometry 执行分支、录音分段、抖音适配及后续修复另有新增实现。

geometry 的协议标识 `geometry-1.0` 与能力版本是不同概念：协议兼容时实现和能力仍会更新。来源目录中的历史名称、旧 ZIP 或旧验证结果不为本次公开源码背书。以当前 Git 提交、逐文件 SHA-256 清单及实时 `contract` 定位实际版本。

## 公开许可

2026-10-13，作者明确授权封装并公开发布其自有代码。本仓库自有实现和文档以 `Copyright (c) 2026 jiefeiyang74-netizen` 的 [MIT](../LICENSE) 发布；此前本地包没有附随 LICENSE 的历史状态不再作为此公开版本的许可说明。

第三方抖音基础源码来自 vangie/douyin-transcriber，保留 BabelCloud MIT 原版权及许可。新增或修改部分不能覆盖原有第三方权利。详见 [第三方说明](../THIRD_PARTY_NOTICES.md) 和 [抖音 NOTICE](../assets/douyin/NOTICE.md)。

外部依赖版本和下载来源记录在 runtime-lock；运行环境、二进制、系统字体、模型和浏览器均不随此源码发行版附带，各适用自己的许可证。FFmpeg 锁定构建为 GPL，不能套用本仓库 MIT。将来若另行分发运行时，须单独履行其适用许可和对应源码提供条件。

## 公开包内容与验证

源码发行版包含 Skill 入口、UI 元数据、执行脚本、必要引擎、导演提示词、运行时锁文件、通用示例、维护测试与合成 fixture 源码。测试输入在运行时生成，不包含私人题目、稿件、音视频或历史产物。

排除虚拟环境、真实运行配置、模型缓存、日志、浏览器会话、密钥、`node_modules`、编译产物、Python cache 与备份文件。实际运行配置在目标机器生成；不引用作者电脑路径。

验证和中间证据存放在包外。封包后解压到独立目录，比较相对路径、文件数和 SHA-256；检查重复条目、路径逃逸及私有材料。当前验证范围记录在 [VALIDATION.md](../VALIDATION.md)。本机独立目录测试不等于第二台全新 Windows、首次完整联网安装、真实新抖音作品或最大长课已通过。
