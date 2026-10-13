"""geometry-1.0: tracker driven primitives and an absolute audio clock."""
import copy
import json
import os
from pathlib import Path
import numpy as np
from manim import (Scene, config, VGroup, VMobject, ValueTracker, Dot, Line, Circle, Sector,
                   DashedLine, Polygon, Arc, Text, RoundedRectangle, DashedVMobject, BackgroundRectangle,
                   FadeIn, FadeOut, Create, Indicate, Transform, TransformFromCopy, UpdateFromAlphaFunc,
                   linear, Animation)
from .math2d import (resolve_points, evaluate_checks, circular_position,
                     circle_motion_parameters, curved_region_geometry, EPS, interval_state, interval_receipt, validate_interval_merge)
from .schema import validate_production_budget, production_limits
from .developable import build_surface, surface_state, validate_surface_parameters
from .conic import conic_state, validate_conic_transition
from .conic_runtime import build_conic, build_arrow
from .reciprocal import build_reciprocal, validate_reciprocal_transition
from .quadratic import quadratic_state, validate_quadratic_transition
from .quadratic_runtime import build_axes, build_quadratic, build_feature

class MaskSafeIndicate(Indicate):
    """Pulse foreground geometry while keeping text masks fixed and opaque."""

    def create_target(self):
        target = super().create_target()
        # Indicate recursively colors/scales the whole family, including each
        # Text.background_rectangle. Restore those exact masks in the target so
        # interpolation never turns them into enlarged foreground-color blocks.
        for original, changed in zip(self.mobject.get_family(), target.get_family()):
            if isinstance(original, BackgroundRectangle):
                changed.become(original)
        return target


def text_motion_position(start, end, via, alpha):
    if via is None:
        return (1-alpha)*start + alpha*end
    waypoint = np.array([*via, 0.])
    return ((1-2*alpha)*start + 2*alpha*waypoint if alpha <= .5
            else (2-2*alpha)*waypoint + (2*alpha-1)*end)


class ReadableTextReplace(Animation):
    """Fade through zero without interpolating unrelated glyph contours.

    Keep the registered root object and its updater; only changed text uses
    exact old/new child families. Unchanged tokens use the normal move path.
    """
    def __init__(self, mobject, target, via=None, **kwargs):
        self.via = via
        self.target_text = target.copy()
        super().__init__(mobject, suspend_mobject_updating=True, **kwargs)

    def begin(self):
        # Cairo captures a flat moving-family list after begin. Keep both exact
        # child families stable for the whole play; replacing children per
        # frame would leave the captured old glyphs painting ghost text.
        self.old_text = self.mobject.copy()
        self.new_text = self.target_text.copy()
        self.start_center = self.old_text.get_center().copy()
        self.end_center = self.new_text.get_center().copy()
        self.mobject.set_points(np.empty((0, 3)))
        self.mobject.set_submobjects([self.old_text, self.new_text])
        super().begin()

    def interpolate_mobject(self, alpha):
        center = text_motion_position(self.start_center, self.end_center, self.via, alpha)
        self.old_text.move_to(center).set_opacity(max(0, 1-2*alpha))
        self.new_text.move_to(center).set_opacity(max(0, 2*alpha-1))


