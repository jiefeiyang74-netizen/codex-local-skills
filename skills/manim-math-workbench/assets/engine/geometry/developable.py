"""Restricted isometric lateral surfaces. Coordinates and measures are intrinsic.

The renderer projects a fixed material mesh; projected lengths are not measures.
"""
import math
import numpy as np
from .math2d import finite_scalar, scalar_value, curved_region_geometry

KINDS = ('cylinder_net', 'cone_net')


def surface_state(obj, parameters):
    kind = obj['type']
    if kind not in KINDS:
        raise ValueError('Expected a developable lateral surface')
    r = finite_scalar(obj['radius'])
    size = finite_scalar(obj['height' if kind == 'cylinder_net' else 'slant'])
    p = finite_scalar(scalar_value(obj['unfold'], parameters))
    if not (1e-6 <= r <= 10000 and 1e-6 <= size <= 10000 and 0 <= p <= 1):
        raise ValueError('Surface dimensions require 1e-6..10000 and unfold requires [0,1]')
    if kind == 'cone_net' and not size > r:
        raise ValueError('Right cone requires slant > radius > 0')
    display_scale = finite_scalar(obj.get('display_scale', 1))
    if not 1e-6 <= display_scale <= 10000:
        raise ValueError('display_scale requires a fixed finite number in [1e-6,10000]')
    state = dict(type=kind, radius=r, unfold=p, display_scale=display_scale, measurement_space='intrinsic/flattened')
    if kind == 'cylinder_net':
        state.update(height=size, width=2*math.pi*r, area=2*math.pi*r*size)
    else:
        state.update(slant=size, beta=r/size, sector_angle_degrees=360*r/size,
                     arc_length=2*math.pi*r, area=math.pi*r*size)
    return state


def surface_xyz(state, u, v):
    """Cylinder: u=s, v=z. Cone: u=theta, v=rho. Analytic p=1 limit."""
    p, r = state['unfold'], state['radius']
    if state['type'] == 'cylinder_net':
        k = (1-p)/r
        if p == 1:
            return np.array([u, v, 0.])
        # sinc and half-angle form avoid cancellation near the flat limit.
        return np.array([u*np.sinc(k*u/math.pi), v, -2*math.sin(k*u/2)**2/k])
    beta = state['beta']
    b = 1-(1-beta)*(1-p)**2
    return np.array([v*b*math.sin(u/b), -v*math.sqrt(max(0., (1-b)*(1+b))),
                     v*b*math.cos(u/b)])


def validate_surface_parameters(objects, parameters):
    for obj in objects:
        if obj['type'] in KINDS:
            surface_state(obj, parameters)
        elif obj['type'] in ('sector', 'circular_segment'):
            curved_region_geometry(obj, [0, 0], parameters)


def project_surface(state, xyz):
    """Rigid view rotation, then orthographic projection; final plane faces camera."""
    p = state['unfold']
    smooth = p*p*(3-2*p)
    if state['type'] == 'cylinder_net':
        angle = math.radians(25)*(1-smooth)
    else:
        angle = math.radians(20+70*smooth)
    x, y, z = xyz
    return np.array([x, math.cos(angle)*y+math.sin(angle)*z,
                     -math.sin(angle)*y+math.cos(angle)*z])


def build_surface(scene, obj):
    from manim import VGroup, Polygon, VMobject
    state = surface_state(obj, scene.parameter_values())
    r = state['radius']
    if state['type'] == 'cylinder_net':
        us = np.linspace(-math.pi*r, math.pi*r, 49)
        vs = np.linspace(-state['height']/2, state['height']/2, 9)
    else:
        us = np.linspace(-math.pi*state['beta'], math.pi*state['beta'], 49)
        vs = np.linspace(0, state['slant'], 9)
    # Material coordinates stay fixed throughout. No interpolation to a static net.
    grid = np.array([[project_surface(state, surface_xyz(state, u, v)) for u in us] for v in vs])
    offset = np.asarray(obj.get('position', [0, 0]))
    mapped = lambda q: scene.mapped(q[:2]*state['display_scale']+offset)
    color, width = obj.get('color', '#52C7EA'), obj.get('stroke_width', 2)
    tiles = []
    for j in range(len(vs)-1):
        for i in range(len(us)-1):
            corners = [grid[j,i], grid[j,i+1], grid[j+1,i+1], grid[j+1,i]]
            tiles.append((float(np.mean([q[2] for q in corners])),
                          Polygon(*[mapped(q) for q in corners], stroke_width=0,
                                  color=color, fill_opacity=obj.get('fill_opacity', .10))))
    result = VGroup(*[tile for _,tile in sorted(tiles, key=lambda t:t[0])])
    lines = []
    for j in range(len(vs)):
        lines.append((grid[j], j in (0, len(vs)-1)))
    for i in range(0, len(us), 4):
        lines.append((grid[:,i], i in (0, len(us)-1)))
    for line, boundary in sorted(lines, key=lambda item: float(np.mean(item[0][:,2]))):
        if np.linalg.norm(np.ptp(line, axis=0)) < 1e-12:
            continue
        result.add(VMobject(color=color, stroke_width=width if boundary else width*.55,
                            stroke_opacity=1 if boundary else .7).set_points_as_corners([mapped(q) for q in line]))
    return result
