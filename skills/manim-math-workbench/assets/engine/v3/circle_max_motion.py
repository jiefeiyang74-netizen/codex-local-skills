"""Safe Manim primitives for the checked circle-linear-maximum storyboard.

This file is injected into the generated source by ``compiler.py``.  It uses
only the Manim symbols and palette already present in runtime_template.py.
"""


def _circle_max_text(value, font_size=28, color=None, weight=NORMAL):
    # This module is injected before the template's palette constants are
    # assigned.  Resolve the default only when the helper is called from the
    # scene, not while Python is defining this function.
    return Text(str(value), font=FONT, font_size=font_size, color=WHITE_TEXT if color is None else color, weight=weight)


def _circle_max_title(title):
    title_text = _circle_max_text(title, font_size=39, color=TITLE_COLOR, weight=BOLD)
    fit_inside(title_text, max_width=6.8, max_height=0.62)
    left = Triangle(fill_color=TITLE_COLOR, fill_opacity=1, stroke_width=0).scale(0.12).rotate(-PI / 2)
    right = Triangle(fill_color=TITLE_COLOR, fill_opacity=1, stroke_width=0).scale(0.12).rotate(PI / 2)
    group = VGroup(left, title_text, right).arrange(RIGHT, buff=0.46)
    group.move_to([0, 5.18, 0])
    return group


def _circle_max_box(target):
    return DashedVMobject(
        RoundedRectangle(
            width=max(0.72, target.width + 0.34),
            height=max(0.52, target.height + 0.26),
            corner_radius=0.14,
            color=BOX_RED,
            stroke_width=2.5,
        ).move_to(target.get_center()),
        num_dashes=24,
    )


def _circle_max_format(value):
    return str(int(round(value))) if abs(value - round(value)) < 1e-8 else f"{value:.3f}".rstrip("0").rstrip(".")


def _circle_max_cue(beat, identifier, *phrases):
    """Use the shared audio aligner's phrase timestamps, including old specs.

    Imported storyboards may drop the optional cue field during normalization;
    the verbatim anchor remains the stable, human-readable fallback.
    """
    actions = list(beat.get("actions") or [])
    for action in actions:
        if action.get("cue") == identifier:
            return action
    for phrase in phrases:
        for action in actions:
            if phrase in str(action.get("anchor", "")):
                return action
    return beat


def _circle_max_wait_for(scene, beat, origin):
    audio = STORYBOARD_SPEC.get("audio") or {}
    if not str(audio.get("path", "")).strip():
        return
    target = origin + max(0.0, float(beat.get("audio_start", 0.0)))
    remaining = target - float(scene.time)
    if remaining > 0.015:
        scene.wait(remaining)


def _circle_max_duration(scene, beat, origin, fallback):
    audio = STORYBOARD_SPEC.get("audio") or {}
    if not str(audio.get("path", "")).strip():
        return fallback
    end = origin + max(float(beat.get("audio_end", 0.0)), float(beat.get("audio_start", 0.0)) + 0.08)
    room = end - float(scene.time) - 0.05
    return max(1.0 / float(config.frame_rate), min(fallback, room))


def _circle_max_action(scene, cue, origin, *animations, duration=0.4):
    _circle_max_wait_for(scene, cue, origin)
    print("STUDIO_CIRCLE_CUE " + json.dumps({
        "anchor": cue.get("anchor", ""),
        "planned": round(origin + float(cue.get("audio_start", 0.0)), 4),
        "actual": round(float(scene.time), 4),
    }, ensure_ascii=False))
    scene.play(*animations, run_time=_circle_max_duration(scene, cue, origin, duration))


def _circle_max_rotate_until(scene, angle, destination, next_cue, origin, fallback):
    """Keep motion alive through a spoken phrase without crossing its next cue."""
    audio = STORYBOARD_SPEC.get("audio") or {}
    duration = fallback
    if str(audio.get("path", "")).strip():
        duration = origin + float(next_cue.get("audio_start", 0.0)) - float(scene.time)
    if duration >= 1.0 / float(config.frame_rate):
        scene.play(angle.animate.set_value(destination), run_time=duration, rate_func=linear)


