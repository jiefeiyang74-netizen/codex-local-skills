# 原像素 Logo 抠图与替换

使用用户提供的 Logo 原图像素，去掉近白底后合成到海报或活动图片。保持画布尺寸、原有透明度和合成区域外的像素，输出新 PNG。Logo 的字形、图案不会交给 AI 重新绘制。

## 安装与依赖

需要 Python 3.10+。运行依赖只有 [Pillow](https://pillow.readthedocs.io/)；无需 Node.js、图像生成 API、账号或密钥。脚本可独立运行，Codex Skill 安装是可选的。

```powershell
git clone https://github.com/jiefeiyang74-netizen/codex-local-skills.git
cd codex-local-skills/skills/replace-logo-with-cutout
python -m pip install -r requirements.txt
```

作为 Codex Skill 使用时，将完整的 `replace-logo-with-cutout` 目录复制到自己的技能目录：有 `CODEX_HOME` 时使用其下的 `skills`；否则使用 `~/.codex/skills`。该目录应包含 `SKILL.md`、`agents/`、`scripts/` 和 `requirements.txt`，运行脚本前安装依赖。

在 Codex 中调用：`用 $replace-logo-with-cutout 将海报中的 Logo 替换为我提供的原图，输出新文件。`

## 无品牌演示

以下命令只生成几何三角形和色块，没有真实 Logo 或客户图片。在本技能目录运行：

```powershell
python scripts/create_demo.py --output-dir demo
python scripts/apply_logos.py --base demo/base.png --logo-specs demo/placements.json --output demo/result.png
```

`demo/result.png` 保留 480×320 画布，在指定位置添加去白底三角形。再次运行时请选择新的输出文件名；演示生成器也拒绝覆盖已有输入。

## 使用自己的图片

先准备干净底图；若原 Logo 仍在，需只擦除其所在区域并修复局部背景，再用原 Logo 像素合成。脚本不会自动擦除旧图案。

```powershell
python scripts/apply_logos.py --base clean-base.png --logo-specs placements.json --output final.png
```

`placements.json` 是非空 JSON 数组，按数组顺序叠放 Logo：

```json
[
  {
    "path": "original-symbol.png",
    "cx": 240,
    "cy": 220,
    "max_width": 70,
    "max_height": 60,
    "white_threshold": 235,
    "remove_white": true
  }
]
```

| 字段 | 含义 |
|---|---|
| `path` | Pillow 支持的像素图片文件；相对路径从 JSON 所在目录解析，SVG 需先转为像素图 |
| `cx`、`cy` | 去掉透明边距后的 Logo 中心坐标，单位为底图像素 |
| `max_width`、`max_height` | 正整数最大宽高；保持比例，只缩小，不放大 |
| `crop` | 可选 `[left, top, right, bottom]` 整数裁剪框，先裁剪再去底，须位于 Logo 内 |
| `white_threshold` | 可选 `1..255` 整数，默认 `235`；各 RGB 分量均达到阈值时去除，在阈值前 30 级内渐变降低 alpha |
| `remove_white` | 可选布尔值，默认 `true`；透明底原图含白色图案时设为 `false` |

去白底按像素颜色处理，会同时影响 Logo 内部的近白色内容。需要保留白色字形时，使用已经透明的原图，并关闭去白底。灰白半透明像素会在原 alpha 基础上降低透明度，不会提高不透明度。

输出只支持 PNG，以保留透明度及未编辑区域像素。底图、Logo、JSON 和任何已有输出都不会被覆盖。错误尺寸、超出画布、空白 Logo、缺失字段、坏图片或坏 JSON 会报错，并在合成完成前停止写入输出。

## 实现与验证

核心脚本是 `scripts/apply_logos.py`；运行期间仅在本机读写指定文件，不联网、不执行外部命令。保留 Pillow 的大图保护。像素合成不包含对旧 Logo 的智能擦除，最终仍需查看原尺寸效果，确认边缘、位置、排列和周围内容。

已在 Windows、Python 3.13.7 下分别用 Pillow 11.3.0 和独立环境安装的 12.3.0 完成 34 项检查，覆盖真实 CLI 合成、透明度、位置与尺寸、区域外像素、错误输入、异目录路径和拒绝覆盖输入。无品牌演示也已运行并查看输出。其他操作系统及 Python 版本尚未实测。

软件采用 [MIT](LICENSE) 许可证。包内不包含客户图片或真实品牌素材。