class GeometryScene(Scene):
    spec = None

    def __init__(self, *args, **kwargs):
        canvas = (self.spec or {}).get('canvas', {})
        width, height = canvas.get('width', 1920), canvas.get('height', 1080)
        config.frame_height = 9 if width >= height else 16
        config.frame_width = config.frame_height * width / height
        config.background_color = '#000000'
        # canvas determines camera aspect only. CLI/pipeline owns output quality.
        encoder = getattr(self, '_native_encoder', None)
        if encoder:
            from manim.renderer.cairo_renderer import CairoRenderer
            from .native_encoder import native_writer
            if args or 'renderer' in kwargs:
                raise ValueError('Explicit native encoder owns renderer')
            # Create the camera AFTER applying native canvas aspect.
            kwargs['renderer'] = CairoRenderer(file_writer_class=native_writer(
                self._native_ffmpeg, encoder['ffmpeg_sha256']))
        super().__init__(*args, **kwargs)

    def construct(self):
        if not isinstance(self.spec, dict):
            raise ValueError('GeometryScene.spec must be geometry-1.0 dict')
        validate_production_budget(self.spec)
        self.long_lesson = self.spec.get('production_profile', 'standard') == 'long_lesson'
        self.events, self.snapshots = [], []
        self._snapshot_spool = None
        if self.long_lesson:
            self._snapshot_spool = self._report_path().with_suffix('.snapshots.jsonl')
            self._snapshot_spool.parent.mkdir(parents=True, exist_ok=True)
            self._snapshot_spool.write_text('', encoding='utf-8')
        self.text_cache = {}
        self.transient = {}
        self._points_signature = None
        self._points_cache = {}
        self.runtime_stats = {'point_resolutions': 0, 'geometry_rebuilds': 0,
                              'focus_rebuilds': 0, 'frozen_waits': 0}
        self.live, self.mobs, self.trackers = set(), {}, {}
        self.focus_box = None
        self.formulas = VGroup()
        self.board = VGroup()
        landscape = config.frame_width >= config.frame_height
        chapter_heading = self.spec.get('heading_mode', 'standard') == 'chapter'
        initial_heading = self.spec['chapters'][0]['title'] if chapter_heading else self.spec.get('title', '数学解题可视化')
        self.title = self.text(initial_heading, 36, '#FFD166').move_to([0, 3.9 if landscape else 7.2, 0])
        self._validate_clock()
        try:
            for index, chapter in enumerate(self.spec['chapters']):
                self.until(chapter['start'])
                old = VGroup(*[self.mobs[k] for k in self.live], self.board, self.formulas)
                heading_changed = chapter_heading and index > 0 and chapter['title'] != self.spec['chapters'][index-1]['title']
                if heading_changed:
                    old.add(self.title)
                    self.title = self.text(chapter['title'], 36, '#FFD166').move_to([0, 3.9 if landscape else 7.2, 0])
                if self.focus_box is not None:
                    old.add(self.focus_box)
                for mob in old.get_family():
                    mob.clear_updaters()
                if self.long_lesson and index:
                    # Cache only the current chapter; old rendered objects remain
                    # alive until their existing transition completes.
                    self.text_cache.clear()
                    self._points_signature = None
                    self._points_cache = {}
                self.chapter = chapter
                self.active_objects = copy.deepcopy(chapter['objects'])
                self.bounds = chapter['world_bounds']
                xmin, xmax, ymin, ymax = self.bounds
                if xmax <= xmin or ymax <= ymin:
                    raise ValueError('world_bounds must have positive area')
                self.plot_rect = chapter.get('plot_rect', [-2.45, -.35, 9.5, 5.8] if landscape else [0, .35, 10.4, 6.9])
                self.formula_rect = chapter.get('formula_rect', [5.05, -.45, 4.5, 4.6] if landscape else [0, -5.1, 10.5, 2.4])
                self.scale = min(self.plot_rect[2] / (xmax - xmin), self.plot_rect[3] / (ymax - ymin))
                self.center = np.array([(xmin + xmax) / 2, (ymin + ymax) / 2])
                self.defs = {o['id']: o for o in self.active_objects}
                self.trackers = {o['id']: [ValueTracker(v) for v in o['xy']]
                                 for o in chapter['objects'] if o['type'] == 'point' and 'xy' in o}
                self.parameters = {k: ValueTracker(v) for k,v in chapter.get('parameters', {}).items()}
                self.merge_locked = set()
                self.live, self.mobs = set(), {}
                self.label_offsets = {}
                self.focus_box = None
                self.formulas = VGroup()
                self.board = VGroup(self.text(chapter['title'], 28, max_width=9.5).move_to([-2.45, 3.1, 0] if landscape else [0, 6.3, 0]))
                if chapter_heading:
                    self.board = VGroup()
                for n, phrase in enumerate(chapter.get('problem', [])[:2]):
                    self.board.add(self.text(phrase, 26, max_width=4.4 if landscape else 10.5).move_to([5.05, 2.7 - .5 * n, 0] if landscape else [0, 5.3 - .6 * n, 0]))
                for key in self.defs:
                    mob = self.build(key)
                    mob._geometry_signature = self.geometry_signature(key)
                    mob.add_updater(lambda m, dt, key=key: self.update_geometry(m, key))
                    self.mobs[key] = mob
                first_at = chapter['actions'][0]['at'] if chapter['actions'] else chapter['end']
                if index:
                    self.play_to(chapter['start'] + .25, FadeOut(old))
                    for mob in old.get_family():
                        mob.clear_updaters()
                    heading_anims = [FadeIn(self.title)] if heading_changed else []
                    self.play_to(chapter['start'] + .5, FadeIn(self.board), *heading_anims)
                    self.record('chapter_transition', chapter['start'], chapter['start'], [], self.time)
                elif first_at >= .5:
                    self.play_to(chapter['start'] + .5, FadeIn(self.title), FadeIn(self.board))
                else:
                    # First action shares the opening animation's duration.
                    self.opening = [FadeIn(self.title), FadeIn(self.board)]
                for action in chapter['actions']:
                    self.until(action['at'])
                    self.perform(action)
                    self.snapshot('action_end')
                self.until(chapter['end'])
                self.snapshot('chapter_end')
                checks = evaluate_checks(chapter['objects'], chapter['actions'], chapter.get('checks', []), chapter.get('parameters', {}))
                self.snapshots[-1]['checks'] = checks
                if any(not c['passed'] for c in checks):
                    raise ValueError(f"Geometry checks failed: {chapter['id']}: {checks}")
                if self.long_lesson:
                    self._flush_snapshot_spool()
                # Only the preceding transition VGroup is retained, never all chapters.
                old = None
            self.until(self.spec['audio_duration'])
        finally:
            self.write_report()

    def _validate_clock(self):
        validate_production_budget(self.spec)
        previous = 0
        for index, ch in enumerate(self.spec['chapters']):
            if ch['start'] < previous or ch['end'] > self.spec['audio_duration']:
                raise ValueError(f"Chapter clock conflict: {ch['id']}")
            end = ch['start'] + (.5 if index else 0)
            for a in ch['actions']:
                if a['duration'] <= 0 or a['at'] < end - 1e-8 or a['at'] + a['duration'] > ch['end'] + 1e-8:
                    raise ValueError(f"Action budget conflict: {ch['id']} {a}; earliest={end}")
                end = a['at'] + a['duration']
            previous = ch['end']

    def until(self, at):
        delta = round(at * config.frame_rate) / config.frame_rate - self.time
        if delta < -1 / config.frame_rate - 1e-7:
            raise ValueError(f'Absolute audio clock overrun: requested={at}, actual={self.time}')
        if delta > 1e-7:
            self.runtime_stats['frozen_waits'] += 1
            self.wait(max(1e-9, delta - 1e-9), frozen_frame=True)

    def play_to(self, at, *animations):
        budget = round(at * config.frame_rate) / config.frame_rate - self.time
        if budget < .5 / config.frame_rate:
            raise ValueError(f'Animation has no frame budget: target={at}, actual={self.time}')
        # Preserve each animation's own easing (notably Indicate's return phase).
        self.play(*animations, run_time=budget - 1e-9)

    def text(self, value, size=28, color='#FFFFFF', max_width=10.5, accent=None):
        key = (str(value), size, color, max_width, accent)
        if key in self.text_cache:
            return self.text_cache[key].copy()
        mob = Text(str(value), font='Microsoft YaHei', font_size=size, color=color,
                   t2c={accent: '#FF4C4C'} if accent else {})
        if mob.width > max_width:
            mob.scale(max_width / mob.width)
        self.text_cache[key] = mob.copy()
        return mob

    def points(self):
        signature = (id(self.active_objects), tuple(sorted(self.parameter_values().items())),
                     tuple((k, tuple(float(v.get_value()) for v in ts)) for k, ts in self.trackers.items()),
                     tuple((k, tuple(begin), tuple(end), float(tracker.get_value()))
                           for k, (begin, end, tracker) in self.transient.items()))
        if signature == self._points_signature:
            return self._points_cache
        overrides = {k: [v.get_value() for v in ts] for k, ts in self.trackers.items()}
        for key, (begin, end, tracker) in self.transient.items():
            overrides[key] = begin + (end - begin) * tracker.get_value()
        # A copy's temporary point is not yet its mathematical destination.
        # Resolve only requested dependencies during that interpolation: an
        # unseen future intersection may be undefined at the starting frame.
        # Requested visible dependencies still fail normally; endpoints retain
        # the default eager validation once transient state is cleared.
        result = resolve_points(self.active_objects, overrides, self.parameter_values(),
                                lazy=bool(self.transient))
        self._points_cache, self._points_signature = result, signature
        self.runtime_stats['point_resolutions'] += 1
        return result

    def geometry_signature(self, key):
        obj, p = self.defs[key], self.points()
        kind = obj['type']
        if kind in ('cylinder_net','cone_net','sector'):
            center = tuple(p[obj['center']]) if kind == 'sector' else ()
            return (center, tuple(sorted(self.parameter_values().items())))
        if kind == 'conic':
            return tuple(self.bounds)
        if kind in ('quadratic', 'quadratic_feature', 'reciprocal'):
            return tuple(sorted(self.parameter_values().items()))
        if kind == 'interval':
            axis = self.defs[obj['axis']]
            state = interval_state(obj, self.parameter_values())
            return (tuple(p[axis['start']]), tuple(p[axis['end']]), tuple(state.items()), obj.get('lane', 0))
        if kind == 'number_line':
            refs = [obj['start'], obj['end']]
        elif kind == 'point':
            refs = [key]
        elif kind == 'line':
            refs = [obj['a'], obj['b']]
        elif kind == 'polygon':
            refs = obj['points']
        elif kind in ('circle','sector','circular_segment'):
            refs = [obj['center']]
        elif kind == 'ticks':
            segment = self.defs[obj['segment']]
            refs = [segment['a'], segment['b']]
        elif kind in ('angle', 'right_angle'):
            refs = [obj['vertex'], obj['arm1'], obj['arm2']]
        else:
            refs = []
        return tuple(tuple(p[k]) for k in refs)

    def update_geometry(self, mob, key):
        # Manim's animation reference copies must retain their own faded/shifted
        # state, rather than being rebuilt as full-opacity geometry each frame.
        if self.mobs.get(key) is not mob or key in self.merge_locked:
            return
        signature = self.geometry_signature(key)
        if signature != mob._geometry_signature:
            fresh = self.build(key)
            if (self.defs[key]['type'] in ('interval', 'quadratic', 'quadratic_feature', 'reciprocal', 'conic', 'sector', 'cylinder_net', 'cone_net') or self.defs[key].get('arrow',False)):
                # Exact child replacement prevents stale caps at empty/singleton transitions.
                mob.set_submobjects(list(fresh.submobjects))
                if self.defs[key]['type'] == 'interval':
                    mob._interval_info = fresh._interval_info
            else:
                mob.become(fresh)
            mob._geometry_signature = signature
            self.runtime_stats['geometry_rebuilds'] += 1

    def mapped(self, p):
        xy = (np.asarray(p) - self.center) * self.scale + self.plot_rect[:2]
        return np.array([*xy, 0.])

    def clipped(self, a, b, kind):
        v = b - a
        if np.linalg.norm(v) <= EPS:
            if kind == 'segment':
                return None
            raise ValueError('Zero length line')
        lo, hi = (0., 1.) if kind == 'segment' else ((0., np.inf) if kind == 'ray' else (-np.inf, np.inf))
        for i, (mn, mx) in enumerate([(self.bounds[0], self.bounds[1]), (self.bounds[2], self.bounds[3])]):
            if abs(v[i]) <= EPS:
                if a[i] < mn or a[i] > mx:
                    return None
            else:
                x, y = sorted(((mn - a[i]) / v[i], (mx - a[i]) / v[i]))
                lo, hi = max(lo, x), min(hi, y)
        return None if lo > hi else (a + lo * v, a + hi * v)

    def build(self, key):
        o, p = self.defs[key], self.points()
        kind, color = o['type'], o.get('color', '#FFFFFF')
        mp = lambda k: self.mapped(p[k])
        if kind in ('cylinder_net','cone_net'):
            return build_surface(self, o)
        if kind == 'coordinate_axes':
            return build_axes(self, o)
        if kind == 'conic':
            return build_conic(self, o)
        if kind == 'reciprocal':
            return build_reciprocal(self, o)
        if kind == 'quadratic':
            return build_quadratic(self, o)
        if kind == 'quadratic_feature':
            return build_feature(self, o)
        if kind == 'number_line':
            return self.build_number_line(o)
        if kind == 'interval':
            return self.build_interval(o)
        if kind == 'point':
            dot = Dot(mp(key), radius=.055, color=color)
            group = VGroup(dot)
            if o.get('label'):
                label = self.text(o['label'], o.get('font_size', 28), color)
                default_offset = [.23, .25]
                if 'label_offset' not in o and key not in self.label_offsets:
                    segments = [(mp(line['a']), mp(line['b'])) for line in self.defs.values() if line['type'] == 'line']
                    def clearance(offset):
                        c = dot.get_center() + np.array([*offset, 0])
                        distances = []
                        for a, b in segments:
                            v = b-a
                            t = np.clip(np.dot(c-a,v)/max(EPS,np.dot(v,v)),0,1)
                            distances.append(np.linalg.norm(c-a-t*v))
                        return min(distances, default=1)
                    default_offset = max(([x,y] for x,y in [(.26,.3),(-.26,.3),(.26,-.3),(-.26,-.3)]), key=clearance)
                    self.label_offsets[key] = default_offset
                offset = np.array([*o.get('label_offset', self.label_offsets.get(key, default_offset)), 0.])
                label.move_to(dot.get_center() + offset)
                # Moving labels can cross circles/segments even when labels do
                # not overlap one another. Mask only the tight text rectangle.
                label.set_z_index(10)
                label.add_background_rectangle(color=config.background_color, opacity=1, buff=.04)
                label.background_rectangle.set_z_index(9)
                group.add(label)
            return group
        if kind == 'line':
            pair = self.clipped(p[o['a']], p[o['b']], o.get('kind', 'segment'))
            if o.get('arrow', False):
                return build_arrow(self, o, pair)
            if pair is None:
                return VGroup()
            cls = DashedLine if o.get('dashed') else Line
            return cls(*map(self.mapped, pair), color=color, stroke_width=o.get('stroke_width', 3))
        if kind == 'polygon':
            return Polygon(*[mp(k) for k in o['points']], color=color, stroke_width=3, fill_opacity=o.get('fill_opacity', .08))
        if kind in ('sector','circular_segment'):
            state = curved_region_geometry(o, p[o['center']], self.parameter_values())
            if kind == 'sector' and state['sweep_radians'] == 0:
                return VGroup()
            kwargs = dict(start_angle=state['start_radians'], angle=state['sweep_radians'],
                          arc_center=mp(o['center']), color=color,
                          stroke_width=o.get('stroke_width',3), fill_opacity=o.get('fill_opacity',.35))
            if kind == 'sector':
                if state['sweep_radians'] == 2*np.pi:
                    region = Circle(radius=state['radius']*self.scale, color=color, stroke_width=o.get('stroke_width',3), fill_opacity=o.get('fill_opacity',.35)).move_to(mp(o['center']))
                else:
                    region = Sector(radius=state['radius']*self.scale, **kwargs)
            else:
                region = Arc(radius=o['radius']*self.scale, **kwargs)
                region.close_path()  # True curved arc plus the straight endpoint chord.
            if o.get('dashed'):
                outline = DashedVMobject(region.copy().set_fill(opacity=0), num_dashes=64)
                return VGroup(region.set_stroke(opacity=0), outline) if o.get('fill_opacity',.35) else VGroup(outline)
            return VGroup(region) if kind == 'sector' else region
        if kind == 'circle':
            circle = Circle(radius=o['radius'] * self.scale, color=color,
                            stroke_width=o.get('stroke_width', 3),
                            fill_opacity=o.get('fill_opacity', 0)).move_to(mp(o['center']))
            if o.get('dashed'):
                # Keep the fill as a complete disk, not a set of filled dash arcs.
                outline = DashedVMobject(circle.copy().set_fill(opacity=0), num_dashes=64)
                return VGroup(circle.set_stroke(opacity=0), outline) if o.get('fill_opacity', 0) else outline
            return circle
        if kind == 'ticks':
            seg = self.defs[o['segment']]
            a, b = mp(seg['a']), mp(seg['b'])
            u = b - a
            if np.linalg.norm(u) <= EPS:
                return VGroup()
            u /= np.linalg.norm(u); v = np.array([-u[1], u[0], 0])
            group = VGroup()
            for i in range(o.get('count', 1)):
                c = (a + b) / 2 + u * (i - (o.get('count', 1) - 1) / 2) * .12
                group.add(Line(c - v * .09, c + v * .09, color=color, stroke_width=3))
            return group
        if kind in ('right_angle', 'angle'):
            c = mp(o['vertex']); u, v = mp(o['arm1']) - c, mp(o['arm2']) - c
            if min(np.linalg.norm(u), np.linalg.norm(v)) <= EPS:
                # A hidden marker has no angle at a collapsed endpoint. Keep
                # its updater so a later nondegenerate geometry rebuilds it.
                if key not in self.live:
                    return VGroup()
                raise ValueError(f'Zero angle arm: {key}')
            u /= np.linalg.norm(u); v /= np.linalg.norm(v)
            if kind == 'right_angle':
                s = o.get('size', .18) * self.scale
                return VMobject(color=color, stroke_width=3).set_points_as_corners([c + s * u, c + s * (u + v), c + s * v])
            start = np.arctan2(u[1], u[0]); sweep = (np.arctan2(v[1], v[0]) - start + np.pi) % (2 * np.pi) - np.pi
            radius = o.get('radius', .45) * self.scale
            arc = Arc(radius=radius, start_angle=start, angle=sweep, arc_center=c, color=color, stroke_width=3)
            group = VGroup(arc)
            if o.get('label'):
                direction = np.array([np.cos(start + sweep / 2), np.sin(start + sweep / 2), 0])
                group.add(self.text(o['label'], 27, color).move_to(c + direction * (radius + .3)))
            return group
        if kind == 'text':
            return self.text(o['text'], o.get('font_size', 28), color, o.get('max_width', 9)).move_to([*o['position'], 0])
        raise ValueError(f'Unsupported geometry object: {kind}')

    def get_moving_and_static_mobjects(self, animations):
        moving, static = super().get_moving_and_static_mobjects(animations)
        # Cairo freezes a flattened family list before interpolation. Interval
        # children are replaced atomically; retain only their live root so that
        # the camera traverses its current children, not detached old caps.
        stale = set()
        for key, mob in getattr(self, 'mobs', {}).items():
            if (self.defs[key]['type'] in ('interval', 'quadratic', 'quadratic_feature', 'reciprocal', 'conic', 'sector', 'cylinder_net', 'cone_net') or self.defs[key].get('arrow',False)) and mob in moving:
                stale.update(mob.get_family()[1:])
        return [m for m in moving if m not in stale], static

    def parameter_values(self):
        return {k: float(t.get_value()) for k,t in self.parameters.items()}

    def axis_position(self, axis, value, lane=0):
        p = self.points()
        lo, hi = axis['range']
        a, b = p[axis['start']], p[axis['end']]
        return self.mapped(a + (b-a) * ((value-lo)/(hi-lo)) + np.array([0., lane]))

    def continuation(self, point, direction, color):
        # Arrowhead at a clipped continuation, never a fabricated finite endpoint.
        return VMobject(color=color, stroke_width=3).set_points_as_corners([
            point + np.array([-direction*.14,.09,0]), point,
            point + np.array([-direction*.14,-.09,0])])

    def build_number_line(self, o):
        lo, hi = o['range']; color=o.get('color','#AAB2BF')
        a,b=self.axis_position(o,lo), self.axis_position(o,hi)
        g=VGroup(Line(a,b,color=color,stroke_width=2), self.continuation(b,1,color))
        for value in o.get('ticks',[]):
            c=self.axis_position(o,value)
            g.add(Line(c+[0,-.06,0],c+[0,.06,0],color=color,stroke_width=2))
            g.add(self.text(f'{value:g}',o.get('font_size',22),color).move_to(c+[0,-.25,0]))
        g.add(self.text(o['variable'],o.get('font_size',22),color).move_to(b+[-.06,.25,0]))
        return g

    def build_interval(self, o):
        state=interval_state(o,self.parameter_values()); axis=self.defs[o['axis']]
        lo,hi=axis['range']; lane=o.get('lane',0); color=o.get('color','#FFD166')
        g=VGroup(); info=interval_receipt(state)
        info.update(endpoint_markers=[],continuations=[],segment_count=0)
        g._interval_info=info
        pos=lambda v:self.axis_position(axis,v,lane)
        if state['empty']:
            if o.get('empty_label'):
                g.add(self.text(o['empty_label'],28,color).move_to(pos((lo+hi)/2)))
            return g
        l,r=state['left'],state['right']; left,right=max(l,lo),min(r,hi)
        if left>right:
            return g
        if left<right:
            g.add(Line(pos(left),pos(right),color=color,stroke_width=o.get('stroke_width',5)))
            info['segment_count']=1
        radius=min(.075,max(.012,np.linalg.norm(pos(right)-pos(left))/4)) if l!=r else .075
        for value,closed,side in [(l,state['left_closed'],'left'),(r,state['right_closed'],'right')]:
            if not lo<=value<=hi or (l==r and side=='right'):
                continue
            marker=(Dot(pos(value),radius=radius,color=color) if closed else
                    Circle(radius=radius,color=color,stroke_width=2.5,fill_color=config.background_color,fill_opacity=1).move_to(pos(value)))
            g.add(marker);info['endpoint_markers'].append({'side':side,'value':value,'closed':closed})
        if l<lo:
            g.add(self.continuation(pos(lo),-1,color));info['continuations'].append('left')
        if r>hi:
            g.add(self.continuation(pos(hi),1,color));info['continuations'].append('right')
        if o.get('label'):
            g.add(self.text(o['label'],25,color).move_to(pos(lo)+[.25,.24,0]))
        return g

    def _make_focus_box(self, selected):
        def box():
            group = VGroup(*selected)
            return DashedVMobject(RoundedRectangle(width=max(.3, group.width + .16), height=max(.3, group.height + .4), corner_radius=.15, color='#FF5252', stroke_width=2).move_to(group), num_dashes=36)
        def signature():
            return tuple((tuple(m.get_center()), float(m.width), float(m.height)) for m in selected)
        result = box()
        result._focus_selected = selected
        result._selection_signature = signature()
        def update_box(m):
            if m is not self.focus_box:
                return
            current = signature()
            if current != m._selection_signature:
                m.become(box())
                m._selection_signature = current
                self.runtime_stats['focus_rebuilds'] += 1
        result.add_updater(update_box)
        return result

    def perform(self, a):
        for mob in self.mobs.values():
            mob.update(0)
        kind, ids = a['type'], a.get('ids', [])
        animations = getattr(self, 'opening', [])
        self.opening = []
        cleanup = []
        transient_cleanup = []
        text_cleanup = []
        focus_restore = None
        hidden_focus = None
        retained_focus = None
        motion_end = a['at'] + a['duration']
        start = self.time
        visible_onset = start
        if kind in ('reveal', 'hide'):
            if kind == 'hide' and self.focus_box is not None:
                hidden_mobs = [self.mobs[key] for key in ids if key in self.live]
                remaining = [mob for mob in self.focus_box._focus_selected if mob not in hidden_mobs]
                if len(remaining) < len(self.focus_box._focus_selected):
                    # Freeze the current bbox and fade with its departing targets.
                    # Do not leave an empty frame or rebuild it from hidden glyphs.
                    hidden_focus = self.focus_box
                    hidden_focus.clear_updaters()
                    if remaining:
                        replacement = GeometryScene._make_focus_box(self, remaining)
                        animations.append(Transform(hidden_focus, replacement))
                        retained_focus = (hidden_focus, replacement)
                        hidden_focus = None
                    else:
                        self.focus_box = None
                        animations.append(FadeOut(hidden_focus))
            for key in ids:
                if kind == 'reveal' and key not in self.live:
                    mob = self.mobs[key]
                    if self.defs[key]['type'] in ('angle', 'right_angle'):
                        self.live.add(key)
                        # Validate even when a hidden empty marker's signature
                        # has not changed; never reveal an undefined angle.
                        self.build(key)
                    animations.append(Create(mob) if a.get('style') == 'draw' and self.defs[key]['type'] in ('line', 'polygon', 'circle', 'quadratic', 'reciprocal', 'sector', 'circular_segment', 'conic') else FadeIn(mob))
                    self.live.add(key)
                elif kind == 'hide' and key in self.live:
                    animations.append(FadeOut(self.mobs[key])); self.live.remove(key)
        elif kind == 'text_transform':
            changed = any(item.get('text', self.defs[item['id']]['text']) != self.defs[item['id']]['text']
                          or not np.allclose(self.mobs[item['id']].get_center(), [*item['position'], 0])
                          or ('via' in item and not np.allclose(self.mobs[item['id']].get_center(), [*item['via'], 0]))
                          for item in a['items'])
            if self.focus_box is not None and changed:
                # Freeze/fade before any glyph moves. Rebuild only after exact
                # text cleanup, never from ReadableTextReplace's two families.
                end_frame = round(motion_end * config.frame_rate)
                frames = end_frame - round(self.time * config.frame_rate)
                if frames < 3:
                    raise ValueError('Focused text transition needs at least three frames')
                fade_frames = min(max(1, round(frames * .15)), frames // 3)
                old = self.focus_box
                focus_restore = old._focus_selected
                old.clear_updaters()
                self.focus_box = None
                self.play_to((round(self.time * config.frame_rate) + fade_frames) / config.frame_rate,
                             *animations, FadeOut(old))
                animations = []
                self.remove(old)
                old.set_opacity(0)
                motion_end = (end_frame - fade_frames) / config.frame_rate
            ids = [item['id'] for item in a['items']]
            for item in a['items']:
                key = item['id']
                if key not in self.live or self.defs[key]['type'] != 'text':
                    raise ValueError('text_transform requires visible text')
                obj, mob = self.defs[key], self.mobs[key]
                position = [*item['position'], 0]
                if item.get('text', obj['text']) == obj['text']:
                    if 'via' in item:
                        begin = mob.get_center().copy()
                        end = np.array(position)
                        via = item['via']
                        animations.append(UpdateFromAlphaFunc(mob,
                            lambda m, alpha, begin=begin, end=end, via=via:
                                m.move_to(text_motion_position(begin, end, via, alpha)),
                            rate_func=linear))
                    else:
                        animations.append(mob.animate(rate_func=linear).move_to(position))
                    target = None
                else:
                    target = self.text(item['text'], obj.get('font_size', 28), obj.get('color', '#FFFFFF'), obj.get('max_width', 9)).move_to(position)
                    animations.append(ReadableTextReplace(mob, target, via=item.get('via'), rate_func=linear))
                text_cleanup.append((key, item, target))
        elif kind == 'set_parameter':
            before = self.parameter_values()
            after = {**before, a['parameter']: a['value']}
            validate_surface_parameters(self.active_objects, before)
            validate_surface_parameters(self.active_objects, after)
            validate_conic_transition(self.active_objects, before, after)
            validate_quadratic_transition(self.active_objects, before, after)
            validate_reciprocal_transition(self.active_objects, before, after)
            from .math2d import validate_rotation_parameters
            validate_rotation_parameters(self.active_objects, before)
            validate_rotation_parameters(self.active_objects, after)
            tracker=self.parameters[a['parameter']]
            animations.append(tracker.animate(rate_func=linear).set_value(a['value']))
        elif kind == 'merge_intervals':
            sources,target=a['sources'],a['target']
            validate_interval_merge(self.defs,sources,target,self.parameter_values())
            if target in self.live or any(k not in self.live for k in sources):
                raise ValueError('merge requires visible sources and hidden target')
            labels=[child for k in sources for child in self.mobs[k].get_family()
                    if isinstance(child,Text)]
            if labels:
                boundaries=[round(v*config.frame_rate) for v in
                            (self.time,a['at']+a['duration']*.15,
                             a['at']+a['duration']*.8,a['at']+a['duration'])]
                if any(y-x<2 for x,y in zip(boundaries,boundaries[1:])):
                    raise ValueError('Labeled merge requires at least two frames per phase')
            self.merge_locked.update(sources)
            if labels:
                # Animate opacity in place. FadeOut(child) would split Scene roots.
                self.play_to(a['at']+a['duration']*.15,
                             *animations,*[child.animate.set_opacity(0) for child in labels])
                animations=[]
            lane=self.defs[target].get('lane',0)
            animations.extend(self.mobs[k].animate(rate_func=linear).shift(
                [0,(lane-self.defs[k].get('lane',0))*self.scale,0]) for k in sources)
            self.play_to(a['at']+a['duration']*.8,*animations)
            self.play_to(a['at']+a['duration'],
                         *[FadeOut(self.mobs[k]) for k in sources],FadeIn(self.mobs[target]))
            for k in sources:
                self.remove(self.mobs[k]);self.live.remove(k)
                fresh=self.build(k)
                self.mobs[k].set_submobjects(list(fresh.submobjects))
                self.mobs[k]._interval_info=fresh._interval_info
                self.mobs[k]._geometry_signature=self.geometry_signature(k)
            self.merge_locked.difference_update(sources);self.live.add(target)
            self.record(kind,a['at'],start,[*sources,target],self.time)
            return
        elif kind == 'move':
            ids = list(a['positions'])
            for key, xy in a['positions'].items():
                if key not in self.trackers:
                    raise ValueError(f'Move requires free point: {key}')
                animations.extend(t.animate.set_value(v) for t, v in zip(self.trackers[key], xy))
        elif kind == 'move_on_circle':
            key = a['point']
            overrides = {k: [t.get_value() for t in ts] for k, ts in self.trackers.items()}
            begin, center = circle_motion_parameters(self.active_objects, overrides,
                                                     key, a['circle'], a['angle'], self.parameter_values())
            ids = [key]
            progress = ValueTracker(0)
            def rotate_point(_, alpha):
                xy = circular_position(begin, center, a['angle'], alpha)
                # Animation interpolation precedes Scene.update_mobjects: both
                # coordinates are committed before any dependent geometry updates.
                for tracker, value in zip(self.trackers[key], xy):
                    tracker.set_value(float(value))
            animations.append(UpdateFromAlphaFunc(progress, rotate_point, rate_func=linear))
        elif kind == 'constrain':
            key = a['point']
            if key not in self.trackers:
                raise ValueError(f'Constrain requires a currently free point: {key}')
            trial = copy.deepcopy(self.active_objects)
            for obj in trial:
                if obj['id'] == key:
                    obj.pop('xy', None)
                    obj['derive'] = copy.deepcopy(a['derive'])
            overrides = {k: [t.get_value() for t in ts] for k, ts in self.trackers.items() if k != key}
            destination = resolve_points(trial, overrides, self.parameter_values())[key]
            animations.extend(t.animate.set_value(v) for t, v in zip(self.trackers[key], destination))
            cleanup.append((key, trial))
            ids = [key]
        elif kind in ('reflect_copy', 'translate_copy'):
            sources = [a['source']] if kind == 'reflect_copy' else a['sources']
            targets = [a['target']] if kind == 'reflect_copy' else a['targets']
            if len(sources) != len(targets):
                raise ValueError('Copy source/target count mismatch')
            ids = targets
            for src, dst in zip(sources, targets):
                if a.get('style') == 'continuous':
                    source_def, target_def = self.defs[src], self.defs[dst]
                    if src not in self.live or dst in self.live:
                        raise ValueError('continuous copy requires visible source and hidden target')
                    if (source_def['type'] != 'text' or target_def['type'] != 'text'
                            or source_def['text'] != target_def['text']
                            or source_def.get('font_size',28) != target_def.get('font_size',28)
                            or source_def.get('color','#FFFFFF').upper() != target_def.get('color','#FFFFFF').upper()
                            or source_def.get('max_width',9) != target_def.get('max_width',9)):
                        raise ValueError('continuous copy content/appearance mismatch')
                    source, target = self.mobs[src], self.mobs[dst]
                    delta = np.array([*np.asarray(a['vector']) * self.scale, 0.])
                    if (not np.allclose(target.get_center()-source.get_center(), delta, atol=1e-8, rtol=0)
                            or source.get_all_points().shape != target.get_all_points().shape
                            or not np.allclose(source.get_all_points()+delta, target.get_all_points(), atol=1e-8, rtol=0)):
                        raise ValueError('continuous copy must be translation of identical glyphs')
                    # TransformFromCopy animates the registered target backwards from
                    # a source reference, retaining the source. Suspend target refresh
                    # during interpolation; normal geometry updates resume at finish.
                    animations.append(TransformFromCopy(source, target, rate_func=linear, suspend_mobject_updating=True))
                    self.live.add(dst)
                    continue
                if dst in self.live:
                    continue
                target = self.mobs[dst]
                shift = (self.mobs[src].get_center() - target.get_center()) if kind == 'reflect_copy' else np.array([*-np.asarray(a['vector']) * self.scale, 0.])
                if self.defs[src]['type'] == self.defs[dst]['type'] == 'point':
                    p = self.points()
                    begin, end = p[src].copy(), p[dst].copy()
                    if kind == 'reflect_copy':
                        u, v = [p[k] for k in a['axis']]
                        axis = v - u
                        if np.dot(axis, axis) <= EPS ** 2:
                            raise ValueError('reflect_copy has zero axis')
                        expected = 2 * (u + axis * np.dot(begin-u, axis) / np.dot(axis,axis)) - begin
                    else:
                        expected = begin + np.asarray(a['vector'])
                    if not np.allclose(expected, end, atol=1e-8, rtol=0):
                        raise ValueError(f'Copy target {dst} does not match declared transform')
                    progress = ValueTracker(0)
                    self.transient[dst] = (begin, end, progress)
                    transient_cleanup.append(dst)
                    shift = self.mapped(begin) - self.mapped(end)
                    animations.append(progress.animate.set_value(1))
                # Animate the target's complete group; no detached label or persistent clone.
                animations.append(FadeIn(target, shift=-shift))
                self.live.add(dst)
        elif kind == 'focus':
            selected = [self.mobs[k] for k in ids if k in self.live]
            old = self.focus_box
            self.focus_box = None
            if old is not None:
                old.clear_updaters()
                self.play_to(a['at'] + a['duration'] / 2, FadeOut(old))
                self.remove(old)
                old.set_opacity(0)
            if selected:
                self.focus_box = GeometryScene._make_focus_box(self, selected)
                animations.append(FadeIn(self.focus_box))
            remaining = a['duration'] - (self.time - start)
            if animations:
                self.play_to(a['at'] + a['duration'], *animations)
            elif remaining > 1e-7:
                self.until(a['at'] + a['duration'])
            self.record(kind, a['at'], start, ids, self.time)
            return
        elif kind == 'highlight':
            animations.extend(MaskSafeIndicate(self.mobs[k], color='#FFD166', scale_factor=1) for k in ids if k in self.live)
        elif kind == 'formula':
            cx, cy, width, height = self.formula_rect
            if len(a['lines']) > 3:
                raise ValueError('Formula supports at most 3 explicitly arranged lines')
            lines = []
            for i, s in enumerate(a['lines']):
                mob = self.text(s, 32, '#FFFFFF', max_width=width - .2, accent=a.get('accent'))
                if mob.font_size < 24:
                    raise ValueError('Formula too long; split into explicit shorter lines')
                lines.append(mob.move_to([cx, cy + .8 - .8 * i, 0]))
            new = VGroup(*lines)
            if len(self.formulas):
                fps = config.frame_rate
                frame_budget = round((a['at'] + a['duration']) * fps) - round(self.time * fps)
                if a['duration'] * fps < 2 - 1e-7 or frame_budget < 2:
                    raise ValueError('Formula replacement requires at least two frames within its duration')
                fade_cap = int(np.floor(.15 * fps + 1e-7))
                if fade_cap < 1:
                    raise ValueError('Frame rate cannot fit a formula fade-out within 0.15 seconds')
                fade_frames = max(1, min(frame_budget - 1, round(frame_budget * .4), fade_cap))
                old = self.formulas
                self.play_to(self.time + fade_frames / fps, FadeOut(old))
                self.remove(old)
                visible_onset = self.time
            animations.append(FadeIn(new)); self.formulas = new
        elif kind != 'hold':
            raise ValueError(f'Unsupported geometry action: {kind}')
        if animations:
            self.play_to(motion_end, *animations)
        else:
            self.until(a['at'] + a['duration'])
        for key, item, target in text_cleanup:
            self.defs[key].update(copy.deepcopy({k:v for k,v in item.items() if k not in ('id', 'via')}))
            if target is not None:
                # Commit exact target children and text metadata for subsequent
                # transforms, hide/reveal and continuous copies.
                self.mobs[key].set_points(target.points.copy())
                self.mobs[key].set_submobjects([m.copy() for m in target.submobjects])
                self.mobs[key].text = item['text']
        if focus_restore is not None:
            self.focus_box = GeometryScene._make_focus_box(self, focus_restore)
            self.play_to(a['at'] + a['duration'], FadeIn(self.focus_box))
        if kind == 'set_parameter':
            self.parameters[a['parameter']].set_value(a['value'])
        if kind == 'move_on_circle':
            rotate_point(progress, 1.)
            self.remove(progress)
        for key, trial in cleanup:
            self.active_objects = trial
            self.defs = {o['id']: o for o in trial}
            del self.trackers[key]
        for key in transient_cleanup:
            del self.transient[key]
        for key in self.live:
            self.mobs[key].update(0)
        if hidden_focus is not None:
            self.remove(hidden_focus)
            hidden_focus.set_opacity(0)
        if retained_focus is not None:
            old, replacement = retained_focus
            old._focus_selected = replacement._focus_selected
            old._selection_signature = replacement._selection_signature
            old.updaters = list(replacement.updaters)
            self.focus_box = old
        self.record(kind, a['at'], visible_onset + (1/config.frame_rate if kind in ('reveal', 'reflect_copy', 'translate_copy', 'formula') else 0), ids, self.time)

    def record(self, kind, planned, visible, ids, completed):
        event = {'planned_at': planned, 'visible_start': visible, 'completed_at': completed,
                 'visible_start_source': 'animation_callback_estimate_not_pixel_measured',
                 'type': kind, 'chapter': self.chapter['id'], 'ids': ids}
        self.events.append(event)
        print('GEOMETRY_EVENT ' + json.dumps(event, ensure_ascii=False), flush=True)

    def snapshot(self, stage):
        def bounds(m):
            return [float(m.get_left()[0]), float(m.get_right()[0]), float(m.get_bottom()[1]), float(m.get_top()[1])]
        objects, labels = {}, []
        for key in sorted(self.live):
            mob = self.mobs[key]; b = bounds(mob)
            cx, cy, w, h = self.plot_rect
            region = [cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2] if self.defs[key]['type'] != 'text' else [-config.frame_width/2+.35, config.frame_width/2-.35, -config.frame_height/2+.3, config.frame_height/2-.3]
            objects[key] = {'bounds': b, 'safe': b[0] >= region[0] and b[1] <= region[1] and b[2] >= region[2] and b[3] <= region[3], 'safe_region': region}
            for i, child in enumerate(mob.get_family()):
                if isinstance(child, Text):
                    labels.append((f'{key}:{i}', bounds(child)))
        collisions = []
        for name, group in [('heading_problem', self.board), ('formula', self.formulas), ('title', self.title)]:
            objects[name] = {'bounds': bounds(group), 'safe_region': [-config.frame_width/2+.35, config.frame_width/2-.35, -config.frame_height/2+.3, config.frame_height/2-.3]}
            b, region = objects[name]['bounds'], objects[name]['safe_region']
            objects[name]['safe'] = b[0] >= region[0] and b[1] <= region[1] and b[2] >= region[2] and b[3] <= region[3]
            for i, child in enumerate(group.get_family()):
                if isinstance(child, Text):
                    labels.append((f'{name}:{i}', bounds(child)))
        for i, (key, a) in enumerate(labels):
            for other, b in labels[i + 1:]:
                if min(a[1], b[1]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[2], b[2]):
                    collisions.append([key, other])
        self.snapshots.append({'chapter': self.chapter['id'], 'at': self.time, 'stage': stage,
                               'objects': objects, 'text_collisions': collisions,
                               'parameters': self.parameter_values(),
                               'curved_regions': {k: curved_region_geometry(self.defs[k],self.points()[self.defs[k]['center']], self.parameter_values()) for k in sorted(self.live) if self.defs[k]['type'] in ('sector','circular_segment')},
                               'developable_surfaces': {k: surface_state(self.defs[k], self.parameter_values()) for k in sorted(self.live) if self.defs[k]['type'] in ('cylinder_net','cone_net')},
                               'conics': {k: conic_state(self.defs[k]) for k in sorted(self.live) if self.defs[k]['type']=='conic'},
                               'quadratics': {k: quadratic_state(self.defs[k], self.parameter_values()) for k in sorted(self.live) if self.defs[k]['type']=='quadratic'},
                               'intervals': {k: self.mobs[k]._interval_info for k in sorted(self.live) if self.defs[k]['type']=='interval'},
                               'end_state': {k: v.tolist() for k, v in self.points().items()}})

    def _report_path(self):
        writer = self.renderer.file_writer
        default = Path(getattr(writer, 'movie_file_path', None) or config.media_dir).with_suffix('.geometry.json')
        path = Path(os.environ.get('GEOMETRY_REPORT_PATH', str(default)))
        return path

    def _flush_snapshot_spool(self):
        if self._snapshot_spool is not None and self.snapshots:
            with self._snapshot_spool.open('a', encoding='utf-8') as stream:
                for snapshot in self.snapshots:
                    stream.write(json.dumps(snapshot, ensure_ascii=False, allow_nan=False) + '\n')
            self.snapshots.clear()

    def write_report(self):
        path = self._report_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        profile = self.spec.get('production_profile', 'standard')
        if getattr(self, '_snapshot_spool', None) is not None:
            self._flush_snapshot_spool()
            # Same JSON report shape without loading all chapter snapshots.
            with path.open('w', encoding='utf-8') as out:
                out.write('{"schema_version":"geometry-1.0","production_profile":' + json.dumps(profile))
                out.write(',"production_limits":' + json.dumps(production_limits(self.spec)))
                out.write(',"events":' + json.dumps(self.events, ensure_ascii=False) + ',"snapshots":[')
                first = True
                with self._snapshot_spool.open('r', encoding='utf-8') as spool:
                    for line in spool:
                        if not first: out.write(',')
                        out.write(line.strip()); first = False
                out.write('],"runtime_stats":' + json.dumps(self.runtime_stats, ensure_ascii=False) + '}')
            return
        path.write_text(json.dumps({'schema_version': 'geometry-1.0', 'production_profile': profile, 'production_limits': production_limits(self.spec), 'events': self.events,
                                    'snapshots': self.snapshots, 'runtime_stats': self.runtime_stats}, ensure_ascii=False, indent=2), encoding='utf-8')
