"""Restricted y=k/x math and bounded cubic rendering. Never executes expressions."""
import math
from .math2d import finite_scalar, scalar_value


def branch_signs(obj):
    """Select by mathematical x sign, independently of k and camera layout."""
    branch = obj.get('branch', 'both')
    if not isinstance(branch, str) or branch not in ('both', 'positive_x', 'negative_x'):
        raise ValueError('Reciprocal branch must be both, positive_x or negative_x')
    return (-1, 1) if branch == 'both' else ((1,) if branch == 'positive_x' else (-1,))


def nonzero(value, parameters, name):
    value = finite_scalar(scalar_value(value, parameters))
    if value == 0:
        raise ValueError(f'Reciprocal {name} must be nonzero')
    return value


def reciprocal_point(derive, definitions, parameters):
    curve = definitions.get(derive['curve'], {})
    if curve.get('type') != 'reciprocal':
        raise ValueError('on_reciprocal requires a reciprocal curve')
    k = nonzero(curve['k'], parameters, 'k')
    x = nonzero(derive['x'], parameters, 'x')
    y = k / x
    if not math.isfinite(y) or y == 0:
        raise ValueError('Reciprocal point outside finite nonzero numeric resolution')
    return [x, y]


def validate_reciprocal_parameters(objects, parameters):
    definitions = {o['id']: o for o in objects}
    for obj in objects:
        if obj['type'] == 'reciprocal':
            branch_signs(obj)
            nonzero(obj['k'], parameters, 'k')
            tolerance = finite_scalar(obj.get('tolerance', .001))
            if not 1e-8 <= tolerance <= .05:
                raise ValueError('Reciprocal tolerance must be in [1e-8, .05] world units')
        if obj['type'] == 'point' and obj.get('derive', {}).get('type') == 'on_reciprocal':
            reciprocal_point(obj['derive'], definitions, parameters)


def validate_reciprocal_transition(objects, before, after):
    # Scalars are affine in one parameter, so equal nonzero endpoint signs
    # prove no zero crossing throughout monotone parameter interpolation.
    validate_reciprocal_parameters(objects, before)
    validate_reciprocal_parameters(objects, after)
    for obj in objects:
        values = []
        if obj['type'] == 'reciprocal':
            values.append((obj['k'], 'k'))
        if obj['type'] == 'point' and obj.get('derive', {}).get('type') == 'on_reciprocal':
            values.append((obj['derive']['x'], 'x'))
        for value, name in values:
            if (nonzero(value, before, name) > 0) != (nonzero(value, after, name) > 0):
                raise ValueError(f'Reciprocal {name} transition crosses zero; use a separate curve/chapter')


def reciprocal_segments(obj, parameters, bounds):
    """Separate branches of C1 cubic Hermite segments, clipped analytically.

    For each segment max |f-H| <= |k| h^4/(16 min|x|^5).
    X is linear in the Bezier parameter; the bound is world-space vertical
    error. Convex-hull checks also keep every control inside the viewport and
    strictly inside one quadrant. No chord can cross either asymptote.
    """
    k = nonzero(obj['k'], parameters, 'k')
    tolerance = finite_scalar(obj.get('tolerance', .001))
    if not 1e-8 <= tolerance <= .05:
        raise ValueError('Reciprocal tolerance must be in [1e-8, .05] world units')
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        raise ValueError('Reciprocal needs four finite bounds')
    xmin, xmax, ymin, ymax = map(finite_scalar, bounds)
    if not xmin < xmax or not ymin < ymax:
        raise ValueError('Reciprocal bounds must have positive area')
    branches = []
    count = 0
    for sx in branch_signs(obj):
        sy = sx if k > 0 else -sx
        ux = sorted((sx*xmin, sx*xmax))
        vy = sorted((sy*ymin, sy*ymax))
        if ux[1] <= 0 or vy[1] <= 0:
            continue
        left = max(ux[0], abs(k)/vy[1])
        right = min(ux[1], abs(k)/vy[0]) if vy[0] > 0 else ux[1]
        if left > right:
            continue
        if left <= 0 or not all(math.isfinite(v) for v in (left,right)):
            raise ValueError('Reciprocal clipping outside numeric resolution')
        segments = []
        def split(a, b, depth=0):
            nonlocal count
            h = b-a
            ya, yb = abs(k)/a, abs(k)/b
            ratio = h/a
            # Log comparison avoids overflow in the certified error bound.
            accurate = h == 0 or math.log(ya)+4*math.log(ratio)-math.log(16) <= math.log(tolerance)
            c1 = ya - ya*(h/a)/3
            c2 = yb + yb*(h/b)/3
            safe = yb <= c1 <= ya and yb <= c2 <= ya
            if not accurate or not safe:
                mid = a+h/2
                if depth >= 64 or mid in (a,b):
                    raise ValueError('Reciprocal subdivision cannot meet tolerance')
                split(a,mid,depth+1); split(mid,b,depth+1)
                return
            count += 1
            if count > 8192:
                raise ValueError('Reciprocal subdivision budget exceeded')
            controls = [[sx*a,sy*ya],[sx*(a+h/3),sy*c1],
                        [sx*(b-h/3),sy*c2],[sx*b,sy*yb]]
            # Analytic boundary divisions may round a few ulps outside bounds.
            for p in controls:
                p[0] = min(xmax,max(xmin,p[0])); p[1] = min(ymax,max(ymin,p[1]))
                if p[0] == 0 or p[1] == 0 or not all(math.isfinite(v) for v in p):
                    raise ValueError('Reciprocal controls outside nonzero numeric resolution')
            segments.append(controls)
        split(left,right)
        branches.append(segments)
    return branches


def build_reciprocal(scene, obj):
    import numpy as np
    from manim import VGroup, VMobject, DashedVMobject
    group = VGroup()
    for segments in reciprocal_segments(obj, scene.parameter_values(), scene.bounds):
        curve = VMobject(color=obj.get('color','#52C7EA'), stroke_width=obj.get('stroke_width',3.5))
        curve.set_points(np.array([scene.mapped(p) for controls in segments for p in controls]))
        if obj.get('dashed',False):
            curve = DashedVMobject(curve,num_dashes=36)
        group.add(curve)
    return group
