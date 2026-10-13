from __future__ import annotations

import math
import re
from typing import Any
from .unit_equation import fraction_multiple_plan
from .equation_motion import equation_motion_tokens, equation_sum_mapping
from .part_motion import part_state_issues
from .capabilities import ALLOWED_KINDS, ALLOWED_ACTIONS, ACTION_FIELDS, BASE_FIELDS, capability_prompt


SCHEMA_VERSION = "4.3"
ALLOWED_LAYOUTS = {"title", "equations", "diagram", "derivation", "summary"}
DEFAULT_COLORS = ("#55B8FF", "#FF7CB9", "#FFA44D", "#8EDB72", "#FFD85C", "#B79CFF")
PLACEHOLDER_RE = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
BANNED_SCREEN_TEXT = (
    "点赞", "关注", "评论", "转发", "收藏", "二维码", "关注我",
    "说说你的", "留言",
)


class StoryboardValidationError(ValueError):
    def __init__(self, errors: list[str], issues=None):
        self.errors = errors
        self.issues = issues or []
        self.category = self.issues[0].get("category", "structure") if self.issues else "structure"
        super().__init__("；".join(errors))


STORYBOARD_SYSTEM_PROMPT = r"""
你是数学短视频的动画分镜导演，不是 Python 程序员。由你根据每道题和逐字旁白决定使用哪些对象、演算步骤、词组动作和连续状态，输出结构化 JSON；Python、3:4竖版排版、图形尺寸与安全动画组件由本机执行。

只返回一个有效 JSON 对象，不要 Markdown，不要代码围栏，不要解释。必须使用以下结构：
{
  "schema_version": "4.3",
  "title": "视频标题",
  "problem": "从用户内容还原的完整题目",
  "entities": [
    {"id":"sun","label":"小孙","kind":"triangle","color":"#55B8FF"},
    {"id":"jing","label":"小景","kind":"square","color":"#FF7CB9"}
  ],
  "beats": [
    {
      "id":"b01",
      "narration":"小孙加小景等于三千万美元。",
      "duration":3.2,
      "layout":"equations",
      "heading":"题目",
      "rows":[
        {"text":"{{sun}}＋{{jing}}＝3000万美元","accent":false}
      ],
      "focus":[0],
      "diagrams":[],
      "actions":[
        {"anchor":"小孙加小景","type":"show_formula","row":0},
        {"anchor":"等于三千万美元","type":"focus_formula","row":0}
      ]
    }
  ]
}

硬性规则：
画面约定：逐字旁白只用于音频对齐与动作锚点，禁止放进 rows/heading 作为底部字幕。必要的数学公式、数字、单位和“几份”标签正常保留。首个 show_whole 在演示区中央出现，同一对象后续切分、抽取仍保持中心位置；只有新增其他图形需要空间时，本机才将原图形连同分割线、抽出部分、标签和指向它的红框整体平滑移至侧边。不得为了排版重复 show_whole、复制旧图形或提前显示后续对象。
1. schema_version 必须是 4.3。实体 id 只能用小写英文字母、数字和下划线，并以字母开头；kind 只能是 circle、square、triangle、badge、rectangle。
2. 屏幕公式用 rows 表达。实体必须写成 {{实体id}}，其余运算符、数字、单位直接写文字。不得用 ○、□、△ 字符代替实体。
3. layout 只能是 title、equations、diagram、derivation、summary。共 4 至 60 个 beats，最后一个必须是 summary。第一处 equations 必须一次给出完整原题；本机将把标题和原题固定在上半区，后续过程不能反复重画原题。
4. 不得按整句粗略配画。必须按“有视觉含义的词组”建立逐词动作：每个 beat 的 narration 必须是用户逐字旁白中的连续原文；actions 中每个 anchor 必须逐字取自本 beat narration，并准确落在触发该变化的词组上。比如“已知”触发定位、“代入”触发替换、“相加”触发合并、“取一份”触发抽离、“所以/等于”触发结果。纯公式阶段允许用 rows 与带 row、anchor 的多个 actions 表达连续状态，混合图形阶段把多次公式变化拆成不同 beats。所有 beats 的 narration 按顺序完整覆盖逐字旁白，不得改写、漏句、重复或打乱。
5. focus 是当前 beat.rows 中需要红框的行号，从 0 开始；不需要时用空数组，summary 用 "all"。focus 只是定位信息，不自动安排逐词红框动作。每次改变讲解对象，必须显式添加有 anchor 的 focus_formula(row=N) 或 focus_diagram(entity/instance)。同时框多行使用 focus:[索引] 加 focus_formula(row=-1)；不是全片累计行号。
6. actions.type 只能使用本机白名单：show_text、show_formula、focus_formula、focus_diagram、show_whole、partition_shape、extract_part、isolate_part、assemble_whole、collect_parts、focus_part、restore_parts、transform_formula、substitute、combine、cancel、divide、show_answer、clear_work、hold、copy_equation、merge_equations。focus_formula 只框公式，focus_diagram 只框已经生成的可视化对象。大模型不能描述任意 Python、坐标或动画代码。每个可见变化必须有独立 action 和准确 anchor；同一 anchor 仅用于紧密相邻的短动作，执行器不保证这些动作并发，不能把后续所有步骤挤在开头。
7. 由你区分数值除法与图形等分：公式中的÷不自动要求切图。若旁白明确“把图形平均分成N份/取一份”，使用 layout="diagram"、diagrams 和对应 show_whole、partition_shape、extract_part 动作；仅计算数值或求一个未知量可使用公式推导，不得虚构切分过程。圆、方形、三角形支持1至12等份；图形必须先出现再分割、再抽离，动作anchor分别对应实际触发词组，同一图形沿用同一instance。公式类 combine/cancel/divide/substitute 当前表示公式状态的平滑过渡，不代表任意几何对象的合并消去；真实等份移动必须使用collect_parts或assemble_whole。
8. 已经完成多个等份图形后，“这些每一份都相等”使用 focus_diagram 且 entity 留空，让红色圆角虚线框包住全部切分图形；连续的“这里是几份”必须分别使用 focus_diagram，并把 entity/instance 指向真实对应图形。顺序由本次原稿决定，不固定为圆、方、三角。禁止另建彩色底板或把图形红框放到下方数字算式上。
9. rows 中 accent=true 仅用于关键结果。人物/图形颜色全程由 entities 锁定，不能在 beat 中改色、缩放或重新定义。
10. 严格保留题目左右顺序、数字和单位。heading 和 rows 严禁生成点赞、关注、评论、转发、收藏、二维码、水印、装饰人物；若用户逐字旁白本身含有结尾互动口播，narration 仍须原样保留，但画面继续停留在上一幅最终答案，绝不能显示互动文字。
11. 加、减、代入、抵消、合并、拆分等连续过程必须提供中间状态，使用多个 beats 或纯公式阶段多个带 row 的 actions 按顺序执行；禁止只给最终结果而跳过中间状态。重复 equations 的 rows 必须与第一块原题板完全一致，仅引用它；新的计算放 derivation。本机会保留顶部原题，并在下半区平滑更新推导，而不是整页切换。
12. 最终 summary 的 rows 只放最终答案，格式优先写为“{{实体id}}＝最终数值”。本机会把短数值平滑回填进顶部原公式中的图形，并保留下方切分图形与计算结果；不得生成重复的“最终答案”大标题或复制上一阶段全部推导。
13. 用户题目留空时，从逐字旁白中还原 problem；信息不足时如实写明，不得虚构。
14. 当旁白说“把这些小份合起来/全部加一起/一共N份”且对应图形已经切好时，使用 collect_parts 真正移动图形，不能只用 combine 更新文字。示例：{"type":"collect_parts","anchor":"这些一共是10份","count":10,"total":"50","targets":[{"entity":"box","instance":0,"selection":"selected"},{"entity":"box","instance":1,"selection":"all"},{"entity":"box","instance":2,"selection":"all"},{"entity":"box","instance":3,"selection":"all"}]}。targets 指向此前已经出现的图形副本，selection 可为 visible（当前可见部分）、all（完整等份）、selected（已抽出的最后一份）。本机会将这些等份保持原大小、方向汇集为整齐的一组，红框包住整组，再显示总和；total 只能用已知总数，不能把“10份”写成“10美元”。不得在旁白尚未说到切分时提前生成九块。一个被丢弃的余下部分不能又计入汇集。
15. 紧接“每一份/其中一份”用 focus_part（part_index 从0开始），红框平移到汇集组中的一份，其余份降低亮度；当前 rows 显示对应的除法或单份数值。需要回到原来摆放位置时使用 restore_parts。需要把同一图形的等份拼回完整图形时使用 assemble_whole 并指定 entity、instance。每次新增完整图形必须分配独立 instance，后续切分、汇集和拼回必须沿用相同编号。
16. 每个 derivation 通常只放当前 1～2 个状态，不能堆积历史推导。每个稍后出现的行必须有对应内容动作和原文 anchor；未引用的 rows 会立即作为上下文显示，绝不能放未来答案。substitute/cancel/divide 等目标式必须确实体现本次运算，并给出中间状态，不得以重复同一式子冒充变化。
17. 新增白名单动作 copy_equation、merge_equations。引用已有两条等式准备相加时，分别 copy_equation(source_row:顶部行号,slot:0或1,row:当前目标行号)，将整式副本从顶部平移到中部上下两行；原题不动，第二组进入时第一组保留。随后 merge_equations(slots:[0,1],row:目标行号) 使用现有副本按项平移成（左式1）＋（左式2）＝右式1＋右式2。右侧多项须加括号，不得提前计算、不丢任何图形。这两种动作仅用于无切分图占据演算区的derivation，额外字段仅source_row/slot和slots；不得重复占用槽位或合并不存在副本。下一句才显示相加数值结果。
18. 上述新动作支持完整原式搬运和两组按项合并；合并后的单条公式用transform_formula/substitute/combine支持保留相同词项对象与尺寸的连续重组、代入、同类项合并。先括出已知子式，再代入数值，最后合并同类项，不得跳步。其他通用更新不代表任意子式复制、局部删除线或自由移动。超出能力须说明。示例数字不可套用到新题。
""".strip() + "\n\n" + capability_prompt()


PART_NUMBER_VALUES = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}
PART_NUMBER_PATTERN = r"(?:12|11|10|[1-9]|十二|十一|十|九|八|七|六|五|四|三|二|两|一)"


def build_storyboard_user_prompt(payload: dict[str, Any]) -> str:
    audio_timing = str(payload.get("audio_timing_summary", "")).strip()
    audio_block = audio_timing or "未提供音频，使用文案估算时间轴。"
    return (
        "请把下面定稿内容整理为 v4.3 逐词语义分镜 JSON。不要生成 Python。\n\n"
        f"【标题】\n{str(payload.get('title', '')).strip()}\n\n"
        f"【题目（可能为空）】\n{str(payload.get('problem', '')).strip()}\n\n"
        f"【逐字旁白】\n{str(payload.get('narration', '')).strip()}\n\n"
        f"【人物/图形映射】\n{str(payload.get('mapping', '')).strip()}\n\n"
        f"【屏幕文字规范】\n{str(payload.get('screen_text', '')).strip()}\n\n"
        f"【视觉与特殊要求】\n{str(payload.get('visual', '')).strip()}\n{str(payload.get('special', '')).strip()}\n\n"
        f"【音频强制时间轴】\n{audio_block}\n\n"
        "【分镜交付要求】\n"
        "按固定导演规范，把有视觉意义的词组拆成对象明确、前后状态连续的动作。"
        "每次红框改目标必须有显式 focus 动作；切分和抽离不能合成一个终态。"
        "代入、同减、求单份分别提供正确中间式；推导区通常只放当前1～2个状态，"
        "引用两条原式准备相加时，优先copy_equation分别搬来完整副本，再merge_equations复用项对象合并；不是整式淡换。"
        "不得堆积历史或提前显示后面的答案。逐字稿不改写，示例数据不套用。"
        "只使用执行器已支持的字段和能力；缺失的核心动作如实报告。"
        "核对数字、单位、对象顺序、anchor、row与最终答案后，只返回 JSON。"
    )


