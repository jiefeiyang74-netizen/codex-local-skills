"""Numerical geometry, independent of renderer and question identity."""
import copy
import math
import numpy as np

EPS = 1e-10
CIRCLE_RADIUS_RTOL = 1e-9

def curved_region_geometry(obj, center, parameters=None):
    """World-space endpoints and area; degree input, positive CCW sweep."""
    if obj.get('type') not in ('sector', 'circular_segment'):
        raise ValueError('Expected sector or circular_segment')
    radius, start, sweep = (finite_scalar(scalar_value(obj.get(k), parameters or {})) if obj['type']=='sector' else obj.get(k) for k in ('radius','start_angle','sweep_angle'))
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (radius,start,sweep)):
        raise ValueError('Curved-region radius and angles must be finite numbers')
    if not 0 < radius <= 10000 or not (0 <= sweep <= 360 if obj['type']=='sector' else 0 < sweep < 360):
        raise ValueError('Curved region requires 0<radius<=10000; sector sweep 0..360, segment sweep strictly 0..360 degrees')
    c = vector(center)
    a, theta = math.radians(start % 360), math.radians(sweep)
    endpoints = [(c + radius*np.array([math.cos(t),math.sin(t)])).tolist() for t in (a,a+theta)]
    # Avoid catastrophic cancellation for very small positive segment sweeps.
    difference = (theta**3/6 * (1-theta**2/20+theta**4/840)) if theta < 1e-3 else theta-math.sin(theta)
    area = .5*radius*radius*(theta if obj['type']=='sector' else difference)
    return {'center':c.tolist(), 'radius':radius, 'start_radians':a, 'sweep_radians':theta,
            'arc_start':endpoints[0], 'arc_end':endpoints[1], 'area':area}

def circular_position(start, center, angle, fraction):
    """Rotate a point analytically; intermediate positions never use chords."""
    start, center = vector(start), vector(center)
    if isinstance(angle, (bool, np.bool_)) or not isinstance(angle, (int, float, np.integer, np.floating)) or not math.isfinite(angle) or not 0 < abs(angle) <= 8 * math.pi:
        raise ValueError('Circular angle must be finite, nonzero and at most 8*pi radians')
    if isinstance(fraction, (bool, np.bool_)) or not isinstance(fraction, (int, float, np.integer, np.floating)) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError('Circular progress must lie in [0, 1]')
    delta = start - center
    if not np.any(delta):
        raise ValueError('Circular start cannot equal its center')
    theta = float(angle) * float(fraction)
    cosine, sine = math.cos(theta), math.sin(theta)
    return vector(center + np.array([cosine * delta[0] - sine * delta[1],
                                    sine * delta[0] + cosine * delta[1]]))

def point_depends_on(objects, point, ancestor):
    """Return whether a point uses ancestor, including indirect derivations."""
    definitions = {o['id']: o for o in objects}
    visited = set()
    def visit(key):
        if key == ancestor:
            return True
        if key in visited:
            return False
        visited.add(key)
        obj = definitions.get(key, {})
        derive = obj.get('derive', {})
        refs = ([derive['source']] if 'source' in derive else [])
        refs += ([derive['center']] if derive.get('type') == 'rotate' else [])
        refs += derive.get('axis', []) + derive.get('line', [])
        refs += [ref for pair in derive.get('lines', []) for ref in pair]
        return any(visit(ref) for ref in refs)
    return visit(point)

def circle_motion_parameters(objects, overrides, point, circle, angle, parameters=None):
    """Validate a circular action against its current state and return its start."""
    definitions = {o['id']: o for o in objects}
    moving, path = definitions.get(point, {}), definitions.get(circle, {})
    if moving.get('type') != 'point' or 'xy' not in moving or 'derive' in moving:
        raise ValueError(f'Circular move requires a free point: {point}')
    if path.get('type') != 'circle':
        raise ValueError(f'Circular move requires a circle: {circle}')
    radius = path.get('radius')
    if type(radius) not in (int, float) or not math.isfinite(radius) or not 0 < radius <= 10000:
        raise ValueError('Circle radius must be finite, positive and at most 10000')
    center_key = path.get('center')
    if definitions.get(center_key, {}).get('type') != 'point':
        raise ValueError('Circle center must reference a point')
    if point_depends_on(objects, center_key, point):
        raise ValueError('Circle center cannot depend on its moving point')
    resolved = resolve_points(objects, overrides, parameters)
    start, center = resolved[point].copy(), resolved[center_key].copy()
    actual = math.hypot(*(start - center))
    if not math.isfinite(actual) or actual <= 0 or abs(actual - radius) > CIRCLE_RADIUS_RTOL * radius:
        raise ValueError(f'Circular move must start on circle: distance={actual}, radius={radius}')
    circular_position(start, center, angle, 0)
    return start, center

