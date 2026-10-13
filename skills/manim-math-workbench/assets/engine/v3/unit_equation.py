"""Reusable phrase plan for one fractional unit plus repeated whole units.

All numbers, the entity and phrase anchors come from the current narration.
This covers x/d + m*x = total; it never embeds a particular recording or answer.
"""
from __future__ import annotations

from fractions import Fraction
import re
from typing import Any


NUMBER = r"(?:\d+(?:\.\d+)?|十二|十一|十|九|八|七|六|五|四|三|两|二|一)"
SMALL = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
         "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}


def number(text: str) -> Fraction:
    return Fraction(SMALL[text]) if text in SMALL else Fraction(text)


def shown(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else str(float(value))


def fraction_multiple_plan(raw: dict[str, Any], request: dict[str, Any]) -> dict[str, Any] | None:
    narration = str(request.get("narration") or "")
    entities = raw.get("entities") or []
    if len(entities) != 1 or not isinstance(entities[0], dict):
        return None
    entity = dict(entities[0])
    kind = entity.get("kind")
    aliases = {"square": r"方框|方块|正方形", "circle": r"圆圈|圆形|圆", "triangle": r"三角形|三角"}
    if kind not in aliases:
        return None
    names = f"(?:{aliases[kind]})"
    division = re.search(names + r"(?:除以|÷)\s*(" + NUMBER + ")", narration)
    multiple = re.search(names + r"(?:乘以|×)\s*(" + NUMBER + ")", narration)
    total_match = re.search(r"(?:全部|全都|一起|总共|总和)[^。；;]{0,40}?(?:等于|就是|为)\s*(" + NUMBER + ")", narration)
    if not (division and multiple and total_match):
        return None
    d, m, total = number(division[1]), number(multiple[1]), number(total_match[1])
    if d.denominator != 1 or m.denominator != 1 or not 2 <= d <= 12 or not 1 <= m <= 4 or total <= 0:
        return None
    d, m = int(d), int(m)
    total_parts = 1 + d * m
    share = total / total_parts
    answer = share * d
    # Recognition requires the independent spoken share-count/answer evidence.
    count_match = re.search(r"(?:一共|总共|总份数)[^，。]{0,5}?(" + NUMBER + r")份", narration)
    answer_match = re.search(names + r"(?:里面|里)?的数(?:就是|是|等于)\s*(" + NUMBER + ")", narration)
    if not count_match or number(count_match[1]) != total_parts or not answer_match or number(answer_match[1]) != answer:
        return None
    if request.get("problem"):
        # An explicit question takes precedence. Recognize only a matching
        # arithmetic expression, not an unrelated question with similar copy.
        compact = re.sub(r"\s+", "", str(request["problem"]))
        compact = re.sub(names + r"|□|○|△|\{\{[a-z0-9_]+\}\}", "X", compact)
        compact = compact.translate(str.maketrans({"÷": "/", "×": "*", "＋": "+", "＝": "="}))
        if f"X/{d}+X*{m}={shown(total)}" not in compact and f"X/{d}+{m}*X={shown(total)}" not in compact:
            return None
    identifier = str(entity.get("id") or "shape")
    symbol = "{{" + identifier + "}}"
    equation = f"{symbol}÷{d}＋{symbol}×{m}＝{shown(total)}"
    texts = re.findall(r"[^，,。！？!?；;\n]+[，,。！？!?；;\n]*", narration)
    if "".join(texts) != narration or len(texts) < 4:
        return None
    beats: list[dict[str, Any]] = []
    divided = False
    extracted = False
    copied = False
    copy_partitioned = False
    isolated = False
    after_share = False
    gathered = False

    def diagram(instance: int, parts: int) -> dict[str, Any]:
        return {"entity": identifier, "instance": instance, "parts": parts, "caption": f"{parts}份"}

    for index, text in enumerate(texts):
        beat: dict[str, Any] = {"id": f"u{index+1:02}", "narration": text, "duration": 2,
                                "layout": "derivation", "heading": "", "rows": [],
                                "diagrams": [], "focus": [], "actions": []}

        def action(kind: str, anchor: str, instance: int = -1, *, all_shapes: bool = False):
            item = {"type": kind, "anchor": anchor,
                                    "entity": "" if all_shapes else identifier,
                                    "instance": instance, "parts": d, "row": 0}
            beat["actions"].append(item)
            return item

        if index == 0:
            beat.update(layout="equations", rows=[equation])
            action("show_formula", text.rstrip("，。"))
        elif re.search(r"平均分成", text):
            divided = True
            targets = list(range(1, m + 1)) if copied else [0]
            copy_partitioned = copied
            beat.update(layout="diagram", diagrams=[diagram(i, d) for i in targets], rows=[f"{symbol}×{m}" if copied else f"{symbol}÷{d}"])
            anchor = text[text.index("平均分成"):].rstrip("，。")
            for instance in targets:
                action("partition_shape", anchor, instance)
        elif re.search(r"(?:其中|取)(?:的)?一份", text) and not copied:
            extracted = True
            beat.update(layout="diagram", diagrams=[diagram(0, d)], rows=[f"{symbol}÷{d}"])
            action("extract_part", re.search(r"(?:其中|取)(?:的)?一份", text)[0], 0)
        elif re.search(names + r"(?:乘以|×)", text) or (not copied and re.search(r"(?:三个|两个|四个).*(?:正方形|圆|三角)", text)):
            copied = True
            beat.update(layout="diagram", diagrams=[diagram(i, 1) for i in range(1, m + 1)], rows=[f"{symbol}×{m}"])
            action("focus_formula", text.rstrip("，。"), 1)
            for instance in range(1, m + 1):
                action("show_whole", text.rstrip("，。"), instance)
        elif re.search(r"画一个|先画|绘制一个", text):
            beat.update(layout="diagram", diagrams=[diagram(0, 1)], rows=[symbol])
            action("show_whole", text.rstrip("，。"), 0)
        elif re.search(names + r"(?:除以|÷)", text):
            beat.update(layout="diagram", diagrams=[diagram(0, d if divided else 1)], rows=[f"{symbol}÷{d}"])
            action("focus_formula", text.rstrip("，。"), 0)
        elif re.search(r"(?:一共|总共).*份", text):
            beat["rows"] = [f"1份＋{m*d}份＝{total_parts}份"]
            if copy_partitioned:
                gather = action("collect_parts", text.rstrip("，。"), all_shapes=True)
                gather.update(count=total_parts, total=shown(total), targets=[
                    {"entity": identifier, "instance": 0, "selection": "selected"},
                    *({"entity": identifier, "instance": i, "selection": "all"} for i in range(1, m + 1)),
                ])
                gathered = True
            else:
                action("focus_diagram", text.rstrip("，。"), all_shapes=True)
            action("show_formula", text.rstrip("，。"))
        elif "每一份" in text or "每份" in text:
            after_share = True
            result = f"每份＝{shown(total)}÷{total_parts}"
            if "÷" not in text and "除以" not in text:
                result += "＝" + shown(share)
            beat["rows"] = [result]
            if gathered:
                action("focus_part", text.rstrip("，。"), 0).update(part_index=0)
            action("divide" if "÷" in text or "除以" in text else "show_answer", text.rstrip("，。"))
        elif after_share and re.search(r"合并|拼回|拼成", text):
            beat.update(layout="diagram", diagrams=[diagram(0, d)], rows=[f"{symbol}＝{d}×{shown(share)}"])
            action("assemble_whole", text.rstrip("，。"), 0)
        elif re.search(names + r"(?:里面|里)?的数(?:就是|是|等于)", text) or "最终答案" in text:
            beat["rows"] = [{"text": f"{symbol}＝{shown(answer)}", "accent": True}]
            beat["layout"] = "summary" if index == len(texts) - 1 else "derivation"
            beat["focus"] = "all"
            action("show_answer", text.rstrip("，。"))
        else:
            says_total = re.search(r"(?:等于|就是|为)\s*" + re.escape(shown(total)), text)
            adding = re.search(r"全部|加一起|一起", text)
            beat["rows"] = [f"总和＝{shown(total)}" if says_total else
                            f"{symbol}÷{d}＋{symbol}×{m}" if copied and adding else
                            f"{symbol}×{m}" if copied else equation]
            action("focus_diagram" if copied else "hold", text.rstrip("，。"), all_shapes=True)
            if copied and (says_total or adding):
                action("show_formula", text.rstrip("，。"))
        if copied and extracted and not isolated and re.search(r"全部|加一起|总共|一起", text):
            # Count only the taken fraction, not its discarded remainder.
            action("isolate_part", text.rstrip("，。"), 0)
            isolated = True
        if index == len(texts) - 1:
            beat.update(layout="summary", rows=[{"text": f"{symbol}＝{shown(answer)}", "accent": True}], focus="all", diagrams=[])
        beats.append(beat)
    if not (divided and extracted and copied and copy_partitioned):
        return None
    return {"schema_version": "4.3", "title": request.get("title") or raw.get("title"),
            "problem": equation, "entities": [entity], "beats": beats,
            "local_math_contract": {"denominator": d, "copies": m, "total": shown(total),
                                    "total_parts": total_parts, "share": shown(share), "answer": shown(answer)}}
