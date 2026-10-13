"""Bounded, axis-aligned conics. No expression execution or project data."""
import math
import numpy as np
from .math2d import finite_scalar, scalar_value


def conic_state(obj):
    kind = obj.get('kind')
    required = {'id', 'type', 'kind', 'center'}
    required |= {'p'} if kind == 'parabola' else {'a', 'b'}
    if kind == 'hyperbola':
        required.add('branch')
    if (obj.get('type') != 'conic' or kind not in ('ellipse', 'hyperbola', 'parabola')
            or not required <= obj.keys()
            or obj.keys() - required - {'color', 'stroke_width', 'dashed', 'tolerance'}):
        raise ValueError('Invalid strict conic fields')
    center = obj['center']
    if not isinstance(center, list) or len(center) != 2 or any(abs(finite_scalar(v)) > 10000 for v in center):
        raise ValueError('Conic center must be fixed finite xy within +/-10000')
    state = dict(kind=kind, center=list(center))
    for key in ('p',) if kind == 'parabola' else ('a', 'b'):
        v = finite_scalar(obj[key])
        if not 1e-6 <= abs(v) <= 10000 or (key != 'p' and v < 0):
            raise ValueError('Conic axes require 1e-6..10000; p may be negative')
        state[key] = v
    if kind == 'hyperbola':
        if obj['branch'] not in ('positive_x', 'negative_x', 'both'):
            raise ValueError('Invalid fixed hyperbola branch')
        state['branch'] = obj['branch']
    tolerance = finite_scalar(obj.get('tolerance', .001))
    if not 1e-8 <= tolerance <= .05:
        raise ValueError('Conic tolerance must be 1e-8..05 world units')
    return state


def position_derivative(state, t, branch=None):
    t = finite_scalar(t)
    kind = state['kind']
    if kind == 'ellipse':
        a, b = state['a'], state['b']
        p, d = [a*math.cos(t), b*math.sin(t)], [-a*math.sin(t), b*math.cos(t)]
    elif kind == 'hyperbola':
        if branch not in ('positive_x', 'negative_x') or state['branch'] not in ('both', branch):
            raise ValueError('Point requires a fixed branch present on its hyperbola')
        a, b = state['a']*(1 if branch == 'positive_x' else -1), state['b']
        p, d = [a*math.cosh(t), b*math.sinh(t)], [a*math.sinh(t), b*math.cosh(t)]
    else:
        p0 = state['p']
        p, d = [p0*t*t, 2*p0*t], [2*p0*t, 2*p0]
    return np.array(p)+state['center'], np.array(d)


def conic_point(derive, definitions, parameters):
    if not isinstance(derive.get('curve'), str):
        raise ValueError('Conic curve must be an ID')
    state = conic_state(definitions.get(derive['curve'], {}))
    required = {'type', 'curve', 't'} | ({'branch'} if state['kind'] == 'hyperbola' else set())
    if set(derive) != required or derive['type'] != 'on_conic':
        raise ValueError('Invalid strict on_conic fields')
    t = finite_scalar(scalar_value(derive['t'], parameters))
    if abs(t) > (12 if state['kind'] == 'hyperbola' else 10000):
        raise ValueError('Conic t outside bounded numeric domain')
    return position_derivative(state, t, derive.get('branch'))


def conic_tangent(derive, definitions, parameters):
    if set(derive) != {'type', 'source', 'scale'} or not isinstance(derive['source'], str):
        raise ValueError('conic_tangent requires only type/source/scale')
    source = definitions.get(derive['source'], {})
    if source.get('type') != 'point' or source.get('derive', {}).get('type') != 'on_conic':
        raise ValueError('conic_tangent source must be an on_conic point')
    scale = finite_scalar(scalar_value(derive['scale'], parameters))
    if abs(scale) > 10000:
        raise ValueError('Conic tangent scale exceeds +/-10000')
    p, d = conic_point(source['derive'], definitions, parameters)
    return p + scale*d


