"""Short silent capability preview plus decoded-pixel legacy comparison."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import av
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/engine'))
from geometry.runtime import GeometryScene
from geometry.schema import validate_spec
from geometry.pipeline import engine_hash
from manim import tempconfig


def fixture():
    objects = [
        dict(id='O', type='point', xy=[0, 0], label='O', label_offset=[-.3, -.3]),
        dict(id='A', type='point', xy=[2, 0], label='A', label_offset=[.3, -.3]),
        dict(id='B', type='point', xy=[1, 2], label='B', label_offset=[0, .35]),
        dict(id='OA', type='line', a='O', b='A', color='#A3B4A9', stroke_width=3),
        dict(id='OB', type='line', a='O', b='B', color='#A3B4A9', stroke_width=3),
        dict(id='AB', type='line', a='A', b='B', color='#A3B4A9', stroke_width=3),
        dict(id='ticks', type='ticks', segment='OB', count=2, color='#718C7E'),
        dict(id='angle', type='angle', vertex='O', arm1='A', arm2='B', color='#718C7E', radius=.45),
        dict(id='region', type='sector', center='O', radius=.45, start_angle=0, sweep_angle=63.43494882, color='#A3B4A9', stroke_width=.5, fill_opacity=.12),
        dict(id='R', type='point', derive=dict(type='rotate', source='A', center='O', angle=dict(parameter='theta', scale=1, offset=0))),
        dict(id='E', type='point', derive=dict(type='scale', source='R', center='O', factor=dict(parameter='length', scale=1, offset=0)), label='E', label_offset=[.3, -.9]),
        dict(id='OE', type='line', a='O', b='E', color='#718C7E', stroke_width=3),
    ]
    actions = [
        dict(type='reveal', at=.5, duration=.5, ids=['region','OA','OB','AB','angle','ticks','O','A','B'], style='draw'),
        dict(type='highlight', at=1.2, duration=1, ids=['OA','OB','angle','ticks'], style='emphasis'),
        dict(type='reveal', at=2.3, duration=.2, ids=['OE','E'], style='draw'),
        dict(type='set_parameter', at=2.5, duration=1, parameter='theta', value=-35),
        dict(type='set_parameter', at=3.8, duration=1, parameter='length', value=1.4),
        dict(type='highlight', at=5, duration=1, ids=['OE','E'], style='emphasis'),
        dict(type='hide', at=6.3, duration=.3, ids=['OE','E']),
    ]
    return dict(schema_version='geometry-1.0', title='Geometry emphasis', audio_duration=7,
                narration='Synthetic silent capability fixture; no production audio.',
                canvas=dict(width=3840, height=2880, fps=60), chapters=[dict(
                    id='demo', title='描线 · 比较 · 旋转 · 延长', start=0, end=7,
                    world_bounds=[-.6, 3.4, -2, 2.7], parameters=dict(theta=0, length=1),
                    problem=[], objects=objects, actions=actions, checks=[])])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    p.add_argument('--baseline-runtime', required=True)
    args = p.parse_args()
    out = Path(args.output).resolve()
    if out == ROOT or ROOT in out.parents: raise ValueError('Evidence must be outside Skill')
    out.mkdir(parents=True, exist_ok=True)
    spec = fixture()
    validate_spec(spec)
    (out / 'spec.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
    module_spec = importlib.util.spec_from_file_location('geometry.baseline_runtime', args.baseline_runtime)
    baseline = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(baseline)
    legacy = copy.deepcopy(spec)
    for action in legacy['chapters'][0]['actions']:
        if action['type'] == 'highlight': action.pop('style')
    evidence = dict(engine_root=str(ROOT / 'assets/engine'), engine_hash=engine_hash(ROOT / 'assets/engine'),
                    scope='7s silent synthetic capability fixture; no production alignment or audio review', videos={})
    for name, base, current in [('emphasis', GeometryScene, spec), ('legacy_before', baseline.GeometryScene, legacy), ('legacy_after', GeometryScene, legacy)]:
        os.environ['GEOMETRY_REPORT_PATH'] = str(out / (name + '-report.json'))
        scene_type = type('EmphasisSmoke', (base,), dict(spec=current, selected_style='paper_guided'))
        with tempconfig(dict(pixel_width=800, pixel_height=600, frame_rate=20, media_dir=str(out / name),
                             output_file=name, disable_caching=True, write_to_movie=True, verbosity='WARNING')):
            scene = scene_type()
            scene.render()
            movie = Path(scene.renderer.file_writer.movie_file_path)
        evidence['videos'][name] = dict(path=str(movie), sha256=hashlib.sha256(movie.read_bytes()).hexdigest())
    def decoded(name):
        with av.open(evidence['videos'][name]['path']) as container:
            return [f.to_ndarray(format='rgb24') for f in container.decode(video=0)]
    before, after = decoded('legacy_before'), decoded('legacy_after')
    assert len(before) == len(after) == 140
    assert all(np.array_equal(a, b) for a, b in zip(before, after))
    evidence['legacy_pixel_comparison'] = dict(equal=True, decoded_frames=140, size=[800,600], fps=20)
    frames = decoded('emphasis')
    assert len(frames) == 140
    from PIL import Image
    evidence['frames'] = []
    for t in (1.1, 1.7, 2.2, 3, 3.5, 4.3, 4.8, 5.5, 6.1, 6.8):
        path = out / f'frame-{t:.1f}.png'
        Image.fromarray(frames[round(t*20)]).save(path)
        evidence['frames'].append(dict(time=t, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    evidence['visual_review'] = 'pending'
    (out / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence))


if __name__ == '__main__': main()
