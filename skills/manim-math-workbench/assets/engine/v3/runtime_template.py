from manim import *
import json
import math
import numpy as np
import re
from v3.part_motion import grid_positions, assert_piece_count, part_state_issues  # __INJECT_PART_MOTION__
from v3.equation_motion import equation_motion_tokens, equation_sum_mapping  # __INJECT_EQUATION_MOTION__
from v3.circle_max_motion import play_circle_linear_max  # __INJECT_CIRCLE_MAX_MOTION__
from v3.cauchy_min_motion import play_cauchy_linear_min  # __INJECT_CAUCHY_MIN_MOTION__


STORYBOARD_SPEC = {}  # __INJECT_STORYBOARD__

# Reference-locked portrait canvas: 1080 x 1440 (3:4). The command line
# chooses pixel resolution; these logical dimensions keep preview/final equal.
config.frame_width = 9.0
config.frame_height = 12.0
config.background_color = BLACK

FONT = "Microsoft YaHei"
TITLE_COLOR = "#FFD23F"
RESULT_RED = "#FF5A5F"
BOX_RED = "#F23B42"
WHITE_TEXT = "#F7F7F7"
MUTED_TEXT = "#A8B0BE"
COUNT_TEXT = "#FFF04A"
COUNT_LABEL_Y = -1.64  # below extracted-piece frame, never on its bottom border
PLACEHOLDER_RE = re.compile(r"(\{\{[a-z][a-z0-9_]*\}\})")
TOKEN_RE = re.compile(
    r"(\{\{[a-z][a-z0-9_]*\}\}|[＋+－−\-×*÷/＝=]|[（）()\[\]]|"
    r"\d+(?:\.\d+)?(?:万|亿|千|百)?(?:美元|元|份)?|[^\s＋+－−\-×*÷/＝=（）()\[\]\d]+)"
)
BANNED_CAPTION_WORDS = (
    "点赞", "关注", "评论", "转发", "收藏", "二维码", "水印",
    "说说你的", "留言",
)
PART_COUNT_VALUES = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
    "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
}
PART_COUNT_PATTERN = r"(?:12|11|10|[1-9]|十二|十一|十|九|八|七|六|五|四|三|二|两|一)"
# A rectangle is drawn as a wide strip (4:1) so partitioning it into 4 pieces
# yields equal squares. Its optical height is slightly reduced so three objects
# (square + rectangle + strip) coexist on one row without overlap.
RECT_SCALE = 0.85


def fit_inside(mobject, max_width=8.15, max_height=4.0):
    factor = min(1.0, max_width / max(mobject.width, 1e-6), max_height / max(mobject.height, 1e-6))
    if factor < 1.0:
        mobject.scale(factor)
    return mobject


def readable_replacement(previous, following):
    """Keep unrelated formula glyphs legible instead of morphing their paths."""
    return Succession(FadeOut(previous), FadeIn(following))


def safe_text(text, font_size=30, color=WHITE_TEXT, weight=NORMAL):
    return Text(str(text), font=FONT, font_size=font_size, color=color, weight=weight)


def entity_map():
    return {item["id"]: item for item in STORYBOARD_SPEC.get("entities", [])}


def make_shape_symbol(entity, height=0.58):
    """Create every icon from one optical-height/stroke factory."""
    kind = entity.get("kind", "badge")
    color = entity.get("color", WHITE_TEXT)
    stroke = 4.0
    if kind == "circle":
        shape = Circle(radius=1.0, color=color, stroke_width=stroke, fill_color=color, fill_opacity=0.12)
    elif kind == "square":
        shape = Square(side_length=2.0, color=color, stroke_width=stroke, fill_color=color, fill_opacity=0.12)
    elif kind == "triangle":
        shape = RegularPolygon(
            n=3,
            start_angle=PI / 2,
            color=color,
            stroke_width=stroke,
            fill_color=color,
            fill_opacity=0.12,
        )
    elif kind == "rectangle":
        shape = Rectangle(
            width=4.0,
            height=1.0,
            color=color,
            stroke_width=stroke,
            fill_color=color,
            fill_opacity=0.12,
        )
    else:
        shape = RoundedRectangle(
            width=1.75,
            height=1.10,
            corner_radius=0.18,
            color=color,
            stroke_width=stroke,
            fill_color=color,
            fill_opacity=0.12,
        )
    shape.set_height(height * (RECT_SCALE if kind == "rectangle" else 1.0))
    shape.move_to(ORIGIN)
    slot = Rectangle(
        width=max(height * 1.24, shape.width),
        height=height * 1.24,
        stroke_width=0,
        stroke_opacity=0,
        fill_opacity=0,
    )
    icon = VGroup(slot, shape)
    if kind == "badge":
        label = safe_text(entity.get("label", ""), font_size=18, color=color, weight=BOLD)
        fit_inside(label, max_width=max(0.2, shape.width * 0.78), max_height=max(0.2, shape.height * 0.58))
        label.move_to(shape.get_center())
        icon.add(label)
    return icon


def formula_tokens(text):
    # Isolate placeholders before the greedy prose alternative can consume
    # e.g. "、{{tri}}" or "求{{box}}" as a single ordinary text token.
    # Unknown IDs remain intact and are rendered literally by make_formula_row.
    result = []
    for segment in PLACEHOLDER_RE.split(str(text)):
        if PLACEHOLDER_RE.fullmatch(segment):
            result.append(segment)
        else:
            result.extend(token for token in TOKEN_RE.findall(segment)
                          if token and not token.isspace())
    return result


def make_formula_row(row_spec, entities, font_size=30):
    accent = bool(row_spec.get("accent", False))
    pieces = []
    keys = []
    for token in formula_tokens(row_spec.get("text", "")):
        if token.startswith("{{") and token.endswith("}}"):
            entity_id = token[2:-2]
            if entity_id in entities:
                pieces.append(make_shape_symbol(entities[entity_id], height=0.58))
                keys.append(f"entity:{entity_id}")
                continue
        normalized = "＝" if token == "=" else "＋" if token == "+" else token
        pieces.append(
            safe_text(
                normalized,
                font_size=font_size,
                color=RESULT_RED if accent else WHITE_TEXT,
                weight=BOLD if accent else NORMAL,
            )
        )
        keys.append(f"text:{normalized}")
    if not pieces:
        pieces = [safe_text("—", font_size=font_size, color=MUTED_TEXT)]
        keys = ["text:—"]
    row = VGroup(*pieces).arrange(RIGHT, buff=0.11)
    fit_inside(row, max_width=8.05, max_height=0.82)
    row._formula_keys = keys
    return row


def build_rows(beat, entities, horizontal=False, max_height=1.75):
    rows = [make_formula_row(row, entities) for row in beat.get("rows", [])]
    if not rows:
        return VGroup(), []
    direction = RIGHT if horizontal else DOWN
    group = VGroup(*rows).arrange(direction, buff=0.42 if horizontal else 0.30)
    fit_inside(group, max_width=8.05, max_height=max_height)
    return group, rows


def partition_lines(shape, kind, parts, color=WHITE_TEXT):
    lines = VGroup()
    if parts <= 1:
        return lines
    if kind == "circle":
        if parts in (2, 4):
            lines.add(Line(shape.get_top(), shape.get_bottom(), color=color, stroke_width=4.0))
        if parts == 4:
            lines.add(Line(shape.get_left(), shape.get_right(), color=color, stroke_width=4.0))
        elif parts not in (2, 4):
            center = shape.get_center()
            radius = shape.width / 2
            # N equally spaced radii create N equal-area sectors.  Keep 2/4
            # as full diameters so the reference vertical/horizontal motion is
            # preserved exactly.
            for index in range(parts):
                angle = -PI / 2 + index * TAU / parts
                endpoint = center + radius * np.array([math.cos(angle), math.sin(angle), 0.0])
                lines.add(Line(center, endpoint, color=color, stroke_width=4.0))
    elif kind == "square":
        left = shape.get_left()[0]
        right = shape.get_right()[0]
        top = shape.get_top()[1]
        bottom = shape.get_bottom()[1]
        for index in range(1, parts):
            x = left + (right - left) * index / parts
            lines.add(Line([x, bottom, 0], [x, top, 0], color=color, stroke_width=4.0))
    elif kind == "rectangle":
        left = shape.get_left()[0]
        right = shape.get_right()[0]
        top = shape.get_top()[1]
        bottom = shape.get_bottom()[1]
        for index in range(1, parts):
            x = left + (right - left) * index / parts
            lines.add(Line([x, bottom, 0], [x, top, 0], color=color, stroke_width=4.0))
    elif kind == "triangle" and 2 <= parts <= 12:
        vertices = list(shape.get_vertices())
        top = max(vertices, key=lambda point: point[1])
        lower = sorted(sorted(vertices, key=lambda point: point[1])[:2], key=lambda point: point[0])
        for index in range(1, parts):
            base_point = lower[0] + (lower[1] - lower[0]) * index / parts
            lines.add(Line(top, base_point, color=color, stroke_width=4.0))
    return lines


