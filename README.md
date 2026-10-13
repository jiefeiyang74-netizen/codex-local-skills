# Codex Local Skills

三个可独立安装的 Codex 技能：数学视频制作、App 产品开发编排、原版 Logo 抠图替换。每个技能包含自己的入口、说明和必要源码；运行环境与模型按需准备。

| 技能 | 输入与交付 | 使用条件 |
|---|---|---|
| [manim-math-workbench](skills/manim-math-workbench/README.md) | 数学题、录音稿和原音频 → 验算、对齐分镜、对象动画、预览与成片 | Windows x64；首次环境准备需要网络和磁盘空间 |
| [app-factory](skills/app-factory/README.md) | 产品想法 → MVP、PRD、架构、实现、测试与发布材料 | Codex；可按当前阶段使用专业技能 |
| [replace-logo-with-cutout](skills/replace-logo-with-cutout/README.md) | 底图、原始 Logo 和位置配置 → 保持原像素的透明合成图片 | Python 与 Pillow；旧 Logo 需先擦除 |

## 安装

下载并解压本仓库或 Release 中的 ZIP。已有 Python 时，在仓库根目录运行：

```powershell
python tools/install_skills.py --list
python tools/install_skills.py --skill app-factory --dry-run
python tools/install_skills.py --all
```

安装器默认使用 `$CODEX_HOME/skills`；未设置时使用 `~/.codex/skills`。若当前环境使用不同的技能目录，用 `--target` 指定实际路径。已有同名技能时默认停止；明确使用 `--replace` 才会先备份到目标目录内的 `.backups`，再替换。安装器不会读取或复制任何账号凭据。

批量安装先检查全部目标，然后逐个提交。某项失败时会恢复该项旧版本并报告已成功安装的项目及备份路径；此前成功的项目保留，不自动回滚整个批次。可使用报告中的备份目录恢复旧版本。

也可以把单个技能 ZIP 附给 Codex，并发送：

> 请将这个 ZIP 中的 Skill 安装到当前环境实际使用的技能目录。先检查文件，保留已有版本备份，完成技能发现和必要运行检查。

仅安装 Skill 不代表其运行依赖已就绪。数学技能附带独立 Windows 环境准备流程；Logo 工具的依赖见对应目录。安装后若当前聊天未发现新技能，重新打开聊天。

## 调用示例

```text
用 $manim-math-workbench 核对这份数学稿，整理录音稿，再根据我回传的原音频制作数学动画。
用 $app-factory 开发一个预约 App，先明确用户、MVP 和架构。
用 $replace-logo-with-cutout 将原始 Logo 合成到已清理旧 Logo 的海报上。
```

用户已明确的选择和授权可继续沿用。App 技能不会因普通维护任务重新启动整个产品规划；产品范围、生产发布等动作按实际授权处理。

## 开源范围与来源

自有代码与文档采用 MIT 许可证。数学技能由自有 Manim Prompt Studio 执行子集封装并持续扩展；其中附带的 BabelCloud 抖音提取源码保留自己的 MIT 版权和许可证。详情见 [THIRD_PARTY.md](THIRD_PARTY.md) 及各技能的来源说明。

Keel、专业开发技能、Remotion 视频套件、电商视觉文案、聊天重命名等外部技能未复制进本仓库；其原始来源列在 [EXTERNAL_SKILLS.md](EXTERNAL_SKILLS.md)。下载的运行依赖各自适用原许可证，仓库 MIT 不覆盖这些依赖。

包内不含个人题目、真实音视频、模型、虚拟环境、浏览器数据或密钥。验证范围与已知限制见 [VALIDATION.md](VALIDATION.md)；通过格式检查不等于任意业务场景或全新电脑已端到端验证。

## 开发检查

```powershell
python -m pip install -r requirements-dev.txt
python tools/validate_repository.py
python -m unittest discover -s tests -v
```

本仓库的 CI 运行格式、公开文件、引用和安装安全检查。数学视频最终画面与音频同步仍须在实际制作任务中验收。