def validate_conic_parameters(objects, parameters):
    defs = {o['id']: o for o in objects}
    for o in objects:
        if o['type'] == 'conic':
            conic_state(o)
        d = o.get('derive', {})
        if d.get('type') == 'on_conic':
            conic_point(d, defs, parameters)
        elif d.get('type') == 'conic_tangent':
            conic_tangent(d, defs, parameters)


def validate_conic_transition(objects, before, after):
    # Only t and tangent scale vary; both are affine. Endpoint bounds prove
    # whole-transition finite bounds, with no branch switching or poles.
    validate_conic_parameters(objects, before)
    validate_conic_parameters(objects, after)


def conic_paths(obj, bounds):
    """Analytically clip parameter intervals, then bounded-error chord sampling.

    Each chord error <= max||P''|| * dt**2/8. Separate visible intervals and
    branches never acquire a connecting chord. Rectangular convexity keeps
    all rendered points/segments within the viewport.
    """
    s = conic_state(obj)
    if len(bounds) != 4:
        raise ValueError('Conic bounds need four numbers')
    xmin, xmax, ymin, ymax = map(finite_scalar, bounds)
    if not xmin < xmax or not ymin < ymax or max(map(abs, bounds)) > 10000:
        raise ValueError('Invalid conic bounds')
    cx, cy = s['center']
    xx, yy = [xmin-cx, xmax-cx], [ymin-cy, ymax-cy]
    tol = obj.get('tolerance', .001)
    branches = ['positive_x', 'negative_x'] if s.get('branch') == 'both' else [s.get('branch')]
    paths, count = [], 0
    for branch in branches:
        roots = []
        if s['kind'] == 'ellipse':
            lo, hi = 0., 2*math.pi
            for x in xx:
                if abs(x/s['a']) <= 1:
                    t = math.acos(x/s['a']); roots += [t, 2*math.pi-t]
            for y in yy:
                if abs(y/s['b']) <= 1:
                    t = math.asin(y/s['b']); roots += [t % (2*math.pi), (math.pi-t) % (2*math.pi)]
            second = max(s['a'], s['b'])
        elif s['kind'] == 'hyperbola':
            lo, hi = math.asinh(yy[0]/s['b']), math.asinh(yy[1]/s['b'])
            sign = 1 if branch == 'positive_x' else -1
            for x in xx:
                if sign*x/s['a'] >= 1:
                    t = math.acosh(sign*x/s['a']); roots += [-t, t]
            second = None
        else:
            lo, hi = sorted(y/(2*s['p']) for y in yy)
            for x in xx:
                if x/s['p'] >= 0:
                    t = math.sqrt(x/s['p']); roots += [-t, t]
            second = 2*abs(s['p'])
        if lo >= hi:
            continue
        knots = sorted(set([lo, hi]+[t for t in roots if lo < t < hi]))
        current = None
        for a, b in zip(knots, knots[1:]):
            p, _ = position_derivative(s, (a+b)/2, branch)
            if not (xmin <= p[0] <= xmax and ymin <= p[1] <= ymax):
                current = None
                continue
            bound = second
            if bound is None:
                m = max(abs(a), abs(b))
                bound = math.hypot(s['a']*math.cosh(m), s['b']*math.sinh(m))
            n = max(1, math.ceil((b-a)*math.sqrt(bound/(8*tol))))
            count += n
            if count > 8192:
                raise ValueError('Conic sampling budget exceeded; relax tolerance or viewport')
            pts = [position_derivative(s, a+(b-a)*i/n, branch)[0] for i in range(n+1)]
            pts = [[min(xmax,max(xmin,float(p[0]))), min(ymax,max(ymin,float(p[1])))] for p in pts]
            if current is None:
                current = pts; paths.append(current)
            else:
                current.extend(pts[1:])
    return paths
