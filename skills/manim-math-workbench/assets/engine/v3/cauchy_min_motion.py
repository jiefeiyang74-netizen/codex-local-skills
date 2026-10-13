"""Checked, phrase-driven right-triangle proof for ax+by=C.

Injected by the workbench compiler; no generated provider code is executed.
The pure coordinate helper is also importable without Manim for math tests.
"""
import math


def cauchy_min_geometry(a, b, total, x):
    a, b, total, x = map(float, (a, b, total, x))
    if not all(math.isfinite(v) for v in (a, b, total, x)) or min(a, b, total) <= 0:
        raise ValueError("三角形演示需要有限的正系数和正常数")
    y = (total - a * x) / b
    if x <= 0 or y <= 0:
        raise ValueError("演示直角边必须为正；任意实数结论由结尾恒等式说明")
    return {
        "x": x, "y": y, "r": math.hypot(x, y),
        "O": (0.0, 0.0), "H": (a * x, 0.0),
        "A": (a * x, a * y),
        # This is the actual clockwise-rotated corner, NOT the reflected corner.
        "J": (a * x, a * y - b * x),
        "B": (a * x + b * y, a * y - b * x),
        "M": (total, 0.0),
        "minimum": total * total / (a * a + b * b),
        "equality_x": a * total / (a * a + b * b),
        "equality_y": b * total / (a * a + b * b),
    }


class _CauchyPreviewComplete(Exception):
    pass


class _CauchyClock:
    def __init__(self, scene, spec):
        self.scene, self.spec = scene, spec
        self.origin = 0.7
        self.stop = float(spec.get("sample_duration") or 0.0)
        self.audio = spec.get("audio") or {}
        self.anchors = spec["local_math_contract"]["cue_anchors"]
        self.actions = [action for beat in spec["beats"] for action in beat.get("actions", [])]
        self.fallback = {key: self.origin + index * 1.3 for index, key in enumerate(self.anchors)}

    def cue(self, name):
        anchor = self.anchors[name]
        matches = [item for item in self.actions if item.get("anchor") == anchor]
        if len(matches) != 1:
            raise ValueError("词组锚点必须唯一：" + name + " / " + anchor)
        return matches[0]

    def target(self, name):
        cue = self.cue(name)
        if self.audio.get("path"):
            return self.origin + float(cue["audio_start"])
        return self.fallback[name]

    def wait_to(self, target):
        reaches_stop = bool(self.stop and target >= self.stop)
        target = min(target, self.stop) if self.stop else target
        gap = target - float(self.scene.time)
        if gap >= 1.0 / float(config.frame_rate):
            self.scene.wait(gap)
        # Manim can quantize a wait down by one frame. A cue beyond the cut
        # must never run merely because the rendered clock stopped at 29.9667.
        if reaches_stop or (self.stop and float(self.scene.time) >= self.stop - 0.5 / float(config.frame_rate)):
            raise _CauchyPreviewComplete()

    def run(self, name, *animations, duration=0.5, next_name=None, rate_func=None):
        planned = self.target(name)
        self.wait_to(planned)
        frame = 1.0 / float(config.frame_rate)
        limits = [self.target(key) for key in self.anchors if self.target(key) > planned + 0.02]
        if next_name:
            limits.append(self.target(next_name))
        if self.stop:
            limits.append(self.stop)
        if limits:
            duration = min(duration, max(frame, min(limits) - float(self.scene.time) - frame))
        print("STUDIO_CAUCHY_CUE " + json.dumps({
            "cue": name, "anchor": self.anchors[name], "planned": round(planned, 4),
            "actual": round(float(self.scene.time), 4),
        }, ensure_ascii=False))
        if animations:
            self.scene.play(*animations, run_time=max(frame, duration), rate_func=rate_func or smooth)
        else:
            self.scene.wait(frame)
        print("STUDIO_STABLE " + json.dumps({"id": name, "time": round(float(self.scene.time), 4)}))


def _cauchy_number(value):
    return str(int(round(value))) if abs(value - round(value)) < 1e-8 else f"{value:.3f}".rstrip("0").rstrip(".")


def _cauchy_text(value, size=27, color=None):
    return _circle_max_text(value, font_size=size, color=color)


