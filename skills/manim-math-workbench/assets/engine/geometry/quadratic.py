"""Restricted quadratic algebra and exact viewport clipping; no executable expressions."""
import math

from .math2d import finite_scalar, scalar_value


def quadratic_scalar(value, parameters):
    """Quadratics accept finite numbers or the existing strict affine form."""
    return finite_scalar(scalar_value(value, parameters))


def _finite_result(value, description):
    if not math.isfinite(value):
        raise ValueError(f'Quadratic {description} is outside finite numeric range')
    return float(value)


def _finite_product(values, description):
    """Avoid intermediate overflow/underflow when the final product fits."""
    if any(value == 0 for value in values):
        return 0.
    mantissa, exponent = 1., 0
    for value in values:
        m, e = math.frexp(value)
        mantissa *= m
        exponent += e
    try:
        value = math.ldexp(mantissa, exponent)
    except OverflowError as exc:
        raise ValueError(f'Quadratic {description} is outside finite numeric range') from exc
    if value == 0:
        raise ValueError(f'Quadratic nonzero {description} is below finite numeric resolution')
    return _finite_result(value, description)


def _coefficients(obj, parameters):
    a, h, k = (quadratic_scalar(obj[name], parameters) for name in ('a', 'h', 'k'))
    if a == 0:
        raise ValueError('Quadratic coefficient a must be nonzero')
    return a, h, k


def quadratic_state(obj, parameters):
    a, h, k = _coefficients(obj, parameters)
    b = _finite_product((-2., a, h), 'linear coefficient')
    c = _finite_result((a * h) * h + k, 'constant coefficient')
    discriminant = _finite_product((-4., a, k), 'discriminant')
    # The vertex form gives the exact real-root classification without a
    # tolerance that would turn a small positive/negative discriminant into zero.
    if k == 0:
        roots = [h]
    elif (k > 0) == (a > 0):
        roots = []
    else:
        # Dividing before sqrt could overflow/underflow even with finite roots.
        radius = _finite_result(math.sqrt(abs(k)) / math.sqrt(abs(a)), 'root offset')
        roots = [_finite_result(h - radius, 'root'), _finite_result(h + radius, 'root')]
    return dict(a=a, h=h, k=k, b=b, c=c, discriminant=discriminant,
                roots=roots, vertex=[h, k])


def quadratic_value(obj, parameters, x):
    a, h, k = _coefficients(obj, parameters)
    x = quadratic_scalar(x, parameters)
    delta = x - h
    return _finite_result((a * delta) * delta + k, 'value')


def quadratic_point(derive, definitions, parameters):
    """A genuine dependency point using only the existing affine scalar grammar."""
    if not isinstance(derive, dict) or set(derive) != {'type', 'curve', 'x'} or derive['type'] != 'on_quadratic':
        raise ValueError('on_quadratic requires only type/curve/x')
    key = derive['curve']
    curve = definitions.get(key, {}) if isinstance(key, str) else {}
    if curve.get('type') != 'quadratic':
        raise ValueError('on_quadratic requires a quadratic curve')
    x = quadratic_scalar(derive['x'], parameters)
    return [x, quadratic_value(curve, parameters, x)]


def feature_state(feature, curve, parameters):
    state = quadratic_state(curve, parameters)
    kind = feature['kind']
    if kind == 'axis':
        return {'kind': kind, 'points': [], 'axis_x': state['h']}
    if kind == 'vertex':
        points = [state['vertex']]
    elif kind == 'roots':
        points = [[root, 0.] for root in state['roots']]
    elif kind == 'y_intercept':
        points = [[0., state['c']]]
    elif kind == 'point':
        x = quadratic_scalar(feature['x'], parameters)
        points = [[x, quadratic_value(curve, parameters, x)]]
    else:
        raise ValueError(f'Unknown quadratic feature: {kind}')
    return {'kind': kind, 'points': points}


def quadratic_segments(obj, parameters, bounds):
    """Return exact cubic Bezier groups, each four [x,y] control points.

    The visible x-domain is solved analytically from the two horizontal window
    boundaries, then intersected with the horizontal window. Disconnected arms
    remain separate groups. An isolated tangency is four identical points.
    """
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        raise ValueError('Quadratic clipping needs four finite world bounds')
    xmin, xmax, ymin, ymax = map(finite_scalar, bounds)
    if not xmin < xmax or not ymin < ymax:
        raise ValueError('Quadratic clipping bounds must have positive area')
    state = quadratic_state(obj, parameters)
    a, h, k = state['a'], state['h'], state['k']
    near, far = (ymin, ymax) if a > 0 else (ymax, ymin)
    far_delta = far - k
    if (a > 0 and far_delta < 0) or (a < 0 and far_delta > 0):
        return []
    outer = math.sqrt(abs(far_delta)) / math.sqrt(abs(a))
    near_delta = near - k
    excludes_vertex = (a > 0 and near_delta > 0) or (a < 0 and near_delta < 0)
    inner = math.sqrt(abs(near_delta)) / math.sqrt(abs(a)) if excludes_vertex else 0.
    # Work in the local coordinate u=x-h. Adding a tiny root offset to a
    # nonzero h too early would collapse a narrow visible arc to its vertex.
    intervals = ([(-outer, -inner), (inner, outer)]
                 if excludes_vertex else [(-outer, outer)])
    result = []
    for left, right in intervals:
        left, right = max(left, xmin-h), min(right, xmax-h)
        if left > right:
            continue
        y0 = _finite_result((a * left) * left + k, 'clipping endpoint')
        y1 = _finite_result((a * right) * right + k, 'clipping endpoint')
        # Removing only floating-point overshoot at an analytically solved
        # boundary keeps the curve in the viewport; it does not create roots.
        y0, y1 = min(ymax, max(ymin, y0)), min(ymax, max(ymin, y1))
        dx = right - left
        c1 = y0 + ((a * left) * dx) * (2 / 3)
        c2 = y1 - ((a * right) * dx) * (2 / 3)
        result.append([[h+left, y0], [h+(left + dx / 3), _finite_result(c1, 'Bezier control')],
                       [h+(right - dx / 3), _finite_result(c2, 'Bezier control')], [h+right, y1]])
    return result


def validate_quadratic_parameters(objects, parameters):
    definitions = {o['id']: o for o in objects}
    for obj in objects:
        if obj['type'] == 'quadratic':
            quadratic_state(obj, parameters)
        elif obj['type'] == 'point' and obj.get('derive', {}).get('type') == 'on_quadratic':
            quadratic_point(obj['derive'], definitions, parameters)
        elif obj['type'] == 'quadratic_feature':
            curve = definitions.get(obj.get('curve'), {})
            if curve.get('type') != 'quadratic':
                raise ValueError('Quadratic feature must reference a quadratic')
            feature_state(obj, curve, parameters)


def validate_quadratic_transition(objects, before, after):
    curves = [obj for obj in objects if obj['type'] == 'quadratic']
    if not curves:
        return
    for obj in curves:
        start, finish = quadratic_state(obj, before), quadratic_state(obj, after)
        if (start['a'] > 0) != (finish['a'] > 0):
            raise ValueError('Parameter transition makes quadratic a cross zero')
    # Each a is affine in one parameter: equal nonzero endpoint signs prove
    # a stays nonzero throughout the linear/eased-monotone parameter update.
    for fraction in (0, .25, .5, .75, 1):
        sampled = {name: before[name] + (after[name] - before[name]) * fraction for name in before}
        validate_quadratic_parameters(objects, sampled)
