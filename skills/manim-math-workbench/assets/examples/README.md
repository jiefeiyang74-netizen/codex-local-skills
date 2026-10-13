# 合成自检数据

`smoke_storyboard.json` 是 runner 内置 smoke 使用的非私人小分镜示例；`video.py smoke` 会在 job attempt 目录里重新生成同等输入和一段正弦 WAV，不读取用户历史音视频。这个音频没有语音，报告必须标记 `timing_source=synthetic_fixture`，不能当作 Whisper 逐字对齐证据。

`runtime-config.example.json` 只展示字段形状，路径必须由安装者按本机 runtime 填写，不能把真实机器路径提交进分发包。