def _cauchy_label_position(start, end, side=1, buff=0.24):
    vector = end - start
    normal = np.array([vector[1], -vector[0], 0.0])
    normal /= max(1e-8, np.linalg.norm(normal))
    return (start + end) / 2 + normal * side * buff


def _cauchy_triangle(origin, x, y, scale, color, label_role):
    o = np.array(origin, dtype=float)
    h, p = o + RIGHT * x * scale, o + (RIGHT * x + UP * y) * scale
    fill = Polygon(o, h, p, stroke_width=0, fill_color=color, fill_opacity=0.07)
    horizontal = Line(o, h, color=color, stroke_width=3.4)
    vertical = Line(h, p, color=color, stroke_width=3.4)
    hypotenuse = Line(o, p, color=color, stroke_width=4.3)
    d = min(x, y) * scale * 0.2
    mark = VMobject(color=color, stroke_width=1.8).set_points_as_corners([
        h + LEFT * d, h + (LEFT + UP) * d, h + UP * d,
    ])
    body = VGroup(fill, horizontal, vertical, hypotenuse, mark)
    labels = VGroup(*[_cauchy_text(value, 26, color) for value in ("x", "y", "r")])
    joined = ValueTracker(0)
    proof_labels = ValueTracker(0)
    def position_labels(group):
        group[0].move_to(_cauchy_label_position(horizontal.get_start(), horizontal.get_end()))
        group[1].move_to(_cauchy_label_position(vertical.get_start(), vertical.get_end()))
        group[2].move_to(_cauchy_label_position(hypotenuse.get_start(), hypotenuse.get_end(), -1, 0.3))
        if label_role == "second":
            # After the connector appears, label 4y above its horizontal leg:
            # the moving yellow hypotenuse occupies the region below that leg.
            group[1].shift(UP * 0.48 * proof_labels.get_value())
        # Once joined, both vertical legs share an x-coordinate. Put their
        # labels on the clear right side at distinct heights, also at equality.
        # Interpolate while joining so the label itself does not jump.
        index, edge = (1, vertical) if label_role == "first" else (0, horizontal)
        clear_position = edge.get_start() + (edge.get_end() - edge.get_start()) * 0.25 + RIGHT * 0.32
        if label_role == "first":
            clear_position += LEFT * 0.64 * proof_labels.get_value()
        group[index].move_to(interpolate(group[index].get_center(), clear_position, joined.get_value()))
    labels.add_updater(position_labels)
    labels.update()
    return {"body": body, "labels": labels, "color": color, "joined_labels": joined,
            "proof_labels": proof_labels}


def _cauchy_scale_labels(triangle, multiplier):
    for label, variable in zip(triangle["labels"], ("x", "y", "r")):
        label.become(_cauchy_text(_cauchy_number(multiplier) + variable, 26, triangle["color"]).move_to(label))


def _cauchy_update_triangle(triangle, o, h, p):
    body = triangle["body"]
    body[0].set_points_as_corners([o, h, p, o])
    body[1].put_start_and_end_on(o, h)
    body[2].put_start_and_end_on(h, p)
    body[3].put_start_and_end_on(o, p)
    u, v = o - h, p - h
    u = u / np.linalg.norm(u) * 0.14
    v = v / np.linalg.norm(v) * 0.14
    body[4].set_points_as_corners([h + u, h + u + v, h + v])


def play_cauchy_linear_min(scene, spec):
    """Execute the checked full lesson; sample_duration stops a preview only."""
    try:
        _play_cauchy_linear_min(scene, spec)
    except _CauchyPreviewComplete:
        # This Manim version does not honor the muxer's shortest option. Trim
        # only the in-memory preview soundtrack, never the user's source file.
        writer = scene.renderer.file_writer
        if writer.includes_sound:
            writer.audio_segment = writer.audio_segment[:round(float(spec["sample_duration"]) * 1000)]
        print("STUDIO_CAUCHY_SAMPLE " + json.dumps({"time": round(float(scene.time), 4)}))