def cross(a, b):
    return float(a[0] * b[1] - a[1] * b[0])

def vector(value):
    a = np.asarray(value, dtype=float)
    if a.shape != (2,) or not np.isfinite(a).all():
        raise ValueError(f"Expected finite 2D coordinate: {value}")
    return a

def resolve_points(objects, overrides=None, parameters=None, *, lazy=False):
    definitions = {o['id']: o for o in objects}
    if len(definitions) != len(objects):
        raise ValueError('Duplicate geometry object id')
    overrides = overrides or {}
    class RequestedPoints(dict):
        def __missing__(self, key):
            return get(key)
    result, visiting = RequestedPoints() if lazy else {}, set()

    def get(key):
        if key in result:
            return result[key]
        if key in visiting:
            raise ValueError(f'Geometry dependency cycle at {key}')
        if key not in definitions or definitions[key]['type'] != 'point':
            raise ValueError(f'Unknown point: {key}')
        visiting.add(key)
        obj = definitions[key]
        if key in overrides:
            p = vector(overrides[key])
        elif 'xy' in obj:
            p = vector(obj['xy'])
        else:
            d = obj['derive']
            kind = d['type']
            if kind == 'on_conic':
                from .conic import conic_point
                p = conic_point(d, definitions, parameters or {})[0]
            elif kind == 'conic_tangent':
                from .conic import conic_tangent
                get(d['source'])
                p = conic_tangent(d, definitions, parameters or {})
            elif kind == 'on_reciprocal':
                from .reciprocal import reciprocal_point
                p = reciprocal_point(d, definitions, parameters or {})
            elif kind == 'on_quadratic':
                from .quadratic import quadratic_point
                p = quadratic_point(d, definitions, parameters or {})
            elif kind in ('reflect', 'project'):
                a, b = map(get, d['axis'] if kind == 'reflect' else d['line'])
                v = b - a
                if np.dot(v, v) <= EPS ** 2:
                    raise ValueError(f'Zero axis for {key}')
                src = get(d['source'])
                foot = a + v * np.dot(src - a, v) / np.dot(v, v)
                p = 2 * foot - src if kind == 'reflect' else foot
            elif kind == 'rotate':
                angle = rotation_angle(d, parameters or {})
                p = rotated_position(get(d['source']), get(d['center']), angle)
            elif kind == 'translate':
                p = get(d['source']) + vector(d['vector'])
            elif kind == 'intersect':
                (a, b), (c, e) = [list(map(get, pair)) for pair in d['lines']]
                v, w = b - a, e - c
                den = cross(v, w)
                if np.linalg.norm(v) <= EPS or np.linalg.norm(w) <= EPS:
                    raise ValueError(f'Zero intersection line for {key}')
                if abs(den) <= EPS * np.linalg.norm(v) * np.linalg.norm(w):
                    raise ValueError(f'Parallel/nonunique intersection for {key}')
                p = a + cross(c - a, w) / den * v
            else:
                raise ValueError(f'Unknown derivation: {kind}')
        result[key] = vector(p)
        visiting.remove(key)
        return result[key]

    if not lazy:
        for obj in objects:
            if obj['type'] == 'point':
                get(obj['id'])
    return result

