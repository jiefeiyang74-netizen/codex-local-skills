# 白名单来源及许可

本目录是本地单视频输入适配器，不是原项目快照。

- `source/internal/downloader/downloader.go`、`resolver/resolver.go`、`transcriber/local.go`：来自 vangie/douyin-transcriber，本地 checkout 基线提交 `80fc29b7edcfcc3e56eade5a40c54e1c7f564aaf`，包含本地已有的 CDN/浏览器回退修复；不能称为该提交的逐字副本。保留 `source/LICENSE`（BabelCloud，MIT）。移植修改包括严格 URL 边界；新增 local-only CLI 不包含云 API 实现。
- `web/scripts/fetch_douyin_media.mjs`：已有本地工作台的浏览器辅助实现，仅新建临时上下文，不加载个人 profile/cookies；随作者授权移植。与新 API/脚本一同作为本 Skill 的维护源码发布，不宣称其由上游 MIT 作者创作。
- `web/server.mjs`：新建兼容单任务 API，未复制原项目账号、Word、网页服务。
- Playwright Core：锁定 `package-lock.json` 的版本与 SHA-512 integrity；Apache-2.0，安装后保留包内 LICENSE/NOTICE。Chromium 仅缺浏览器时由该锁定 Playwright 版本安装，下载器使用其固定 browser revision；遵循随附第三方许可。
- Node.js：官方 Windows ZIP，MIT 及随附第三方许可；Go：官方 Windows ZIP，BSD-3-Clause 及随附许可。URL/SHA-256 在 runtime-lock.json。来源校验页面为对应 Node SHASUMS256.txt 和 https://go.dev/dl/?mode=json&include=all 。已有可用 Node>=20/Go>=1.24 可复用，版本记录以本机实际可执行文件为准。
- whisper.cpp/small 模型、FFmpeg：复用上层 `assets/runtime-lock.json` 的锁定来源及 SHA-256；whisper.cpp/Whisper MIT，选用的 FFmpeg 是 GPL 构建。依赖在用户机器下载，Skill 不携带这些二进制；如另行分发二进制，需保留其许可并满足适用源代码提供义务。

禁止随本目录发布 node_modules、编译产物、runtime/config、runs、cookies、音视频、密钥或用户路径。setup 下载/构建结果位于包外。白名单只包含此目录源码、锁文件、许可和入口脚本；测试 fixture 现场生成，不收入私人媒体。

公开版本自有贡献采用根目录 MIT；该许可证不替代上述 BabelCloud 原有许可或外部依赖许可。维护测试与合成 fixture 源码可随源码发行版发布，运行产物留在包外。
