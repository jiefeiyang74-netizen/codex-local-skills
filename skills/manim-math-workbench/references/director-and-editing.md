# 分镜与对话编辑

## Codex 直接规划

`contract` 是当前权威接口，不要凭旧网页或示例猜字段。先按任务选择管线：geometry-1.0 读取 [geometry](geometry.md) 与 `assets/engine/prompts/geometry_director.md`，使用 chapters/objects/actions/checks；不要套用下面的 generic beat 字段。以下 beat/equations/entity 约束仅适用于 generic 管线，规划时读取 `assets/engine/prompts/animation_director.md` 和 `storyboard.py:STORYBOARD_SYSTEM_PROMPT`，只返回一个 JSON 对象：

- `schema_version` 必须等于 contract 的实际版本；实体 id 是小写标识，`kind` 只能来自能力表。
- 每个 beat 的 `narration` 是完整旁白的连续原文；所有动作 `anchor` 必须逐字出现在该 beat 中。
- `equations` 保留同一份原题板；推导放在 `derivation`；最后一个 beat 必须是 `summary`。
- 图形必须先 `show_whole` 再分割，再抽取/汇集；相同图形以 entity/instance 区分，不去重。
- `unsupported_requirements` 只要包含当前执行器不支持的核心要求，runner 就拒绝渲染。

可执行动作和字段以 `contract` 输出为准。不要添加 `target`、自由路径、任意旋转或未列出的参数；公式动作使用当前支持的 `row`，图解动作使用精确 `entity`/`instance`。

## 视觉与连续性

- 黑底、顶部黄色标题，不烧录底部旁白字幕；无指定画幅时默认 3:4，用户指定的支持画幅写入本期 canvas；公式、几何对象、颜色、尺寸和方向跨场景可追踪。
- 动效服务于旁白中的词组，不做逐字弹跳；红色虚线圆角框只跟随当前对象/子式。
- 先完整显示图形，讲到切分时才生长分割线，讲到取份时才从真实图形抽离。不要用静态字幕卡替代未实现的几何动作。
- 顶部原题保留；工作副本移动至推导区时保留来源和重复对象。`clear_work` 不等于清除图解。

## 对话修改

恢复安装版任务时，读取指定 attempt 的 `manifest.json`、`request.json` 和 report，确认这是用户要修改的版本。分镜优先用项目保存的原始输入；generic attempt 有 `storyboard_input.json`，geometry attempt 有 `storyboard_normalized.json`，不强求另一管线的文件。保留输入原件和旧 attempt，把 request 与分镜复制到新的编辑目录，只修改授权字段，不手改生成 Python。检查原音频是否仍存在；迁移时修正新 request 的输入路径并核对内容，包括音频、对齐和审计附件，不能重新生成音频冒充原件。

重新运行 `contract`，核对 schema、能力和 `editable_fields`；后者为空的专用路线不能声称普通 JSON 编辑必然生效。Codex 根据新要求修改分镜，检查跨 beat 对象生命周期和音频锚点，然后使用相同 JobDir、新输入路径执行 preview，生成新的 attempt。查看真实动作片段后再 final，交付新 manifest 指向的成片及可继续编辑的输入文件。

这个恢复过程不依赖原网页应用。只有用户明确要求修改已有网页会话时，才读取其另行安装的工作台、旧会话和锁定段。

旁白或音频一旦改变，旧对齐不可复用；仅改视觉分镜时可复用有效 alignment，但必须更新分镜与动作审计，并记录当前代码及输入身份。geometry 和 generic 的缓存绑定不同，按对应管线校验，不手改哈希伪造匹配。未实现的核心效果按 SKILL.md 的能力缺口与已有授权规则处理，不降低为“看起来差不多”。