def evaluate_checks(objects, actions, checks, parameters=None):
    from .quadratic import (quadratic_state, feature_state,
                            validate_quadratic_parameters, validate_quadratic_transition)
    from .reciprocal import validate_reciprocal_parameters, validate_reciprocal_transition
    objects = copy.deepcopy(objects)
    parameters = dict(parameters or {})
    overrides = {}
    defs = {o['id']: o for o in objects}
    from .developable import validate_surface_parameters
    validate_surface_parameters(objects, parameters)
    validate_quadratic_parameters(objects, parameters)
    validate_reciprocal_parameters(objects, parameters)
    for action in actions:
        if action['type'] == 'set_parameter':
            if action['parameter'] not in parameters:
                raise ValueError('Unknown parameter')
            updated = dict(parameters)
            updated[action['parameter']] = finite_scalar(action['value'])
            validate_quadratic_transition(objects, parameters, updated)
            validate_reciprocal_transition(objects, parameters, updated)
            validate_surface_parameters(objects, updated)
            parameters = updated
        if action['type'] == 'merge_intervals':
            validate_interval_merge(defs, action['sources'], action['target'], parameters)
        if action['type'] == 'constrain':
            key = action['point']
            if key not in defs or defs[key]['type'] != 'point':
                raise ValueError(f'Constraint requires point: {key}')
            defs[key].pop('xy', None)
            defs[key]['derive'] = copy.deepcopy(action['derive'])
            overrides.pop(key, None)
            resolve_points(objects, overrides, parameters)
        if action['type'] == 'move':
            for key, xy in action['positions'].items():
                if key not in defs or 'xy' not in defs[key]:
                    raise ValueError(f'Move requires free point: {key}')
                overrides[key] = vector(xy)
        if action['type'] == 'move_on_circle':
            start, center = circle_motion_parameters(objects, overrides, action['point'], action['circle'], action['angle'], parameters)
            overrides[action['point']] = circular_position(start, center, action['angle'], 1)
    p = resolve_points(objects, overrides, parameters)
    results = []
    def length(pair):
        return float(np.linalg.norm(p[pair[1]] - p[pair[0]]))
    for check in checks:
        kind, tol = check['type'], check.get('tolerance', 1e-7)
        if kind == 'quadratic_state':
            actual = quadratic_state(defs[check['curve']], parameters)
            values = {'vertex': actual['vertex'], 'roots': actual['roots'],
                      'y_intercept': actual['c'], 'coefficients': [actual['a'], actual['b'], actual['c']]}
            differences, matching_counts = [], True
            for name in ('vertex','roots','y_intercept','coefficients'):
                if name not in check:
                    continue
                observed, expected = values[name], check[name]
                if isinstance(expected, list):
                    matching_counts = matching_counts and len(observed)==len(expected)
                    if len(observed)==len(expected):
                        differences.extend(abs(a-b) for a,b in zip(observed,expected))
                else:
                    differences.append(abs(observed-expected))
            error = max(differences, default=0.) if matching_counts else None
            results.append({'type': kind, 'passed': bool(matching_counts and error<=tol),
                            'actual': actual, 'error': error, 'tolerance': tol, 'check': check})
            continue
        if kind == 'quadratic_point':
            feature = defs[check['feature']]
            state = feature_state(feature, defs[feature['curve']], parameters)
            if len(state['points']) != 1:
                raise ValueError('Quadratic point check needs exactly one point')
            actual = state['points'][0]
            error = max(abs(a-b) for a,b in zip(actual,check['value']))
            results.append({'type': kind, 'passed': bool(error<=tol), 'actual': actual,
                            'error': error, 'tolerance': tol, 'check': check})
            continue
        if kind.startswith('interval_'):
            if kind == 'interval_state':
                state = interval_state(defs[check['interval']], parameters)
                passed = state['empty'] == check['empty']
                for key in ('left', 'right', 'left_closed', 'right_closed'):
                    if key in check:
                        expected = scalar_value(check[key], parameters) if key in ('left','right') else check[key]
                        passed = passed and state[key] == expected
                actual = interval_receipt(state)
            elif kind == 'interval_subset':
                sub, sup = defs[check['subset']], defs[check['superset']]
                if sub['axis'] != sup['axis']: raise ValueError('Subset requires same axis')
                actual = interval_subset(interval_state(sub, parameters), interval_state(sup, parameters))
                passed = actual == check['expected']
            elif kind == 'interval_union':
                actual = interval_receipt(validate_interval_merge(defs, check['sources'], check['target'], parameters))
                passed = True
            else: raise ValueError('Unknown interval check')
            results.append({'type':kind,'passed':bool(passed),'actual':actual,'check':check})
            continue
        if kind == 'distance':
            actual = length(check['points']); error = abs(actual - check['value'])
        elif kind == 'path_length':
            actual = sum(length(pair) for pair in zip(check['points'], check['points'][1:]))
            error = abs(actual - check['value'])
        elif kind == 'equal_length':
            actual = [length(pair) for pair in check['segments']]
            error = max(actual) - min(actual)
        elif kind == 'perpendicular':
            u, v = [p[b] - p[a] for a, b in check['lines']]
            scale = np.linalg.norm(u) * np.linalg.norm(v)
            if scale <= EPS ** 2:
                raise ValueError('Perpendicular check has zero arm')
            actual = float(np.dot(u, v) / scale); error = abs(actual)
        elif kind in ('collinear', 'on_ray'):
            ids = check['points'] if kind == 'collinear' else [*check['ray'], check['point']]
            base = p[ids[0]]
            axis = p[ids[-1]] - base if kind == 'collinear' else p[ids[1]] - base
            size = np.linalg.norm(axis)
            if size <= EPS:
                raise ValueError(f'{kind} check has zero axis')
            projections = [float(np.dot(p[i] - base, axis) / size) for i in ids]
            actual = max(abs(cross(p[i] - base, axis)) / size for i in ids)
            error = actual
            if kind == 'on_ray':
                error = max(error, -projections[-1])
            elif check.get('ordered'):
                error = max([error] + [a - b for a, b in zip(projections, projections[1:])])
        else:
            raise ValueError(f'Unknown check: {kind}')
        results.append({'type': kind, 'passed': bool(error <= tol), 'actual': actual,
                        'error': float(error), 'tolerance': tol, 'check': check})
    return results


