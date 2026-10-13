"""Trusted renderers for declarative quadratic graphs; no user expressions."""
import numpy as np
from manim import VGroup, VMobject, Line, DashedLine, Dot, DashedVMobject, config
from .schema import axis_tick_key
from .math2d import scalar_value
from .quadratic import quadratic_state, quadratic_segments


def display_number(value):
    if abs(value) < 1e-9:
        value = 0
    return f'{value:.3g}'


def build_axes(scene, obj):
    xmin, xmax, ymin, ymax = scene.bounds
    color = obj.get('color', '#8C96A5')
    size = obj.get('font_size', 21)
    group = VGroup()
    point = scene.mapped
    offsets = obj.get('label_offsets', {})
    if obj.get('grid', False):
        for x in obj.get('x_ticks', []):
            if x != 0:
                group.add(Line(point([x, ymin]), point([x, ymax]), color='#242A33', stroke_width=1))
        for y in obj.get('y_ticks', []):
            if y != 0:
                group.add(Line(point([xmin, y]), point([xmax, y]), color='#242A33', stroke_width=1))
    if ymin <= 0 <= ymax:
        end = point([xmax, 0])
        group.add(Line(point([xmin, 0]), end, color=color, stroke_width=2))
        group.add(scene.continuation(end, 1, color))
        group.add(scene.text('x', size, color).move_to(end + [-.22, .25, 0]))
        for x in obj.get('x_ticks', []):
            if x == 0:
                continue
            p = point([x, 0])
            group.add(Line(p + [0, -.045, 0], p + [0, .045, 0], color=color, stroke_width=1.5))
            label = scene.text(display_number(x), size, color).move_to(p + [*offsets.get(axis_tick_key('x', x), [0, -.27]), 0])
            label.set_z_index(10)
            label.add_background_rectangle(color=config.background_color, opacity=1, buff=.025)
            label.background_rectangle.set_z_index(9)
            group.add(label)
    if xmin <= 0 <= xmax:
        end = point([0, ymax])
        group.add(Line(point([0, ymin]), end, color=color, stroke_width=2))
        group.add(VMobject(color=color, stroke_width=2).set_points_as_corners([end + [-.09, -.14, 0], end, end + [.09, -.14, 0]]))
        group.add(scene.text('y', size, color).move_to(end + [.25, -.2, 0]))
        for y in obj.get('y_ticks', []):
            if y == 0:
                continue
            p = point([0, y])
            group.add(Line(p + [-.045, 0, 0], p + [.045, 0, 0], color=color, stroke_width=1.5))
            label = scene.text(display_number(y), size, color).move_to(p + [*offsets.get(axis_tick_key('y', y), [-.3, 0]), 0])
            label.set_z_index(10)
            label.add_background_rectangle(color=config.background_color, opacity=1, buff=.025)
            label.background_rectangle.set_z_index(9)
            group.add(label)
    if xmin < 0 < xmax and ymin < 0 < ymax:
        group.add(scene.text('O', size, color).move_to(point([0, 0]) + [*offsets.get('origin', [-.23, -.25]), 0]))
    return group


def build_quadratic(scene, obj):
    color = obj.get('color', '#52C7EA')
    group = VGroup()
    for controls in quadratic_segments(obj, scene.parameter_values(), scene.bounds):
        curve = VMobject(color=color, stroke_width=obj.get('stroke_width', 3.5))
        curve.set_points(np.array([scene.mapped(p) for p in controls]))
        if obj.get('dashed', False):
            curve = DashedVMobject(curve, num_dashes=36)
        group.add(curve)
    return group


def build_feature(scene, obj):
    params = scene.parameter_values()
    state = quadratic_state(scene.defs[obj['curve']], params)
    kind = obj['kind']
    xmin, xmax, ymin, ymax = scene.bounds
    color = obj.get('color', '#FFD166')
    group = VGroup()
    if kind == 'axis':
        x = state['h']
        if xmin <= x <= xmax:
            group.add(DashedLine(scene.mapped([x, ymin]), scene.mapped([x, ymax]), color=color, stroke_width=2, dash_length=.12))
        return group
    if kind == 'vertex':
        points = [state['vertex']]
    elif kind == 'roots':
        points = [[x, 0] for x in state['roots']]
    elif kind == 'y_intercept':
        points = [[0, state['c']]]
    elif kind == 'point':
        x = scalar_value(obj['x'], params)
        points = [[x, state['a'] * (x - state['h'])**2 + state['k']]]
    else:
        raise ValueError('Unsupported quadratic feature')
    for index, xy in enumerate(points):
        if not (xmin <= xy[0] <= xmax and ymin <= xy[1] <= ymax):
            continue
        center = scene.mapped(xy)
        group.add(Dot(center, radius=.07, color=color).set_z_index(8))
        if obj.get('show_label', True):
            label = obj.get('label') or f'({display_number(xy[0])}, {display_number(xy[1])})'
            if kind == 'roots' and obj.get('label') and len(points) > 1:
                label += str(index + 1)
            text = scene.text(label, obj.get('font_size', 22), color, max_width=4)
            offset = obj.get('label_offset', [.35, -.5] if kind == 'vertex' else [.45, .5])
            text.move_to(center + [*offset, 0])
            # Keep the label inside the display rectangle without moving its point.
            cx, cy, width, height = scene.plot_rect
            desired = text.get_center().copy()
            desired[0] = np.clip(desired[0], cx-width/2+text.width/2+.06, cx+width/2-text.width/2-.06)
            desired[1] = np.clip(desired[1], cy-height/2+text.height/2+.06, cy+height/2-text.height/2-.06)
            text.move_to(desired)
            text.add_background_rectangle(color=config.background_color, opacity=1, buff=.045)
            text.set_z_index(10)
            text.background_rectangle.set_z_index(9)
            group.add(text)
    return group
