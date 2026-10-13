"""Geometry-only planning shared by preview, final rendering and tests."""
import math


def part_state_issues(beats):
    """Shared pure preflight, in runtime phase order (units, collection, diagrams).

    clear_work clears formula work only; geometry remains available.
    Collection members are (entity/instance, part index), never lookalike copies.
    """
    objects, collection, issues = {}, set(), []
    collection_source = None
    for number, beat in enumerate(beats, 1):
        actions = [a for a in beat.get("actions", []) if isinstance(a, dict)]
        beat_id = beat.get("id") or f"b{number:02d}"
        def fail(index, key, code, message, source=None):
            issues.append(dict(category="state", code=code, beat_id=beat_id,
                action_index=index, object={"entity": key[0], "instance": key[1]} if key else None,
                source_beat=source, problem=f"第{number}个模型分镜" + message))
        for index, action in enumerate(actions):
            kind = action.get("type")
            if kind not in {"isolate_part", "assemble_whole"}:
                continue
            key = (action.get("entity"), action.get("instance", 0))
            state = objects.get(key)
            if not state or not state["extracted"]:
                fail(index, key, "PART_NOT_EXTRACTED", f"的{kind}目标尚未抽取", state and state["source"])
                continue
            if kind == "isolate_part":
                if collection:
                    fail(index, key, "PART_STILL_COLLECTED", "须先还原汇集再丢弃其余等份", collection_source)
                state["isolated"] = True
            else:
                objects = {key: state}
                state.update(extracted=False, isolated=False, source=beat_id)
                collection.clear()
                collection_source = beat_id
        for index, action in enumerate(actions):
            kind = action.get("type")
            if kind == "collect_parts":
                targets = action.get("targets") or [dict(entity=k[0], instance=k[1]) for k in objects
                    if not action.get("entity") or k[0] == action["entity"]]
                selected, valid = set(), True
                for target in targets:
                    key = (target.get("entity"), target.get("instance", 0))
                    state = objects.get(key)
                    selection = target.get("selection", "visible")
                    if not state or state["parts"] < 2 or (selection == "selected" and not state["extracted"]) or (selection == "all" and state["isolated"]):
                        fail(index, key, "COLLECTION_SOURCE_UNAVAILABLE", "汇集目标尚未完成切分/抽取或已退场", state and state["source"])
                        valid = False
                        continue
                    indices = [state["parts"] - 1] if selection == "selected" or state["isolated"] else range(state["parts"])
                    selected.update((key, i) for i in indices)
                if not selected or (action.get("count") and action["count"] != len(selected)):
                    fail(index, None, "COLLECTION_COUNT_MISMATCH", "没有可汇集的等份或数量不符")
                    valid = False
                if valid:
                    collection, collection_source = selected, beat_id
            elif kind in {"focus_part", "restore_parts"}:
                if not collection:
                    fail(index, None, "COLLECTION_EMPTY", f"的{kind}要求此前已经汇集等份（还原后须重新汇集）", collection_source)
                elif kind == "focus_part" and not 0 <= action.get("part_index", 0) < len(collection):
                    fail(index, None, "COLLECTION_INDEX_OUT_OF_RANGE", "单份编号超出汇集数量", collection_source)
                elif kind == "restore_parts":
                    collection.clear()
                    collection_source = beat_id
        current_keys = {(d.get("entity"), d.get("instance", 0)) for d in beat.get("diagrams", []) if isinstance(d, dict)} if beat.get("layout") == "diagram" else set()
        for index, action in enumerate(actions):
            if action.get("type") == "focus_diagram":
                keys = set(objects) | current_keys
                entity, instance = action.get("entity"), action.get("instance", -1)
                if not any((not entity or key[0] == entity) and (instance < 0 or key[1] == instance) for key in keys):
                    fail(index, (entity, instance), "DIAGRAM_NOT_VISIBLE", "红框目标尚未出现或已退场")
        if beat.get("layout") != "diagram":
            continue
        for diagram in beat.get("diagrams", []):
            if not isinstance(diagram, dict):
                continue
            key = (diagram.get("entity"), diagram.get("instance", 0))
            parts = diagram.get("parts", 1)
            if type(parts) is not int or not 1 <= parts <= 12:
                continue
            state = objects.setdefault(key, dict(parts=1, extracted=False, isolated=False, source=beat_id))
            matches = [(i, a) for i, a in enumerate(actions) if a.get("entity") == key[0]
                       and a.get("instance", -1) in {-1, key[1]}]
            for index, action in matches:
                if action.get("type") == "partition_shape" and parts > 1:
                    if any(item[0] == key for item in collection):
                        fail(index, key, "PART_STILL_COLLECTED", "须先还原汇集再重新切分", collection_source)
                    state.update(parts=parts, extracted=False, isolated=False, source=beat_id)
                elif action.get("type") == "extract_part":
                    if parts < 2 or state["parts"] != parts:
                        fail(index, key, "PART_NOT_PARTITIONED", "必须先切分再抽取，不能从未等分图形直接抽取", state["source"])
                    else:
                        state.update(extracted=True, source=beat_id)
    return issues


def grid_positions(dimensions, center=(0.0, 0.05), width=7.0, height=3.0, gap=0.18):
    """Pack real-size pieces without resizing, rotation or overlaps.

    Return the centers in input order. Oversized collections need another beat;
    silently shrinking every unit would change its meaning relative to a whole.
    """
    if not dimensions:
        raise ValueError("没有可汇集的等份")
    if any(len(item) != 2 or any(not math.isfinite(v) or v <= 0 for v in item) for item in dimensions):
        raise ValueError("等份尺寸必须是有限正数")
    cell_w = max(item[0] for item in dimensions)
    cell_h = max(item[1] for item in dimensions)
    max_cols = math.floor((width + gap) / (cell_w + gap))
    max_rows = math.floor((height + gap) / (cell_h + gap))
    if max_cols < 1 or max_rows < 1 or len(dimensions) > max_cols * max_rows:
        raise ValueError("等份数量超出当前画面容量，请拆成多个汇集步骤")
    columns = min(5, max_cols, len(dimensions))
    columns = max(columns, math.ceil(len(dimensions) / max_rows))
    rows = math.ceil(len(dimensions) / columns)
    return [
        (center[0] + (index % columns - (columns - 1) / 2) * (cell_w + gap),
         center[1] + ((rows - 1) / 2 - index // columns) * (cell_h + gap))
        for index in range(len(dimensions))
    ]


def assert_piece_count(actual, expected):
    if expected and actual != expected:
        raise ValueError(f"汇集等份数量不一致：实际 {actual} 份，分镜要求 {expected} 份")