# Restricted scalar and real-interval algebra; no expression evaluation.
def finite_scalar(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Expected finite scalar (not bool)')
    return float(value)


def scalar_value(value, parameters):
    if isinstance(value, str):
        if value == '-inf': return -math.inf
        if value == '+inf': return math.inf
        raise ValueError('Unknown scalar string; expressions are not executable')
    if isinstance(value, dict):
        if set(value) != {'parameter','scale','offset'}:
            raise ValueError('Affine scalar requires only parameter/scale/offset')
        key = value['parameter']
        if not isinstance(key, str) or key not in parameters:
            raise ValueError('Unknown affine parameter')
        return finite_scalar(finite_scalar(value['scale']) * finite_scalar(parameters[key]) + finite_scalar(value['offset']))
    return finite_scalar(value)


def interval_state(obj, parameters):
    left, right = scalar_value(obj['left'], parameters), scalar_value(obj['right'], parameters)
    lc, rc = obj['left_closed'], obj['right_closed']
    if type(lc) is not bool or type(rc) is not bool:
        raise ValueError('Interval closure must be boolean')
    if left == math.inf or right == -math.inf:
        raise ValueError('Infinity on wrong interval side')
    if (not math.isfinite(left) and lc) or (not math.isfinite(right) and rc):
        raise ValueError('Infinity cannot be closed')
    return dict(left=left,right=right,left_closed=lc,right_closed=rc,
                empty=left > right or (left == right and not (lc and rc)))


def interval_receipt(state):
    return {k: ('-inf' if v == -math.inf else '+inf' if v == math.inf else v)
            for k,v in state.items()}


def interval_subset(sub, sup):
    if sub['empty']: return True
    if sup['empty']: return False
    left_ok = sub['left'] > sup['left'] or (sub['left'] == sup['left'] and (not sub['left_closed'] or sup['left_closed']))
    right_ok = sub['right'] < sup['right'] or (sub['right'] == sup['right'] and (not sub['right_closed'] or sup['right_closed']))
    return left_ok and right_ok


def interval_union(states):
    ordered = sorted((dict(s) for s in states if not s['empty']), key=lambda s:(s['left'],not s['left_closed']))
    if not ordered: return dict(left=0.,right=0.,left_closed=False,right_closed=False,empty=True)
    result = ordered[0]
    for following in ordered[1:]:
        if following['left'] > result['right'] or (following['left'] == result['right'] and not (result['right_closed'] or following['left_closed'])):
            raise ValueError('Union is disconnected; cannot draw a single interval')
        if following['left'] == result['left']:
            result['left_closed'] = result['left_closed'] or following['left_closed']
        if following['right'] > result['right']:
            result['right'],result['right_closed'] = following['right'],following['right_closed']
        elif following['right'] == result['right']:
            result['right_closed'] = result['right_closed'] or following['right_closed']
    return result


def validate_interval_merge(definitions, sources, target, parameters):
    if not isinstance(sources,list) or not 2 <= len(sources) <= 8 or len(set(sources)) != len(sources) or target in sources:
        raise ValueError('Merge requires distinct sources and target')
    items = [definitions[k] for k in [*sources,target]]
    if any(o['type'] != 'interval' for o in items) or len({o['axis'] for o in items}) != 1:
        raise ValueError('Merge requires intervals on the same axis')
    expected = interval_union([interval_state(o,parameters) for o in items[:-1]])
    actual = interval_state(items[-1],parameters)
    if not (expected['empty'] and actual['empty']) and expected != actual:
        raise ValueError('Merge target does not equal the actual union')
    return expected


def rotation_angle(derive, parameters):
    """Strict finite degree scalar; interval infinity strings are not angles."""
    if not isinstance(derive, dict) or set(derive) != {'type', 'source', 'center', 'angle'} or derive['type'] != 'rotate':
        raise ValueError('rotate requires only type/source/center/angle')
    if any(not isinstance(derive[k], str) for k in ('source', 'center')):
        raise ValueError('Rotation source and center must be point IDs')
    return finite_scalar(scalar_value(derive['angle'], parameters))


def rotated_position(source, center, angle):
    """Rigid rotation in degrees, positive counterclockwise, including zero radius."""
    angle = finite_scalar(angle)
    source, center = vector(source), vector(center)
    theta = math.radians(angle % 360)
    cosine, sine = math.cos(theta), math.sin(theta)
    delta = source - center
    return vector(center + np.array([cosine*delta[0]-sine*delta[1],
                                     sine*delta[0]+cosine*delta[1]]))


def validate_rotation_parameters(objects, parameters):
    for obj in objects:
        derive = obj.get('derive', {})
        if obj.get('type') == 'point' and derive.get('type') == 'rotate':
            rotation_angle(derive, parameters)
