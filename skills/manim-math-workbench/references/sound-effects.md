# 动效音效（默认交付）

用户 2026-10-30 要求：之后的成片都配动效音效。音效是成片验收后的独立后处理，不进入分镜、不改动画、不改原成片。

适用范围：`scripts/add_sfx.py` 目前只读取 geometry 规范化分镜（`storyboard_normalized.json` 的 `chapters`）；generic/v3 分镜使用 entities/beats，尚未适配，直接传入会报错，需另行适配并验证后才能用于该分支。

## 流程

1. 照常完成 preview → visual_review → final。无音效 final 留在其 attempt 中作为 add_sfx 输入和回退材料。
2. 用 runtime venv 的 python 运行：

```powershell
& <runtime python> .\scripts\add_sfx.py `
  --storyboard <final attempt>\storyboard_normalized.json `
  --video <final attempt 的无音效成片>.mp4 `
  --out <项目>\成片_vN_音效版\<名称>_音效版_<W>x<H>_<fps>fps.mp4 `
  --runtime-config <runtime.json>
```

3. 核对：视频流帧数与原成片一致（视频流 `-c:v copy`，不重新编码）、整片可解码、音轨双声道；报告 `*.sfx_report.json` 记录每个音效的时间、类型、来源动作索引和响度。
4. 交付份数：清柏思维等已确认只交音效版的账号（见[已确认账号偏好](account-preferences.md)）或用户明确要求时，只交付音效版成片，无音效 final 不另复制到交付区或打包；其他情况按本次约定交付。已有项目里的无音效文件不因此删除。按实际听审范围报告（记录方式见[维护与验收](maintenance-and-qa.md)）：未试听就写明未试听、不写通过，请用户听后反馈响度或类型。

## 动作与音色

时间取自分镜动作计划的 `at`/`duration`，音效按计划时间放置；这只是计划定位，不等于已实测音画同步，实际对应要在当前输出上抽帧、试听核验后据实报告。音色由脚本程序合成，无外部素材和版权依赖。

| 动作 | 音效 |
|---|---|
| reveal + draw（画线、画圆） | pencil：铅笔沙沙声，长度随绘制时长（≤0.9s） |
| reveal 含 heavy 粗体大字（片头） | thump：低频“咚” |
| reveal 面板/卡片 | paper：纸张轻拍 |
| reveal 文字或点 | pop：短促“啵” |
| highlight | ding：轻铃 |
| set_parameter / move / move_on_circle / 复制运动 | whoosh：风声，长度随运动（≤1.8s） |
| text_transform | tick：清脆“嗒” |
| hide、纯填充淡入 | 不配音 |

`--min-gap`（默认 0.22s）内只留优先级最高的一个（ding/thump > whoosh > pencil > paper > pop > tick），避免密集动作堆成噪声。

## 调整

- 整体响度：`--gain-db`，默认 -12（第38条实测：人声有效 RMS ≈ -15 dB，音效 ≈ -31 dB）。用户嫌吵就降到 -16 左右，嫌听不见就升到 -8。
- 关掉某类：`--no-ding`、`--no-pop` 等。
- 输出已存在时拒绝覆盖，换新文件名或新版本目录。
- 只在混音会削波时整体压低，报告 `limiter_scale` 记录压低比例。