def _circle_max_stable(scene, identifier):
    """Expose actual stable times to the shared preview/keyframe validator."""
    print("STUDIO_STABLE " + json.dumps({"id": identifier, "time": round(float(scene.time), 4)}))


def play_circle_linear_max(scene, spec):
    """Render a circle/vector proof with continuous, truthful geometry."""
    contract = dict(spec.get("local_math_contract") or {})
    c = int(contract["C"])
    a = int(contract["a"])
    b = int(contract["b"])
    radius_value = math.sqrt(c)
    vector_norm = math.sqrt(a * a + b * b)
    answer = str(contract.get("answer") or _circle_max_format(radius_value * vector_norm))
    radius_label = _circle_max_format(radius_value)
    norm_label = _circle_max_format(vector_norm)
    beats = list(spec.get("beats") or [])

    scene.camera.background_color = BLACK
    title = _circle_max_title(spec.get("title") or "数学解题可视化")
    scene.play(FadeIn(title, shift=DOWN * 0.08), run_time=0.7)

    audio = spec.get("audio") or {}
    audio_path = str(audio.get("path", "")).strip()
    # The shared audio validator and keyframe planner use an exact 0.7 s lead.
    # Account for frame rounding at low preview frame rates when adding sound.
    audio_origin = 0.7
    if audio_path:
        scene.add_sound(audio_path, time_offset=audio_origin - float(scene.time))

    center = np.array([0.0, -0.35, 0.0])
    display_radius = 1.58
    direction = np.array([float(a), float(b), 0.0]) / max(vector_norm, 1e-9)
    # The arrow is deliberately allowed to extend past the constraint circle:
    # it represents a different vector of length sqrt(a²+b²), not the point P.
    arrow_length = min(2.82, max(2.06, display_radius * vector_norm / max(radius_value, 1e-9)))
    arrow_end = center + direction * arrow_length
    target_angle = math.atan2(float(b), float(a))
    start_angle = target_angle + 1.13  # positive projection, so the segment t is visible from its first frame
    angle = ValueTracker(start_angle)

    constraint = _circle_max_text(f"x²＋y²＝{c}", font_size=31, color=WHITE_TEXT, weight=BOLD)
    objective = _circle_max_text(f"{a}x＋{b}y 的最大值？", font_size=31, color=WHITE_TEXT, weight=BOLD)
    top_board = VGroup(constraint, objective).arrange(DOWN, buff=0.18).move_to([0, 3.86, 0])
    focus_box = _circle_max_box(constraint)
    b01 = beats[0] if beats else {}
    _circle_max_action(scene, _circle_max_cue(b01, "constraint", "已知"), audio_origin,
                       FadeIn(constraint, shift=DOWN * 0.08), FadeIn(focus_box), duration=0.38)
    _circle_max_action(scene, _circle_max_cue(b01, "objective", "求"), audio_origin,
                       FadeIn(objective, shift=DOWN * 0.08), duration=0.35)
    _circle_max_stable(scene, "b01")

    circle = Circle(radius=display_radius, color=TITLE_COLOR, stroke_width=4.4, fill_color=TITLE_COLOR, fill_opacity=0.04)
    circle.move_to(center)
    horizontal_axis = Line(center + LEFT * (display_radius + 0.12), center + RIGHT * (display_radius + 0.12),
                           color=MUTED_TEXT, stroke_width=1.4, stroke_opacity=0.35)
    vertical_axis = Line(center + DOWN * (display_radius + 0.12), center + UP * (display_radius + 0.12),
                         color=MUTED_TEXT, stroke_width=1.4, stroke_opacity=0.35)
    origin_dot = Dot(center, radius=0.055, color=WHITE_TEXT)
    origin_label = _circle_max_text("O", font_size=20, color=MUTED_TEXT).next_to(origin_dot, DOWN + RIGHT, buff=0.12)

    def point_position():
        return center + display_radius * np.array([math.cos(angle.get_value()), math.sin(angle.get_value()), 0.0])

    radius_line = Line(center, point_position(), color=TITLE_COLOR, stroke_width=4.4)
    radius_line.add_updater(lambda mob: mob.put_start_and_end_on(center, point_position()))
    point = Dot(point_position(), radius=0.09, color=WHITE_TEXT)
    point.add_updater(lambda mob: mob.move_to(point_position()))
    point_label = _circle_max_text("P(x,y)", font_size=21, color=WHITE_TEXT)
    point_label.add_updater(lambda mob: mob.next_to(point_position(), UP, buff=0.28).shift(LEFT * 0.6))
    point_label.update()
    op_label = _circle_max_text(f"OP＝{radius_label}", font_size=24, color=TITLE_COLOR, weight=BOLD)
    op_label.move_to(center + LEFT * 1.9 + DOWN * 1.66)

    b02 = beats[1] if len(beats) > 1 else {}
    _circle_max_action(scene, _circle_max_cue(b02, "point", "平面上的一个点", "一个点"), audio_origin,
                       FadeIn(horizontal_axis), FadeIn(vertical_axis), FadeIn(origin_dot), FadeIn(origin_label),
                       FadeIn(point), FadeIn(point_label), duration=0.38)
    _circle_max_action(scene, _circle_max_cue(b02, "radius", "距离", "半径"), audio_origin,
                       Create(radius_line), FadeIn(op_label), duration=0.4)
    _circle_max_action(scene, _circle_max_cue(b02, "circle", "圆周", "沿着圆"), audio_origin,
                       Create(circle), duration=0.52)
    b03 = beats[2] if len(beats) > 2 else {}
    horizontal_cue = _circle_max_cue(b03, "horizontal", "向右")
    _circle_max_rotate_until(scene, angle, start_angle + 0.18, horizontal_cue, audio_origin, 0.55)
    _circle_max_stable(scene, "b02")

    horizontal = Line(center, center + np.array([a, 0, 0]) * (arrow_length / vector_norm), color="#55B8FF", stroke_width=3.2)
    vertical = Line(horizontal.get_end(), arrow_end, color="#55B8FF", stroke_width=3.2)
    h_label = _circle_max_text(str(a), font_size=22, color="#55B8FF").next_to(horizontal, DOWN, buff=0.09)
    v_label = _circle_max_text(str(b), font_size=22, color="#55B8FF").next_to(vertical, RIGHT, buff=0.09)
    direction_arrow = Arrow(center, arrow_end, buff=0, color="#55B8FF", stroke_width=4.4, max_tip_length_to_length_ratio=0.11)
    vector_label = _circle_max_text(f"a＝({a},{b})", font_size=21, color="#55B8FF", weight=BOLD)
    vector_label.next_to(direction_arrow, RIGHT, buff=0.14)
    norm_text = _circle_max_text(f"|a|＝√({a}²＋{b}²)＝{norm_label}", font_size=23, color=WHITE_TEXT, weight=BOLD)
    norm_text.move_to([0, -3.05, 0])
    _circle_max_action(scene, horizontal_cue, audio_origin,
                       FadeOut(focus_box), Create(horizontal), FadeIn(h_label), duration=0.38)
    _circle_max_action(scene, _circle_max_cue(b03, "vertical", "向上"), audio_origin,
                       Create(vertical), FadeIn(v_label), duration=0.38)
    _circle_max_action(scene, _circle_max_cue(b03, "arrow", "连接", "连起"), audio_origin,
                       GrowArrow(direction_arrow), FadeIn(vector_label), duration=0.5)
    _circle_max_action(scene, _circle_max_cue(b03, "norm", "长度"), audio_origin,
                       FadeIn(norm_text), duration=0.42)
    scene.play(FadeOut(horizontal), FadeOut(vertical), FadeOut(h_label), FadeOut(v_label), run_time=0.24)
    _circle_max_stable(scene, "b03")

    b04 = beats[3] if len(beats) > 3 else {}
    bound = _circle_max_text(f"{a}x＋{b}y ≤ {radius_label}×{norm_label}", font_size=29, color=WHITE_TEXT, weight=BOLD)
    bound.move_to([0, -3.82, 0])
    bound_box = _circle_max_box(bound)
    _circle_max_action(scene, _circle_max_cue(b04, "bound", "不会超过", "不超过", "柯西"), audio_origin,
                       FadeIn(bound, shift=UP * 0.04), FadeIn(bound_box), duration=0.54)
    _circle_max_stable(scene, "b04")

    b05 = beats[4] if len(beats) > 4 else {}
    rotate_cue = _circle_max_cue(b05, "rotate", "继续移动", "点移动")
    align_cue = _circle_max_cue(b05, "align", "同一个方向", "同向")
    equality_cue = _circle_max_cue(b05, "equality", "等号", "取等")
    direction_line = DashedLine(center - direction * 1.84, center + direction * 2.92, color="#55B8FF", stroke_width=1.8, dash_length=0.11)

    def projection_position():
        delta = point_position() - center
        return center + direction * float(np.dot(delta, direction))

    projection_line = always_redraw(lambda: Line(center, projection_position(), color=WHITE_TEXT, stroke_width=3.1))

    def perpendicular():
        p, h = point_position(), projection_position()
        return DashedLine(p, h, color=MUTED_TEXT, stroke_width=1.7, dash_length=0.08) if np.linalg.norm(p - h) > 0.02 else VGroup()

    perpendicular_line = always_redraw(perpendicular)
    projection_label = _circle_max_text("t", font_size=21, color=WHITE_TEXT)
    projection_label.add_updater(lambda mob: mob.next_to(projection_position(), DOWN, buff=0.08))
    projection_label.update()
    alignment_box = _circle_max_box(circle)
    _circle_max_action(scene, rotate_cue, audio_origin,
                       Create(direction_line), Create(projection_line), FadeIn(perpendicular_line), FadeIn(projection_label),
                       FadeOut(bound_box), FadeIn(alignment_box), duration=0.38)
    _circle_max_rotate_until(scene, angle, target_angle + 0.24, align_cue, audio_origin, 0.6)
    _circle_max_action(scene, align_cue, audio_origin, angle.animate.set_value(target_angle), duration=0.65)
    equal_label = _circle_max_text("同向时，等号成立", font_size=24, color=TITLE_COLOR, weight=BOLD)
    equal_label.move_to([0, -2.42, 0])
    _circle_max_action(scene, equality_cue, audio_origin,
                       FadeOut(perpendicular_line), FadeOut(projection_label), FadeIn(equal_label, shift=UP * 0.04), duration=0.34)
    _circle_max_stable(scene, "b05")

    b06 = beats[5] if len(beats) > 5 else {}
    product = _circle_max_text(f"最大值＝{radius_label}×{norm_label}", font_size=34, color=WHITE_TEXT, weight=BOLD)
    product.move_to(bound.get_center())
    product_box = _circle_max_box(product)
    _circle_max_action(scene, _circle_max_cue(b06, "product", "乘", "最大值"), audio_origin,
                       FadeOut(alignment_box), ReplacementTransform(bound, product), FadeIn(product_box), duration=0.45)
    result = _circle_max_text(f"最大值＝{radius_label}×{norm_label}＝{answer}", font_size=34, color=WHITE_TEXT, weight=BOLD)
    result.move_to(product.get_center())
    result_box = _circle_max_box(result)
    answer_text = _circle_max_text(str(answer), font_size=44, color=RESULT_RED, weight=BOLD)
    answer_text.move_to([0, -4.55, 0])
    _circle_max_action(scene, _circle_max_cue(b06, "answer", "等于", "答案"), audio_origin,
                       ReplacementTransform(product, result), ReplacementTransform(product_box, result_box),
                       FadeIn(answer_text, scale=0.94), duration=0.44)
    _circle_max_stable(scene, "b06")

    # Keep the proof geometry and answer on screen while any remaining audio
    # finishes.  The user asked for no lower-third narration captions.
    if audio_path:
        tail_hold = max(0.0, float(audio.get("tail_hold", 2.0)))
        target = audio_origin + float(audio.get("duration", 0.0)) + tail_hold
        remaining = target - float(scene.time)
        if remaining > 0.02:
            scene.wait(remaining)
    else:
        scene.wait(1.2)
    _circle_max_stable(scene, "final_stable")