def _play_cauchy_linear_min(scene, spec):
    contract = spec["local_math_contract"]
    a, b, total = (float(contract[key]) for key in ("a", "b", "C"))
    norm = math.hypot(a, b)
    an, bn, cn, nn = map(_cauchy_number, (a, b, total, norm))
    x0 = (a * total / (a * a + b * b)) * (2.0 / 3.0)
    data = cauchy_min_geometry(a, b, total, x0)
    y0 = data["y"]
    scale = min(5.0 / total, 4.0 / (b * data["r"]), 3.0 / (a * y0))
    origin = np.array([-total * scale / 2, -1.3, 0.0])
    scene.camera.background_color = BLACK
    title = _circle_max_title(spec.get("title") or "数学解题可视化")
    scene.play(FadeIn(title, shift=DOWN * 0.06), run_time=0.7)
    clock = _CauchyClock(scene, spec)
    if clock.audio.get("path"):
        scene.add_sound(clock.audio["path"], time_offset=clock.origin - float(scene.time))

    opening = _cauchy_text("柯西不等式", 42, WHITE_TEXT).move_to([0, 0.6, 0])
    focus = _circle_max_box(opening)
    clock.run("intro", FadeIn(opening), FadeIn(focus), duration=0.55)
    condition = _cauchy_text(f"{an}x ＋ {bn}y ＝ {cn}", 33).move_to([0, 3.93, 0])
    objective = _cauchy_text("求 x² ＋ y² 的最小值", 29).move_to([0, 3.27, 0])
    clock.run("problem", FadeOut(opening), FadeIn(condition), Transform(focus, _circle_max_box(condition)))
    clock.run("objective", FadeIn(objective), Transform(focus, _circle_max_box(objective)))

    first = _cauchy_triangle([-1.25, -0.28, 0], x0, y0, scale, "#55B8FF", "first")
    second = _cauchy_triangle([0.75, -0.28, 0], x0, y0, scale, "#8FD175", "second")
    clock.run("triangles", LaggedStart(Create(first["body"]), Create(second["body"]), lag_ratio=0.35), FadeOut(focus), duration=0.85)
    # Labels remain separate from rotating paths, so the letters stay upright.
    for triangle in (first, second):
        triangle["labels"][2].set_opacity(0)
    clock.run("legs", FadeIn(first["labels"]), FadeIn(second["labels"]), duration=0.45)
    relation = _cauchy_text("x² ＋ y² ＝ r²", 30).move_to([0, -4.15, 0])
    clock.run("radius", first["labels"][2].animate.set_opacity(1), second["labels"][2].animate.set_opacity(1),
              FadeIn(relation), duration=0.48)

    # Both copies start at exactly the same scale. Only their scale multipliers
    # differ; subsequent rotation is rigid and the full assembly shares one scale.
    left_o = np.array([-3.4, -1.3, 0.0])
    right_o = np.array([-0.85, -1.7, 0.0])
    first_target = first["body"].copy().scale(a, about_point=first["body"][1].get_start())
    first_target.shift(left_o - first_target[1].get_start())
    clock.wait_to(clock.target("scale3"))
    _cauchy_scale_labels(first, a)
    clock.run("scale3", Transform(first["body"], first_target), duration=1.15)
    second_target = second["body"].copy().scale(b, about_point=second["body"][1].get_start())
    second_target.shift(right_o - second_target[1].get_start())
    clock.wait_to(clock.target("scale4"))
    _cauchy_scale_labels(second, b)
    clock.run("scale4", Transform(second["body"], second_target), duration=1.05)
    clock.run("similar", first["body"][3].animate.set_stroke(width=5), second["body"][3].animate.set_stroke(width=5), duration=0.4)

    pivot = second["body"][1].get_start().copy()
    rotation_arc = Arc(radius=0.7, start_angle=math.atan2(y0, x0), angle=-PI/2,
                       arc_center=pivot, color=BOX_RED, stroke_width=2.7).add_tip(tip_length=0.12)
    angle_label = _cauchy_text("90°", 25, BOX_RED).move_to(pivot + RIGHT * 0.82 + UP * 0.26)
    clock.run("rotate", Rotate(second["body"], angle=-PI / 2, about_point=pivot),
              Create(rotation_arc), FadeIn(angle_label), duration=1.45)
    first_shift = origin - first["body"][1].get_start()
    join_point = first["body"][3].get_end() + first_shift
    clock.run("join", first["body"].animate.shift(first_shift),
              second["body"].animate.shift(join_point - second["body"][3].get_start()),
              first["joined_labels"].animate.set_value(1), second["joined_labels"].animate.set_value(1),
              FadeOut(rotation_arc), FadeOut(angle_label), duration=1.0)

    tracker = ValueTracker(x0)
    def geometry():
        return cauchy_min_geometry(a, b, total, tracker.get_value())
    def point(name):
        return origin + np.array([*geometry()[name], 0.0]) * scale
    first["body"].add_updater(lambda _: _cauchy_update_triangle(first, point("O"), point("H"), point("A")))
    second["body"].add_updater(lambda _: _cauchy_update_triangle(second, point("A"), point("J"), point("B")))

    def right_marker():
        p, o, q = point("A"), point("O"), point("B")
        u, v = (o-p) / np.linalg.norm(o-p)*0.2, (q-p) / np.linalg.norm(q-p)*0.2
        return VMobject(color=WHITE_TEXT, stroke_width=2.7).set_points_as_corners([p+u, p+u+v, p+v])
    large_right = always_redraw(right_marker)
    clock.run("right", Create(large_right), duration=0.45)

    connector = Line(point("O"), point("B"), color=TITLE_COLOR, stroke_width=4.8)
    connector.add_updater(lambda mob: mob.put_start_and_end_on(point("O"), point("B")))
    clock.run("connect", Create(connector), first["proof_labels"].animate.set_value(1),
              second["proof_labels"].animate.set_value(1), duration=0.65)
    theorem = _cauchy_text(f"({an}r)² ＋ ({bn}r)²", 30).move_to(relation)
    clock.run("pythagorean", ReplacementTransform(relation, theorem), duration=0.48)
    clock.run("legs_scaled", first["body"][3].animate.set_stroke(width=5.8), second["body"][3].animate.set_stroke(width=5.8), duration=0.45)
    hyp_label = _cauchy_text(nn + "r", 29, TITLE_COLOR)
    hyp_label.move_to([0, origin[1] - 0.42, 0])
    # A labeled callout keeps 5r attached to OB without any moving edge or
    # horizontal baseline passing through the characters.
    hyp_leader = always_redraw(lambda: Arrow(
        hyp_label.get_top() + UP * 0.04,
        (point("O") + point("B")) / 2 + DOWN * 0.055,
        color=TITLE_COLOR, stroke_width=1.8, buff=0,
        max_tip_length_to_length_ratio=0.18, tip_length=0.09,
    ))
    theorem2 = _cauchy_text(f"({an}r)² ＋ ({bn}r)² ＝ ({nn}r)²", 29).move_to(theorem)
    fit_inside(theorem2, 7.7, 0.6)
    clock.run("hypotenuse", FadeIn(hyp_label), Create(hyp_leader),
              ReplacementTransform(theorem, theorem2), duration=0.55)

    baseline_y = origin[1] - 0.76
    dimension_start = np.array([origin[0], baseline_y, 0])
    dimension_end = dimension_start + RIGHT * total * scale
    dimension = Line(dimension_start, dimension_end, color=WHITE_TEXT, stroke_width=2.6)
    ticks = VGroup(*[Line(pos + UP * 0.1, pos + DOWN * 0.1, color=WHITE_TEXT, stroke_width=2)
                    for pos in (dimension_start, dimension_end)])
    clock.run("horizontal", Create(dimension), Create(ticks), duration=0.5)
    split_pos = dimension_start + RIGHT * a * x0 * scale
    width_a = _cauchy_text(an + "x", 26, first["color"]).move_to((dimension_start + split_pos) / 2 + DOWN * 0.3)
    width_b = _cauchy_text(bn + "y", 26, second["color"]).move_to((split_pos + dimension_end) / 2 + DOWN * 0.3)
    split_tick = Line(split_pos + UP * .1, split_pos + DOWN * .1, color=MUTED_TEXT, stroke_width=1.8)
    clock.run("width", FadeIn(width_a), FadeIn(width_b), Create(split_tick), duration=0.48)
    width_sum = _cauchy_text(f"{an}x ＋ {bn}y ＝ {cn}", 28).move_to((dimension_start + dimension_end)/2 + DOWN * 0.35)
    clock.run("constant", FadeOut(width_a), FadeOut(width_b), FadeOut(split_tick), FadeIn(width_sum),
              FadeIn(focus.become(_circle_max_box(condition))), duration=0.5)

    # There is exactly one independent variable: y is recomputed from ax+by=C.
    x1 = data["equality_x"] * 0.82
    clock.run("vary", tracker.animate.set_value(x1), FadeOut(focus), duration=1.3)
    def perpendicular():
        end, foot = point("B"), point("M")
        if np.linalg.norm(end-foot) < 0.02:
            return VGroup()
        return DashedLine(end, foot, color=MUTED_TEXT, stroke_width=2, dash_length=0.09)
    projection = always_redraw(perpendicular)
    fixed_base = Line(point("O"), point("M"), color=WHITE_TEXT, stroke_width=2.8)
    clock.run("compare", Create(fixed_base), Create(projection), duration=0.6)
    inequality = _cauchy_text(f"{nn}r ≥ {cn}", 34).move_to(theorem2)
    clock.run("bound", ReplacementTransform(theorem2, inequality), FadeIn(focus.become(_circle_max_box(inequality))), duration=0.5)
    question = _cauchy_text("什么时候取等？", 29).move_to([0, -3.27, 0])
    clock.run("question", FadeIn(question), duration=0.45)
    equality = _cauchy_text(f"{an}y ＝ {bn}x", 30, TITLE_COLOR).move_to(question)
    clock.run("equality", ReplacementTransform(question, equality),
              first["body"][2].animate.set_stroke(width=5), second["body"][1].animate.set_stroke(width=5), duration=0.5)
    clock.run("level", tracker.animate.set_value(data["equality_x"]), duration=0.8)
    clock.run("coincide", FadeOut(projection), FadeOut(fixed_base), FadeOut(hyp_label), FadeOut(hyp_leader),
              connector.animate.set_stroke(width=5.6), duration=0.4)
    eq_product = _cauchy_text(f"{nn}r ＝ {cn}", 34).move_to(inequality)
    clock.run("eq5r", ReplacementTransform(inequality, eq_product), Transform(focus, _circle_max_box(eq_product)), duration=0.4)
    eq_radius = _cauchy_text(f"r ＝ {_cauchy_number(total / norm)}", 34).move_to(eq_product)
    clock.run("eqr", ReplacementTransform(eq_product, eq_radius), Transform(focus, _circle_max_box(eq_radius)), duration=0.4)
    result = _cauchy_text("min(x² ＋ y²) ＝ " + str(contract.get("answer_text") or _cauchy_number(data["minimum"])), 33, TITLE_COLOR).move_to(eq_radius)
    clock.run("answer", ReplacementTransform(eq_radius, result), Transform(focus, _circle_max_box(result)), duration=0.55)

    # Numerical proof is complete. Generalization is a separate algebraic view:
    # no negative coefficient is ever drawn as a negative physical side length.
    general_a = _cauchy_text(f"a² ＋ {bn}²", 34).move_to([0, 1.05, 0])
    clock.run("general_a", FadeOut(first["body"]), FadeOut(second["body"]),
              FadeOut(first["labels"]), FadeOut(second["labels"]), FadeOut(large_right),
              FadeOut(connector), FadeOut(dimension), FadeOut(ticks), FadeOut(width_sum),
              FadeOut(equality), FadeOut(focus), FadeOut(result), FadeOut(condition), FadeOut(objective),
              FadeIn(general_a), duration=0.65)
    general_ab = _cauchy_text("a² ＋ b²", 34).move_to(general_a)
    clock.run("general_b", ReplacementTransform(general_a, general_ab), duration=0.4)
    general = _cauchy_text("(a²＋b²)(x²＋y²) ≥ (ax＋by)²", 31).move_to([0, .65, 0])
    fit_inside(general, 7.75, 0.7)
    identity = _cauchy_text("两边之差 ＝ (ay－bx)² ≥ 0", 27).move_to([0, -.35, 0])
    condition_general = _cauchy_text("等号成立 ⇔ ay＝bx", 27, TITLE_COLOR).move_to([0, -1.18, 0])
    domain = _cauchy_text("a、b、x、y 为任意实数", 21, MUTED_TEXT).move_to([0, -1.92, 0])
    clock.run("general", ReplacementTransform(general_ab, general), FadeIn(identity),
              FadeIn(condition_general), FadeIn(domain), duration=0.65)
    clock.run("close", FadeIn(focus.become(_circle_max_box(general))), duration=0.45)
    end = clock.origin + float(clock.audio.get("duration") or scene.time) + float(clock.audio.get("tail_hold", 2.0))
    clock.wait_to(end)
    print("STUDIO_STABLE " + json.dumps({"id": "final_stable", "time": round(float(scene.time), 4)}))
