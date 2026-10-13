# 第三方来源与许可

## 仓库内的第三方源码

`assets/douyin/source/internal/downloader/downloader.go`、`internal/resolver/resolver.go` 与 `internal/transcriber/local.go` 基于 [vangie/douyin-transcriber](https://github.com/vangie/douyin-transcriber) 的提交 `80fc29b7edcfcc3e56eade5a40c54e1c7f564aaf`，含本地已有的 CDN/浏览器回退和边界修改，不是该提交逐字快照。

上游为 MIT，Copyright (c) 2026 BabelCloud。保留完整 [原许可证](assets/douyin/source/LICENSE)，并已对照[该提交的许可证](https://github.com/vangie/douyin-transcriber/blob/80fc29b7edcfcc3e56eade5a40c54e1c7f564aaf/LICENSE)。新增 local-only CLI、URL guard 和适配服务的维护贡献归本仓库作者；原有版权声明仍适用。其余分文件说明见 [assets/douyin/NOTICE.md](assets/douyin/NOTICE.md)。

## 安装时获取的依赖

下列运行环境不随本源码仓库或源码 ZIP 附带。安装器从 `assets/runtime-lock.json`、`assets/douyin/runtime-lock.json` 与 npm 锁文件指定来源获取，原有许可证和通知保留在下载的运行环境中。

| 组件 | 许可概况与来源 |
|---|---|
| Manim Community | MIT；[Manim](https://github.com/ManimCommunity/manim)。本工作台封装并非 Manim 官方发布。 |
| whisper.cpp / Whisper 模型 | MIT；[whisper.cpp](https://github.com/ggml-org/whisper.cpp)、[Whisper](https://github.com/openai/whisper)。模型与下载文件适用各自随附材料。 |
| FFmpeg | 本锁文件选用 BtbN 的 GPL 构建；[下载来源](https://github.com/BtbN/FFmpeg-Builds)、[FFmpeg 许可说明](https://ffmpeg.org/legal.html)。MIT 不覆盖该二进制或库；另行分发须核对其具体构建许可证和对应源码义务。 |
| PyAV 及其 FFmpeg 库 | [PyAV](https://github.com/PyAV-Org/PyAV) BSD-3-Clause，随 wheel 的 FFmpeg/其他库各有适用许可；查看安装产物，不用 PyAV 的许可证替代其依赖许可证。 |
| uv / Python | [uv](https://github.com/astral-sh/uv) MIT / Apache-2.0；[CPython](https://github.com/python/cpython) PSF 及随附第三方许可。 |
| Node.js / Go | [Node.js](https://github.com/nodejs/node) MIT 及随附第三方许可；[Go](https://go.dev/LICENSE) BSD-3-Clause 及随附第三方许可。 |
| Playwright Core / 浏览器 | [Playwright](https://github.com/microsoft/playwright) Apache-2.0；Edge/Chrome/Chromium 各自的许可与第三方通知，系统浏览器不随本仓库发布。 |
| Pillow / NumPy / 其他 Python 包 | 每个锁定包分别适用其包内 LICENSE / NOTICE / METADATA；不宣称全部依赖均为 MIT。 |
| 系统微软雅黑 | 使用目标 Windows 的已安装字体；不从本仓库重新分发字体文件，不授予字体许可。 |

源码开源不等于可以将所有运行时、字体、模型和用户素材任意打包再发布。若制作二进制便携发行版，必须针对实际包含的文件重新汇总适用许可与通知，并履行其再分发条件。