def _clean_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:limit]


def _lock_narration_excerpt(candidate: Any, narration: str) -> str:
    """Keep only a verbatim excerpt of the user-approved narration.

    Models occasionally turn a short final line into a newly written summary.
    Narration is immutable in v3, so an invented excerpt is discarded locally
    instead of triggering another paid model request. Whitespace-only layout
    differences are accepted while the returned text still comes from the
    original narration.
    """
    excerpt = _clean_text(candidate, 500)
    if not excerpt or not narration:
        return ""
    direct = narration.find(excerpt)
    if direct >= 0:
        return narration[direct:direct + len(excerpt)]

    compact_source: list[str] = []
    source_indexes: list[int] = []
    for index, character in enumerate(narration):
        if not character.isspace():
            compact_source.append(character)
            source_indexes.append(index)
    compact_excerpt = "".join(character for character in excerpt if not character.isspace())
    if not compact_excerpt:
        return ""
    compact_start = "".join(compact_source).find(compact_excerpt)
    if compact_start < 0:
        return ""
    source_start = source_indexes[compact_start]
    source_end = source_indexes[compact_start + len(compact_excerpt) - 1] + 1
    return narration[source_start:source_end].strip()


def _normalise_color(value: Any, fallback: str) -> str:
    color = str(value or "").strip().upper()
    if re.fullmatch(r"#[0-9A-F]{6}", color):
        return color
    return fallback


def _normalise_entity(raw: Any, index: int, used: set[str]) -> dict[str, Any]:
    value = raw if isinstance(raw, dict) else {}
    proposed = re.sub(r"[^a-z0-9_]", "_", str(value.get("id") or f"entity_{index + 1}").lower()).strip("_")
    if not proposed or not proposed[0].isalpha():
        proposed = f"entity_{index + 1}"
    proposed = proposed[:32]
    base = proposed
    suffix = 2
    while proposed in used:
        proposed = f"{base}_{suffix}"
        suffix += 1
    used.add(proposed)
    kind = str(value.get("kind") or "badge").lower().strip()
    aliases = {"round": "circle", "person": "badge", "text": "badge"}
    kind = aliases.get(kind, kind)
    if kind not in ALLOWED_KINDS:
        kind = "badge"
    return {
        "id": proposed,
        "label": _clean_text(value.get("label") or proposed, 16),
        "kind": kind,
        "color": _normalise_color(value.get("color"), DEFAULT_COLORS[index % len(DEFAULT_COLORS)]),
    }


