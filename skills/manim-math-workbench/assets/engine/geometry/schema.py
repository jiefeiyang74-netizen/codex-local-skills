"""Strict, non-normalizing geometry-1.0 contract. No executable user code."""
import copy
import math
import re
from decimal import Decimal

SCHEMA_VERSION = "geometry-1.0"
CAPABILITY_VERSION = "geometry-1.9.7"
PANEL_SHADOW_OFFSET = (.06, -.06)
PANEL_OUTLINE_SHADOW_OFFSET = (.0375, -.0375)
PRODUCTION_PROFILES = {
    "standard": {"max_duration": 7200, "max_chapters": 100, "max_total_actions": 3000},
    "long_lesson": {"max_duration": 14400, "max_chapters": 512, "max_total_actions": 12000},
}

OBJECT_FIELDS = {
    'panel': ('id type rect', 'color fill_color fill_opacity stroke_width shadow shadow_style accent'),
    'cylinder_net': ('id type radius height unfold', 'position display_scale color stroke_width fill_opacity'),
    'cone_net': ('id type radius slant unfold', 'position display_scale color stroke_width fill_opacity'),
    'conic': ('id type kind center', 'a b p branch color stroke_width dashed tolerance'),
    'sector': ('id type center radius start_angle sweep_angle', 'color stroke_width dashed fill_opacity'),
    'circular_segment': ('id type center radius start_angle sweep_angle', 'color stroke_width dashed fill_opacity'),
    'coordinate_axes': ('id type', 'x_ticks y_ticks color font_size grid label_offsets'),
    'reciprocal': ('id type k', 'color stroke_width dashed tolerance branch'),
    'quadratic': ('id type a h k', 'color stroke_width dashed'),
    'quadratic_feature': ('id type curve kind', 'x color label show_label font_size label_offset'),
    'number_line': ('id type variable range start end', 'ticks color font_size'),
    'interval': ('id type axis left right left_closed right_closed', 'lane label empty_label color stroke_width'),
    'point': ('id type', 'xy derive label color label_offset font_size typography label_mask'),
    'circle': ('id type center radius', 'color stroke_width dashed fill_opacity'),
    'line': ('id type a b', 'kind color stroke_width dashed arrow'),
    'polygon': ('id type points', 'color fill_opacity'),
    'ticks': ('id type segment', 'count color'),
    'right_angle': ('id type vertex arm1 arm2', 'color size'),
    'angle': ('id type vertex arm1 arm2', 'label color radius'),
    'text': ('id type text position', 'font_size color max_width formula_group typography'),
}
ACTION_FIELDS = {
    'text_transform': ('type at duration items', ''),
    'reveal': ('at duration type ids', 'style'), 'hide': ('at duration type ids', ''),
    'move': ('at duration type positions', ''),
    'set_parameter': ('at duration type parameter value', ''),
    'merge_intervals': ('at duration type sources target', ''),
    'move_on_circle': ('at duration type point circle angle', ''),
    'reflect_copy': ('at duration type source target axis', ''),
    'translate_copy': ('at duration type sources targets vector', 'style'),
    'focus': ('at duration type ids', ''), 'highlight': ('at duration type ids', 'style'),
    'formula': ('at duration type lines', 'accent'), 'hold': ('at duration type', ''),
    'constrain': ('at duration type point derive', ''),
}
CHECK_FIELDS = {
    'quadratic_state': ('type curve', 'vertex roots y_intercept coefficients tolerance'),
    'quadratic_point': ('type feature value', 'tolerance'),
    'interval_state': ('type interval empty', 'left right left_closed right_closed'),
    'interval_subset': ('type subset superset expected', ''),
    'interval_union': ('type sources target', ''),
    'distance': ('type points value', 'tolerance'),
    'equal_length': ('type segments', 'tolerance'),
    'perpendicular': ('type lines', 'tolerance'),
    'collinear': ('type points', 'ordered tolerance'),
    'on_ray': ('type point ray', 'tolerance'),
    'path_length': ('type points value', 'tolerance'),
}

