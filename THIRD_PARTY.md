# 第三方代码与依赖

根目录及各技能的 MIT 许可证适用于用户自有的代码和文档。以下项目保留原有权利和许可边界。

| 范围 | 来源 | 处理方式 |
|---|---|---|
| 数学技能附带的抖音提取源码 | BabelCloud 的 douyin-transcriber | 原始 MIT 许可证保留于 `skills/manim-math-workbench/assets/douyin/source/LICENSE`，对应版权归 BabelCloud |
| 数学环境中的 Python、Manim、FFmpeg、whisper.cpp、模型等 | 数学技能运行锁文件中列出的原始下载源 | 按需下载，不附带环境或二进制；各自许可证、模型使用条件及再分发要求继续适用 |
| Logo 图像处理依赖 | Pillow | 作为外部依赖安装，不复制其源码或二进制；原许可证继续适用 |
| App Factory 的可选专业技能 | Keel 及专业开发技能的各上游项目 | 本仓库只说明调用关系，不附带第三方技能源码 |

数学源码的详细来源见 [provenance.md](skills/manim-math-workbench/references/provenance.md)。特别是，FFmpeg 的具体下载构建可能采用 GPL；本仓库的 MIT 许可不改变该构建的许可和再分发义务。公开源码仓库与下载后的运行环境应分别处理。
