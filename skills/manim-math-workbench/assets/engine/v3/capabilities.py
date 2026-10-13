"""Versioned executor contract, shared by creation, editing and validators."""
import json

CAPABILITY_VERSION = "p0-1"
ALLOWED_KINDS = {"circle", "square", "triangle", "badge", "rectangle"}
ALLOWED_ACTIONS = set("show_text show_formula focus_formula focus_diagram show_whole partition_shape extract_part isolate_part assemble_whole collect_parts focus_part restore_parts transform_formula substitute combine cancel divide show_answer clear_work hold copy_equation merge_equations".split())
BASE_FIELDS = {"type", "anchor", "entity", "instance", "parts", "row", "direction", "anchor_offset"}
ACTION_FIELDS = {name: BASE_FIELDS | (
    {"count", "part_index", "total", "targets"} if name in {"collect_parts", "focus_part", "restore_parts"}
    else {"source_row", "slot"} if name == "copy_equation"
    else {"slots"} if name == "merge_equations" else set()) for name in ALLOWED_ACTIONS}
SPECIAL_RENDERERS = {"cauchy_linear_min_v1", "circle_linear_max_v1"}


def renderer_capability(spec):
    renderer = (spec.get("local_math_contract") or {}).get("renderer", "generic")
    return {"version": CAPABILITY_VERSION, "renderer": renderer,
        "editable_beat_fields": [] if renderer in SPECIAL_RENDERERS else
            ["duration", "layout", "heading", "rows", "focus", "diagrams", "actions", "operators"],
        "limitation": "专用几何运行器按已验证数学合同生成画面，暂不支持对话修改通用分镜字段；不会把无效修改当作成功。" if renderer in SPECIAL_RENDERERS else ""}


def capability_prompt():
    return "【执行器能力清单，优先于旧示例；版本 " + CAPABILITY_VERSION + "】\n" + json.dumps({
        "entity_kinds": sorted(ALLOWED_KINDS),
        "actions": {k: sorted(v) for k, v in sorted(ACTION_FIELDS.items())},
        "state_validator": "v3.part_motion.part_state_issues",
        "formula_validator": "v3.rendering._formula_action_report",
        "rules": ["还原汇集后集合为空；再次focus_part必须先collect_parts。",
                  "assemble_whole还原目标并移除其他图解；不可继续引用已移除实例。",
                  "clear_work只清理演算公式，不清理图解。",
                  "isolate_part/assemble_whole必须指定精确的entity和instance，不可使用instance=-1。",
                  "单位操作、汇集操作先于本段新图解执行；需要新切分结果时拆到下一段。",
                  "只支持所列动作。自由路径、任意旋转/投影不可冒充已支持；报告unsupported_requirements。",
                  "相同图形按出现次序区分加数，不能去重；复制/合并/重排保持已有对象尺寸。"],
        "examples": ["partition_shape → extract_part → 下一段collect_parts → restore_parts → 重新collect_parts → focus_part",
                     "copy_equation(slot=0) → copy_equation(slot=1) → merge_equations(slots=[0,1]) → transform_formula"]
    }, ensure_ascii=False)