def _normalise_row(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        text = raw
        accent = False
    elif isinstance(raw, dict):
        text = raw.get("text", "")
        accent = bool(raw.get("accent", False))
    else:
        text = ""
        accent = False
    return {"text": _clean_text(text, 180), "accent": accent}


def _normalise_focus(value: Any, row_count: int) -> list[int] | str:
    if str(value).lower().strip() == "all" or value == ["all"]:
        return "all"
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    result: list[int] = []
    for item in values:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= number < row_count and number not in result:
            result.append(number)
    return result


def _normalise_diagram(raw: Any, entity_ids: set[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    entity = str(raw.get("entity") or "").strip().lower()
    if entity not in entity_ids:
        return None
    try:
        parts = int(raw.get("parts", 1))
    except (TypeError, ValueError):
        parts = 1
    result = {
        "entity": entity,
        "parts": max(1, min(12, parts)),
        "caption": _clean_text(raw.get("caption"), 24),
        # This value is intentionally locked locally. The model may describe
        # what should happen, but it cannot replace the deterministic motion
        # with an already-partitioned static picture.
        "animation": "show_then_partition",
    }
    # A known instance must survive cache -> normalization -> render unchanged.
    if isinstance(raw.get("instance"), int) and 0 <= raw["instance"] < 60:
        result["instance"] = raw["instance"]
    return result


def _normalise_action(raw: Any, entity_ids: set[str], narration: str, allow_silent: bool = False) -> dict[str, Any] | None:
    """Accept only phrase-anchored declarative actions from the model.

    The model may choose *what* should change, but it cannot provide Python,
    coordinates, animation class names, or arbitrary parameters.  The anchor is
    locked back to the user's exact narration so a hallucinated phrase can
    never become a timestamp.
    """
    if not isinstance(raw, dict):
        return None
    action_type = str(raw.get("type") or "").strip().lower()
    aliases = {
        "highlight": "focus_formula",
        "focus": "focus_formula",
        "focus_shape": "focus_diagram",
        "highlight_shape": "focus_diagram",
        "show": "show_formula",
        "replace": "substitute",
        "merge": "combine",
        "result": "show_answer",
    }
    action_type = aliases.get(action_type, action_type)
    if action_type not in ALLOWED_ACTIONS:
        raise StoryboardValidationError([f"不支持的动作类型：{action_type or '(空)'}；请使用已实现的动画组件或说明能力不足"],
            [{"category": "capability", "code": "ACTION_UNSUPPORTED", "action_type": action_type}])
    anchor = _lock_narration_excerpt(raw.get("anchor"), narration)
    if not anchor and not (allow_silent and not narration and not raw.get("anchor") and action_type in {"show_answer", "focus_formula", "hold"}):
        return None
    entity = str(raw.get("entity") or "").strip().lower()
    if entity not in entity_ids:
        entity = ""
    try:
        row = int(raw.get("row", -1))
    except (TypeError, ValueError):
        row = -1
    try:
        parts = int(raw.get("parts", 1))
    except (TypeError, ValueError):
        parts = 1
    # A cached, already-normalised storyboard may point at one of several
    # simultaneously visible copies of the same entity.  Keep that bounded
    # declarative target across later local recompiles.  Dropping it here made
    # a second normalisation silently retarget a focus action to the newest
    # copy, so preview and final render could disagree despite identical JSON.
    try:
        instance = int(raw.get("instance", -1))
    except (TypeError, ValueError):
        instance = -1
    action = {
        "anchor": anchor,
        "type": action_type,
        "entity": entity,
        "row": max(-1, min(5, row)),
        "parts": max(1, min(12, parts)),
        "instance": max(-1, min(59, instance)),
        # Extraction direction is deliberately locked to the reference style.
        "direction": "down_right",
    }
    if action_type == "copy_equation":
        for field, maximum in (("source_row", 5), ("slot", 1)):
            value = raw.get(field)
            if type(value) is not int or not 0 <= value <= maximum:
                raise StoryboardValidationError([f"copy_equation 的 {field} 必须为0至{maximum}的整数"])
            action[field] = value
    if action_type == "merge_equations":
        slots = raw.get("slots")
        if not isinstance(slots, list) or len(slots) != 2 or any(type(v) is not int for v in slots) or set(slots) != {0, 1}:
            raise StoryboardValidationError(["merge_equations 的 slots 必须是 [0,1] 或 [1,0]"])
        action["slots"] = list(slots)
    if action_type in {"collect_parts", "focus_part", "restore_parts"}:
        for field, maximum in (("count", 72), ("part_index", 71)):
            try:
                value = int(raw.get(field, 0))
            except (TypeError, ValueError):
                raise StoryboardValidationError([f"{action_type} 的 {field} 必须是整数"])
            if not 0 <= value <= maximum:
                raise StoryboardValidationError([f"{action_type} 的 {field} 超出范围"])
            action[field] = value
        total = str(raw.get("total") or "").strip()
        if total and not re.fullmatch(r"[+-]?\d{1,12}(?:\.\d{1,6})?(?:万|亿|千|百)?(?:美元|元)?", total):
            raise StoryboardValidationError(["汇集总数必须是已知数值及单位"])
        action["total"] = total
        targets = raw.get("targets") or []
        if not isinstance(targets, list) or len(targets) > 12:
            raise StoryboardValidationError(["汇集 targets 必须是最多12个已存在图形目标"])
        action["targets"] = []
        for target in targets:
            if not isinstance(target, dict) or target.get("entity") not in entity_ids:
                raise StoryboardValidationError(["汇集动作引用不存在的图形"])
            try:
                target_instance = int(target.get("instance", 0))
            except (TypeError, ValueError):
                raise StoryboardValidationError(["汇集图形编号必须是整数"])
            selection = str(target.get("selection", "visible"))
            if not 0 <= target_instance <= 59 or selection not in {"visible", "all", "selected"}:
                raise StoryboardValidationError(["汇集图形编号或选取范围不正确"])
            normalized_target = {"entity": target["entity"], "instance": target_instance, "selection": selection}
            if normalized_target not in action["targets"]:
                action["targets"].append(normalized_target)
    return action


def _first_exact_anchor(text: str, patterns: tuple[str, ...], fallback_limit: int = 12) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip("，。！？；;、 \n")
    stripped = str(text or "").strip("，。！？；;、 \n")
    return stripped[:fallback_limit]


def _entity_names(entity: dict[str, Any]) -> tuple[str, ...]:
    kind_aliases = {
        "circle": ("圆圈", "圆形", "圆"),
        "square": ("正方形", "方框", "方形"),
        "triangle": ("三角形", "三角"),
        "badge": (),
    }
    names = [str(entity.get("label", "")).strip(), *kind_aliases.get(entity.get("kind", "badge"), ())]
    return tuple(dict.fromkeys(name for name in names if name))


def _part_spellings(parts: int) -> tuple[str, ...]:
    chinese = next((key for key, value in PART_NUMBER_VALUES.items() if value == parts and key != "两"), "")
    return tuple(value for value in (str(parts), chinese, "两" if parts == 2 else "") if value)


def _partition_word_actions(
    narration: str,
    diagram: dict[str, Any],
    entity: dict[str, Any],
) -> list[dict[str, Any]]:
    """Derive the reference four-step motion directly from exact spoken words."""
    text = str(narration or "")
    entity_id = str(diagram.get("entity") or "")
    parts = int(diagram.get("parts", 1))
    names = _entity_names(entity)
    number_words = _part_spellings(parts)
    name_pattern = "(?:" + "|".join(re.escape(name) for name in names) + ")"
    number_pattern = "(?:" + "|".join(re.escape(number) for number in number_words) + ")"
    division_match = re.search(rf"{name_pattern}\s*(?:除以|÷)\s*{number_pattern}", text)
    division = division_match.group(0).strip() if division_match else ""
    partition_match = None
    for pattern in (
        rf"(?:就是)?把(?:一个)?{name_pattern}.{{0,5}}?平均分成{number_pattern}份",
        rf"{name_pattern}.{{0,8}}?平均分成{number_pattern}份",
        rf"平均分成{number_pattern}份",
    ):
        partition_match = re.search(pattern, text)
        if partition_match:
            break
    partition = partition_match.group(0).strip() if partition_match else ""
    take_match = re.search(r"取(?:出)?(?:其中)?(?:的)?一份", text)
    take = take_match.group(0) if take_match else ""
    start_anchor = division or partition
    actions = [
        {"anchor": start_anchor, "type": "focus_formula", "entity": entity_id, "row": -1, "parts": parts, "direction": "down_right"},
        {"anchor": start_anchor, "type": "show_whole", "entity": entity_id, "row": -1, "parts": parts, "direction": "down_right"},
    ]
    if parts > 1:
        actions.append({
            "anchor": partition or division,
            "type": "partition_shape",
            "entity": entity_id,
            "row": -1,
            "parts": parts,
            "direction": "down_right",
        })
    if take and start_anchor:
        actions.append({
            "anchor": take,
            "type": "extract_part",
            "entity": entity_id,
            "row": -1,
            "parts": parts,
            "direction": "down_right",
        })
    return [action for action in actions if action.get("anchor")]


def _semantic_word_actions(beat: dict[str, Any]) -> list[dict[str, Any]]:
    """Add safe word-level actions for non-diagram mathematical language."""
    text = str(beat.get("narration", ""))
    layout = str(beat.get("layout", "derivation"))
    candidates: list[tuple[int, str, str]] = []
    patterns = (
        (
            r"已知|再看第[一二三四五]条|最后看第[一二三四五]条|求"
            r"|[^，。！？；;]{1,18}(?:加|＋)[^，。！？；;]{1,18}(?=(?:等于|＝))"
            r"|[^，。！？；;]{1,12}(?:是|有)\s*[0-9一二三四五六七八九十百千万两]+\s*份",
            "focus_formula",
        ),
        (r"代入|替换", "substitute"),
        (r"相加|加起来|全部加|合并|重新排列|排成|相等|每一份都相等", "combine"),
        (r"减去|抵消|约掉", "cancel"),
        (r"除以|总数除", "divide"),
        (
            r"所以|得出|算出|最终答案|答案"
            r"|(?:等于|＝)\s*[^，。！？；;]{1,14}"
            r"|每一份\s*(?:就是|就|等于|是)\s*[0-9一二三四五六七八九十百千万两]+",
            "show_answer",
        ),
    )
    for pattern, action_type in patterns:
        for match in re.finditer(pattern, text):
            candidates.append((match.start(), match.group(0), action_type))
    candidates.sort(key=lambda item: item[0])
    actions: list[dict[str, Any]] = []
    for _, anchor, action_type in candidates[:5]:
        actions.append({
            "anchor": anchor,
            "type": action_type,
            "entity": "",
            "row": beat.get("focus", [0])[0] if isinstance(beat.get("focus"), list) and beat.get("focus") else -1,
            "parts": 1,
            "direction": "down_right",
        })

    state_types = {"show_text", "show_formula", "transform_formula", "substitute", "combine", "cancel", "divide", "show_answer"}
    if not any(action["type"] in state_types for action in actions):
        default_type = {
            "title": "show_text",
            "equations": "show_formula",
            "summary": "show_answer",
        }.get(layout, "transform_formula")
        anchor = _first_exact_anchor(
            text,
            (r"所以[^，。！？；;]{0,10}", r"等于[^，。！？；;]{0,10}", r"[^，。！？；;]{2,14}"),
        )
        if anchor:
            actions.append({
                "anchor": anchor,
                "type": default_type,
                "entity": "",
                "row": -1,
                "parts": 1,
                "direction": "down_right",
            })
    if beat.get("focus") and not any(action["type"] == "focus_formula" for action in actions):
        anchor = actions[0]["anchor"] if actions else _first_exact_anchor(text, (r"[^，。！？；;]{2,12}",))
        if anchor:
            actions.insert(0, {
                "anchor": anchor,
                "type": "focus_formula",
                "entity": "",
                "row": beat.get("focus", [0])[0] if isinstance(beat.get("focus"), list) and beat.get("focus") else -1,
                "parts": 1,
                "direction": "down_right",
            })
    return actions


def _diagram_reference_actions(
    narration: str,
    available_diagrams: list[Any],
) -> list[dict[str, Any]]:
    """Map spoken deictic phrases back to already-rendered partition diagrams."""
    if not available_diagrams:
        return []
    states: list[dict[str, Any]] = []
    for index, item in enumerate(available_diagrams):
        if isinstance(item, dict):
            state = dict(item)
        else:
            values = list(item) if isinstance(item, (list, tuple)) else []
            if len(values) < 2:
                continue
            state = {
                "entity": str(values[0]),
                "parts": int(values[1]),
                "instance": int(values[2]) if len(values) > 2 else -1,
                "caption_count": int(values[3]) if len(values) > 3 and values[3] else None,
                "extracted": bool(values[4]) if len(values) > 4 else False,
                "label": str(values[5]) if len(values) > 5 else "",
            }
        state["order"] = index
        states.append(state)
    actions: list[dict[str, Any]] = []
    equal_match = re.search(r"(?:这|这些|这几|这三|这两|每一).{0,8}?份.{0,5}?相等|每一份都相等", narration)
    if equal_match and len(states) >= 2:
        actions.append({
            "anchor": equal_match.group(0),
            "type": "focus_diagram",
            "entity": "",
            "row": -1,
            "parts": 1,
            "direction": "down_right",
        })

    used_visuals: set[tuple[str, int]] = set()
    for match in re.finditer(
        rf"这里\s*(?P<qualifier>(?:一共|共有|总共)?)\s*(?:是|有)?\s*(?P<parts>{PART_NUMBER_PATTERN})\s*份",
        narration,
    ):
        parts = _part_number(match.group("parts"))
        qualifier = str(match.group("qualifier") or "")
        tail = narration[match.end():match.end() + 10]
        candidates: list[tuple[int, int, dict[str, Any]]] = []
        for state in states:
            entity_id = str(state.get("entity", ""))
            instance = int(state.get("instance", -1))
            key = (entity_id, instance)
            if not entity_id or key in used_visuals:
                continue
            geometry_parts = int(state.get("parts", 1))
            caption_count = state.get("caption_count")
            if geometry_parts != parts and caption_count != parts:
                continue
            score = 0
            if caption_count == parts:
                score += 8
            if geometry_parts == parts:
                score += 3
            if qualifier and bool(state.get("extracted")):
                score += 5
            label = str(state.get("label", ""))
            if label and label in tail:
                score += 10
            candidates.append((score, int(state.get("order", 0)), state))
        if not candidates:
            continue
        _, _, selected = max(candidates, key=lambda item: (item[0], -item[1]))
        entity_id = str(selected.get("entity", ""))
        instance = int(selected.get("instance", -1))
        used_visuals.add((entity_id, instance))
        action = {
            "anchor": match.group(0),
            "type": "focus_diagram",
            "entity": entity_id,
            "row": -1,
            "parts": parts,
            "direction": "down_right",
        }
        if instance >= 0:
            action["instance"] = instance
        actions.append(action)
    return actions


def _ensure_word_actions(beats: list[dict[str, Any]], entities: list[dict[str, Any]]) -> None:
    """Guarantee every visible state change is anchored to exact narration."""
    by_id = {entity["id"]: entity for entity in entities}
    available_diagrams: list[dict[str, Any]] = []
    for beat in beats:
        narration = str(beat.get("narration", ""))
        normalized = [
            action for action in (
                _normalise_action(action, set(by_id), narration)
                for action in beat.get("actions", [])
            ) if action
        ]
        if beat.get("layout") == "diagram":
            for diagram in beat.get("diagrams", []):
                entity_id = str(diagram.get("entity", ""))
                instance = int(diagram.get("instance", 0))
                diagram_key = (entity_id, instance)
                caption_match = re.fullmatch(
                    rf"\s*(?P<parts>{PART_NUMBER_PATTERN})\s*份\s*",
                    str(diagram.get("caption", "")),
                )
                caption_count = _part_number(caption_match.group("parts")) if caption_match else None
                state = next(
                    (
                        item for item in available_diagrams
                        if (item.get("entity"), int(item.get("instance", -1))) == diagram_key
                    ),
                    None,
                )
                extracted = any(
                    action.get("type") == "extract_part"
                    and (not action.get("entity") or action.get("entity") == entity_id)
                    for action in normalized
                )
                if entity_id:
                    if state is None:
                        state = {
                            "entity": entity_id,
                            "parts": int(diagram.get("parts", 1)),
                            "instance": instance,
                            "caption_count": caption_count,
                            "extracted": extracted,
                            "label": str(by_id.get(entity_id, {}).get("label", "")),
                        }
                        available_diagrams.append(state)
                    else:
                        state["parts"] = int(diagram.get("parts", state.get("parts", 1)))
                        if caption_count is not None:
                            state["caption_count"] = caption_count
                        state["extracted"] = bool(state.get("extracted")) or extracted
                entity = by_id.get(diagram.get("entity"), {})
                inferred = _partition_word_actions(narration, diagram, entity)
                for action in inferred:
                    if not any(
                        existing["type"] == action["type"]
                        and existing.get("entity") == action.get("entity")
                        for existing in normalized
                    ):
                        normalized.append(action)
        has_part_motion = any(action["type"] in {"collect_parts", "focus_part", "restore_parts", "assemble_whole"} for action in normalized)
        diagram_references = [] if has_part_motion else _diagram_reference_actions(narration, available_diagrams)
        if diagram_references:
            # A deictic count points at the already-cut object.  Remove a model
            # fallback that would frame the top formula on the same words.
            normalized = [
                item for item in normalized
                if not (
                    item.get("type") == "focus_formula"
                    and any(
                        str(reference.get("anchor", "")) in str(item.get("anchor", ""))
                        or str(item.get("anchor", "")) in str(reference.get("anchor", ""))
                        for reference in diagram_references
                    )
                )
            ]
        present_diagram_focus = {
            (item.get("anchor"), item.get("entity"))
            for item in normalized if item.get("type") == "focus_diagram"
        }
        normalized.extend(
            item for item in diagram_references
            if (item.get("anchor"), item.get("entity")) not in present_diagram_focus
        )
        if not normalized:
            normalized = _semantic_word_actions(beat)
        elif not has_part_motion and beat.get("layout") != "diagram" and not any(
            item.get("type") == "focus_diagram" for item in normalized
        ):
            inferred = _semantic_word_actions(beat)
            present = {(item["type"], item["anchor"]) for item in normalized}
            normalized.extend(item for item in inferred if (item["type"], item["anchor"]) not in present)
        # Resolve repeated spoken words locally.  A bare ``str.find`` maps all
        # occurrences of words such as “等于” to the first one, which can make
        # later visual changes fire too early.  Consecutive actions on the same
        # phrase (for example focus_formula + show_whole) intentionally share
        # one offset; otherwise the cursor advances to the next occurrence.
        cursor = 0
        last_anchor = ""
        last_action: dict[str, Any] | None = None
        last_offset = -1
        for action in normalized:
            anchor = str(action.get("anchor", ""))
            shareable = (
                anchor
                and anchor == last_anchor
                and last_offset >= 0
                and last_action is not None
                and action.get("entity") == last_action.get("entity")
                and {str(action.get("type")), str(last_action.get("type"))}
                <= {"focus_formula", "show_whole", "show_formula"}
            )
            if shareable:
                offset = last_offset
            else:
                offset = narration.find(anchor, cursor) if anchor else -1
                if offset < 0 and anchor:
                    offset = narration.find(anchor)
                if offset >= 0:
                    cursor = offset + len(anchor)
            action["anchor_offset"] = offset
            last_anchor = anchor
            last_action = action
            last_offset = offset

        position = {id(action): int(action.get("anchor_offset", -1)) for action in normalized}
        rank = {"focus_formula": 0, "focus_diagram": 0, "show_whole": 1, "partition_shape": 2, "extract_part": 3}
        normalized.sort(key=lambda action: (
            position.get(id(action), 10**9) if position.get(id(action), -1) >= 0 else 10**9,
            rank.get(action["type"], 5),
        ))
        beat["actions"] = normalized[:12]


def _part_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    return PART_NUMBER_VALUES.get(value, 1)


def _deictic_part_count(text: str) -> int | None:
    """Return the count in a spoken pointer such as ``这里是5份``.

    A pointer can describe a visible subset without repartitioning the source
    object.  For example, a six-part circle may have one known part removed and
    the narration then says "这里是5份" about the remainder.  This count is a
    label/focus instruction, not a command to redraw the circle into five
    sectors.
    """
    compact = re.sub(r"\s+", "", str(text or ""))
    match = re.search(
        rf"(?:这里|这边|此处|一共|共有|总共)[^，。！？；;]{{0,8}}?(?P<parts>{PART_NUMBER_PATTERN})份",
        compact,
    )
    if not match:
        return None
    return max(1, min(12, _part_number(match.group("parts"))))


def _partition_supported(kind: str, parts: int) -> bool:
    return kind in {"circle", "square", "triangle", "rectangle"} and 1 <= parts <= 12


def _partition_requirements(text: str, entities: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """Extract visible partition operations from natural Chinese or rows.

    The model is not trusted to remember a diagram object. If the approved
    copy says "圆圈除以4" or "把圆圈平均分成四份", the local normalizer
    deterministically attaches a show-then-partition diagram to that beat.
    """
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return []
    found: list[tuple[str, int]] = []
    kind_aliases = {
        "circle": ("圆", "圆形", "圆圈"),
        "square": ("方形", "方框", "正方形"),
        "triangle": ("三角", "三角形"),
        "rectangle": ("长方形", "矩形"),
        "badge": (),
    }
    for entity in entities:
        entity_id = entity["id"]
        names = {f"{{{{{entity_id}}}}}", str(entity.get("label", "")).strip()}
        names.update(kind_aliases.get(entity.get("kind", "badge"), ()))
        names.discard("")
        for name in sorted(names, key=len, reverse=True):
            escaped = re.escape(name)
            patterns = (
                rf"{escaped}(?:÷|除以)(?P<parts>{PART_NUMBER_PATTERN})",
                rf"(?:把)?(?:一个)?{escaped}.{{0,12}}?平均分成(?P<parts>{PART_NUMBER_PATTERN})份",
                rf"{escaped}.{{0,12}}?分成(?P<parts>{PART_NUMBER_PATTERN})份",
            )
            for pattern in patterns:
                for match in re.finditer(pattern, compact):
                    parts = _part_number(match.group("parts"))
                    item = (entity_id, parts)
                    if item not in found:
                        found.append(item)
    return found


def _ensure_semantic_partition_diagrams(
    beats: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    problem: str,
    narration: str,
) -> None:
    """Repair missing semantic diagrams without another paid model call."""
    by_id = {entity["id"]: entity for entity in entities}

    def add_to_beat(beat: dict[str, Any], entity_id: str, parts: int) -> None:
        entity = by_id.get(entity_id)
        if not entity or not _partition_supported(entity.get("kind", "badge"), parts):
            return
        diagrams = beat.setdefault("diagrams", [])
        for item in diagrams:
            if item.get("entity") != entity_id:
                continue
            # Exact narration is authoritative.  Correct a model-proposed
            # count in place instead of keeping contradictory copies such as
            # parts=4 with caption="6份".
            item["parts"] = parts
            item["caption"] = f"{parts}份"
            item["animation"] = "show_then_partition"
            for action in beat.get("actions", []):
                if action.get("entity") == entity_id and action.get("type") in {
                    "show_whole", "partition_shape", "extract_part", "focus_diagram"
                }:
                    action["parts"] = parts
            if beat.get("layout") not in {"summary", "title"}:
                beat["layout"] = "diagram"
            return
        if len(diagrams) >= 5:
            return
        diagrams.append({
            "entity": entity_id,
            "parts": parts,
            "caption": f"{parts}份",
            "animation": "show_then_partition",
        })
        if beat.get("layout") not in {"summary", "title"}:
            beat["layout"] = "diagram"

    # Explicit explanation copy must be visualized in the very same beat.
    for beat in beats:
        if beat.get("layout") == "summary":
            continue
        explicit_text = beat.get("narration", "")
        for entity_id, parts in _partition_requirements(explicit_text, entities):
            add_to_beat(beat, entity_id, parts)

    existing = {
        (item.get("entity"), int(item.get("parts", 1)))
        for beat in beats
        for item in beat.get("diagrams", [])
    }
    # Formula rows are the next strongest signal. Add only if no later
    # explanatory beat already demonstrates the same operation.
    for beat in beats:
        if beat.get("layout") == "summary":
            continue
        row_text = "\n".join(row.get("text", "") for row in beat.get("rows", []))
        for entity_id, parts in _partition_requirements(row_text, entities):
            if (entity_id, parts) not in existing:
                add_to_beat(beat, entity_id, parts)
                existing.add((entity_id, parts))

    # Last safety net: if the full approved problem/copy contains an operation
    # omitted from all beat excerpts, attach it to the first suitable stage.
    requirements = _partition_requirements(problem + "\n" + narration, entities)
    suitable = next((beat for beat in beats if beat.get("layout") not in {"title", "summary"}), None)
    if suitable:
        for entity_id, parts in requirements:
            if (entity_id, parts) not in existing:
                add_to_beat(suitable, entity_id, parts)
                existing.add((entity_id, parts))


NEW_DIAGRAM_INSTANCE_RE = re.compile(
    r"(?:再|另|又)(?:画|绘|放|摆|出现|添加|生成)|第二(?:个|只|组)|另一个|同样的(?:圆|圆圈|方框|正方形|三角形)"
)


def _starts_new_diagram_instance(narration: str) -> bool:
    return bool(NEW_DIAGRAM_INSTANCE_RE.search(re.sub(r"\s+", "", str(narration or ""))))


def _repair_diagram_part_sequences(
    beats: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    problem: str,
    narration: str,
) -> None:
    """Keep a visible shape's partition count coherent across phrase beats.

    A model commonly emits three beats for one motion (show, partition,
    extract) and gives each beat a different `parts` value.  The runtime must
    continue transforming the same object.  An explicit count in the exact
    narration wins; otherwise a unique count established for that entity is
    carried through later partition/extraction/focus beats.  A spoken “再画一
    个” starts another visual instance without losing the first one.
    """
    global_counts: dict[str, set[int]] = {}
    for entity_id, parts in _partition_requirements(problem + "\n" + narration, entities):
        if parts > 1:
            global_counts.setdefault(entity_id, set()).add(parts)
    canonical = {
        entity_id: next(iter(counts))
        for entity_id, counts in global_counts.items()
        if len(counts) == 1
    }

    active_instance: dict[str, int] = {}
    next_instance: dict[str, int] = {}
    state_parts: dict[tuple[str, int], int] = {}
    for beat in beats:
        beat_text = str(beat.get("narration", ""))
        row_text = "\n".join(str(row.get("text", "")) for row in beat.get("rows", []))
        explicit: dict[str, int] = {}
        for entity_id, parts in _partition_requirements(beat_text + "\n" + row_text, entities):
            explicit[entity_id] = parts
        new_instance_cue = _starts_new_diagram_instance(beat_text)
        cue_consumed: set[str] = set()
        seen_in_beat: set[str] = set()

        for diagram in beat.get("diagrams", []):
            entity_id = str(diagram.get("entity", ""))
            if not entity_id:
                continue
            must_create = entity_id not in active_instance
            if entity_id in seen_in_beat:
                must_create = True
            elif new_instance_cue and entity_id not in cue_consumed and entity_id in active_instance:
                must_create = True
                cue_consumed.add(entity_id)
            if "instance" in diagram:
                instance = int(diagram["instance"])
                active_instance[entity_id] = instance
                next_instance[entity_id] = max(next_instance.get(entity_id, 0), instance + 1)
            elif must_create:
                instance = next_instance.get(entity_id, 0)
                next_instance[entity_id] = instance + 1
                active_instance[entity_id] = instance
            instance = active_instance[entity_id]
            key = (entity_id, instance)
            diagram["instance"] = instance
            seen_in_beat.add(entity_id)

            actions = [
                action for action in beat.get("actions", [])
                if action.get("entity") == entity_id
            ]
            action_types = {str(action.get("type", "")) for action in actions}
            current = state_parts.get(key, 1)
            proposed = max(1, min(12, int(diagram.get("parts", 1))))
            if entity_id in explicit:
                desired = explicit[entity_id]
            elif "extract_part" in action_types and current > 1:
                desired = current
            elif "partition_shape" in action_types and entity_id in canonical:
                desired = canonical[entity_id]
            elif current > 1:
                desired = current
            else:
                desired = proposed
            desired = max(1, min(12, desired))
            diagram["parts"] = desired
            spoken_focus_count = _deictic_part_count(beat_text)
            is_focus_only = (
                "focus_diagram" in action_types
                and not action_types.intersection({"show_whole", "partition_shape", "extract_part"})
            )
            if is_focus_only and spoken_focus_count is not None:
                # Keep the geometric partition count, but label the subset the
                # narration is pointing at (for example 5 remaining parts of a
                # circle that is still divided into 6 equal sectors).
                diagram["caption"] = f"{spoken_focus_count}份"
            elif (
                re.fullmatch(r"\s*\d+\s*份\s*", str(diagram.get("caption", "")))
                and (
                    entity_id in explicit
                    or "partition_shape" in action_types
                    or key not in state_parts
                )
            ):
                diagram["caption"] = f"{desired}份"
            for action in actions:
                if action.get("type") in {"show_whole", "partition_shape", "extract_part", "focus_diagram"}:
                    action["parts"] = desired
            if key not in state_parts or "partition_shape" in action_types:
                state_parts[key] = desired


def _annotate_diagram_instances(beats: list[dict[str, Any]]) -> None:
    """Attach a deterministic visual-instance index to diagrams and actions."""
    active_instance: dict[str, int] = {}
    next_instance: dict[str, int] = {}
    for beat in beats:
        new_instance_cue = _starts_new_diagram_instance(str(beat.get("narration", "")))
        cue_consumed: set[str] = set()
        seen_in_beat: set[str] = set()
        for diagram in beat.get("diagrams", []):
            entity_id = str(diagram.get("entity", ""))
            if not entity_id:
                continue
            must_create = entity_id not in active_instance or entity_id in seen_in_beat
            if new_instance_cue and entity_id in active_instance and entity_id not in cue_consumed:
                must_create = True
                cue_consumed.add(entity_id)
            if "instance" in diagram:
                active_instance[entity_id] = int(diagram["instance"])
                next_instance[entity_id] = max(next_instance.get(entity_id, 0), int(diagram["instance"]) + 1)
            elif must_create:
                instance = next_instance.get(entity_id, 0)
                next_instance[entity_id] = instance + 1
                active_instance[entity_id] = instance
            diagram["instance"] = active_instance[entity_id]
            seen_in_beat.add(entity_id)
        for action in beat.get("actions", []):
            entity_id = str(action.get("entity", ""))
            requested_instance = int(action.get("instance", -1))
            action["instance"] = (
                requested_instance
                if entity_id and requested_instance >= 0
                else active_instance.get(entity_id, -1) if entity_id else -1
            )


def _partition_line_count(kind: str, parts: int) -> int:
    if parts <= 1:
        return 0
    if kind == "circle":
        if parts == 2:
            return 1
        if parts == 4:
            return 2
        return parts
    if kind == "square":
        return parts - 1
    if kind == "triangle":
        return parts - 1
    return 0


def estimate_motion_seconds(
    beat: dict[str, Any],
    entities: list[dict[str, Any]],
    beat_index: int = 0,
    include_hold: bool = True,
) -> float:
    """Return the portrait reference template's unscaled action duration."""
    by_id = {entity["id"]: entity for entity in entities}
    seconds = 0.0  # narration controls timing but is never burned in as subtitles
    part_costs = {"collect_parts": 1.1, "focus_part": 0.36, "restore_parts": 0.65,
                  "isolate_part": 0.6, "assemble_whole": 0.6}
    seconds += sum(part_costs.get(action.get("type"), 0.0) for action in beat.get("actions", []))
    layout = beat.get("layout")
    if layout == "equations":
        seconds += 0.22 * len(beat.get("rows", []))
        if beat.get("focus"):
            seconds += 0.24
    if beat.get("layout") == "diagram":
        for item in beat.get("diagrams", []):
            kind = by_id.get(item.get("entity"), {}).get("kind", "badge")
            seconds += 0.30  # red frame and complete shape appear together
            line_count = _partition_line_count(kind, int(item.get("parts", 1)))
            seconds += 0.25 * line_count
            if line_count:
                seconds += 0.18  # stable view after all dividers finish
            has_extract = any(
                action.get("type") == "extract_part"
                and (not action.get("entity") or action.get("entity") == item.get("entity"))
                for action in beat.get("actions", [])
            )
            seconds += 0.58 if has_extract else 0.12
        seconds += 0.22 * len(beat.get("rows", []))
    elif layout == "derivation":
        diagram_focus = any(action.get("type") == "focus_diagram" for action in beat.get("actions", []))
        seconds += 0.24 if diagram_focus else (0.34 if beat.get("rows") else 0.0)
        if beat.get("focus") and not diagram_focus:
            seconds += 0.24
    elif layout == "summary":
        seconds += 0.18  # previous red frame exits
        seconds += 0.22 * len(beat.get("rows", []))
        seconds += 0.36  # fallback answer-strip transform
    elif layout == "title":
        seconds += 0.28 * len(beat.get("rows", []))
    if include_hold:
        seconds += 2.0 if beat.get("layout") == "summary" else 0.35
    return seconds


def _enforce_motion_duration(beats: list[dict[str, Any]], entities: list[dict[str, Any]]) -> None:
    """Reserve enough time for the deterministic action sequence and hold."""
    for index, beat in enumerate(beats):
        seconds = estimate_motion_seconds(beat, entities, index, include_hold=True)
        minimum = math.ceil(seconds * 10.0) / 10.0
        beat["duration"] = round(min(8.0, max(float(beat.get("duration", 3.0)), minimum)), 1)


def _normalise_operators(raw: Any, entity_ids: set[str]) -> list[dict[str, Any]]:
    """Normalise diagram-area relation symbols shown between two shapes.

    A beat may place "+" / "=" style symbols between already-visible diagram
    instances to spell out an equation in the diagram zone. Each entry looks
    like {"symbol": "+", "between": ["num@0", "rect24@0"]}; the symbol is drawn
    at the midpoint between the two objects' facing edges.
    """
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    operators: list[dict[str, Any]] = []
    full_width = {"+": "＋", "-": "－", "×": "×", "÷": "÷", "=": "＝", "＋": "＋", "－": "－", "＝": "＝"}
    for item in raw[:4]:
        if not isinstance(item, dict):
            continue
        symbol = full_width.get(str(item.get("symbol", "")).strip())
        between = item.get("between")
        if not symbol or not isinstance(between, list) or len(between) != 2:
            continue
        keys: list[str] = []
        for ref in between:
            value = str(ref or "").strip()
            if "@" not in value:
                break
            entity_id, _, raw_instance = value.partition("@")
            if entity_id not in entity_ids:
                break
            try:
                instance = max(0, int(raw_instance))
            except (TypeError, ValueError):
                break
            keys.append(f"{entity_id}@{instance}")
        if len(keys) == 2 and keys[0] != keys[1]:
            operators.append({"symbol": symbol, "between": keys})
    return operators


def _normalise_beat(raw: Any, index: int, entity_ids: set[str]) -> dict[str, Any]:
    value = raw if isinstance(raw, dict) else {}
    narration = _clean_text(value.get("narration"), 500)
    layout = str(value.get("layout") or "derivation").lower().strip()
    if layout not in ALLOWED_LAYOUTS:
        layout = "derivation"
    rows = [_normalise_row(row) for row in (value.get("rows") or [])]
    rows = [row for row in rows if row["text"]][:6]
    diagrams = [item for item in (_normalise_diagram(item, entity_ids) for item in (value.get("diagrams") or [])) if item]
    diagrams = diagrams[:5]
    # Models sometimes label a formula-only stage as "diagram" even though
    # they correctly provide rows and no diagrams. The visual intent is
    # unambiguous, so repair the layout locally instead of paying for another
    # model rewrite or rejecting otherwise complete content.
    if layout == "diagram" and not diagrams and rows:
        layout = "derivation"
    try:
        duration = float(value.get("duration", 3.0))
    except (TypeError, ValueError):
        duration = 3.0
    minimum = 2.5 if layout == "summary" else 1.5
    duration = round(max(minimum, min(8.0, duration)), 1)
    return {
        "id": f"b{index + 1:02d}",
        "narration": narration,
        "duration": duration,
        "layout": layout,
        "heading": _clean_text(value.get("heading"), 36),
        "rows": rows,
        "focus": _normalise_focus(value.get("focus"), len(rows)),
        "diagrams": diagrams,
        "operators": _normalise_operators(value.get("operators"), entity_ids),
        "actions": [
            action for action in (
                _normalise_action(item, entity_ids, narration, allow_silent=layout == "summary")
                for item in (value.get("actions") or [])
            ) if action
        ][:8],
    }


def _has_banned_screen_text(text: Any) -> bool:
    value = str(text or "")
    return any(banned in value for banned in BANNED_SCREEN_TEXT)


def _remove_banned_screen_beats(beats: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Keep approved audio narration while deterministically hiding CTA cards.

    A supplied soundtrack may intentionally contain a spoken closing call to
    action even though the visual style forbids engagement text. Models often
    turn that final sentence into a 24th on-screen card. Dropping its narration
    would break audio coverage, so merge a CTA-only beat into the preceding
    visual beat: the final answer simply stays on screen while the audio ends.
    """
    cleaned: list[dict[str, Any]] = []
    pending_narration = ""
    repairs: list[str] = []
    for beat in beats:
        original_rows = list(beat.get("rows") or [])
        safe_rows: list[dict[str, Any]] = []
        index_map: dict[int, int] = {}
        removed_words: set[str] = set()
        for original_index, row in enumerate(original_rows):
            words = {word for word in BANNED_SCREEN_TEXT if word in str(row.get("text", ""))}
            if words:
                removed_words.update(words)
                continue
            index_map[original_index] = len(safe_rows)
            safe_rows.append(row)

        heading = str(beat.get("heading", ""))
        heading_words = {word for word in BANNED_SCREEN_TEXT if word in heading}
        removed_words.update(heading_words)
        had_banned_visual = bool(removed_words)
        if not had_banned_visual:
            if pending_narration:
                beat["narration"] = pending_narration + str(beat.get("narration", ""))
                pending_narration = ""
            cleaned.append(beat)
            continue

        beat["heading"] = "" if heading_words else heading
        beat["rows"] = safe_rows
        focus = beat.get("focus", [])
        if focus == "all":
            beat["focus"] = "all" if safe_rows else []
        else:
            beat["focus"] = [index_map[index] for index in focus if index in index_map]

        if not safe_rows and not beat.get("diagrams"):
            narration = str(beat.get("narration", ""))
            if cleaned:
                cleaned[-1]["narration"] = str(cleaned[-1].get("narration", "")) + narration
            else:
                pending_narration += narration
            repairs.append("互动口播镜头已并入相邻画面，未生成互动文字：" + "、".join(sorted(removed_words)))
            continue

        if pending_narration:
            beat["narration"] = pending_narration + str(beat.get("narration", ""))
            pending_narration = ""
        repairs.append("已从混合画面移除互动文字：" + "、".join(sorted(removed_words)))
        cleaned.append(beat)

    if pending_narration and cleaned:
        cleaned[-1]["narration"] = str(cleaned[-1].get("narration", "")) + pending_narration
    return cleaned, repairs


def _promote_final_answer_layout(beats: list[dict[str, Any]]) -> None:
    if not beats or not beats[-1].get("rows") or beats[-1].get("layout") == "summary":
        return
    heading = str(beats[-1].get("heading", ""))
    if "答案" in heading or "结果" in heading or beats[-1].get("focus") == "all":
        beats[-1]["layout"] = "summary"
        beats[-1]["focus"] = "all"


def _lock_primary_equation_layout(beats: list[dict[str, Any]]) -> list[str]:
    """Reserve the first equation board for the full problem.

    Models sometimes label every later calculation as ``equations``.  The
    runtime then replaces the original problem at the top, even though the
    visual contract requires that board to stay fixed.  All later equation
    states belong to the lower derivation area.
    """
    found_primary = False
    rerouted = 0
    for beat in beats:
        if beat.get("layout") != "equations" or not beat.get("rows"):
            continue
        if not found_primary:
            found_primary = True
            continue
        beat["layout"] = "derivation"
        rerouted += 1
    if not rerouted:
        return []
    return [f"已固定首个原题公式板，并将后续{rerouted}个公式阶段转入下方推导区"]


def _sanitize_model_mechanical_errors(raw: dict[str, Any]) -> list[str]:
    """Deterministically repair layout-local model slips before strict validation.

    The model repeatedly emits the same mechanical mistakes on opening beats,
    which would otherwise burn a paid generation. Only semantics-preserving
    fixes are allowed here; anything ambiguous is left for _validate_model_plan
    to reject:
    - drop empty beats only when they have no actions or visual content;
    - leave unsupported title actions intact for strict validation;
    - a title beat without rows gets the fixed heading as a placeholder row
      (the title renderer ignores work-area rows anyway).
    """
    repairs: list[str] = []
    beats = raw.get("beats")
    if not isinstance(beats, list):
        return repairs
    kept: list[dict[str, Any]] = []
    shown_answer = False
    for beat in beats:
        if not isinstance(beat, dict):
            continue
        actions = beat.get("actions") or []
        has_answer = any(isinstance(a, dict) and a.get("type") == "show_answer" for a in actions)
        layout = str(beat.get("layout") or "").lower().strip()
        if not str(beat.get("narration") or "").strip():
            # A single silent summary tail before any answer is an intentional
            # hold-the-answer frame; empty beats after the answer (or outside
            # summary) are model duplicates.
            silent_tail = layout == "summary" and has_answer and not shown_answer
            if not silent_tail and not actions and not beat.get("diagrams") and not beat.get("rows"):
                repairs.append("已删除旁白为空的多余分镜")
                continue
        if has_answer:
            shown_answer = True
        if layout == "title":
            # Never erase an intended motion by converting it to a hold.
            # Unsupported title actions must reach the strict validator.
            if not beat.get("rows"):
                heading = str(beat.get("heading") or "").strip() or "数学解题可视化"
                beat["rows"] = [{"text": heading}]
                repairs.append("开场标题分镜已补固定标题行")
        kept.append(beat)
    raw["beats"] = kept
    return list(dict.fromkeys(repairs))


def _validate_model_plan(raw: dict[str, Any]) -> None:
    """Reject decisions the current executor would silently drop or collapse."""
    errors = []
    capability_issues = []
    entities = raw.get("entities") or []
    beats = raw.get("beats") or []
    if not isinstance(entities, list) or not 1 <= len(entities) <= 6:
        raise StoryboardValidationError(["模型分镜必须声明1至6个受支持实体"])
    by_id = {}
    for entity in entities:
        if not isinstance(entity, dict) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", str(entity.get("id", ""))):
            errors.append("实体id必须是合法且唯一的小写标识")
            continue
        if entity["id"] in by_id or entity.get("kind") not in ALLOWED_KINDS:
            errors.append(f"实体 {entity['id']} 重复或使用未实现的图形类型")
        by_id[entity["id"]] = entity
    if not isinstance(beats, list) or not 4 <= len(beats) <= 60:
        raise StoryboardValidationError(errors + ["模型分镜必须包含4至60个阶段，不能截断保存"])
    if not isinstance(beats[-1], dict) or beats[-1].get("layout") != "summary":
        errors.append("模型分镜最后阶段必须显式使用summary；本机不会把演算阶段改成最终答案")
    boards = [beat for beat in beats if isinstance(beat, dict) and beat.get("layout") == "equations"]
    board_signature = lambda b: [str(r.get("text", "") if isinstance(r, dict) else r).strip() for r in b.get("rows", [])]
    if boards and any(board_signature(b) != board_signature(boards[0]) for b in boards[1:]):
        errors.append("重复equations必须引用同一个原题板；不同内容的计算请使用derivation")
    visible = {}  # (entity, instance) -> currently available number of equal parts
    formula_changes = {"show_text", "show_formula", "transform_formula", "substitute", "combine", "cancel", "divide", "copy_equation", "merge_equations"}
    copied_equations = {}
    original_rows = None
    state_beats = []
    for index, beat in enumerate(beats, 1):
        prefix = f"第{index}个模型分镜"
        if not isinstance(beat, dict):
            errors.append(prefix + "必须是对象")
            continue
        layout = beat.get("layout", "derivation")
        silent_tail = index == len(beats) and layout == "summary" and not str(beat.get("narration", "")).strip()
        rows, diagrams, actions = beat.get("rows") or [], beat.get("diagrams") or [], beat.get("actions") or []
        if layout == "equations" and original_rows is None:
            original_rows = board_signature(beat)
        if layout not in ALLOWED_LAYOUTS or len(rows) > 6 or len(diagrams) > 5 or len(actions) > 8:
            errors.append(prefix + "布局不支持，或行/图解/动作数量超出6/5/8上限；请拆分阶段")
        if not actions:
            errors.append(prefix + "缺少模型决定的词组动作；本机不会代写动作")
        if diagrams and layout != "diagram":
            errors.append(prefix + "的图解只会在diagram布局执行，请修正布局")
        current = {}
        for diagram in diagrams:
            if not isinstance(diagram, dict):
                errors.append(prefix + "的图解必须是对象")
                continue
            entity, instance, parts = diagram.get("entity"), diagram.get("instance", 0), diagram.get("parts", 1)
            if entity not in by_id or not isinstance(instance, int) or not 0 <= instance < 60 or not isinstance(parts, int) or not 1 <= parts <= 12:
                errors.append(prefix + "的图形引用、编号或等份数不受支持")
                continue
            if not _partition_supported(by_id[entity]["kind"], parts):
                errors.append(prefix + "所选实体无法执行该等分动作")
            current[entity, instance] = parts
        normalized_actions = []
        for action in actions:
            if not isinstance(action, dict):
                errors.append(prefix + "动作必须是对象")
                continue
            entity = action.get("entity") or ""
            if entity and entity not in by_id:
                errors.append(prefix + f"动作引用不存在的实体 {entity}")
            allowed_fields = ACTION_FIELDS.get(action.get("type"), BASE_FIELDS)
            unknown = set(action) - allowed_fields
            if unknown:
                errors.append(prefix + "动作包含未实现参数：" + ",".join(sorted(unknown)))
                capability_issues.append({"category": "capability", "code": "ACTION_FIELDS_UNSUPPORTED",
                    "beat_id": beat.get("id") or f"b{index:02d}", "fields": sorted(unknown)})
            for field, lower, upper in (("row", -1, 5), ("parts", 1, 12), ("instance", -1, 59)):
                if field in action and (not isinstance(action[field], int) or not lower <= action[field] <= upper):
                    errors.append(prefix + f"动作{field}超出可执行范围")
            silent_action = silent_tail and not action.get("anchor") and action.get("type") in {"show_answer", "focus_formula", "hold"}
            if not silent_action and not _lock_narration_excerpt(action.get("anchor"), str(beat.get("narration", ""))):
                errors.append(prefix + "动作锚点不在该段旁白中")
            normalized = _normalise_action(action, set(by_id), str(beat.get("narration", "")), allow_silent=silent_tail)
            if normalized:
                normalized_actions.append(normalized)
        state_beats.append({**beat, "actions": normalized_actions})
        types = [a["type"] for a in normalized_actions]
        for action in normalized_actions:
            kind = action["type"]
            if kind in {"copy_equation", "merge_equations"}:
                row = action["row"]
                if layout != "derivation" or diagrams or visible or not 0 <= row < len(rows):
                    errors.append(prefix + "等式搬运/合并仅用于无切分图的derivation，必须指定有效row")
                    continue
                target = str(rows[row].get("text", "") if isinstance(rows[row], dict) else rows[row])
                try:
                    if kind == "copy_equation":
                        source, slot = action["source_row"], action["slot"]
                        if original_rows is None or source >= len(original_rows):
                            raise ValueError("原题来源行尚未出现")
                        if slot in copied_equations:
                            raise ValueError("搬运槽位已有等式，不能覆盖；请先合并或clear_work")
                        equation_sum_mapping(original_rows[source], original_rows[source])
                        if equation_motion_tokens(target) != equation_motion_tokens(original_rows[source]):
                            raise ValueError("copy_equation目标行必须与原题source_row相同，不得改数或换顺序")
                        copied_equations[slot] = original_rows[source]
                    else:
                        slots = action["slots"]
                        if any(slot not in copied_equations for slot in slots):
                            raise ValueError("合并前必须先搬来两组等式，不能引用尚未出现或已清理的副本")
                        equation_sum_mapping(*(copied_equations[slot] for slot in slots), target=target)
                        copied_equations.clear()
                except ValueError as exc:
                    errors.append(prefix + str(exc))
            elif kind == "clear_work" or (layout == "derivation" and kind in formula_changes | {"show_answer"}):
                copied_equations.clear()
        if diagrams and copied_equations:
            errors.append(prefix + "搬运中的等式与图解不能混排，请先完成合并并清理演算区")
        queue_types = formula_changes | {"focus_formula", "show_answer", "hold", "clear_work"}
        ordered_formula = layout in {"equations", "derivation"} and set(types) <= queue_types
        if not ordered_formula and (sum(t in formula_changes for t in types) > 1 or types.count("show_answer") > 1):
            errors.append(prefix + "混合图形阶段包含多个公式状态变化，请拆分beats")
        if not ordered_formula and layout != "diagram" and types.count("focus_formula") > 1:
            errors.append(prefix + "该混合阶段包含多次公式红框移动，请拆分beats")
        if ordered_formula:
            for action in normalized_actions:
                if action["type"] in formula_changes | {"focus_formula", "show_answer"}:
                    if action["row"] >= len(rows):
                        errors.append(prefix + "动作row引用不存在的公式行")
                    if action["type"] in formula_changes | {"show_answer"} and action["row"] < 0 and len(rows) != 1:
                        errors.append(prefix + "多行连续公式动作必须明确指定row，不能猜测目标")
        if layout == "title" and any(t not in {"hold", "clear_work"} for t in types):
            errors.append(prefix + "title仅保留固定顶部标题；动态内容请使用equations或derivation")
        if layout == "summary" and any(t in {"substitute", "combine", "cancel", "divide"} for t in types):
            errors.append(prefix + "最终答案前的演算必须放在derivation阶段")
        for action in normalized_actions:
            kind, entity, instance = action["type"], action["entity"], action["instance"]
            matching = lambda source: [key for key in source if (not entity or key[0] == entity) and (instance < 0 or key[1] == instance)]
            if kind in {"show_whole", "partition_shape", "extract_part"}:
                keys = matching(current)
                if layout != "diagram" or not entity or not keys:
                    errors.append(prefix + f"的{kind}缺少当前diagram实体目标")
            elif kind == "focus_diagram" and not matching({**visible, **current}):
                errors.append(prefix + "红框目标图解尚未出现")
        for key, parts in current.items():
            visible.setdefault(key, 1)
            if any(a["type"] == "partition_shape" and a["entity"] == key[0] and a["instance"] in {-1, key[1]} for a in normalized_actions):
                visible[key] = parts
    if errors:
        raise StoryboardValidationError(errors[:30], capability_issues)
    state_issues = part_state_issues(state_beats)
    if state_issues:
        raise StoryboardValidationError([item["problem"] for item in state_issues], state_issues)


def _bind_model_word_actions(beats: list[dict[str, Any]]) -> None:
    """Bind only declared model actions; do not infer, append or replace them."""
    for beat in beats:
        narration = beat["narration"]
        cursor, last_anchor, last_offset = 0, "", -1
        for action in beat["actions"]:
            anchor = action["anchor"]
            offset = last_offset if anchor == last_anchor else narration.find(anchor, cursor)
            if offset < 0:
                offset = narration.find(anchor)
            action["anchor_offset"] = offset
            cursor, last_anchor, last_offset = offset + len(anchor), anchor, offset
        for diagram in beat["diagrams"]:
            diagram.setdefault("instance", 0)


def _schedule_model_focus_dependencies(beats: list[dict[str, Any]]) -> list[str]:
    """A frame may follow its producer, but must never reveal a future answer.

    Deterministic scheduling only: keep content, number, row and narration;
    rebind premature focus to its own same-beat producer and disclose the repair.
    """
    repairs = []
    board, work = set(), set()
    content = {"show_text", "show_formula", "transform_formula", "substitute", "combine",
               "cancel", "divide", "show_answer", "copy_equation", "merge_equations"}
    cue_types = {"substitute", "combine", "cancel", "divide"}
    signature = lambda text: tuple(equation_motion_tokens(text))
    for beat in beats:
        rows = [signature(row['text']) for row in beat.get('rows', [])]
        actions = sorted(beat.get('actions', []), key=lambda a: a.get('anchor_offset', 0))
        if beat['layout'] == 'equations' and not board:
            board.update(rows)
        if beat['layout'] not in {'equations', 'derivation'}:
            if beat['layout'] == 'summary':
                work = set(rows)
            continue
        def target(action):
            row = action.get('row', -1)
            if row < 0 and len(rows) == 1:
                row = 0
            return rows[row] if 0 <= row < len(rows) else None
        def produces(index):
            item = actions[index]
            if item['type'] not in content:
                return False
            # These early operation cues do not expose the later same-row state.
            return not (item['type'] in cue_types and any(
                other['type'] in content and target(other) == target(item)
                for other in actions[index + 1:]))
        ordered, waiting = [], {}
        for index, action in enumerate(actions):
            text = target(action)
            if action['type'] == 'focus_formula' and text is not None and text not in board | work:
                producer = next((i for i in range(index + 1, len(actions))
                                 if produces(i) and target(actions[i]) == text), None)
                if producer is None:
                    raise StoryboardValidationError([f"{beat['id']}红框目标尚未出现，且该段没有创建此算式的动作；请先显示对应row"])
                original_anchor = action['anchor']
                source = actions[producer]
                action['anchor'], action['anchor_offset'] = source['anchor'], source['anchor_offset']
                waiting.setdefault(producer, []).append(action)
                repairs.append(f"{beat['id']}：红框原锚点“{original_anchor}”早于目标算式出现，已延后至“{source['anchor']}”对应算式显示后；未改旁白或提前显示答案。")
                continue
            ordered.append(action)
            if action['type'] == 'clear_work':
                work.clear()
            elif produces(index) and text is not None and text not in board:
                # Runtime retains displayed rows within this beat; future rows
                # are not included. Copies also remain live until merged.
                if action['type'] == 'copy_equation':
                    work.add(text)
                else:
                    work = {text} | {target(a) for a in ordered if a['type'] in content and target(a) is not None}
            ordered.extend(waiting.pop(index, []))
        beat['actions'] = ordered
    return repairs


def normalize_storyboard(raw: Any, request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StoryboardValidationError(["模型返回的分镜不是 JSON 对象"])
    unsupported = raw.get("unsupported_requirements") or []
    if not isinstance(unsupported, list):
        raise StoryboardValidationError(["unsupported_requirements必须是列表"])
    if unsupported:
        raise StoryboardValidationError(["当前动画组件尚不支持：" + str(item)[:500] for item in unsupported[:20]])
    model_directed = request.get("planner_mode") == "model" or raw.get("planner_mode") == "model"
    local_repairs: list[str] = []
    if model_directed:
        local_repairs.extend(_sanitize_model_mechanical_errors(raw))
        _validate_model_plan(raw)
    # Preserve declared plans. The old empty-beat entry remains available to
    # explicit local callers, but cannot replace a model-authored storyboard.
    unit_plan = fraction_multiple_plan(raw, request) if not model_directed and not raw.get("beats") else None
    if unit_plan is not None:
        raw = unit_plan
    used: set[str] = set()
    entities = [_normalise_entity(item, index, used) for index, item in enumerate(raw.get("entities") or [])][:6]
    entity_ids = {entity["id"] for entity in entities}
    beats = [_normalise_beat(item, index, entity_ids) for index, item in enumerate(raw.get("beats") or [])][:60]
    if not model_directed:
        _promote_final_answer_layout(beats)

    title = _clean_text(request.get("title") or raw.get("title") or "数学解题可视化", 40)
    requested_problem = _clean_text(request.get("problem"), 4000)
    problem = requested_problem or _clean_text(raw.get("problem"), 4000)
    narration = _clean_text(request.get("narration"), 12000)
    for beat in beats:
        beat["narration"] = _lock_narration_excerpt(beat.get("narration"), narration)
    beats, banned_repairs = _remove_banned_screen_beats(beats)
    local_repairs.extend(banned_repairs)
    if not model_directed:
        _promote_final_answer_layout(beats)
        local_repairs.extend(_lock_primary_equation_layout(beats))
    local_contract = unit_plan.get("local_math_contract") if unit_plan is not None else raw.get("local_math_contract") if not model_directed else None
    if model_directed:
        _bind_model_word_actions(beats)
        local_repairs.extend(_schedule_model_focus_dependencies(beats))
    elif local_contract is not None:
        local_repairs.append("已从当前旁白核对分数项、倍数项、总份数和答案；每个图形副本使用固定编号与独立词组动作。")
    else:
        _ensure_semantic_partition_diagrams(beats, entities, problem, narration)
        _repair_diagram_part_sequences(beats, entities, problem, narration)
        _ensure_word_actions(beats, entities)
        _annotate_diagram_instances(beats)
    _enforce_motion_duration(beats, entities)
    # The runtime already keeps one title at the top. If the model repeats the
    # exact same title as both the opening heading and opening row, replace that
    # redundant centre stack with the user's verbatim opening narration.
    if beats and beats[0]["layout"] == "title" and beats[0]["narration"]:
        visible_opening = [beats[0].get("heading", "")] + [row["text"] for row in beats[0].get("rows", [])]
        nonempty_opening = [text.strip() for text in visible_opening if text.strip()]
        if nonempty_opening and all(text == title for text in nonempty_opening):
            beats[0]["heading"] = ""
            beats[0]["rows"] = [{"text": beats[0]["narration"], "accent": False}]
            beats[0]["focus"] = []
    spec = {
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "problem": problem,
        "narration": narration,
        "entities": entities,
        "beats": beats,
        "local_repairs": local_repairs,
    }
    if model_directed:
        spec["planner_mode"] = "model"
        spec["unsupported_requirements"] = []
    if local_contract is not None:
        spec["local_math_contract"] = local_contract
    errors: list[str] = []
    if not title:
        errors.append("缺少视频标题")
    if not problem:
        errors.append("没有识别出完整题目")
    if not narration:
        errors.append("缺少逐字旁白")
    if not entities:
        errors.append("至少需要一个人物或图形实体")
    if not 4 <= len(beats) <= 60:
        errors.append("分镜必须包含 4 至 60 个阶段")
    if beats and beats[-1]["layout"] != "summary":
        errors.append("最后一个分镜必须是 summary 最终答案")
    if str(request.get("audio_timing_summary", "")).strip():
        source_compact = "".join(character for character in narration if not character.isspace())
        beat_compact = "".join(
            character
            for beat in beats
            for character in str(beat.get("narration", ""))
            if not character.isspace()
        )
        if beat_compact != source_compact:
            errors.append("音频模式下所有分镜 narration 必须按顺序完整覆盖逐字旁白，不得漏句、重复或改写")

    for beat_index, beat in enumerate(beats, start=1):
        if not beat["rows"] and not beat["diagrams"]:
            errors.append(f"第 {beat_index} 个分镜没有任何屏幕内容")
        if beat["layout"] == "diagram" and not beat["diagrams"]:
            errors.append(f"第 {beat_index} 个 diagram 分镜缺少 diagrams")
        if beat["layout"] == "summary" and not beat["rows"]:
            errors.append(f"第 {beat_index} 个 summary 分镜缺少最终答案")
        for row in beat["rows"]:
            for banned in BANNED_SCREEN_TEXT:
                if banned in row["text"]:
                    errors.append(f"第 {beat_index} 个分镜含禁止文案“{banned}”")
            references = PLACEHOLDER_RE.findall(row["text"])
            unknown = sorted(set(references) - entity_ids)
            if unknown:
                errors.append(f"第 {beat_index} 个分镜引用不存在的实体：{', '.join(unknown)}")
            if any(symbol in row["text"] for symbol in ("○", "□", "△", "◯", "●", "■", "▲")):
                errors.append(f"第 {beat_index} 个分镜使用了字体图形字符，必须改为实体占位符")
        for diagram in beat["diagrams"]:
            kind = next(entity["kind"] for entity in entities if entity["id"] == diagram["entity"])
            parts = diagram["parts"]
            if diagram.get("animation") != "show_then_partition":
                errors.append(f"第 {beat_index} 个分镜没有锁定先显示图形再等分的动画")
            if not _partition_supported(kind, parts):
                errors.append(f"{kind} 只支持 1 至 12 等分，第 {beat_index} 个分镜写了 {parts}")
        if beat.get("narration") and not beat.get("actions"):
            errors.append(f"第 {beat_index} 个分镜缺少逐词动作锚点")
        for action in beat.get("actions", []):
            if action.get("type") not in ALLOWED_ACTIONS:
                errors.append(f"第 {beat_index} 个分镜含不允许的动作类型")
            if str(action.get("anchor", "")) not in str(beat.get("narration", "")):
                errors.append(f"第 {beat_index} 个分镜动作锚点不在逐字旁白中")

    if errors:
        raise StoryboardValidationError(errors[:30])
    return spec


def storyboard_timeline(spec: dict[str, Any]) -> list[dict[str, Any]]:
    current = 0.7
    events: list[dict[str, Any]] = []
    entities = {item["id"]: item for item in spec.get("entities") or []}
    diagram_keys: list[tuple[str, int]] = []
    for source_beat in spec.get("beats") or []:
        for source_diagram in source_beat.get("diagrams") or []:
            entity_id = str(source_diagram.get("entity") or "")
            key = (entity_id, max(0, int(source_diagram.get("instance", 0))))
            if entity_id in entities and key not in diagram_keys:
                diagram_keys.append(key)
    visible_diagram_keys: set[tuple[str, int]] = set()
    diagram_parts_state: dict[tuple[str, int], int] = {}
    extracted_diagram_keys: set[tuple[str, int]] = set()
    audio = spec.get("audio") or {}
    audio_mode = bool(str(audio.get("path", "")).strip())
    for beat_index, beat in enumerate(spec.get("beats") or []):
        if audio_mode:
            start = 0.7 + max(0.0, float(beat.get("audio_start", 0.0)))
            end = 0.7 + max(float(beat.get("audio_end", 0.0)), float(beat.get("audio_start", 0.0)) + 0.08)
            motion_scale = max(0.12, min(1.0, float(beat.get("motion_scale", 1.0))))
        else:
            duration = float(beat.get("duration", 3.0))
            start = current
            end = start + duration
            motion_scale = 1.0

        def scaled(base: float) -> float:
            return max(0.04, base * motion_scale)

        cursor = start
        checkpoints: list[dict[str, Any]] = []
        layout = beat.get("layout")
        if layout == "equations":
            cursor += scaled(0.22) * len(beat.get("rows") or [])
            if beat.get("focus"):
                cursor += scaled(0.24)
        elif layout == "diagram":
            for diagram_index, diagram in enumerate(beat.get("diagrams") or [], start=1):
                entity = entities.get(diagram.get("entity"), {})
                label = entity.get("label") or diagram.get("entity") or "图形"
                parts = int(diagram.get("parts", 1))
                entity_id = str(diagram.get("entity") or "")
                instance = max(0, int(diagram.get("instance", 0)))
                diagram_key = (entity_id, instance)
                actions = [
                    action for action in beat.get("actions", [])
                    if not action.get("entity") or action.get("entity") == entity_id
                    if int(action.get("instance", -1)) in {-1, instance}
                ]
                by_type = {action.get("type"): action for action in actions}
                show_action = by_type.get("show_whole")
                partition_action = by_type.get("partition_shape")
                extract_action = by_type.get("extract_part")
                slot_index = diagram_keys.index(diagram_key) if diagram_key in diagram_keys else 0
                slot_count = max(1, len(diagram_keys))

                # A diagram can span several narration beats: first the whole
                # shape appears, then later words draw its dividers, and a
                # later phrase extracts one part.  Only create a “whole” QA
                # checkpoint when this visual instance is genuinely new.
                if diagram_key not in visible_diagram_keys:
                    opening_action = show_action or partition_action or extract_action
                    if audio_mode and opening_action:
                        opening_time = 0.7 + float(opening_action.get("audio_start", beat.get("audio_start", 0.0)))
                        cursor = max(cursor, opening_time)
                    if len(visible_diagram_keys) == 1:
                        cursor += scaled(0.42)  # first diagram smoothly makes room
                    cursor += scaled(0.30)
                    checkpoints.append({
                        "id": f"{beat.get('id', '')}_d{diagram_index}_i{instance}_whole",
                        "time": round(min(end - 0.05, max(start + 0.04, cursor + scaled(0.10))), 2),
                        "expected": f"{label}先完整出现，尚未分割",
                        "geometry_stage": "whole",
                        "entity": entity_id,
                        "instance": instance,
                        "kind": entity.get("kind", "badge"),
                        "color": entity.get("color", "#FFFFFF"),
                        "slot_index": slot_index,
                        "slot_count": slot_count,
                    })
                    visible_diagram_keys.add(diagram_key)
                    diagram_parts_state[diagram_key] = 1

                line_count = _partition_line_count(entity.get("kind", "badge"), parts)
                fallback_partition = bool(
                    not audio_mode
                    and not actions
                    and parts > 1
                    and diagram.get("animation") == "show_then_partition"
                )
                needs_partition = bool(
                    (partition_action or fallback_partition)
                    and parts > 1
                    and (
                        diagram_parts_state.get(diagram_key, 1) != parts
                        or diagram_key in extracted_diagram_keys
                    )
                )
                if needs_partition:
                    if audio_mode:
                        partition_time = 0.7 + float(partition_action.get("audio_start", beat.get("audio_start", 0.0)))
                        cursor = max(cursor, partition_time)
                    partition_total = scaled(min(0.90, 0.24 * max(1, line_count)))
                    if audio_mode and partition_action:
                        action_start = float(partition_action.get("audio_start", beat.get("audio_start", 0.0)))
                        later = [
                            float(item.get("audio_start", beat.get("audio_end", action_start)))
                            for item in beat.get("actions", [])
                            if float(item.get("audio_start", beat.get("audio_end", action_start))) > action_start + 0.015
                        ]
                        next_start = min(later) if later else float(beat.get("audio_end", action_start + 0.08))
                        room = 0.7 + next_start - cursor - 0.025
                        partition_total = 0.04 if room <= 0.04 else max(0.04, min(partition_total, room))
                    partition_total = max(0.02 * max(1, line_count), partition_total)
                    cursor += partition_total
                    checkpoints.append({
                        "id": f"{beat.get('id', '')}_d{diagram_index}_i{instance}_partitioned",
                        "time": round(min(end - 0.05, max(start + 0.05, cursor + scaled(0.10))), 2),
                        "expected": f"{label}已由动态分割线平均分成{parts}份",
                        "geometry_stage": "partitioned",
                        "entity": entity_id,
                        "instance": instance,
                        "kind": entity.get("kind", "badge"),
                        "color": entity.get("color", "#FFFFFF"),
                        "slot_index": slot_index,
                        "slot_count": slot_count,
                    })
                    diagram_parts_state[diagram_key] = parts
                    extracted_diagram_keys.discard(diagram_key)
                    if not audio_mode:
                        cursor += scaled(0.14)

                needs_extract = bool(
                    extract_action
                    and parts > 1
                    and diagram_key not in extracted_diagram_keys
                )
                if needs_extract:
                    if audio_mode:
                        extract_time = 0.7 + float(extract_action.get("audio_start", beat.get("audio_start", 0.0)))
                        cursor = max(cursor, extract_time)
                    cursor += scaled(0.58)
                    checkpoints.append({
                        "id": f"{beat.get('id', '')}_d{diagram_index}_i{instance}_extracted",
                        "time": round(min(end - 0.04, max(start + 0.06, cursor + scaled(0.08))), 2),
                        "expected": f"{label}只抽离其中1份且其余部分保持原位",
                        "geometry_stage": "extracted",
                        "entity": entity_id,
                        "instance": instance,
                        "kind": entity.get("kind", "badge"),
                        "color": entity.get("color", "#FFFFFF"),
                        "slot_index": slot_index,
                        "slot_count": slot_count,
                    })
                    diagram_parts_state[diagram_key] = parts
                    extracted_diagram_keys.add(diagram_key)
                elif not needs_partition and diagram_key in visible_diagram_keys:
                    cursor += scaled(0.12)

            diagram_focus_actions = sorted(
                [action for action in beat.get("actions", []) if action.get("type") == "focus_diagram"],
                key=lambda item: float(item.get("audio_start", beat.get("audio_start", 0.0))),
            )
            for focus_index, action in enumerate(diagram_focus_actions, start=1):
                action_start = action.get("audio_start")
                if audio_mode and action_start is not None:
                    cursor = max(cursor, 0.7 + float(action_start))
                cursor += scaled(0.28)
                entity_id = str(action.get("entity", ""))
                instance = max(0, int(action.get("instance", 0)))
                diagram_key = (entity_id, instance)
                entity = entities.get(entity_id, {})
                checkpoint = {
                    "id": f"{beat.get('id', '')}_diagram_focus{focus_index}",
                    "time": round(min(end - 0.04, max(start + 0.06, cursor + scaled(0.08))), 2),
                    "expected": (
                        f"红色虚线框已移动到切分后的{entity.get('label', entity_id)}"
                        if entity_id else "红色虚线框已包住全部切分图形"
                    ),
                }
                if diagram_key in diagram_keys:
                    checkpoint.update({
                        "geometry_stage": "diagram_focus",
                        "entity": entity_id,
                        "instance": instance,
                        "kind": entity.get("kind", "badge"),
                        "color": entity.get("color", "#FFFFFF"),
                        "slot_index": diagram_keys.index(diagram_key),
                        "slot_count": max(1, len(diagram_keys)),
                    })
                checkpoints.append(checkpoint)
            cursor += scaled(0.22) * len(beat.get("rows") or [])
        elif layout == "derivation":
            diagram_focus_actions = [
                action for action in beat.get("actions", [])
                if action.get("type") == "focus_diagram"
            ]
            if diagram_focus_actions:
                for focus_index, action in enumerate(diagram_focus_actions, start=1):
                    action_start = action.get("audio_start")
                    if audio_mode and action_start is not None:
                        cursor = max(cursor, 0.7 + float(action_start))
                    cursor += scaled(0.28)
                    entity_id = str(action.get("entity", ""))
                    instance = max(0, int(action.get("instance", 0)))
                    diagram_key = (entity_id, instance)
                    entity = entities.get(entity_id, {})
                    checkpoint = {
                        "id": f"{beat.get('id', '')}_focus{focus_index}",
                        "time": round(min(end - 0.04, max(start + 0.06, cursor + scaled(0.08))), 2),
                        "expected": (
                            f"红色虚线框已移动到切分后的{entity.get('label', entity_id)}"
                            if entity_id else "红色虚线框已包住全部切分图形"
                        ),
                    }
                    if diagram_key in diagram_keys:
                        checkpoint.update({
                            "geometry_stage": "diagram_focus",
                            "entity": entity_id,
                            "instance": instance,
                            "kind": entity.get("kind", "badge"),
                            "color": entity.get("color", "#FFFFFF"),
                            "slot_index": diagram_keys.index(diagram_key),
                            "slot_count": max(1, len(diagram_keys)),
                        })
                    checkpoints.append(checkpoint)
            else:
                if beat.get("rows"):
                    cursor += scaled(0.34)
                if beat.get("focus"):
                    cursor += scaled(0.24)
        elif layout == "summary":
            cursor += scaled(0.18) + scaled(0.22) * len(beat.get("rows") or [])
        else:
            cursor += scaled(0.28) * len(beat.get("rows") or [])

        # Stable-frame QA must sample *after* the final phrase-triggered visual
        # event, not merely after the old sentence-level duration estimate.
        # Otherwise a late “相等/所以/答案” action can be absent from the
        # contact sheet even though it renders correctly a moment later.
        if audio_mode:
            action_costs = {
                "focus_formula": 0.24,
                "focus_diagram": 0.28,
                "show_whole": 0.30,
                "partition_shape": 0.55,
                "extract_part": 0.58,
                "collect_parts": 1.1,
                "focus_part": 0.36,
                "restore_parts": 0.65,
                "isolate_part": 0.6,
                "assemble_whole": 0.6,
                "show_text": 0.28,
                "show_formula": 0.34,
                "transform_formula": 0.34,
                "substitute": 0.34,
                "combine": 0.54,
                "cancel": 0.34,
                "divide": 0.34,
                "show_answer": 0.24,
                "clear_work": 0.18,
                "hold": 0.04,
            }
            for action in beat.get("actions", []):
                action_start = action.get("audio_start")
                if action_start is None:
                    continue
                action_time = 0.7 + float(action_start)
                cursor = max(cursor, action_time + scaled(action_costs.get(action.get("type"), 0.24)))
        stable = min(end - 0.04, cursor + scaled(0.45))
        events.append({
            "id": beat.get("id", ""),
            "layout": beat.get("layout", ""),
            "heading": beat.get("heading", ""),
            "start": round(start, 2),
            "stable": round(max(start + 0.1, stable), 2),
            "end": round(end, 2),
            "checkpoints": checkpoints,
            "formula_queue": bool(spec.get("planner_mode") == "model" and layout in {"equations", "derivation"}
                and all(a.get("type") in {"show_text", "show_formula", "transform_formula", "substitute",
                    "combine", "cancel", "divide", "focus_formula", "show_answer", "hold", "clear_work", "copy_equation", "merge_equations"}
                    for a in beat.get("actions", []))),
            "actions": [
                {
                    "anchor": action.get("anchor", ""),
                    "type": action.get("type", ""),
                    "audio_start": action.get("audio_start"),
                    "audio_end": action.get("audio_end"),
                    "count": action.get("count", 0),
                    "total": action.get("total", ""),
                    "source_row": action.get("source_row"),
                    "slot": action.get("slot"),
                    "slots": action.get("slots"),
                    "target_text": (beat.get("rows") or [])[action.get("row", -1)]["text"]
                        if beat.get("rows") and -1 <= action.get("row", -1) < len(beat["rows"]) else None,
                }
                for action in beat.get("actions", [])
            ],
        })
        current = end
    if events and audio_mode:
        events[-1]["video_end"] = round(
            0.7 + float(audio.get("duration", 0.0)) + float(audio.get("tail_hold", 2.0)),
            2,
        )
    return events
