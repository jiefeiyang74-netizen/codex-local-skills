# App Factory · App 项目流程编排

把一个 App 想法推进为可验收的产品：先明确 MVP 和产品需求，再完成交互与架构，随后实现、验证、部署准备、发布和维护。已有项目从当前阶段继续，普通修复和小改动不重启完整规划。

这是 Codex 的工作流程 Skill，不是自动部署服务，也不包含 App 源码模板、第三方技能或云账户凭据。

## 输入与交付

你可以提供产品想法、目标用户、已有项目、当前问题或希望完成的阶段。技能按实际任务组织以下成果：

| 阶段 | 典型交付 |
| --- | --- |
| 产品规划 | 问题与用户、MVP 边界、PRD、用户故事及验收标准 |
| 交互与架构 | 用户旅程、关键状态、技术选型、数据/API 边界、实现和验证计划 |
| 实现与质量 | 已授权功能、适当的运行验证、缺陷修复、实际测试与残留问题记录 |
| 部署与发布 | 可复现的部署方案、回滚与监控、发布材料和实际发布范围 |
| 维护 | 优先级清晰的迭代任务，以及当前阶段和待解决事项 |

默认保留产品规划 → 架构 → 实现的先后关系。生产变更、公开发布、付费、敏感数据传输、对外发送消息和破坏性操作需要覆盖该动作的明确授权；已有授权直接复用。

## 安装

仓库：[jiefeiyang74-netizen/codex-local-skills](https://github.com/jiefeiyang74-netizen/codex-local-skills)。技能目录为 `skills/app-factory`。

在 Codex 中发送：

```text
请从 https://github.com/jiefeiyang74-netizen/codex-local-skills 安装 skills/app-factory 这个 Skill。保留已有同名版本，不自动安装可选第三方技能。
```

也可下载或克隆仓库，在仓库根目录运行下面的 PowerShell 示例。目标存在时脚本会停止，请先备份已有版本并选择新的安装位置或明确替换。

```powershell
$sourceSkill = Join-Path (Get-Location) 'skills\app-factory'
$skillRoot = if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME 'skills'
} else {
    Join-Path $env:USERPROFILE '.codex\skills'
}
$targetSkill = Join-Path $skillRoot 'app-factory'
if (!(Test-Path -LiteralPath (Join-Path $sourceSkill 'SKILL.md'))) {
    throw '请在下载或克隆后的仓库根目录运行此示例。'
}
if (Test-Path -LiteralPath $targetSkill) {
    throw '已存在 app-factory，请先备份并明确替换方式。'
}
New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
Copy-Item -LiteralPath $sourceSkill -Destination $skillRoot -Recurse
```

安装后开启新聊天；若尚未发现该技能，刷新或重启 Codex。不同环境的技能根目录可能不同，以当前环境发现结果为准。最终结构应为 `app-factory/SKILL.md`，不要多嵌套一层同名文件夹。

## 使用示例

```text
使用 $app-factory 规划一个宠物预约 App，先定义首版 MVP、用户旅程和验收标准，然后完成架构。
```

```text
使用 $app-factory 继续这个已有项目。MVP 与架构已经确定，本次只修复预约失败的问题，验证受影响流程并记录结果。
```

技能只编排工作，不承诺完成任意 App，也不会因为调用技能就获得发布、账户访问或额外执行权限。

## 可选第三方技能

`keel` 可以补充生命周期复核；`app-builder`、前后端、移动端、数据库、测试、安全和部署类技能可以在对应阶段按需调用。具体名称见 [SKILL.md](SKILL.md)。

它们全部是可选依赖。本包不复制第三方 Skill 正文、代码、模板或资源，也不自动安装它们。未安装时可以继续使用本技能的阶段交付和验收标准；仅当实际缺少必要能力或账户访问时，说明具体阻塞并继续独立工作。第三方技能的许可由其各自来源决定，本包的 MIT 许可不覆盖它们。

## 包内文件与许可

- [SKILL.md](SKILL.md)：编排流程、范围与阶段验收条件。
- [agents/openai.yaml](agents/openai.yaml)：Codex 界面元数据。
- [PROVENANCE.md](PROVENANCE.md)：来源、整理范围和第三方边界。
- [LICENSE](LICENSE)：MIT 许可，Copyright 2026 jiefeiyang74-netizen。

仅安装该技能不需要 Node、Python、Docker 或任何第三方服务。实际 App 开发使用的工具与依赖按项目决定。