def make_exploded_parts(entity, parts, height=1.06):
    """Build joined, equal-area pieces with the exact original silhouette."""
    kind = entity.get("kind", "badge")
    color = entity.get("color", WHITE_TEXT)
    pieces = VGroup()
    if kind == "circle" and 2 <= parts <= 12:
        radius = height / 2
        # Match partition_lines exactly: halves use the vertical diameter and
        # general N-way partitions start at the bottom radius.  Four quarters
        # retain the reference ordering so the last piece is the lower-right.
        start_offset = 0 if parts == 4 else -PI / 2
        for index in range(parts):
            piece = Sector(
                radius=radius,
                angle=TAU / parts,
                start_angle=start_offset + index * TAU / parts,
                stroke_color=color,
                stroke_width=4.0,
                fill_color=color,
                fill_opacity=0.18,
            )
            pieces.add(piece)
    elif kind == "square" and 1 <= parts <= 12:
        piece_width = height / parts
        piece_height = height
        for index in range(parts):
            piece = Rectangle(
                width=piece_width,
                height=piece_height,
                stroke_color=color,
                stroke_width=4.0,
                fill_color=color,
                fill_opacity=0.18,
            )
            piece.move_to([
                (index - (parts - 1) / 2) * piece_width,
                0,
                0,
            ])
            pieces.add(piece)
    elif kind == "triangle" and 2 <= parts <= 12:
        triangle_height = height
        triangle_width = triangle_height * 2 / math.sqrt(3)
        top = np.array([0.0, triangle_height / 2, 0.0])
        base_left = np.array([-triangle_width / 2, -triangle_height / 2, 0.0])
        base_right = np.array([triangle_width / 2, -triangle_height / 2, 0.0])
        for index in range(parts):
            first = base_left + (base_right - base_left) * index / parts
            second = base_left + (base_right - base_left) * (index + 1) / parts
            pieces.add(Polygon(
                top,
                first,
                second,
                stroke_color=color,
                stroke_width=4.0,
                fill_color=color,
                fill_opacity=0.18,
            ))
    elif kind == "rectangle" and 1 <= parts <= 12:
        # Tiles exactly cover the bar: partitioning preserves area and orientation.
        bar_height = height * RECT_SCALE
        bar_width = bar_height * 4.0
        piece_width = bar_width / parts
        for index in range(parts):
            piece = Rectangle(
                width=piece_width, height=bar_height,
                stroke_color=color, stroke_width=4.0,
                fill_color=color, fill_opacity=0.18,
            )
            piece.move_to([-bar_width / 2 + piece_width * (index + 0.5), 0, 0])
            pieces.add(piece)
    else:
        for index in range(max(1, parts)):
            copy = make_shape_symbol(entity, height=height * 0.46)
            copy.move_to([(index % 3 - 1) * height * 0.48, (0.5 - index // 3) * height * 0.58, 0])
            pieces.add(copy)
    return pieces


def deictic_part_count_label(text):
    """Turn a spoken pointer such as '这里是五份' into the label '5份'."""
    compact = re.sub(r"\s+", "", str(text or ""))
    match = re.search(
        rf"(?:这里|这边|此处|一共|共有|总共)[^，。！？；;]{{0,8}}?({PART_COUNT_PATTERN})份",
        compact,
    )
    if not match:
        return ""
    raw = match.group(1)
    value = int(raw) if raw.isdigit() else PART_COUNT_VALUES.get(raw, 0)
    return f"{value}份" if 1 <= value <= 12 else ""


def dashed_outline(target, buff_x=0.18, buff_y=0.13):
    outline = RoundedRectangle(
        width=target.width + buff_x * 2,
        height=target.height + buff_y * 2,
        corner_radius=0.12,
        color=BOX_RED,
        stroke_width=2.8,
        fill_opacity=0,
    ).move_to(target.get_center())
    perimeter = 2 * (outline.width + outline.height)
    return DashedVMobject(outline, num_dashes=max(18, int(perimeter * 3.0)), dashed_ratio=0.62)


def make_dashed_box(targets, separate=False):
    if separate:
        box = VGroup(*(dashed_outline(target, 0.12, 0.10) for target in targets))
    else:
        box = dashed_outline(VGroup(*targets))
    # Identity references, not copies: a frame targeting a diagram must travel
    # with that diagram, whereas a frame targeting the problem board stays put.
    box._focus_target_ids = {id(member) for target in targets for member in target.get_family()}
    return box


def row_key_indexes(row, key):
    return [index for index, value in enumerate(getattr(row, "_formula_keys", [])) if value == key]


def entity_expression_targets(board_rows, entity_id):
    entity_key = f"entity:{entity_id}"
    for row in board_rows:
        keys = getattr(row, "_formula_keys", [])
        for index, key in enumerate(keys):
            if key != entity_key:
                continue
            targets = [row[index]]
            if index + 1 < len(keys) and keys[index + 1] == "text:÷":
                targets.append(row[index + 1])
                if index + 2 < len(keys):
                    targets.append(row[index + 2])
            return targets
    return []


def formula_key_sequence(text):
    keys = []
    for token in formula_tokens(text):
        if token.startswith("{{") and token.endswith("}}"):
            keys.append(f"entity:{token[2:-2]}")
        else:
            normalized = "＝" if token == "=" else "＋" if token == "+" else token
            keys.append(f"text:{normalized}")
    return keys


def board_subformula_targets(requested_texts, board_rows):
    """Find exact contiguous formula fragments on the persistent problem board."""
    all_targets = []
    requested = [str(text).strip() for text in requested_texts if str(text).strip()]
    if not requested:
        return [], False
    for text in requested:
        needle = formula_key_sequence(text)
        if not needle:
            return [], False
        found = []
        for row in board_rows:
            haystack = list(getattr(row, "_formula_keys", []))
            for start in range(0, len(haystack) - len(needle) + 1):
                if haystack[start:start + len(needle)] == needle:
                    found = [row[index] for index in range(start, start + len(needle))]
                    break
            if found:
                break
        if not found:
            return [], False
        all_targets.extend(found)
    return all_targets, True


def semantic_board_focus(beat, board_rows, entities):
    if not board_rows:
        return [], False
    # The same variable can occur in both x/d and x*m. Use the requested
    # contiguous expression before falling back to the entity's first icon.
    if any(action.get("type") == "focus_formula" for action in beat.get("actions", [])):
        exact, matched = board_subformula_targets([row.get("text", "") for row in beat.get("rows", [])], board_rows)
        if matched and exact:
            return exact, False
    text = str(beat.get("narration", "")) + str(beat.get("heading", ""))
    mentioned = [entity_id for entity_id, entity in entities.items() if str(entity.get("label", "")) in text]
    if len(mentioned) == 1:
        targets = entity_expression_targets(board_rows, mentioned[0])
        if targets:
            return targets, False
    if "相等" in text or "等于号" in text:
        equals = []
        for row in board_rows:
            indexes = row_key_indexes(row, "text:＝")
            if len(indexes) >= 2:
                equals.extend(row[index] for index in indexes)
                break
        if equals:
            return equals, True
    if ("加" in text or "＋" in text) and len(mentioned) >= 2:
        for row in board_rows:
            keys = set(getattr(row, "_formula_keys", []))
            if "text:＋" in keys and all(f"entity:{entity_id}" in keys for entity_id in mentioned):
                return [row], False
    if "第一条" in text and len(board_rows) >= 1:
        return [board_rows[0]], False
    if "第二条" in text and len(board_rows) >= 2:
        return [board_rows[1]], False
    if "第三条" in text and len(board_rows) >= 3:
        return [board_rows[2]], False
    if mentioned:
        for row in board_rows:
            keys = set(getattr(row, "_formula_keys", []))
            if all(f"entity:{entity_id}" in keys for entity_id in mentioned):
                return [row], False
    if any(word in text for word in ("全部", "总的", "总和", "一起")):
        for row in board_rows:
            if "text:＋" in getattr(row, "_formula_keys", []):
                return [row], False
    return [], False


def explicit_focus_targets(beat, refs):
    focus = beat.get("focus", [])
    if focus == "all":
        return list(refs)
    return [refs[index] for index in focus if isinstance(index, int) and 0 <= index < len(refs)]


def answer_values(rows):
    """Extract independent value assignments, never a derivation's last number.

    A summary may contain several assignments on one row. Conversely, a row
    such as ``{{box}}=10/2=5`` must remain a worked derivation rather than being
    silently replaced by the direct-answer overlay path.
    """
    answers = []
    separators = " \t\r\n,，;；、。"
    assignment = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}\s*[＝=]\s*")
    number = r"[+\-−]?(?:\d+(?:\.\d+)?(?:\s*/\s*\d+)?|[零〇一二两三四五六七八九十百千万亿]+)"
    unit = r"(?:\s*[万亿])?(?:\s*(?:美元|人民币|元|块|个|份|米|厘米|千米|克|千克|秒))?"
    literal_value = re.compile(number + unit)
    for row in rows:
        text = str(row.get("text", "")).strip()
        matches = list(assignment.finditer(text))
        if not matches or text[:matches[0].start()].strip(separators):
            continue
        row_answers = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            if index + 1 < len(matches) and text[end - 1] not in separators:
                break
            value = text[match.end():end].strip(separators)
            if not literal_value.fullmatch(value):
                break
            row_answers.append((match.group(1), value))
        else:
            # Partial recognition of a complex expression is unsafe: only a
            # fully consumed row of explicit assignments qualifies.
            answers.extend(row_answers)
    return answers


def short_shape_answer_values(rows, entities):
    results = []
    for entity_id, value in answer_values(rows):
        entity = entities.get(entity_id, {})
        if entity.get("kind") in {"circle", "square", "triangle"} and len(value) <= 6:
            results.append((entity_id, value))
    return results


def diagram_positions(ids):
    # Formula-only derivations have no standalone partition diagrams. An empty
    # reservation is valid; do not invent a slot or index a nonexistent object.
    count = len(ids)
    if count == 0:
        return {}
    if count == 1:
        return {ids[0]: 0.0}
    # 18%, 50%, 82% of the 1080px canvas, matching the reference spacing.
    left = -2.88
    right = 2.88
    return {entity_id: left + (right - left) * index / (count - 1) for index, entity_id in enumerate(ids)}


class GeneratedMathVideo(Scene):
    def construct(self):
        self.camera.background_color = BLACK
        if STORYBOARD_SPEC.get("planner_mode") == "model":
            state_errors = part_state_issues(STORYBOARD_SPEC.get("beats", []))
            if state_errors:
                raise ValueError(json.dumps(state_errors, ensure_ascii=False))
        if (STORYBOARD_SPEC.get("local_math_contract") or {}).get("renderer") == "cauchy_linear_min_v1":
            play_cauchy_linear_min(self, STORYBOARD_SPEC)
            return
        if (STORYBOARD_SPEC.get("local_math_contract") or {}).get("renderer") == "circle_linear_max_v1":
            play_circle_linear_max(self, STORYBOARD_SPEC)
            return
        entities = entity_map()
        all_beats = list(STORYBOARD_SPEC.get("beats", []))
        diagram_keys = []
        for beat in all_beats:
            for diagram in beat.get("diagrams", []):
                entity_id = diagram.get("entity")
                key = (entity_id, int(diagram.get("instance", 0)))
                if entity_id in entities and key not in diagram_keys:
                    diagram_keys.append(key)
        reserved_positions = diagram_positions(diagram_keys)
        # A reservation is not an initial placement. The first diagram has the
        # stage to itself until a NEW visual object actually needs the space.
        x_positions = {}

        title_text = safe_text(STORYBOARD_SPEC.get("title", "数学解题可视化"), font_size=39, color=TITLE_COLOR, weight=BOLD)
        fit_inside(title_text, max_width=6.8, max_height=0.62)
        left_arrow = Triangle(fill_color=TITLE_COLOR, fill_opacity=1, stroke_width=0).scale(0.12).rotate(-PI / 2)
        right_arrow = Triangle(fill_color=TITLE_COLOR, fill_opacity=1, stroke_width=0).scale(0.12).rotate(PI / 2)
        title_group = VGroup(left_arrow, title_text, right_arrow).arrange(RIGHT, buff=0.46)
        title_group.move_to([0, 5.18, 0])
        self.play(FadeIn(title_group, shift=DOWN * 0.08), run_time=0.7)

        audio_spec = STORYBOARD_SPEC.get("audio") or {}
        audio_path = str(audio_spec.get("path", "")).strip()
        audio_mode = bool(audio_path)
        audio_origin = float(self.time)
        if audio_mode:
            self.add_sound(audio_path)

        board_group = None
        board_rows = []
        board_texts = []
        model_work_texts = []
        model_work_visuals = []
        equation_copies = {}
        equation_copy_texts = {}
        equation_result_active = False
        current_work = None
        current_box = None
        # Diagram objects live across beats.  Keys include an instance index so
        # “再画一个同样的圆圈” creates a second object while later phrases keep
        # transforming the currently active one.
        diagram_objects = {}
        diagram_wholes = {}
        diagram_lines_by_key = {}
        diagram_parts_by_key = {}
        diagram_piece_sets = {}
        piece_home_positions = {}
        isolated_diagram_keys = set()
        collected_parts = []
        collection_home = []
        collection_label = None
        extracted_diagram_keys = set()
        active_diagram_keys = {}
        count_labels = {}
        shown_count_labels = {}
        shown_count_label_text = {}
        operator_objects = {}
        answer_overlays = {}
        last_summary_signature = None

        def trace_layout():
            print("STUDIO_LAYOUT " + json.dumps({"time": float(self.time), "centers": {
                f"{key[0]}@{key[1]}": [float(x), 0.05, 0]
                for key, x in x_positions.items() if key in diagram_objects
            }}), flush=True)

        def trace_geometry(beat, key, stage):
            print("STUDIO_GEOMETRY " + json.dumps({"id": beat.get("id", ""),
                  "entity": key[0], "instance": key[1], "stage": stage,
                  "time": float(self.time)}), flush=True)

        def make_room_for_diagram(new_key, action):
            """Translate a complete live diagram, including its hidden homes.

            Never animate hidden pieces: doing so would add them back to the
            scene. They move offstage only after the visible group has travelled.
            This also keeps a later assemble_whole from returning to the center.
            """
            nonlocal used
            if not x_positions:
                x_positions[new_key] = 0.0
                return
            animations, hidden_moves, changes = [], [], []
            moved_ids = set()
            for key, visual in diagram_objects.items():
                old_x = x_positions[key]
                new_x = reserved_positions.get(key, old_x)
                if abs(new_x - old_x) < 1e-6:
                    continue
                delta = RIGHT * (new_x - old_x)
                visible_ids = {id(item) for item in visual.get_family()}
                animations.append(visual.animate.shift(delta))
                moved_ids.update(visible_ids)
                label = shown_count_labels.get(key)
                if label is not None:
                    animations.append(label.animate.shift(delta))
                    moved_ids.update(id(item) for item in label.get_family())
                for piece in diagram_piece_sets.get(key, []):
                    if id(piece) not in visible_ids:
                        hidden_moves.append((piece, delta))
                unshown_label = count_labels.get(key)
                if unshown_label is not None and unshown_label is not label:
                    hidden_moves.append((unshown_label, delta))
                if current_box is not None and visible_ids.intersection(getattr(current_box, "_focus_target_ids", set())):
                    animations.append(current_box.animate.shift(delta))
                changes.append((key, new_x, delta))
            if animations:
                before = float(self.time)
                run_time = anchored_step_time(0.42, action)
                self.play(*animations, run_time=run_time, rate_func=smooth)
                used += run_time
                for hidden, delta in hidden_moves:
                    if id(hidden) not in moved_ids:
                        hidden.shift(delta)
                        moved_ids.update(id(item) for item in hidden.get_family())
                for key, new_x, delta in changes:
                    x_positions[key] = new_x
                    if key in piece_home_positions:
                        piece_home_positions[key] = [point + delta for point in piece_home_positions[key]]
                print("STUDIO_REFLOW " + json.dumps({"start": before, "end": float(self.time),
                      "trigger": f"{new_key[0]}@{new_key[1]}", "keys": [f"{key[0]}@{key[1]}" for key, _, _ in changes]}), flush=True)
                trace_layout()
            x_positions[new_key] = reserved_positions.get(new_key, 0.0)

        def visual_keys_for_action(action):
            entity_id = str(action.get("entity", "")) if action else ""
            if not entity_id:
                return [key for key in diagram_keys if key in diagram_objects]
            requested_instance = int(action.get("instance", -1)) if action else -1
            requested_parts = int(action.get("parts", 1)) if action else 1
            exact_key = (entity_id, requested_instance)
            if requested_instance >= 0 and exact_key in diagram_objects:
                return [exact_key]
            matching = [key for key in diagram_keys if key[0] == entity_id and key in diagram_objects]
            matching_parts = [key for key in matching if diagram_parts_by_key.get(key, 1) == requested_parts]
            if matching_parts:
                return [matching_parts[-1]]
            active_key = active_diagram_keys.get(entity_id)
            if active_key in diagram_objects:
                return [active_key]
            return matching

        def visual_targets_for_action(action):
            return [diagram_objects[key] for key in visual_keys_for_action(action)]

        def count_label_animation(action, diagram_key):
            """Animate a count only when the spoken words explicitly point to it."""
            label_text = deictic_part_count_label((action or {}).get("anchor", ""))
            if not label_text:
                return None
            previous = shown_count_labels.get(diagram_key)
            if previous is not None and shown_count_label_text.get(diagram_key) == label_text:
                return None
            label = safe_text(label_text, font_size=21, color=COUNT_TEXT, weight=BOLD)
            label.move_to([x_positions.get(diagram_key, 0.0), COUNT_LABEL_Y, 0])
            count_labels[diagram_key] = label
            shown_count_labels[diagram_key] = label
            shown_count_label_text[diagram_key] = label_text
            if previous is None:
                return FadeIn(label, shift=UP * 0.03)
            return ReplacementTransform(previous, label)

        for beat_index, beat in enumerate(all_beats):
            layout = beat.get("layout", "derivation")
            if audio_mode:
                cue_start = max(0.0, float(beat.get("audio_start", 0.0)))
                cue_end = max(cue_start + 0.08, float(beat.get("audio_end", cue_start + 0.08)))
                until_start = audio_origin + cue_start - float(self.time)
                if until_start > 1e-3:
                    self.wait(until_start)
                duration = cue_end - cue_start
                motion_scale = max(0.12, min(1.0, float(beat.get("motion_scale", 1.0))))
            else:
                cue_start = 0.0
                cue_end = 0.0
                duration = max(1.2, float(beat.get("duration", 3.0)))
                motion_scale = 1.0

            def step_time(base):
                return max(0.04, float(base) * motion_scale)

            used = 0.0
            word_actions = list(beat.get("actions") or [])
            formula_queue_types = {"show_text", "show_formula", "transform_formula", "substitute",
                                   "combine", "cancel", "divide", "focus_formula", "show_answer", "hold", "clear_work",
                                   "copy_equation", "merge_equations"}
            ordered_formula_mode = (STORYBOARD_SPEC.get("planner_mode") == "model"
                                    and layout in {"equations", "derivation"}
                                    and all(a.get("type") in formula_queue_types for a in word_actions))

            def find_action(action_types, entity_id="", instance=None):
                allowed = set(action_types) if isinstance(action_types, (list, tuple, set)) else {action_types}
                matches = [
                    action for action in word_actions
                    if action.get("type") in allowed
                    and (not entity_id or not action.get("entity") or action.get("entity") == entity_id)
                    and (
                        instance is None
                        or int(action.get("instance", -1)) in {-1, int(instance)}
                    )
                ]
                if not matches:
                    return None
                return min(matches, key=lambda item: float(item.get("audio_start", cue_start if audio_mode else 0.0)))

            def wait_for_action(action):
                if not audio_mode or not action:
                    return
                target = audio_origin + float(action.get("audio_start", cue_start))
                remaining = target - float(self.time)
                if remaining > 1e-3:
                    self.wait(remaining)

            def anchored_step_time(base, action=None):
                run_time = step_time(base)
                if not audio_mode or not action:
                    return run_time
                action_start = float(action.get("audio_start", cue_start))
                later = [
                    float(item.get("audio_start", cue_end))
                    for item in word_actions
                    if float(item.get("audio_start", cue_end)) > action_start + 0.015
                ]
                next_start = min(later) if later else cue_end
                room = audio_origin + next_start - float(self.time) - 0.025
                if room <= 0.04:
                    return 0.04
                return max(0.04, min(run_time, room))

            # Narration remains the exact audio/action clock, never a caption
            # mobject. Mathematical rows and diagram count labels are retained.

            clear_action = find_action("clear_work")
            if operator_objects and (clear_action or layout == "summary" or any(
                a.get("type") in {"assemble_whole", "isolate_part", "collect_parts"}
                for a in word_actions
            )):
                for symbol in operator_objects.values():
                    symbol.clear_updaters()
                run_time = anchored_step_time(0.18, clear_action)
                self.play(*[FadeOut(symbol) for symbol in operator_objects.values()], run_time=run_time)
                used += run_time
                operator_objects.clear()
            if clear_action and current_work is not None and not ordered_formula_mode:
                wait_for_action(clear_action)
                run_time = anchored_step_time(0.18, clear_action)
                self.play(FadeOut(current_work), run_time=run_time)
                current_work = None
                used += run_time

            # Declarative unit operations: retain one fraction, or reassemble
            # its equal pieces. All coordinates are derived from the same shape.
            for unit_action in word_actions:
                operation = unit_action.get("type")
                if operation not in {"isolate_part", "assemble_whole"}:
                    continue
                key = (unit_action.get("entity"), int(unit_action.get("instance", 0)))
                pieces = diagram_piece_sets.get(key)
                if pieces is None or not len(pieces):
                    continue
                wait_for_action(unit_action)
                selected = pieces[-1]
                if current_box is not None:
                    self.play(FadeOut(current_box), run_time=anchored_step_time(0.12, unit_action))
                    current_box = None
                run_time = anchored_step_time(0.36, unit_action)
                if operation == "isolate_part":
                    self.play(FadeOut(VGroup(*pieces[:-1])), run_time=run_time)
                    diagram_objects[key] = VGroup(selected)
                    isolated_diagram_keys.add(key)
                    label = safe_text("1份", font_size=21, color=COUNT_TEXT, weight=BOLD)
                    label.move_to([x_positions.get(key, 0.0), COUNT_LABEL_Y, 0])
                    old_label = shown_count_labels.get(key)
                    self.play(ReplacementTransform(old_label, label) if old_label is not None else FadeIn(label),
                              run_time=anchored_step_time(0.12, unit_action))
                    shown_count_labels[key] = label
                else:
                    # Once reassembled, every equal part has the same visual
                    # weight; the formerly selected piece is no longer special.
                    home = piece_home_positions.get(key)
                    home_position = home[-1] if home else selected.get_center() + UP * 0.68 + LEFT * 0.08
                    animations = [selected.animate.move_to(home_position).set_fill(opacity=0.62),
                                  FadeIn(VGroup(*pieces[:-1]))]
                    for other_key in list(diagram_objects):
                        if other_key != key:
                            animations.append(FadeOut(diagram_objects.pop(other_key)))
                            diagram_piece_sets.pop(other_key, None)
                            diagram_parts_by_key.pop(other_key, None)
                            extracted_diagram_keys.discard(other_key)
                            isolated_diagram_keys.discard(other_key)
                    for label in shown_count_labels.values():
                        animations.append(FadeOut(label))
                    if collection_label is not None:
                        animations.append(FadeOut(collection_label))
                        collection_label = None
                    collected_parts = []
                    collection_home = []
                    shown_count_labels.clear()
                    self.play(*animations, run_time=run_time)
                    diagram_objects[key] = pieces
                    extracted_diagram_keys.discard(key)
                    isolated_diagram_keys.discard(key)
                    label = safe_text(f"{len(pieces)}份", font_size=21, color=COUNT_TEXT, weight=BOLD)
                    label.move_to([x_positions.get(key, 0.0), COUNT_LABEL_Y, 0])
                    self.play(FadeIn(label), run_time=anchored_step_time(0.12, unit_action))
                    shown_count_labels[key] = label
                used += run_time

            # Geometry operations shared by model-authored and local plans.
            # Operate on the original piece objects, never independent lookalikes.
            for part_action in word_actions:
                operation = part_action.get("type")
                if operation not in {"collect_parts", "focus_part", "restore_parts"}:
                    continue
                wait_for_action(part_action)
                motion_started = float(self.time)
                if operation == "collect_parts":
                    target_specs = part_action.get("targets") or [
                        {"entity": key[0], "instance": key[1], "selection": "visible"}
                        for key in diagram_keys if key in diagram_objects
                        and (not part_action.get("entity") or key[0] == part_action["entity"])
                    ]
                    pieces_to_move = []
                    swaps = []
                    for target in target_specs:
                        key = (target["entity"], int(target.get("instance", 0)))
                        if key not in diagram_objects:
                            raise ValueError(f"汇集目标尚未出现：{key}")
                        parts = diagram_parts_by_key.get(key, 1)
                        if parts < 2:
                            raise ValueError(f"汇集目标尚未完成等分：{key}")
                        pieces = diagram_piece_sets.get(key)
                        if pieces is None:
                            original = diagram_objects[key]
                            pieces = make_exploded_parts(entities[key[0]], parts, height=1.06)
                            pieces.move_to(original.get_center())
                            pieces.set_fill(opacity=0.62)
                            piece_home_positions[key] = [piece.get_center().copy() for piece in pieces]
                            swaps.extend([FadeOut(original), FadeIn(pieces)])
                            diagram_piece_sets[key] = pieces
                            diagram_objects[key] = pieces
                            diagram_wholes[key] = None
                            diagram_lines_by_key[key] = VGroup()
                        selection = target.get("selection", "visible")
                        if selection == "selected":
                            if key not in extracted_diagram_keys:
                                raise ValueError(f"目标尚未抽出一份：{key}")
                            chosen = [pieces[-1]]
                        elif selection == "all":
                            if key in isolated_diagram_keys:
                                raise ValueError("不能把已经丢弃的余下部分重新计入汇集")
                            chosen = list(pieces)
                        else:
                            visible_family = diagram_objects[key].get_family()
                            chosen = [piece for piece in pieces if piece in visible_family]
                        for piece in chosen:
                            if piece not in pieces_to_move:
                                pieces_to_move.append(piece)
                    assert_piece_count(len(pieces_to_move), int(part_action.get("count", 0)))
                    positions = grid_positions([(piece.width, piece.height) for piece in pieces_to_move])
                    previous_homes = {id(piece): position for piece, position in zip(collected_parts, collection_home)}
                    collection_home = [previous_homes.get(id(piece), piece.get_center().copy()) for piece in pieces_to_move]
                    collected_parts = pieces_to_move
                    before_sizes = [(float(piece.width), float(piece.height)) for piece in collected_parts]
                    if current_box is not None:
                        swaps.append(FadeOut(current_box))
                        current_box = None
                    swaps.extend(FadeOut(label) for label in shown_count_labels.values())
                    shown_count_labels.clear()
                    if collection_label is not None:
                        swaps.append(FadeOut(collection_label))
                        collection_label = None
                    if swaps:
                        self.play(*swaps, run_time=anchored_step_time(0.12, part_action))
                    self.play(LaggedStart(*[
                        piece.animate.move_to([x, y, 0]).set_fill(opacity=0.62)
                        for piece, (x, y) in zip(collected_parts, positions)
                    ], lag_ratio=0.035), run_time=anchored_step_time(0.62, part_action), rate_func=smooth)
                    group = VGroup(*collected_parts)
                    total = str(part_action.get("total", ""))
                    label_text = f"{len(collected_parts)}份合计＝{total}" if total else f"一共{len(collected_parts)}份"
                    collection_label = safe_text(label_text, font_size=25, color=TITLE_COLOR)
                    fit_inside(collection_label, max_width=6.6, max_height=0.42)
                    collection_label.next_to(group, DOWN, buff=0.3)
                    current_box = make_dashed_box([group])
                    self.play(FadeIn(current_box), FadeIn(collection_label, shift=UP * 0.04),
                              run_time=anchored_step_time(0.26, part_action))
                    print("STUDIO_MOTION " + json.dumps({"id": beat.get("id"), "action": operation,
                          "time": float(self.time), "count": len(collected_parts), "total": total,
                          "before_sizes": before_sizes,
                          "after_sizes": [(float(p.width), float(p.height)) for p in collected_parts]}), flush=True)
                elif operation == "focus_part":
                    if not collected_parts:
                        raise ValueError("突出单份之前必须先汇集已有等份")
                    index = int(part_action.get("part_index", 0))
                    if index >= len(collected_parts):
                        raise ValueError("单份编号超出汇集数量")
                    chosen = collected_parts[index]
                    next_box = make_dashed_box([chosen])
                    animations = [piece.animate.set_fill(opacity=0.95 if piece is chosen else 0.22)
                                  for piece in collected_parts]
                    animations.append(ReplacementTransform(current_box, next_box) if current_box is not None else FadeIn(next_box))
                    if collection_label is not None:
                        animations.append(FadeOut(collection_label))
                        collection_label = None
                    self.play(*animations, run_time=anchored_step_time(0.36, part_action), rate_func=smooth)
                    current_box = next_box
                    print("STUDIO_MOTION " + json.dumps({"id": beat.get("id"), "action": operation,
                          "time": float(self.time), "count": len(collected_parts), "part_index": index}), flush=True)
                else:
                    if collected_parts:
                        animations = [piece.animate.move_to(position).set_fill(opacity=0.62)
                                      for piece, position in zip(collected_parts, collection_home)]
                        if current_box is not None:
                            animations.append(FadeOut(current_box))
                            current_box = None
                        if collection_label is not None:
                            animations.append(FadeOut(collection_label))
                            collection_label = None
                        self.play(*animations, run_time=anchored_step_time(0.65, part_action), rate_func=smooth)
                        collected_parts = []
                        collection_home = []
                used += float(self.time) - motion_started

            def animate_board_answer(entity_id, value):
                nonlocal used
                if board_group is None or answer_overlays.get(entity_id) == value:
                    return False
                color = entities[entity_id].get("color", RESULT_RED)
                overlays = VGroup()
                for row in board_rows:
                    for index in row_key_indexes(row, f"entity:{entity_id}"):
                        icon = row[index]
                        number = safe_text(value, font_size=21, color=color, weight=BOLD)
                        number.set_stroke(BLACK, width=2.2, background=True)
                        fit_inside(
                            number,
                            max_width=max(0.2, icon.width * 0.76),
                            max_height=max(0.2, icon.height * 0.58),
                        )
                        number.move_to(icon.get_center())
                        overlays.add(number)
                if not len(overlays):
                    return False
                run_time = step_time(0.22)
                self.play(FadeIn(overlays, scale=0.92), run_time=run_time)
                used += run_time
                answer_overlays[entity_id] = value
                return True

            if layout == "title":
                # The persistent title was already rendered once above.  A
                # model-supplied title row must never leak into the lower work
                # area and overlap the later diagram demonstration.
                pass

            elif ordered_formula_mode:
                # Execute the model's row references and anchors one by one.
                # Repeated equations are references to ONE persistent board,
                # not extra boards and not a locally rewritten storyboard.
                row_specs = beat.get("rows", [])
                row_texts = [str(r.get("text", "")).strip() for r in row_specs]
                content_types = formula_queue_types - {"focus_formula", "hold", "clear_work"}
                scheduled = sorted(enumerate(word_actions), key=lambda pair: (
                    float(pair[1].get("audio_start", 0)) if audio_mode else int(pair[1].get("anchor_offset", 0)), pair[0]))
                board_opening = None
                if layout == "equations" and board_group is None:
                    wait_for_action(scheduled[0][1] if scheduled else None)
                    board_group, board_rows = build_rows(beat, entities, max_height=1.75)
                    board_group.move_to([0, 3.35, 0])
                    board_texts = list(row_texts)
                    opening_time = anchored_step_time(0.35, scheduled[0][1] if scheduled else None)
                    opening_started = float(self.time)
                    self.play(FadeIn(board_group), run_time=opening_time)
                    if scheduled and scheduled[0][1].get("type") in {"show_formula", "show_text"}:
                        board_opening = (scheduled[0][0], opening_started)
                    used += opening_time
                elif layout == "equations" and board_texts != row_texts:
                    raise ValueError("重复原题板内容发生变化，不能覆盖原题")
                referenced = {int(a.get("row", -1)) for a in word_actions if a.get("type") in content_types}
                shown_rows = set(range(len(row_specs))) - referenced

                def queue_focus(targets, action):
                    nonlocal current_box, used
                    if not targets:
                        raise ValueError("公式红框目标尚未显示")
                    next_box = make_dashed_box(targets)
                    timing = anchored_step_time(0.20, action)
                    self.play(ReplacementTransform(current_box, next_box) if current_box is not None else FadeIn(next_box), run_time=timing)
                    current_box = next_box
                    used += timing

                for queue_index, (original_index, action) in enumerate(scheduled):
                    wait_for_action(action)
                    started = float(self.time)
                    used_before_action = used
                    operation = action.get("type")
                    row_index = int(action.get("row", -1))
                    if row_index < 0 and len(row_specs) == 1:
                        row_index = 0
                    text = row_texts[row_index] if 0 <= row_index < len(row_texts) else ""
                    board_target = [board_rows[board_texts.index(text)]] if text and text in board_texts else []
                    work_target = [model_work_visuals[model_work_texts.index(text)]] if text and text in model_work_texts else []
                    effect = operation
                    motion_receipt = None
                    if board_opening is not None and original_index == board_opening[0] and board_target:
                        # This action already introduced the board. Record its
                        # FadeIn onset, not a second, delayed reference pulse.
                        started = board_opening[1]
                        effect = "board_opening"
                    elif operation == "hold":
                        effect = "hold"
                    elif operation == "clear_work":
                        leaving = [m for m in (current_box, current_work) if m is not None]
                        if leaving:
                            timing = anchored_step_time(0.18, action)
                            self.play(*(FadeOut(m) for m in leaving), run_time=timing)
                            used += timing
                        current_work, current_box = None, None
                        model_work_texts, model_work_visuals = [], []
                        equation_copies.clear()
                        equation_copy_texts.clear()
                        equation_result_active = False
                    elif operation == "focus_formula":
                        if row_index < 0:
                            candidates = board_rows if layout == "equations" else model_work_visuals
                            targets = explicit_focus_targets(beat, candidates) or list(candidates)
                        else:
                            targets = board_target or work_target
                        queue_focus(targets, action)
                    elif operation == "copy_equation":
                        equation_result_active = False
                        if diagram_objects:
                            raise ValueError("等式搬运需要独立演算区，不能与未清理的切分图重叠")
                        source_index, slot = int(action["source_row"]), int(action["slot"])
                        if not 0 <= source_index < len(board_rows) or slot in equation_copies:
                            raise ValueError("等式来源不存在或搬运槽位已被占用")
                        source = board_rows[source_index]
                        if equation_motion_tokens(text) != equation_motion_tokens(board_texts[source_index]):
                            raise ValueError("等式搬运不能修改原题")
                        if not equation_copies and current_work is not None:
                            self.play(FadeOut(current_work), run_time=anchored_step_time(0.15, action))
                            current_work = None
                        queue_focus([source], action)
                        self.play(FadeOut(current_box), run_time=anchored_step_time(0.10, action))
                        current_box = None
                        original_points = source.get_all_points().copy()
                        clone = source.copy()
                        before_sizes = [(float(m.width), float(m.height)) for m in clone]
                        before_center = clone.get_center().copy()
                        candidates = {**equation_copies, slot: clone}
                        lower, upper = -4.0, 4.0
                        for candidate in candidates.values():
                            equal_index = list(candidate._formula_keys).index("text:＝")
                            equal_x = candidate[equal_index].get_center()[0]
                            lower = max(lower, -3.8 + equal_x - candidate.get_left()[0])
                            upper = min(upper, 3.8 - candidate.get_right()[0] + equal_x)
                        if lower > upper:
                            raise ValueError("两条原式按原尺寸对齐后超出安全区，请将长表达式拆步")
                        axis = max(lower, min(0.8, upper))
                        movements = []
                        copy_destination = None
                        for index, candidate in candidates.items():
                            equal_index = list(candidate._formula_keys).index("text:＝")
                            destination = candidate.copy().shift(RIGHT * (axis - candidate[equal_index].get_center()[0]))
                            destination.shift(UP * ((0.50 if index == 0 else -0.75) - destination.get_center()[1]))
                            if index == slot:
                                copy_destination = destination.get_center().copy()
                            else:
                                movements.append(candidate.animate.move_to(destination.get_center()))
                        # A direct downward translation crosses the other
                        # original equations. Use a bounded side corridor,
                        # translating without rotation or changing icon sizes.
                        obstacles = [board_group, *equation_copies.values()]
                        right_lane = max(m.get_right()[0] for m in obstacles) + clone.width / 2 + 0.22
                        left_lane = min(m.get_left()[0] for m in obstacles) - clone.width / 2 - 0.22
                        if right_lane + clone.width / 2 <= 3.85:
                            lane_x = right_lane
                        elif left_lane - clone.width / 2 >= -3.85:
                            lane_x = left_lane
                        else:
                            raise ValueError("原式太宽，没有不穿过其他等式的搬运通道，请拆分长式")
                        clone.move_to([lane_x, source.get_center()[1], 0])
                        self.play(TransformFromCopy(source, clone), run_time=anchored_step_time(0.20, action), rate_func=smooth)
                        self.play(clone.animate.move_to([lane_x, copy_destination[1], 0]),
                                  run_time=anchored_step_time(0.34, action), rate_func=smooth)
                        self.play(clone.animate.move_to(copy_destination), *movements,
                                  run_time=anchored_step_time(0.22, action), rate_func=smooth)
                        equation_copies[slot], equation_copy_texts[slot] = clone, text
                        current_work = VGroup(*(equation_copies[i] for i in sorted(equation_copies)))
                        model_work_visuals = [equation_copies[i] for i in sorted(equation_copies)]
                        model_work_texts = [equation_copy_texts[i] for i in sorted(equation_copies)]
                        queue_focus([clone], action)
                        motion_receipt = {
                            "source_row": source_index, "slot": slot, "copy_count": len(equation_copies),
                            "source_stationary": bool(np.allclose(original_points, source.get_all_points())),
                            "distinct_copy": id(source) != id(clone),
                            "moved": float(np.linalg.norm(clone.get_center() - before_center)),
                            "route": "side_corridor",
                            "before_sizes": before_sizes,
                            "after_sizes": [(float(m.width), float(m.height)) for m in clone],
                        }
                    elif operation == "merge_equations":
                        slots = list(action["slots"])
                        if any(slot not in equation_copies for slot in slots):
                            raise ValueError("两组等式尚未搬来，不能合并")
                        sources = [equation_copies[slot] for slot in slots]
                        mapping = equation_sum_mapping(*(equation_copy_texts[slot] for slot in slots), target=text)
                        for source, source_text in zip(sources, (equation_copy_texts[s] for s in slots)):
                            if len(source) != len(equation_motion_tokens(source_text)):
                                raise ValueError("公式项与实际图形数量不一致，不能按项搬运")
                        first_equal = list(sources[0]._formula_keys).index("text:＝")
                        equal_sample = safe_text("＝", font_size=30)
                        font_scale = sources[0][first_equal].height / max(equal_sample.height, 1e-6)
                        actual, targets, reused = [], [], []
                        for token, source_slot, token_index in mapping:
                            if source_slot is None:
                                piece = safe_text(token, font_size=30).scale(font_scale)
                            else:
                                piece = sources[source_slot][token_index]
                                reused.append(piece)
                            actual.append(piece)
                            targets.append(piece.copy())
                        destination = VGroup(*targets).arrange(RIGHT, buff=0.08 * font_scale)
                        destination.move_to([0, -0.30, 0])
                        if destination.width > 7.65 or destination.height > 1.2:
                            raise ValueError("合并公式保持原尺寸后超出安全区，请拆分长算式，不能偷偷缩小图形")
                        queue_focus(sources, action)
                        self.play(FadeOut(current_box), run_time=anchored_step_time(0.10, action))
                        current_box = None
                        before_sizes = [(float(m.width), float(m.height)) for m in reused]
                        before_ids = [id(m) for m in reused]
                        old_tokens = [m for group in sources for m in group]
                        before_entities = sorted(key for group in sources for key in group._formula_keys if key.startswith("entity:"))
                        # Ownership changes only: every old token stays at the
                        # exact same position when row wrappers are detached.
                        self.remove(*sources, current_work)
                        self.add(*old_tokens)
                        moving, moved_count = [], 0
                        for piece, target, (_, source_slot, _) in zip(actual, targets, mapping):
                            if source_slot is None:
                                piece.move_to(target.get_center())
                                moving.append(FadeIn(piece))
                            else:
                                moved_count += int(np.linalg.norm(piece.get_center() - target.get_center()) > 0.01)
                                moving.append(piece.animate.move_to(target.get_center()))
                        reused_ids = set(before_ids)
                        redundant = [m for m in old_tokens if id(m) not in reused_ids]
                        moving.extend(FadeOut(m) for m in redundant)
                        self.play(*moving, run_time=anchored_step_time(0.88, action), rate_func=smooth)
                        merged = VGroup(*actual)
                        merged._formula_keys = ["entity:" + token[2:-2] if token.startswith("{{") else "text:" + token
                                                for token, _, _ in mapping]
                        self.remove(*old_tokens, *actual)
                        self.add(merged)
                        current_work, model_work_visuals, model_work_texts = merged, [merged], [text]
                        equation_copies.clear()
                        equation_copy_texts.clear()
                        equation_result_active = True
                        queue_focus([merged], action)
                        motion_receipt = {
                            "slots": slots, "moved_count": moved_count, "removed_equals": len(redundant),
                            "reused_tokens": before_ids == [id(piece) for piece, (_, source_slot, _) in zip(actual, mapping) if source_slot is not None],
                            "entities_before": before_entities,
                            "entities_after": sorted(k for k in merged._formula_keys if k.startswith("entity:")),
                            "before_sizes": before_sizes,
                            "after_sizes": [(float(m.width), float(m.height)) for m in reused],
                        }
                    elif (operation in {"transform_formula", "show_answer"} and equation_result_active
                          and len(row_specs) == len(model_work_texts) == 1
                          and equation_motion_tokens(text).count("＝") == 1
                          and equation_motion_tokens(model_work_texts[0]).count("＝") == 1
                          and equation_motion_tokens(text).index("＝") == equation_motion_tokens(model_work_texts[0]).index("＝")
                          and equation_motion_tokens(text)[:equation_motion_tokens(text).index("＝")]
                              == equation_motion_tokens(model_work_texts[0])[:equation_motion_tokens(model_work_texts[0]).index("＝")]):
                        # After a physical merge, evaluating 7+9 -> 16 must not
                        # recreate/enlarge the four LHS icons. Only RHS changes.
                        tokens = equation_motion_tokens(text)
                        equal_index = tokens.index("＝")
                        left = list(current_work)[:equal_index + 1]
                        old_right = list(current_work)[equal_index + 1:]
                        original_left = [m.get_all_points().copy() for m in left]
                        original_left_tokens = equation_motion_tokens(model_work_texts[0])[:equal_index + 1]
                        original_left_sizes = [(float(m.width), float(m.height)) for m in left]
                        rhs_text = "".join(tokens[equal_index + 1:])
                        new_right = make_formula_row({"text": rhs_text, "accent": row_specs[row_index].get("accent", False)}, entities)
                        reference_equal = safe_text("＝", font_size=30)
                        new_right.scale(left[-1].height / max(reference_equal.height, 1e-6))
                        new_right.next_to(left[-1], RIGHT, buff=0.08)
                        if new_right.get_right()[0] > 3.85:
                            raise ValueError("右侧更新后超出安全区，请拆分表达式")
                        if current_box is not None:
                            self.play(FadeOut(current_box), run_time=anchored_step_time(0.10, action))
                            current_box = None
                        self.remove(current_work)
                        self.add(*left, *old_right)
                        self.play(FadeOut(VGroup(*old_right)), FadeIn(new_right),
                                  run_time=anchored_step_time(0.30, action))
                        self.remove(*left, *old_right, new_right)
                        current_work = VGroup(*left, *list(new_right))
                        current_work._formula_keys = ["entity:" + token[2:-2] if token.startswith("{{") else "text:" + token for token in tokens]
                        self.add(current_work)
                        model_work_texts, model_work_visuals = [text], [current_work]
                        queue_focus([current_work], action)
                        effect = "rhs_update"
                        motion_receipt = {"before_tokens": original_left_tokens,
                                          "left_count": len(left), "after_left_tokens": tokens[:equal_index + 1],
                                          "before_sizes": original_left_sizes,
                                          "after_sizes": [(float(m.width), float(m.height)) for m in left],
                                          "left_stationary": all(np.allclose(points, m.get_all_points()) for points, m in zip(original_left, left)),
                                          "left_ids_preserved": [id(m) for m in left] == [id(m) for m in list(current_work)[:len(left)]]}
                        used = used_before_action + float(self.time) - started
                    elif (operation in {"transform_formula", "substitute", "combine"} and equation_result_active
                          and len(model_work_texts) == 1 and hasattr(current_work, "_formula_keys")
                          and equation_motion_tokens(text).count("＝") == 1):
                        # Continue the SAME equation: retain tokens by occurrence,
                        # including duplicate shapes. Only changed terms enter/exit.
                        old_tokens = equation_motion_tokens(model_work_texts[0])
                        new_tokens = equation_motion_tokens(text)
                        old_parts = list(current_work)
                        if len(old_parts) != len(old_tokens):
                            raise ValueError("连续公式的对象与词项不一致，不能整式替换")
                        equal = old_tokens.index("＝")
                        scale = old_parts[equal].height / max(safe_text("＝", font_size=30).height, 1e-6)
                        available = list(range(len(old_parts)))
                        actual, layout_parts, reused, created = [], [], [], []
                        for token in new_tokens:
                            match = next((i for i in available if old_tokens[i] == token), None)
                            if match is not None:
                                available.remove(match)
                                piece = old_parts[match]
                                reused.append(piece)
                            else:
                                piece = make_formula_row({"text": token}, entities)[0]
                                piece.scale(scale)
                                created.append(piece)
                            actual.append(piece)
                            layout_parts.append(piece.copy())
                        layout = VGroup(*layout_parts).arrange(RIGHT, buff=0.08 * scale)
                        layout.move_to(current_work.get_center())
                        if layout.width > 7.65:
                            raise ValueError("连续公式重排超出安全宽度，请拆分推导")
                        before_sizes = [(float(m.width), float(m.height)) for m in reused]
                        if current_box is not None:
                            self.play(FadeOut(current_box), run_time=anchored_step_time(0.10, action))
                            current_box = None
                        self.remove(current_work)
                        self.add(*old_parts)
                        animations = []
                        for piece, destination in zip(actual, layout_parts):
                            if piece in created:
                                piece.move_to(destination.get_center())
                                animations.append(FadeIn(piece))
                            else:
                                animations.append(piece.animate.move_to(destination.get_center()))
                        for i in available:
                            token = old_tokens[i]
                            # Repeated shapes converge into their surviving term.
                            destination = next((layout_parts[j].get_center() for j, t in enumerate(new_tokens)
                                                if t == token and token.startswith("{{")), None)
                            if destination is None and token.startswith("{{") and created:
                                destination = created[0].get_center()
                            animations.append(FadeOut(old_parts[i], target_position=destination) if destination is not None else FadeOut(old_parts[i]))
                        self.play(*animations, run_time=anchored_step_time(0.55, action), rate_func=smooth)
                        self.remove(*old_parts, *created)
                        current_work = VGroup(*actual)
                        current_work._formula_keys = ["entity:" + t[2:-2] if t.startswith("{{") else "text:" + t for t in new_tokens]
                        self.add(current_work)
                        model_work_texts, model_work_visuals = [text], [current_work]
                        queue_focus([current_work], action)
                        effect = "continuous_terms"
                        motion_receipt = {"before_tokens": old_tokens, "after_tokens": new_tokens,
                                          "before_ids": [id(m) for m in old_parts], "after_ids": [id(m) for m in actual],
                                          "reused_count": len(reused), "created_count": len(created),
                                          "removed_count": len(available), "before_sizes": before_sizes,
                                          "after_sizes": [(float(m.width), float(m.height)) for m in reused]}
                        used = used_before_action + float(self.time) - started
                    else:
                        later_same_row = any(a.get("type") in content_types and int(a.get("row", -1)) == row_index
                                             for _, a in scheduled[queue_index + 1:])
                        # The model sometimes declares an operation cue and a
                        # later state display for the SAME row. Do not expose
                        # that future result on the earlier operation word.
                        if operation in {"cancel", "combine", "divide", "substitute"} and later_same_row:
                            target = current_work if current_work is not None else board_group
                            if target is None:
                                raise ValueError("运算提示缺少此前显示的公式")
                            timing = anchored_step_time(0.20, action)
                            self.play(Indicate(target, color=RESULT_RED, scale_factor=1.015), run_time=timing)
                            used += timing
                            effect = "operation_cue"
                        elif board_target:
                            timing = anchored_step_time(0.20, action)
                            self.play(Indicate(VGroup(*board_target), color=RESULT_RED, scale_factor=1.015), run_time=timing)
                            used += timing
                            effect = "board_reference"
                        else:
                            if not 0 <= row_index < len(row_specs):
                                raise ValueError("连续公式动作缺少有效row目标")
                            shown_rows.add(row_index)
                            indices = sorted(shown_rows)
                            selected_specs = [row_specs[i] for i in indices]
                            new_work, work_rows = build_rows({"rows": selected_specs}, entities, max_height=1.35 if diagram_objects else 3.2)
                            new_work.move_to([0, -3.55 if diagram_objects else -0.35, 0])
                            # A frame must exit before its target is replaced.
                            if current_box is not None:
                                timing = anchored_step_time(0.10, action)
                                self.play(FadeOut(current_box), run_time=timing)
                                current_box = None
                                used += timing
                            timing = anchored_step_time(0.28, action)
                            self.play(readable_replacement(current_work, new_work) if current_work is not None else FadeIn(new_work), run_time=timing)
                            used += timing
                            current_work = new_work
                            model_work_texts = [row_texts[i] for i in indices]
                            model_work_visuals = work_rows
                            equation_copies.clear()
                            equation_copy_texts.clear()
                            equation_result_active = False
                            if operation == "show_answer":
                                for entity_id, value in short_shape_answer_values([row_specs[row_index]], entities):
                                    animate_board_answer(entity_id, value)
                    if operation in {"copy_equation", "merge_equations"}:
                        used = used_before_action + float(self.time) - started
                    print("STUDIO_FORMULA_ACTION " + json.dumps({"id": beat.get("id"), "index": original_index,
                          "type": operation, "anchor": action.get("anchor"), "row": row_index, "effect": effect,
                          "motion": motion_receipt,
                          "start": started, "end": float(self.time), "text": text}), flush=True)

            elif layout == "equations":
                content_action = find_action({"show_formula", "show_text", "transform_formula", "show_answer"})
                wait_for_action(content_action)
                new_board, new_rows = build_rows(beat, entities, max_height=1.75)
                new_board.move_to([0, 3.35, 0])
                if current_box is not None:
                    run_time = step_time(0.14)
                    self.play(FadeOut(current_box), run_time=run_time)
                    current_box = None
                    used += run_time
                if board_group is None:
                    for row in new_rows:
                        run_time = anchored_step_time(0.22, content_action)
                        self.play(FadeIn(row, shift=UP * 0.05), run_time=run_time)
                        used += run_time
                    board_group = new_board
                else:
                    run_time = anchored_step_time(0.34, content_action)
                    self.play(ReplacementTransform(board_group, new_board), run_time=run_time)
                    used += run_time
                    board_group = new_board
                board_rows = new_rows
                board_texts = [str(row.get("text", "")).strip() for row in beat.get("rows", [])]
                targets, separate = semantic_board_focus(beat, board_rows, entities)
                if not targets:
                    targets = explicit_focus_targets(beat, board_rows)
                if targets:
                    focus_action = find_action("focus_formula")
                    wait_for_action(focus_action)
                    current_box = make_dashed_box(targets, separate=separate)
                    run_time = anchored_step_time(0.24, focus_action)
                    self.play(FadeIn(current_box), run_time=run_time)
                    used += run_time

            elif layout == "diagram":
                for diagram in beat.get("diagrams", []):
                    entity_id = diagram.get("entity")
                    if entity_id not in entities:
                        continue
                    entity = entities[entity_id]
                    instance = max(0, int(diagram.get("instance", 0)))
                    diagram_key = (entity_id, instance)
                    active_diagram_keys[entity_id] = diagram_key
                    parts = max(1, int(diagram.get("parts", 1)))
                    focus_action = find_action("focus_formula", entity_id, instance)
                    show_action = find_action("show_whole", entity_id, instance)
                    partition_action = find_action("partition_shape", entity_id, instance)
                    extract_action = find_action("extract_part", entity_id, instance)
                    fallback_partition = bool(
                        not audio_mode
                        and not word_actions
                        and parts > 1
                        and diagram.get("animation") == "show_then_partition"
                    )
                    candidates = [action for action in (focus_action, show_action, partition_action, extract_action) if action]
                    start_action = min(
                        candidates,
                        key=lambda item: float(item.get("audio_start", cue_start if audio_mode else 0.0)),
                    ) if candidates else None
                    if focus_action and show_action:
                        start_action = min(
                            (focus_action, show_action),
                            key=lambda item: float(item.get("audio_start", cue_start if audio_mode else 0.0)),
                        )
                    wait_for_action(start_action)

                    if diagram_key not in diagram_objects:
                        # First mention: show one complete shape.  Later beats
                        # reuse this exact object instead of silently skipping
                        # their partition/extraction actions.
                        make_room_for_diagram(diagram_key, start_action)
                        targets, separate = semantic_board_focus(beat, board_rows, entities)
                        next_box = make_dashed_box(targets, separate=separate) if targets and focus_action else None
                        whole = make_shape_symbol(entity, height=1.06)
                        whole.move_to([x_positions.get(diagram_key, 0.0), 0.05, 0])
                        opening_animations = [FadeIn(whole, scale=0.95)]
                        if next_box is not None:
                            if current_box is None:
                                opening_animations.append(FadeIn(next_box))
                            else:
                                opening_animations.append(ReplacementTransform(current_box, next_box))
                        run_time = anchored_step_time(0.30, start_action)
                        self.play(*opening_animations, run_time=run_time)
                        used += run_time
                        if next_box is not None:
                            current_box = next_box
                        diagram_objects[diagram_key] = whole
                        diagram_wholes[diagram_key] = whole
                        diagram_lines_by_key[diagram_key] = VGroup()
                        diagram_parts_by_key[diagram_key] = 1
                        trace_layout()
                        trace_geometry(beat, diagram_key, "whole")
                    elif focus_action:
                        # The object already exists, but the spoken formula cue
                        # still has to move the red frame at this exact moment.
                        targets, separate = semantic_board_focus(beat, board_rows, entities)
                        if targets:
                            next_box = make_dashed_box(targets, separate=separate)
                            run_time = anchored_step_time(0.24, focus_action)
                            if current_box is None:
                                self.play(FadeIn(next_box), run_time=run_time)
                            else:
                                self.play(ReplacementTransform(current_box, next_box), run_time=run_time)
                            current_box = next_box
                            used += run_time

                    if (partition_action or fallback_partition) and parts > 1 and (
                        diagram_parts_by_key.get(diagram_key, 1) != parts
                        or not len(diagram_lines_by_key.get(diagram_key, VGroup()))
                    ):
                        wait_for_action(partition_action)
                        if diagram_key in extracted_diagram_keys or diagram_wholes.get(diagram_key) is None:
                            old_visual = diagram_objects[diagram_key]
                            whole = make_shape_symbol(entity, height=1.06)
                            whole.move_to([x_positions.get(diagram_key, 0.0), 0.05, 0])
                            run_time = anchored_step_time(0.16, partition_action)
                            self.play(ReplacementTransform(old_visual, whole), run_time=run_time)
                            used += run_time
                            diagram_objects[diagram_key] = whole
                            diagram_wholes[diagram_key] = whole
                            diagram_lines_by_key[diagram_key] = VGroup()
                            extracted_diagram_keys.discard(diagram_key)
                            isolated_diagram_keys.discard(diagram_key)
                            diagram_piece_sets.pop(diagram_key, None)
                        whole = diagram_wholes[diagram_key]
                        old_lines = diagram_lines_by_key.get(diagram_key, VGroup())
                        if len(old_lines):
                            run_time = anchored_step_time(0.10, partition_action)
                            self.play(FadeOut(old_lines), run_time=run_time)
                            used += run_time
                        lines = partition_lines(
                            whole[1],
                            entity.get("kind", "badge"),
                            parts,
                            color=entity.get("color", WHITE_TEXT),
                        )
                        # Allocate one total phrase budget across every divider.
                        # Charging 0.25 s per line made 6-12 part animations run
                        # past the next spoken cue and caused QA frames to sample
                        # half-finished motion.
                        line_count = max(1, len(lines))
                        partition_total = max(
                            0.02 * line_count,
                            anchored_step_time(min(0.90, 0.24 * line_count), partition_action),
                        )
                        divider_run_time = partition_total / line_count
                        for divider in lines:
                            kind = entity.get("kind", "badge")
                            if kind == "circle" and parts not in (2, 4):
                                animation = GrowFromPoint(divider, whole[1].get_center())
                            elif kind == "triangle":
                                top = max(whole[1].get_vertices(), key=lambda point: point[1])
                                animation = GrowFromPoint(divider, top)
                            else:
                                animation = GrowFromCenter(divider)
                            self.play(animation, run_time=divider_run_time)
                            used += divider_run_time
                        if len(lines) and not audio_mode:
                            run_time = step_time(0.14)
                            self.wait(run_time)
                            used += run_time
                        diagram_lines_by_key[diagram_key] = lines
                        diagram_parts_by_key[diagram_key] = parts
                        diagram_objects[diagram_key] = VGroup(whole, lines)
                        trace_geometry(beat, diagram_key, "partitioned")

                    if extract_action and parts > 1 and diagram_key not in extracted_diagram_keys:
                        wait_for_action(extract_action)
                        pieces = make_exploded_parts(entity, parts, height=1.06)
                        pieces.move_to([x_positions.get(diagram_key, 0.0), 0.05, 0])
                        piece_home_positions[diagram_key] = [piece.get_center().copy() for piece in pieces]
                        old_visual = diagram_objects[diagram_key]
                        run_time = anchored_step_time(0.12, extract_action)
                        swap = [FadeOut(old_visual), FadeIn(pieces)]
                        self.play(*swap, run_time=run_time)
                        used += run_time
                        selected = pieces[-1]
                        fill_animations = [
                            piece.animate.set_fill(
                                entity.get("color", WHITE_TEXT),
                                opacity=0.95 if piece is selected else 0.62,
                            )
                            for piece in pieces
                        ]
                        run_time = anchored_step_time(0.12, extract_action)
                        self.play(*fill_animations, run_time=run_time)
                        used += run_time
                        run_time = anchored_step_time(0.34, extract_action)
                        self.play(
                            selected.animate.shift(DOWN * 0.68 + RIGHT * 0.08),
                            run_time=run_time,
                            rate_func=smooth,
                        )
                        used += run_time
                        diagram_objects[diagram_key] = pieces
                        diagram_piece_sets[diagram_key] = pieces
                        diagram_wholes[diagram_key] = None
                        diagram_lines_by_key[diagram_key] = VGroup()
                        diagram_parts_by_key[diagram_key] = parts
                        extracted_diagram_keys.add(diagram_key)
                        trace_geometry(beat, diagram_key, "extracted")

                    visible_parts = diagram_parts_by_key.get(diagram_key, parts)
                    label_text = deictic_part_count_label(diagram.get("caption", "")) or f"{visible_parts}份"
                    label = safe_text(label_text, font_size=21, color=COUNT_TEXT, weight=BOLD)
                    label.move_to([x_positions.get(diagram_key, 0.0), COUNT_LABEL_Y, 0])
                    count_labels[diagram_key] = label
                    if STORYBOARD_SPEC.get("local_math_contract") and partition_action:
                        old_label = shown_count_labels.get(diagram_key)
                        self.play(ReplacementTransform(old_label, label) if old_label is not None else FadeIn(label),
                                  run_time=anchored_step_time(0.12, partition_action))
                        shown_count_labels[diagram_key] = label

                # Some models keep a reference-to-diagram sentence in a
                # ``diagram`` beat (instead of ``derivation``).  Those spoken
                # cues must still move the same red dashed frame onto the
                # already-rendered shape(s), including repeated instances.
                diagram_focus_actions = sorted(
                    [action for action in word_actions if action.get("type") == "focus_diagram"],
                    key=lambda item: float(item.get("audio_start", cue_start if audio_mode else 0.0)),
                )
                for diagram_focus_action in diagram_focus_actions:
                    wait_for_action(diagram_focus_action)
                    focus_entity = str(diagram_focus_action.get("entity", ""))
                    focus_keys = visual_keys_for_action(diagram_focus_action)
                    visual_targets = [diagram_objects[key] for key in focus_keys]
                    if not visual_targets:
                        continue
                    next_box = make_dashed_box(visual_targets, separate=False)
                    animations = []
                    if current_box is None:
                        animations.append(FadeIn(next_box))
                    else:
                        animations.append(ReplacementTransform(current_box, next_box))
                    if focus_entity and focus_keys:
                        focus_key = focus_keys[-1]
                        label_animation = count_label_animation(diagram_focus_action, focus_key)
                        if label_animation is not None:
                            animations.append(label_animation)
                    run_time = anchored_step_time(0.28, diagram_focus_action)
                    self.play(*animations, run_time=run_time, rate_func=smooth)
                    current_box = next_box
                    used += run_time

                if beat.get("rows"):
                    row_action = find_action({"show_formula", "transform_formula", "substitute", "combine", "cancel", "divide", "show_answer"})
                    wait_for_action(row_action)
                    new_work, work_rows = build_rows(beat, entities, max_height=1.05)
                    new_work.move_to([0, -3.55, 0])
                    if current_work is None:
                        for row in work_rows:
                            run_time = anchored_step_time(0.22, row_action)
                            self.play(FadeIn(row, shift=UP * 0.04), run_time=run_time)
                            used += run_time
                    else:
                        run_time = anchored_step_time(0.34, row_action)
                        self.play(readable_replacement(current_work, new_work), run_time=run_time)
                        used += run_time
                    current_work = new_work

                # Diagram-area relation symbols: "+" / "=" drawn between the
                # facing edges of two live diagram objects. Revealed once per
                # symbol; existing objects stay on screen across beats.
                for operator in beat.get("operators", []):
                    op_key = (operator["symbol"], tuple(operator["between"]))
                    if op_key in operator_objects:
                        continue
                    left_key = operator["between"][0].split("@")
                    right_key = operator["between"][1].split("@")
                    left_key = (left_key[0], int(left_key[1]))
                    right_key = (right_key[0], int(right_key[1]))
                    if left_key not in diagram_objects or right_key not in diagram_objects:
                        continue
                    symbol = safe_text(
                        operator["symbol"], font_size=42, color=WHITE_TEXT, weight=BOLD
                    )
                    mid_x = (
                        diagram_objects[left_key].get_right()[0]
                        + diagram_objects[right_key].get_left()[0]
                    ) / 2.0
                    symbol.move_to([mid_x, 0.05, 0])
                    run_time = anchored_step_time(0.26, start_action)
                    self.play(FadeIn(symbol, scale=0.9), run_time=run_time)
                    used += run_time
                    operator_objects[op_key] = symbol
                    def follow_sources(mob, left_key=left_key, right_key=right_key):
                        if left_key in diagram_objects and right_key in diagram_objects:
                            left = diagram_objects[left_key]
                            right = diagram_objects[right_key]
                            mob.move_to((left.get_right() + right.get_left()) / 2)
                    symbol.add_updater(follow_sources)

            elif layout == "summary":
                summary_action = find_action({"show_answer", "show_formula", "transform_formula"})
                wait_for_action(summary_action)
                summary_signature = tuple(str(row.get("text", "")).strip() for row in beat.get("rows", []))
                if summary_signature != last_summary_signature:
                    if current_box is not None:
                        run_time = anchored_step_time(0.18, summary_action)
                        self.play(FadeOut(current_box), run_time=run_time)
                        current_box = None
                        used += run_time
                    short_shape_answers = short_shape_answer_values(beat.get("rows", []), entities)
                    for entity_id, value in short_shape_answers:
                        animate_board_answer(entity_id, value)

                    # Always show the explicit final-answer row.  Filling a
                    # value into the persistent problem board is useful proof,
                    # but it is not a substitute for an unambiguous result such
                    # as “圆＝42” in the final answer area.
                    summary_group, summary_rows = build_rows(
                        beat,
                        entities,
                        horizontal=len(beat.get("rows", [])) <= 3,
                        max_height=1.25,
                    )
                    summary_group.move_to([0, -3.55 if diagram_objects else -0.45, 0])
                    if current_work is None:
                        for row in summary_rows:
                            run_time = anchored_step_time(0.22, summary_action)
                            self.play(FadeIn(row, shift=UP * 0.04), run_time=run_time)
                            used += run_time
                    else:
                        run_time = anchored_step_time(0.36, summary_action)
                        self.play(readable_replacement(current_work, summary_group), run_time=run_time)
                        used += run_time
                    current_work = summary_group
                    if summary_rows and beat.get("focus"):
                        next_box = make_dashed_box(summary_rows, separate=False)
                        run_time = anchored_step_time(0.24, summary_action)
                        self.play(FadeIn(next_box), run_time=run_time)
                        current_box = next_box
                        used += run_time
                    last_summary_signature = summary_signature

            else:
                # Spoken references such as “这些每一份都相等 / 这里是4份 / 这里是3份”
                # point back to the already-cut diagrams themselves.  Keep the
                # black canvas and morph the one red dashed frame across those
                # visual objects; never create a coloured comparison panel or a
                # duplicate numeric row at the bottom.
                diagram_focus_actions = sorted(
                    [action for action in word_actions if action.get("type") == "focus_diagram"],
                    key=lambda item: float(item.get("audio_start", cue_start if audio_mode else 0.0)),
                )
                if diagram_focus_actions and diagram_objects:
                    for diagram_focus_action in diagram_focus_actions:
                        wait_for_action(diagram_focus_action)
                        focus_entity = str(diagram_focus_action.get("entity", ""))
                        focus_keys = visual_keys_for_action(diagram_focus_action)
                        visual_targets = [diagram_objects[key] for key in focus_keys]
                        if not visual_targets:
                            continue
                        next_box = make_dashed_box(visual_targets, separate=False)
                        animations = []
                        if current_box is None:
                            animations.append(FadeIn(next_box))
                        else:
                            animations.append(ReplacementTransform(current_box, next_box))
                        if focus_entity and focus_keys:
                            focus_key = focus_keys[-1]
                            label_animation = count_label_animation(diagram_focus_action, focus_key)
                            if label_animation is not None:
                                animations.append(label_animation)
                        run_time = anchored_step_time(0.28, diagram_focus_action)
                        self.play(*animations, run_time=run_time, rate_func=smooth)
                        current_box = next_box
                        used += run_time

                    has_followup_state_action = bool(
                        beat.get("rows")
                        and any(
                            action.get("type") in {
                                "show_text", "show_formula", "transform_formula", "substitute",
                                "combine", "cancel", "divide", "show_answer",
                            }
                            for action in word_actions
                        )
                    )
                    if not has_followup_state_action:
                        if audio_mode:
                            remaining = audio_origin + cue_end - float(self.time)
                        else:
                            remaining = duration - used
                        print("STUDIO_STABLE " + json.dumps({"id": beat.get("id", ""),
                              "time": float(self.time) + min(0.1, max(0.0, remaining) / 2)}), flush=True)
                        if remaining > 1e-3:
                            self.wait(remaining)
                        continue

                parsed_progress = answer_values(beat.get("rows", []))
                short_progress = short_shape_answer_values(beat.get("rows", []), entities)
                direct_fill = board_group is not None and len(parsed_progress) == 1 and len(short_progress) == 1
                requested_texts = [str(row.get("text", "")).strip() for row in beat.get("rows", [])]
                subformula_targets, all_requested_rows_on_board = board_subformula_targets(
                    requested_texts, board_rows
                )
                content_action = find_action({
                    "show_text", "show_formula", "transform_formula", "substitute",
                    "combine", "cancel", "divide",
                })
                answer_action = find_action("show_answer")

                # “已知/再看/某某相加” must move the red frame before a later
                # “代入/等于” changes the derivation.  The previous runtime
                # always built the new row first, which delayed an early spoken
                # focus cue until the end of the sentence.
                focus_action = find_action("focus_formula")
                board_targets, board_separate = semantic_board_focus(beat, board_rows, entities)
                if all_requested_rows_on_board:
                    board_targets = subformula_targets
                    board_separate = False
                content_clock = float(content_action.get("audio_start", cue_end)) if content_action else cue_end
                focus_clock = float(focus_action.get("audio_start", cue_end)) if focus_action else cue_end
                early_board_focus = bool(board_targets and focus_action and focus_clock <= content_clock + 0.015)
                if early_board_focus:
                    wait_for_action(focus_action)
                    next_box = make_dashed_box(board_targets, separate=board_separate)
                    run_time = anchored_step_time(0.24, focus_action)
                    if current_box is None:
                        self.play(FadeIn(next_box), run_time=run_time)
                    else:
                        self.play(ReplacementTransform(current_box, next_box), run_time=run_time)
                    current_box = next_box
                    used += run_time

                if content_action is None:
                    content_action = answer_action
                wait_for_action(content_action)
                work_rows = []
                board_only = bool(board_targets and all_requested_rows_on_board)
                if board_only:
                    # Re-speaking an original equation should focus the one
                    # persistent board, not create a duplicate below it.
                    if content_action is not None:
                        run_time = anchored_step_time(0.20, content_action)
                        self.play(
                            Indicate(VGroup(*board_targets), color=RESULT_RED, scale_factor=1.015),
                            run_time=run_time,
                        )
                        used += run_time
                elif direct_fill:
                    animate_board_answer(*short_progress[0])
                else:
                    new_work, work_rows = build_rows(beat, entities, max_height=1.35 if diagram_objects else 3.2)
                    new_work.move_to([0, -3.55 if diagram_objects else -0.35, 0])
                    if current_work is None:
                        for row in work_rows:
                            run_time = anchored_step_time(0.22, content_action)
                            self.play(FadeIn(row, shift=UP * 0.04), run_time=run_time)
                            used += run_time
                    else:
                        run_time = anchored_step_time(0.34, content_action)
                        self.play(readable_replacement(current_work, new_work), run_time=run_time)
                        used += run_time
                    current_work = new_work
                targets, separate = board_targets, board_separate
                if not targets:
                    targets = explicit_focus_targets(beat, work_rows)
                    separate = False
                if targets and focus_action and not early_board_focus:
                    wait_for_action(focus_action)
                    next_box = make_dashed_box(targets, separate=separate)
                    run_time = anchored_step_time(0.24, focus_action)
                    if current_box is None:
                        self.play(FadeIn(next_box), run_time=run_time)
                    else:
                        self.play(ReplacementTransform(current_box, next_box), run_time=run_time)
                    current_box = next_box
                    used += run_time

                # A later “所以/等于/答案” is a separate visible event even
                # when the row itself was introduced on an earlier operation
                # word.  Pulse the result rather than leaving the action inert.
                if answer_action and answer_action is not content_action:
                    answer_clock = float(answer_action.get("audio_start", cue_end))
                    if answer_clock > float(content_action.get("audio_start", cue_start)) + 0.015:
                        wait_for_action(answer_action)
                        emphasis_target = current_work if current_work is not None else board_group
                        if emphasis_target is not None:
                            run_time = anchored_step_time(0.22, answer_action)
                            self.play(
                                Indicate(emphasis_target, color=RESULT_RED, scale_factor=1.025),
                                run_time=run_time,
                            )
                            used += run_time

            if audio_mode:
                remaining = audio_origin + cue_end - float(self.time)
            else:
                remaining = duration - used
            # The actual renderer clock includes all sequential operations and
            # frame quantisation. Do not guess this timestamp from action costs.
            print("STUDIO_STABLE " + json.dumps({"id": beat.get("id", ""),
                  "time": float(self.time) + min(0.1, max(0.0, remaining) / 2)}), flush=True)
            if remaining > 1e-3:
                self.wait(remaining)

        if audio_mode:
            final_target = audio_origin + float(audio_spec.get("duration", 0.0)) + float(audio_spec.get("tail_hold", 2.0))
            final_remaining = final_target - float(self.time)
            if final_remaining > 1e-3:
                self.wait(final_remaining)
        elif all_beats:
            self.wait(2.0)
