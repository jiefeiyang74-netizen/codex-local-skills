"""Conic drawing and stable segment-arrow families."""
import numpy as np
from manim import VGroup, VMobject, Line, DashedLine, Polygon
from .conic import conic_paths


def build_conic(scene, obj):
    from manim import DashedVMobject
    result = VGroup()
    for path in conic_paths(obj, scene.bounds):
        curve = VMobject(color=obj.get('color', '#52C7EA'), stroke_width=obj.get('stroke_width', 3.5))
        curve.set_points_as_corners([scene.mapped(p) for p in path])
        if obj.get('dashed', False):
            curve = DashedVMobject(curve, num_dashes=48)
        result.add(curve)
    return result


def build_arrow(scene, obj, pair):
    result = VGroup()
    if pair is None:
        return result
    a, b = map(scene.mapped, pair)
    length = np.linalg.norm(b-a)
    if length <= 1e-10:
        return result
    u = (b-a)/length
    normal = np.array([-u[1], u[0], 0.])
    tip = min(.16, .25*length)
    color = obj.get('color', '#FFFFFF')
    cls = DashedLine if obj.get('dashed') else Line
    result.add(cls(a, b, color=color, stroke_width=obj.get('stroke_width', 3)))
    result.add(Polygon(b, b-tip*u+.45*tip*normal, b-tip*u-.45*tip*normal,
                       color=color, fill_opacity=1, stroke_width=0))
    return result