class GeometryValidationError(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise GeometryValidationError(message)

def number(x):
    return type(x) in (int, float) and math.isfinite(x)

def fields(obj, required, optional=''):
    require(isinstance(obj, dict), 'expected object')
    required, optional = set(required.split()), set(optional.split())
    require(required <= obj.keys(), f'missing fields: {required - obj.keys()}')
    require(obj.keys() <= required | optional, f'unknown fields: {obj.keys() - required - optional}')

def vector(v):
    require(isinstance(v, list) and len(v) == 2 and all(number(n) and abs(n) <= 10000 for n in v), 'invalid finite 2D vector')

def axis_tick_key(axis, value):
    """Canonical numeric identity, independent of rounded display text."""
    if value == 0:
        return axis + ':0'
    text = format(Decimal(str(value)), 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return axis + ':' + text


def short(s, limit):
    require(isinstance(s, str) and 0 < len(s) <= limit and '\n' not in s and '\\' not in s, 'text budget exceeded or TeX/multiline text')

def _finite_tree(x):
    if isinstance(x, float):
        require(math.isfinite(x), 'non-finite number')
    elif isinstance(x, dict):
        for v in x.values(): _finite_tree(v)
    elif isinstance(x, list):
        for v in x: _finite_tree(v)

def production_limits(spec):
    profile = spec.get('production_profile', 'standard')
    require(type(profile) is str and profile in PRODUCTION_PROFILES, 'unknown production_profile')
    return dict(PRODUCTION_PROFILES[profile])


def validate_layout_style(spec, selected_style):
    if 'paper_palette' in spec:
        require(spec['paper_palette'] == 'reference_yellow', 'invalid paper_palette')
        require(selected_style == 'paper_guided', 'paper_palette requires paper_guided')
    for chapter in spec.get('chapters', []):
        if chapter.get('proof_layout', 'single') == 'steps':
            require(selected_style == 'paper_guided', 'proof_layout steps requires paper_guided')
        if any(o.get('typography') == 'heavy' for o in chapter.get('objects', [])):
            require(selected_style == 'paper_guided', 'heavy typography requires paper_guided')


def panel_stroke_padding(obj):
    return .01 * max(obj.get('stroke_width', 1), 3 if 'accent' in obj else 0,
                     1 if obj.get('shadow_style') == 'outline' else 0)


def panel_shadow_offset(obj):
    return PANEL_OUTLINE_SHADOW_OFFSET if obj.get('shadow_style', 'soft') == 'outline' else PANEL_SHADOW_OFFSET


def panel_bounds(obj):
    cx, cy, width, height = obj['rect']
    dx, dy = panel_shadow_offset(obj) if obj.get('shadow', False) else (0, 0)
    pad = panel_stroke_padding(obj)
    return [cx-width/2-pad, cx+width/2+dx+pad,
            cy-height/2+dy-pad, cy+height/2+pad]

def validate_production_budget(spec):
    limits = production_limits(spec)
    duration, chapters = spec.get('audio_duration'), spec.get('chapters')
    require(number(duration) and 0 < duration <= limits['max_duration'], 'invalid audio_duration for production_profile')
    require(isinstance(chapters, list) and 0 < len(chapters) <= limits['max_chapters'], 'chapter budget for production_profile')
    require(all(isinstance(c, dict) and isinstance(c.get('actions'), list) for c in chapters), 'invalid chapter actions')
    require(sum(len(c['actions']) for c in chapters) <= limits['max_total_actions'], 'total event budget for production_profile')
    return limits

def validate_spec(raw, *, run_math=True):
    _finite_tree(raw)
    fields(raw, 'schema_version title audio_duration narration chapters', 'canvas heading_mode production_profile paper_palette')
    if 'paper_palette' in raw: require(raw['paper_palette'] == 'reference_yellow', 'invalid paper_palette')
    limits = validate_production_budget(raw)
    require(raw.get('heading_mode', 'standard') in ('standard', 'chapter'), 'invalid heading_mode')
    if 'canvas' in raw:
        fields(raw['canvas'], 'width height fps')
        cv = raw['canvas']
        require(all(type(cv[k]) is int for k in cv) and 320 <= cv['width'] <= 3840 and 320 <= cv['height'] <= 3840 and cv['width'] % 2 == cv['height'] % 2 == 0 and cv['fps'] == 60, 'invalid canvas (even dimensions, final fps=60)')
    canvas = raw.get('canvas', {'width':1920,'height':1080})
    frame_height = 9 if canvas['width'] >= canvas['height'] else 16
    frame_width = frame_height * canvas['width'] / canvas['height']
    require(raw['schema_version'] == SCHEMA_VERSION, 'unsupported schema')
    short(raw['title'], 40)
    require(isinstance(raw['narration'], str) and 0 < len(raw['narration']) <= 100000, 'invalid narration')
    duration = raw['audio_duration']
    require(number(duration) and 0 < duration <= limits['max_duration'], 'invalid audio_duration')
    chapters = raw['chapters']
    require(isinstance(chapters, list) and 0 < len(chapters) <= limits['max_chapters'], 'chapter budget')
    chapter_ids, previous_end, total_actions = set(), 0, 0
    for ci, c in enumerate(chapters):
        fields(c, 'id title start end world_bounds problem objects actions checks', 'plot_rect formula_rect parameters presentation proof_layout')
        require(c.get('presentation', 'standard') in ('standard', 'freeform'), 'invalid chapter presentation')
        require(c.get('proof_layout', 'single') in ('single', 'steps'), 'invalid chapter proof_layout')
        steps = c.get('proof_layout', 'single') == 'steps'
        parameters = c.get('parameters', {})
        require(isinstance(parameters,dict) and len(parameters) <= 16, 'parameter budget')
        for key,value in parameters.items():
            require(isinstance(key,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',key) and number(value) and abs(value) <= 10000, 'invalid parameter')
        parameters = dict(parameters)
        from .developable import surface_state, validate_surface_parameters
        from .conic import conic_state, conic_paths, validate_conic_parameters, validate_conic_transition
        from .reciprocal import validate_reciprocal_parameters, validate_reciprocal_transition, reciprocal_segments
        from .math2d import interval_state, validate_interval_merge, scalar_value
        from .quadratic import (quadratic_scalar, quadratic_state,
                                validate_quadratic_parameters, validate_quadratic_transition)
        for key in ('plot_rect','formula_rect'):
            if key in c:
                rect = c[key]
                require(isinstance(rect,list) and len(rect)==4 and all(number(x) for x in rect) and rect[2]>0 and rect[3]>0, 'invalid layout rect')
        require(isinstance(c['id'], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', c['id']) and c['id'] not in chapter_ids, 'invalid/duplicate chapter id')
        chapter_ids.add(c['id']); short(c['title'], 40)
        require(number(c['start']) and number(c['end']) and previous_end <= c['start'] < c['end'] <= duration + 1/30, 'chapter interval invalid')
        require(ci > 0 or c['start'] == 0, 'chapters must start at zero')
        previous_end = c['end']
        b = c['world_bounds']
        require(isinstance(b, list) and len(b) == 4 and all(number(v) and abs(v) <= 10000 for v in b) and b[0] < b[1] and b[2] < b[3], 'invalid world_bounds')
        require(isinstance(c['problem'], list) and len(c['problem']) <= 2, 'problem line budget')
        for s in c['problem']: short(s, 52)
        require(isinstance(c['objects'], list) and len(c['objects']) <= (144 if steps else 120), 'object budget')
        objects = {}
        for o in c['objects']:
            require(isinstance(o, dict) and o.get('type') in OBJECT_FIELDS, 'unknown object type')
            fields(o, *OBJECT_FIELDS[o['type']])
            oid = o['id']
            require(isinstance(oid, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', oid) and oid not in objects, 'invalid/duplicate object id')
            objects[oid] = o
            if 'typography' in o:
                require(o['typography'] in ('body', 'math', 'serif', 'heavy'), 'invalid typography')
                require(o['typography'] != 'heavy' or o['type'] == 'text', 'heavy typography is for text objects only')
            if 'label_mask' in o: require(type(o['label_mask']) is bool, 'label_mask must be boolean')
            if 'color' in o: require(isinstance(o['color'], str) and re.fullmatch(r'#[0-9a-fA-F]{6}', o['color']), 'invalid color')
            if o['type'] == 'panel':
                rect = o['rect']
                require(isinstance(rect, list) and len(rect) == 4 and all(number(x) for x in rect)
                        and rect[2] > 0 and rect[3] > 0, 'invalid panel rect')
                for key in ('fill_color', 'accent'):
                    if key in o: require(isinstance(o[key], str) and re.fullmatch(r'#[0-9a-fA-F]{6}', o[key]), f'invalid panel {key}')
                if 'shadow' in o: require(type(o['shadow']) is bool, 'panel shadow must be boolean')
                if 'shadow_style' in o: require(o['shadow_style'] in ('soft','outline'), 'invalid shadow_style')
                require(o.get('shadow_style') != 'outline' or o.get('shadow') is True, 'outline requires shadow:true')
            if 'label' in o: short(o['label'], 20)
            if o['type'] == 'coordinate_axes':
                for name, lo, hi in [('x_ticks',b[0],b[1]), ('y_ticks',b[2],b[3])]:
                    ticks = o.get(name, [])
                    require(isinstance(ticks,list) and len(ticks)<=21 and all(number(v) and lo<=v<=hi for v in ticks) and len(set(ticks))==len(ticks), f'invalid coordinate-axis {name}')
                if 'grid' in o: require(type(o['grid']) is bool, 'coordinate-axis grid must be boolean')
                offsets = o.get('label_offsets', {})
                require(isinstance(offsets, dict), 'coordinate-axis label_offsets must be a mapping')
                allowed = {'origin'} | {axis_tick_key(axis, v) for axis in ('x', 'y') for v in o.get(axis + '_ticks', [])}
                for key, offset in offsets.items():
                    require(isinstance(key, str) and key in allowed, 'unknown/noncanonical coordinate-axis label_offsets key')
                    require(isinstance(offset, list) and len(offset) == 2 and all(number(v) and abs(v) <= 1.5 for v in offset), 'coordinate-axis label_offsets must be finite 2D screen offsets within +/-1.5')
            if o['type'] == 'conic':
                try: conic_state(o); conic_paths(o, b)
                except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
            if 'arrow' in o:
                require(type(o['arrow']) is bool and o.get('kind','segment') == 'segment', 'arrow requires boolean and segment kind')
            if o['type'] == 'quadratic':
                try: quadratic_state(o,parameters)
                except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
            if o['type'] == 'quadratic_feature':
                require(o['kind'] in ('vertex','axis','roots','y_intercept','point'), 'unknown quadratic feature')
                require(('x' in o) == (o['kind']=='point'), 'only point feature requires x')
                if 'x' in o:
                    try: quadratic_scalar(o['x'],parameters)
                    except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
                if 'show_label' in o: require(type(o['show_label']) is bool, 'show_label must be boolean')
                if o['kind']=='axis': require('label' not in o, 'quadratic axis has no label')
            if o['type'] == 'number_line':
                short(o['variable'],8)
                require(isinstance(o['range'],list) and len(o['range'])==2 and all(number(v) and abs(v)<=10000 for v in o['range']) and o['range'][0]<o['range'][1], 'invalid number-line range')
                ticks=o.get('ticks',[])
                require(isinstance(ticks,list) and len(ticks)<=21 and all(number(v) and o['range'][0]<=v<=o['range'][1] for v in ticks) and len(set(ticks))==len(ticks), 'invalid number-line ticks')
            if o['type'] == 'interval':
                require(number(o.get('lane',0)) and abs(o.get('lane',0))<=10, 'invalid interval lane')
                if 'empty_label' in o: short(o['empty_label'],8)
                try: interval_state(o,parameters)
                except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
            for key in ('xy', 'position', 'label_offset'):
                if key in o: vector(o[key])
            for key, lo, hi in [('stroke_width', .1, 12), ('fill_opacity', 0, 1), ('size', .01, 2), ('font_size', 12, 80 if o['type'] == 'text' else 48), ('max_width', .2, 10)]:
                if key in o: require(number(o[key]) and lo <= o[key] <= hi, f'invalid {key}')
            if 'radius' in o and o['type'] not in ('sector','cylinder_net','cone_net'):
                require(number(o['radius']) and (0 < o['radius'] <= 10000 if o['type'] in ('circle','sector','circular_segment') else .01 <= o['radius'] <= 5), 'invalid radius')
            if 'dashed' in o: require(type(o['dashed']) is bool, 'dashed must be boolean')
            if o['type'] == 'panel':
                bounds = panel_bounds(o)
                require(bounds[0] >= -frame_width/2+.35 and bounds[1] <= frame_width/2-.35
                        and bounds[2] >= -frame_height/2+.3 and bounds[3] <= frame_height/2-.3,
                        'panel including shadow/stroke outside canvas safe budget')
            if 'count' in o: require(type(o['count']) is int and 1 <= o['count'] <= 4, 'ticks count')
            if o['type']=='line' and 'kind' in o: require(o['kind'] in ('segment', 'line', 'ray'), 'line kind')
            if o['type'] in ('sector','circular_segment'):
                from .math2d import curved_region_geometry
                try: curved_region_geometry(o, [0,0], parameters)
                except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
            if o['type'] in ('cylinder_net','cone_net'):
                try: surface_state(o, parameters)
                except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
            if o['type'] == 'text':
                short(o['text'], 64)
                if 'formula_group' in o:
                    require(isinstance(o['formula_group'], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', o['formula_group']), 'invalid formula_group id')
                require(abs(o['position'][0]) <= frame_width/2-.35 and abs(o['position'][1]) <= frame_height/2-.3, 'text outside canvas safe budget')
        def ref(v, point=False):
            require(isinstance(v, str) and v in objects, f'unknown reference {v}')
            require(not point or objects[v]['type'] == 'point', f'point reference required: {v}')
        def refs(v, n=None, point=True):
            require(isinstance(v, list) and (n is None or len(v) == n) and len(v) > 0 and len(set(v)) == len(v), 'invalid reference list')
            for r in v: ref(r, point)
        dependencies = {}
        for oid, o in objects.items():
            t = o['type']; deps = []
            if t == 'point':
                require(('xy' in o) != ('derive' in o), 'point needs exactly xy or derive')
                if 'derive' in o:
                    d = o['derive']; dt = d.get('type') if isinstance(d, dict) else None
                    require(dt in ('reflect', 'project', 'translate', 'intersect', 'on_reciprocal', 'on_quadratic', 'rotate', 'scale', 'on_conic', 'conic_tangent'), 'unknown derivation')
                    fields(d, {'reflect':'type source axis', 'project':'type source line', 'translate':'type source vector', 'intersect':'type lines', 'on_reciprocal':'type curve x', 'on_quadratic':'type curve x', 'scale':'type source center factor', 'rotate':'type source center angle', 'on_conic':'type curve t', 'conic_tangent':'type source scale'}[dt], 'branch' if dt == 'on_conic' else '')
                    if dt == 'on_conic':
                        ref(d['curve']); require(objects[d['curve']]['type']=='conic', 'on_conic requires conic'); deps.append(d['curve'])
                    elif dt == 'conic_tangent':
                        ref(d['source'], True); deps.append(d['source'])
                        require(objects[d['source']].get('derive',{}).get('type')=='on_conic', 'conic_tangent requires on_conic source')
                    elif dt == 'on_reciprocal':
                        ref(d['curve']); require(objects[d['curve']]['type']=='reciprocal', 'on_reciprocal requires reciprocal'); deps.append(d['curve'])
                    elif dt == 'on_quadratic':
                        ref(d['curve']); require(objects[d['curve']]['type']=='quadratic', 'on_quadratic requires quadratic'); deps.append(d['curve'])
                    elif dt in ('rotate', 'scale'):
                        ref(d['source'], True); ref(d['center'], True)
                        deps.extend([d['source'], d['center']])
                        from .math2d import rotation_angle, scale_factor
                        try: (rotation_angle if dt == 'rotate' else scale_factor)(d, parameters)
                        except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
                    elif dt == 'intersect':
                        require(isinstance(d['lines'], list) and len(d['lines']) == 2, 'intersection lines')
                        for line in d['lines']: refs(line, 2); deps.extend(line)
                    else:
                        ref(d['source'], True); deps.append(d['source'])
                        if dt == 'translate': vector(d['vector'])
                        else:
                            pair = d['axis' if dt == 'reflect' else 'line']; refs(pair, 2); deps.extend(pair)
            elif t == 'number_line':
                refs([o['start'],o['end']],2); deps=[o['start'],o['end']]
                require(all('xy' in objects[k] for k in deps), 'number-line anchors must be free points')
                first,last=[objects[k]['xy'] for k in deps]
                require(first[0]<last[0] and first[1]==last[1], 'number line must be horizontal and increasing')
            elif t == 'interval':
                ref(o['axis']); require(objects[o['axis']]['type']=='number_line','interval axis must be number_line');deps=[o['axis']]
            elif t == 'quadratic_feature':
                ref(o['curve']); require(objects[o['curve']]['type']=='quadratic','quadratic feature requires quadratic curve'); deps=[o['curve']]
            elif t in ('circle','sector','circular_segment'): ref(o['center'], True); deps = [o['center']]
            elif t == 'line': deps = [o['a'], o['b']]; refs(deps, 2)
            elif t == 'polygon':
                refs(o['points']); require(3 <= len(o['points']) <= 12, 'polygon budget'); deps = o['points']
            elif t in ('angle', 'right_angle'): deps = [o['vertex'], o['arm1'], o['arm2']]; refs(deps, 3)
            elif t == 'ticks':
                ref(o['segment']); require(objects[o['segment']]['type'] == 'line', 'ticks require line'); deps = [o['segment']]
            dependencies[oid] = deps
        done, active = set(), set()
        def visit(oid):
            require(oid not in active, f'cyclic geometry dependency: {oid}')
            if oid in done: return
            active.add(oid)
            for dep in dependencies[oid]: visit(dep)
            active.remove(oid); done.add(oid)
        for oid in objects: visit(oid)
        try:
            validate_surface_parameters(c['objects'], parameters)
            validate_conic_parameters(c['objects'], parameters)
            validate_quadratic_parameters(c['objects'], parameters)
            validate_reciprocal_parameters(c['objects'], parameters)
            for obj in c['objects']:
                if obj['type']=='reciprocal': reciprocal_segments(obj, parameters, b)
        except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
        require(isinstance(c['actions'], list) and len(c['actions']) <= 500, 'action budget')
        total_actions += len(c['actions'])
        if c['actions'] and c.get('presentation') != 'freeform' and not (ci and chapters[ci-1].get('presentation') == 'freeform'):
            require(c['actions'][0].get('at', -1) >= c['start'] + .5, 'reserve at least .5s for chapter heading transition')
        visible, end = set(), c['start']
        state_objects = copy.deepcopy(c['objects'])
        state_defs = {o['id']:o for o in state_objects}
        overrides = {}
        for ai, a in enumerate(c['actions']):
            require(isinstance(a, dict) and a.get('type') in ACTION_FIELDS, 'unknown action')
            fields(a, *ACTION_FIELDS[a['type']]); t = a['type']
            panel_ids = {key for key, obj in objects.items() if obj['type'] == 'panel'}
            for key in ('ids', 'sources', 'targets', 'source', 'target'):
                value = a.get(key, [])
                values = value if isinstance(value, list) else [value]
                if any(isinstance(v, str) and v in panel_ids for v in values):
                    require(t in ('reveal', 'hide') and a.get('style', 'fade') == 'fade',
                            'panel supports only reveal fade and hide')
            require(number(a['at']) and number(a['duration']) and a['duration'] > 0 and a['at'] >= end - 1e-8 and a['at'] + a['duration'] <= min(c['end'], duration) + 1e-8, f"{c['id']}.actions[{ai}] {t}: action overlap/outside audio or chapter; at={a['at']}, duration={a['duration']}, previous_end={end}, chapter_end={c['end']}")
            end = a['at'] + a['duration']
            if 'ids' in a:
                if a['ids'] != [] or t != 'focus': refs(a['ids'], point=False)
                if t == 'reveal':
                    require(not visible.intersection(a['ids']), 'reveal already visible object'); visible.update(a['ids'])
                else:
                    require(set(a['ids']) <= visible, 'action references hidden object')
                    if t == 'hide': visible.difference_update(a['ids'])
            if 'style' in a:
                require(a['style'] in (('continuous',) if t == 'translate_copy' else ('emphasis',) if t == 'highlight' else ('draw', 'fade')), 'unknown action style')
            if t == 'set_parameter':
                require(isinstance(a['parameter'],str) and a['parameter'] in parameters and number(a['value']) and abs(a['value'])<=10000, 'invalid parameter update')
                updated = dict(parameters); updated[a['parameter']]=a['value']
                try:
                    validate_surface_parameters(state_objects, updated)
                    validate_conic_transition(state_objects, parameters, updated)
                    validate_quadratic_transition(state_objects, parameters, updated)
                    validate_reciprocal_transition(state_objects, parameters, updated)
                    from .math2d import validate_rotation_parameters, validate_scale_parameters
                    validate_rotation_parameters(state_objects, updated)
                    validate_scale_parameters(state_objects, updated)
                    for obj in state_objects:
                        if obj['type']=='reciprocal': reciprocal_segments(obj, updated, b)
                except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
                parameters = updated
                for obj in objects.values():
                    if obj['type']=='interval':
                        try: interval_state(obj,parameters)
                        except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
            if t == 'merge_intervals':
                refs(a['sources'],point=False);ref(a['target'])
                require(set(a['sources'])<=visible and a['target'] not in visible and a['duration']>=.4,'merge lifecycle/duration')
                try: validate_interval_merge(objects,a['sources'],a['target'],parameters)
                except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
                if any(objects[k].get('label') or objects[k].get('empty_label') for k in a['sources']):
                    for fps in (30,60):
                        boundaries=[round((a['at']+a['duration']*f)*fps) for f in (0,.15,.8,1)]
                        require(all(y-x>=2 for x,y in zip(boundaries,boundaries[1:])), 'labeled merge phase needs >=2 frames at preview30/final60')
                visible.difference_update(a['sources']);visible.add(a['target'])
            if t == 'text_transform':
                require(isinstance(a['items'], list) and 1 <= len(a['items']) <= 48, 'text_transform item budget')
                seen = set()
                for item in a['items']:
                    require(isinstance(item, dict), 'text_transform item must be object')
                    fields(item, 'id position', 'text via')
                    ref(item['id'])
                    key = item['id']
                    require(key not in seen, 'duplicate text_transform ID'); seen.add(key)
                    require(key in visible and state_defs[key]['type'] == 'text', 'text_transform requires visible text')
                    vector(item['position'])
                    if 'via' in item:
                        vector(item['via'])
                        require(abs(item['via'][0]) <= frame_width/2-.35 and abs(item['via'][1]) <= frame_height/2-.3, 'text via outside canvas safe budget')
                    require(abs(item['position'][0]) <= frame_width/2-.35 and abs(item['position'][1]) <= frame_height/2-.3, 'text outside canvas safe budget')
                    if 'text' in item: short(item['text'], 64)
                    state_defs[key].update(copy.deepcopy({k:v for k,v in item.items() if k not in ('id', 'via')}))
            if t == 'move':
                require(isinstance(a['positions'], dict) and a['positions'], 'empty move')
                for oid, xy in a['positions'].items():
                    ref(oid, True); require('xy' in state_defs[oid], 'move requires free unconstrained point'); vector(xy)
                if run_math:
                    from .math2d import resolve_points
                    initial = resolve_points(state_objects, overrides, parameters)
                    for fraction in (0,.25,.5,.75,1):
                        sampled = dict(overrides)
                        for oid, xy in a['positions'].items(): sampled[oid] = [float(initial[oid][j]) + (xy[j]-float(initial[oid][j]))*fraction for j in (0,1)]
                        resolve_points(state_objects, sampled, parameters)
                overrides.update(a['positions'])
                for axis in objects.values():
                    if axis['type']=='number_line':
                        first,last=[overrides.get(k,objects[k]['xy']) for k in (axis['start'],axis['end'])]
                        require(first[0]<last[0] and first[1]==last[1], 'move breaks number-line axis')
            if t == 'move_on_circle':
                ref(a['point'], True); ref(a['circle'])
                require(not any(o['type']=='number_line' and a['point'] in (o['start'],o['end']) for o in objects.values()), 'cannot rotate number-line anchor')
                require('xy' in state_defs[a['point']], 'circular move requires free unconstrained point')
                require(state_defs[a['circle']]['type'] == 'circle', 'circular move requires circle reference')
                require(number(a['angle']) and 0 < abs(a['angle']) <= 8 * math.pi, 'invalid circular angle (nonzero radians, at most 8*pi)')
                from .math2d import point_depends_on
                require(not point_depends_on(state_objects, state_defs[a['circle']]['center'], a['point']), 'circle center cannot depend on moving point')
                if run_math:
                    from .math2d import circle_motion_parameters, circular_position, resolve_points
                    try:
                        start, center = circle_motion_parameters(state_objects, overrides, a['point'], a['circle'], a['angle'], parameters)
                        for sample in range(65):
                            sampled = dict(overrides)
                            sampled[a['point']] = circular_position(start, center, a['angle'], sample / 64)
                            resolve_points(state_objects, sampled, parameters)
                        overrides[a['point']] = circular_position(start, center, a['angle'], 1)
                    except ValueError as exc:
                        raise GeometryValidationError(f"{c['id']}.actions[{ai}] move_on_circle: {exc}") from exc
            if t == 'constrain':
                ref(a['point'], True)
                require('xy' in state_defs[a['point']], 'constrain requires free point')
                require(not any(o['type']=='number_line' and a['point'] in (o['start'],o['end']) for o in objects.values()), 'cannot constrain number-line anchor')
                # Reuse the strict object/dependency validator on the changed definition.
                candidate = copy.deepcopy(raw)
                changed = candidate['chapters'][ci]
                changed['parameters'] = dict(parameters)
                changed['objects'] = copy.deepcopy(state_objects)
                target = next(o for o in changed['objects'] if o['id'] == a['point'])
                target.pop('xy',None); target['derive'] = copy.deepcopy(a['derive'])
                for ch in candidate['chapters']: ch['actions'] = []; ch['checks'] = []
                validate_spec(candidate, run_math=False)
                state_defs[a['point']].pop('xy',None)
                state_defs[a['point']]['derive'] = copy.deepcopy(a['derive'])
                overrides.pop(a['point'],None)
                if run_math:
                    from .math2d import resolve_points
                    resolve_points(state_objects, overrides, parameters)
            if t == 'reflect_copy':
                ref(a['source'], True); ref(a['target'], True); refs(a['axis'], 2)
                source, target = objects[a['source']], objects[a['target']]
                require(source.get('typography','body') == target.get('typography','body') and source.get('label_mask',True) == target.get('label_mask',True), 'point copy typography/mask mismatch')
                require(a['source'] in visible and a['target'] not in visible and a['source'] != a['target'], 'reflect lifecycle')
                require(objects[a['target']].get('derive') == {'type':'reflect', 'source':a['source'], 'axis':a['axis']}, 'reflect target definition mismatch')
                visible.add(a['target'])
            if t == 'translate_copy':
                refs(a['sources'], point=False); refs(a['targets'], point=False); vector(a['vector'])
                require(len(a['sources']) == len(a['targets']) and not set(a['sources']).intersection(a['targets']) and set(a['sources']) <= visible, 'translate lifecycle/count')
                for s, target in zip(a['sources'], a['targets']): require(objects[s]['type'] == objects[target]['type'], 'translate types differ')
                for s, target in zip(a['sources'], a['targets']):
                    if objects[s]['type'] == 'point':
                        require(objects[s].get('typography','body') == objects[target].get('typography','body') and objects[s].get('label_mask',True) == objects[target].get('label_mask',True), 'point copy typography/mask mismatch')
                if a.get('style') == 'continuous':
                    require(not set(a['targets']).intersection(visible), 'continuous copy target already visible')
                    rect = c.get('plot_rect', [-2.45, -.35, 9.5, 5.8] if frame_width >= frame_height else [0, .35, 10.4, 6.9])
                    scale = min(rect[2] / (b[1]-b[0]), rect[3] / (b[3]-b[2]))
                    for source_id, target_id in zip(a['sources'], a['targets']):
                        source, target = state_defs[source_id], state_defs[target_id]
                        require(source['type'] == target['type'] == 'text', 'continuous copy requires text')
                        require(source['text'] == target['text'] and source.get('font_size',28) == target.get('font_size',28), 'continuous copy content/font_size mismatch')
                        require(source.get('color','#FFFFFF').upper() == target.get('color','#FFFFFF').upper() and source.get('max_width',9) == target.get('max_width',9), 'continuous copy appearance mismatch')
                        require(source.get('typography','body') == target.get('typography','body'), 'continuous copy typography mismatch')
                        require(all(abs(target['position'][j]-source['position'][j]-a['vector'][j]*scale) <= 1e-8 for j in (0,1)), 'continuous copy vector mismatch')
                visible.update(a['targets'])
            if t == 'formula':
                require(isinstance(a['lines'], list) and 1 <= len(a['lines']) <= 3, 'formula line budget')
                for s in a['lines']: short(s, 64)
                if 'accent' in a: short(a['accent'], 24)
            texts = [state_defs[x] for x in visible if state_defs[x]['type'] == 'text']
            groups = {}
            for obj in texts:
                if 'formula_group' in obj:
                    group = obj['formula_group']
                    groups[group] = groups.get(group, 0) + 1
            require(sum('formula_group' not in obj for obj in texts) + len(groups) <= 6, 'visible text/group budget')
            require(all(count <= 24 for count in groups.values()), 'formula_group item budget')
            require(len(texts) <= 48, 'visible text total budget')
            require(sum(len(obj['text']) for obj in texts) <= 200, 'visible text character budget')
        require(isinstance(c['checks'], list) and len(c['checks']) <= 100, 'check budget')
        for ck in c['checks']:
            require(isinstance(ck, dict) and ck.get('type') in CHECK_FIELDS, 'unknown check')
            fields(ck, *CHECK_FIELDS[ck['type']])
            if ck['type']=='quadratic_state':
                ref(ck['curve']); require(objects[ck['curve']]['type']=='quadratic', 'quadratic check requires curve')
                require(bool(set(ck)&{'vertex','roots','y_intercept','coefficients'}), 'quadratic_state needs expected values')
                for name, length in [('vertex',2), ('coefficients',3)]:
                    if name in ck:
                        require(isinstance(ck[name],list) and len(ck[name])==length and all(number(v) for v in ck[name]), f'invalid quadratic {name} check')
                if 'roots' in ck:
                    roots=ck['roots']
                    require(isinstance(roots,list) and len(roots)<=2 and all(number(v) for v in roots) and all(a<b for a,b in zip(roots,roots[1:])), 'roots check requires sorted distinct finite roots')
                if 'y_intercept' in ck: require(number(ck['y_intercept']), 'invalid y-intercept check')
            if ck['type']=='quadratic_point':
                ref(ck['feature']); feature=objects[ck['feature']]
                require(feature['type']=='quadratic_feature' and feature['kind'] in ('point','vertex','y_intercept'), 'quadratic_point requires single point feature')
                require(isinstance(ck['value'],list) and len(ck['value'])==2 and all(number(v) for v in ck['value']), 'quadratic_point value must be finite [x,y]')
            if ck['type'].startswith('interval_'):
                keys=([ck['interval']] if ck['type']=='interval_state' else [ck['subset'],ck['superset']] if ck['type']=='interval_subset' else [*ck['sources'],ck['target']])
                for key in keys: ref(key);require(objects[key]['type']=='interval','interval check reference')
                if ck['type']=='interval_state':
                    require(type(ck['empty']) is bool,'empty check must be boolean')
                    for side in ('left','right'):
                        if side in ck:
                            try: scalar_value(ck[side],parameters)
                            except ValueError as exc: raise GeometryValidationError(str(exc)) from exc
                    for side in ('left_closed','right_closed'):
                        if side in ck: require(type(ck[side]) is bool,'closure check must be boolean')
                if ck['type']=='interval_subset': require(type(ck['expected']) is bool,'subset expected must be boolean')
            if 'points' in ck:
                refs(ck['points']); require(len(ck['points']) >= 2, 'check needs two points')
                if ck['type'] == 'distance': require(len(ck['points']) == 2, 'distance point count')
            for key in ('segments', 'lines'):
                if key in ck:
                    require(isinstance(ck[key], list) and len(ck[key]) == 2, 'check requires two pairs')
                    for pair in ck[key]: refs(pair, 2)
            if 'point' in ck: ref(ck['point'], True); refs(ck['ray'], 2)
            if 'value' in ck and ck['type']!='quadratic_point': require(number(ck['value']) and ck['value'] >= 0, 'check value')
            if 'tolerance' in ck: require(number(ck['tolerance']) and 0 < ck['tolerance'] <= .01, 'check tolerance')
            if 'ordered' in ck: require(type(ck['ordered']) is bool, 'ordered must be boolean')
        if run_math:
            from .math2d import resolve_points, evaluate_checks
            resolve_points(c['objects'], parameters=c.get('parameters', {}))
            results = evaluate_checks(copy.deepcopy(c['objects']), c['actions'], c['checks'], c.get('parameters',{}))
            require(isinstance(results, (dict, list)), 'math evaluator must return auditable results')
            entries = results.get('checks', results.get('results', [])) if isinstance(results, dict) else results
            require(len(entries) == len(c['checks']) and all(r.get('passed') is True for r in entries), f'mathematical checks failed: {results}')
    require(total_actions <= limits['max_total_actions'], 'total event budget')
    require(abs(previous_end - duration) <= 1/30 + 1e-8, 'chapters must cover full audio tail; gaps hold preceding chapter')
    return copy.deepcopy(raw)

def contract():
    return {'schema_version': SCHEMA_VERSION, 'capability_version': CAPABILITY_VERSION, 'production_profiles': {key: dict(value) for key, value in PRODUCTION_PROFILES.items()}, 'production_profile_default': 'standard', 'render_timeout_seconds': 43200, 'extensions': ['long_lesson', 'dynamic_sector', 'cylinder_net', 'cone_net', 'conic', 'on_conic', 'conic_tangent', 'segment_arrow', 'text_transform', 'formula_group', 'continuous_text_copy', 'coordinate_axes_label_offsets', 'point_on_quadratic', 'point_rotate', 'point_scale', 'chapter_heading'], 'text_transform_rules': {'items': '1..48 unique visible text IDs; each requires id and finite scene-coordinate position; optional text <=64 chars; optional via is a finite safe-canvas point reached halfway through the same play', 'semantics': 'one play; preserve ID/style/group; unchanged text moves without recreation; changed text fades through zero without glyph morphing; repeat for further movement, then translate_copy/hide; point move unchanged'}, 'text_budget': {'ungrouped_plus_groups': 6, 'visible_per_group': 24, 'visible_total': 48, 'visible_characters': 200}, 'object_fields': OBJECT_FIELDS, 'action_fields': ACTION_FIELDS,
            'coordinate_axes_label_offsets': {'keys': 'origin or canonical x:<tick>/y:<tick> in declared ticks', 'units': 'screen units relative to true tick/origin, replaces default offset', 'max_abs_component': 1.5, 'defaults_unchanged': True, 'numeric_key_rule': 'plain decimal, no redundant zeros/sign/exponent; zero uses origin label'},
            'heading_mode': {'values':['standard','chapter'], 'default':'standard', 'chapter':'single current chapter title in selected style (classic: warm-yellow); no global heading or duplicate subtitle'},
            'alignment_sources': {'default':'local_whisper', 'optional':['qwen_forced_aligner'], 'qwen_contract_version':1, 'qwen_route':'explicit alignment_path with timing_source=qwen_forced_aligner; immutable known-text chunk inference, direct acoustic envelopes, exact PCM offsets and source ranges', 'runtime_dependency_policy':'optional external aligner; default installation and Whisper fallback unchanged', 'details':'geometry/qwen_alignment.md'},
            'chapter_optional_fields': ['plot_rect','formula_rect','parameters','presentation','proof_layout'],
            'proof_layout': {'default':'single','values':['single','steps'],'steps':'paper_guided only; standard retains heading/problem, freeform suppresses all automatic heading/card/problem; both keep clock/plot_rect/formula_rect; classic rejected by compiler/runner/runtime', 'object_budget':{'single':120,'steps':144}, 'other_budgets':'unchanged'},
            'paper_palette': {'optional':'reference_yellow','scope':'paper_guided only; background #FAF4D0 for all chapters; omitted preserves old style; no other color changes'},
            'typography': {'objects':['text','point'],'default':'body','values':['body','math','serif','heavy'],'body':'unchanged Microsoft YaHei','heavy':'paper_guided text only: Microsoft YaHei BOLD at any font_size (kinetic headline type); opt-in, other typographies unchanged','math':'Cambria italic; math symbols use Cambria Math regular; Chinese/fullwidth text uses SimSun regular','serif':'SimSun regular, mathematical symbols use Cambria Math regular','continuity':'text_transform preserves typography; continuous text copy and point copy require matching typography; point copy also requires matching label_mask; no arbitrary font or transform style field','formula_action':'unchanged; use declared text for styled formula rows'},
            'label_mask': {'object':'point','default':True,'false':'no label background rectangle; keep label z-index and explicit offset planning'},
            'panel_shadow_style': {'default':'soft','values':['soft','outline'],'soft':'unchanged exposed strips, offset [0.06,-0.06]','outline':{'requires':'shadow:true','offset':list(PANEL_OUTLINE_SHADOW_OFFSET),'color':'#7C7965','stroke_width':1,'fill_opacity':0},'bounds':'use selected offset plus conservative stroke padding; no extra object budget'},
            'panel': {'coordinates':'scene rect [cx,cy,w,h], positive finite sizes; full bounds including shadow and conservative stroke padding stay inside canvas safe area', 'defaults':{'color':'#D4D7CF','fill_color':'#FFFFFF','fill_opacity':1,'stroke_width':1,'shadow':False}, 'shadow':{'offset':list(PANEL_SHADOW_OFFSET),'color':'#263633','opacity':.1,'coverage':'only exposed parts outside the face; transparent panels do not tint their interior'}, 'accent':'optional hex color; bottom edge only, width max(3,stroke_width)', 'layers':'shadow below panel; panel behind geometry and text, independent of reveal order; no text content', 'actions':['reveal fade','hide'], 'text':'separate text objects retain existing budgets and text_transform; no new arbitrary code or z_index field'},
            'presentation': {'default':'standard','values':['standard','freeform'],'freeform':'No automatic heading or paper card; declared primitives own composition, with no automatic shadow. Entry/exit fade preserves live scene painter order and shares the first explicit action duration (including hold). Without actions, it starts at the chapter boundary for up to 0.5s within that chapter, frame-quantized; with no available frame, cleanup is immediate. Action clock remains absolute. Pure standard transitions are unchanged.'},
            'interval_scalar': 'finite number | -inf/+inf on correct open side | {parameter,scale,offset}; no eval',
            'interval_rules': ['Empty when left>right or equal unless both closed','Same-axis connected union only','Finite off-viewport endpoints have no false caps'],
            'curved_region_rules': ['sector/circular_segment: center is a point reference; 0<radius<=10000', 'sector radius/start_angle/sweep_angle: finite numeric or exact {parameter,scale,offset}; degrees, +x start, CCW sweep in [0,360]; 0 is empty, 360 is disk; set_parameter updates arc and endpoints', 'circular_segment remains static numeric with 0<sweep_angle<360', 'segment closes the swept arc with a chord; sweep>180 selects the major segment', 'move the center point to translate; hide removes visibility; no Boolean subtraction'],
            'developable_surface_rules': {'types':['cylinder_net','cone_net'], 'dimensions':'fixed finite radius,height/slant in [1e-6,10000]; cone slant>radius', 'unfold':'finite scalar or exact {parameter,scale,offset}, resolved [0,1]; set_parameter; no eval', 'position':'optional fixed world xy offset, default [0,0], not multiplied by display_scale', 'display_scale':'optional fixed finite number in [1e-6,10000], default 1; projected coordinates only, intrinsic dimensions unchanged', 'scope':'lateral surface only, no caps; conic is unrelated', 'cylinder':'s in [-pi*r,pi*r], z in [-h/2,h/2], k=(1-p)/r; (sin(k*s)/k,z,(cos(k*s)-1)/k); p=1 analytic (s,z,0)', 'cone':'beta=r/slant; b=1-(1-beta)*(1-p)^2; theta in [-pi*beta,pi*beta], rho in [0,slant]; (rho*b*sin(theta/b),-rho*sqrt(1-b*b),rho*b*cos(theta/b))', 'rendering':'fixed 48x8 material mesh, orthographic rigid view rotation, depth sorted; final faces camera; measurements intrinsic/flattened, not projected', 'final':'cylinder width 2*pi*r and height h; cone radius slant, angle 360*r/slant degrees, arc 2*pi*r, area pi*r*slant'},
            'reciprocal_branches': {'values': ['both', 'positive_x', 'negative_x'], 'default': 'both', 'selection': 'mathematical x sign, independent of k; rendering only'},
            'reciprocal_branch_example': 'examples/reciprocal_branches.json',
            'reciprocal_rules': ['y=k/x; nonzero finite k; existing affine scalars only', 'point derive={type:on_reciprocal,curve:id,x:scalar}; projections/lines/polygons follow', 'set_parameter keeps k and x signs; move requires a free point', 'separate cubic branches clipped to world_bounds; tolerance is max vertical error in world units, default .001, range 1e-8..05; budget 8192 segments'],
            'rotation_point_example': 'examples/rotation_points.json',
            'conic_rules': {'kinds': ['ellipse','hyperbola','parabola'], 'center': 'fixed finite xy; abs<=10000', 'shape': 'fixed a,b in [1e-6,10000]; nonzero signed p with same magnitude bounds; y^2=4px', 'hyperbola_branch': 'required positive_x|negative_x|both; point branch required positive_x|negative_x and must be present', 'parameterization': 'ellipse=(a cos t,b sin t); hyperbola=(sign*a cosh t,b sinh t); parabola=(p*t*t,2*p*t); plus center', 't_bounds': 'hyperbola +/-12; others +/-10000; affine scalar allowed', 'rendering': 'analytic viewport clipping, separate paths, bounded chord error tolerance default .001 [1e-8,.05], 8192 segments max', 'rotation': False}, 'arrow_rules': 'boolean on segment only; zero length is empty; clipped endpoint gets a visible direction tip',
            'point_scale_example': 'examples/scale_points.json',
            'point_derivations': {'scale': {'required': ['type','source','center','factor'], 'additional_fields': False, 'source': 'point id', 'center': 'point id; source may equal center; no dependency cycles', 'factor': 'finite number or exact {parameter,scale,offset}; resolved 0<factor<=10000; no eval', 'position': 'center + factor*(source-center)', 'animation': 'set_parameter; source and center recomputed each frame; shared parameter can drive sector radius; derived points cannot move directly', 'parameter_range': [-10000,10000]}, 'on_conic': {'required': ['type','curve','t'], 'hyperbola_required': ['branch'], 'additional_fields': False}, 'conic_tangent': {'required': ['type','source','scale'], 'additional_fields': False, 'source': 'on_conic point id', 'scale': 'finite number or exact affine scalar, abs<=10000', 'position': 'P+scale*P_derivative(t)'}, 'rotate': {'required': ['type', 'source', 'center', 'angle'], 'additional_fields': False, 'source': 'point id', 'center': 'point id; may equal source without a dependency cycle', 'angle': 'finite degrees or exact {parameter,scale,offset}; positive CCW, negative CW', 'position': 'center + R(angle)*(source-center)', 'animation': 'set_parameter; dependencies recomputed each frame, labels and edges follow', 'parameter_range': [-10000, 10000]}, 'on_quadratic': {'required': ['type', 'curve', 'x'], 'additional_fields': False, 'curve': 'quadratic id', 'x': 'finite number or exact {parameter,scale,offset}', 'position': '[x, a*(x-h)^2+k]', 'parameter_range': [-10000, 10000], 'viewport_is_not_domain': True}},
            'quadratic_point_example': 'examples/quadratic_derived_points.json',
            'quadratic_scalar': 'finite number | {parameter,scale,offset}; no infinity and no eval',
            'quadratic_rules': ['y=a(x-h)^2+k; a is nonzero throughout parameter actions', 'Roots are distinct real roots; tangency has one root', 'Exact cubic Bezier groups clipped to world_bounds; disconnected arms stay separate', 'Features are direct render objects and cannot be used as point references; use point.derive on_quadratic for downstream geometry', 'quadratic_point checks point/vertex/y_intercept features; axis has no label'],
            'check_fields': CHECK_FIELDS, 'reference': 'references/geometry.md',
            'highlight_rules': 'Color-only foreground pulse (scale=1); dots, glyphs and line coordinates stay fixed; text background masks retain geometry and style',
            'highlight_emphasis': {'style': 'emphasis', 'semantics': 'Opt-in single ids group pulse; visible strokes peak at 1.45x width, paper color #244F46, classic color #FFD166; original color/width/opacity restored at end; masks, coordinates and z-index unchanged; no hidden objects revealed', 'default': 'Omit style for the unchanged legacy color-only pulse', 'scope': 'Temporary emphasis only; no persistent dimming or layer reordering; existing sector/reveal(draw)/rotate/set_parameter supply area fill, drawing and motion'},
            'quality': {'preview': 'long edge <=720, no upscale, even dimensions, aspect preserved (rounding for unusual ratios), 30fps', 'final': 'canvas at 60fps'},
            'director_prompt': 'assets/engine/prompts/geometry_director.md',
            'reciprocal_example': 'examples/reciprocal_motion.json',
            'example': 'examples/geometry_minimal.json', 'analyze': 'scripts/video.ps1 analyze',
            'timing': 'absolute audio seconds; SHA-bound raw Whisper files + exact original tokens; derived alignment requires original alignment backlinks and sample-verified PCM offsets; source-bound cue trigger separate from reviewed sentence motion window; no character interpolation',
            'whisper_audit_requirements': {'alignment':'raw_evidence path/sha256 to original full JSON; exact token count/order/raw object/text/times including null; derived provenance_sources + token.origin with verified PCM sample offset', 'source':'master_char_start/end and exact anchor_text; global spans require audit.source_document path/sha256 and narration_master_char_start', 'trigger':'trigger_evidence.anchor_ids and alignment_pairs(master_char,expected,raw_token_id) inside actual cue', 'motion':'motion_window master_char_start/end,text,anchor_ids; outside cue envelope requires same-cue prior action and explicit bounded review; following explanation is not a replacement onset', 'synthetic':'unit-test explicit synthetic_fixture opt-in only; production runner never opts in'},
            'final_gate': 'matching preview and explicit visual_review.json evidence required'}
