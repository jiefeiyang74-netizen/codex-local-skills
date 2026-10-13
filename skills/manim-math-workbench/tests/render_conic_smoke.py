"""Render a public synthetic fixture; outputs must be outside the Skill."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from geometry.schema import validate_spec
from geometry.runtime import GeometryScene
from geometry.pipeline import engine_hash
from manim import tempconfig


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    out=Path(args.output).resolve()
    if out==ROOT or ROOT in out.parents:
        raise ValueError('Render evidence must be outside the Skill package')
    out.mkdir(parents=True,exist_ok=True)
    spec=json.loads((ROOT/'examples/conic_motion.json').read_text(encoding='utf-8'))
    base=spec['chapters'][0]
    spec['chapters']=[]
    for i,kind in enumerate(['ellipse','hyperbola','parabola']):
        chapter=copy.deepcopy(base)
        chapter.update(id=kind,title=kind+' tangent and signed projection',start=5*i,end=5*(i+1))
        curve=chapter['objects'][i];curve['id']='c';curve['color']='#52C7EA'
        chapter['objects']=[curve]+chapter['objects'][3:]
        if kind=='hyperbola':chapter['objects'][1]['derive']['branch']='positive_x'
        for action in chapter['actions']:action['at']+=5*i
        chapter['actions'][0]['ids']=['c','P','velocity','projection','normal']
        spec['chapters'].append(chapter)
    spec['audio_duration']=15
    validate_spec(spec)
    (out/'spec.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    os.environ['GEOMETRY_REPORT_PATH']=str(out/'geometry-report.json')
    class ConicSmoke(GeometryScene):pass
    ConicSmoke.spec=spec
    with tempconfig(dict(pixel_width=640,pixel_height=360,frame_rate=12,media_dir=str(out/'media'),
                         output_file='conic_smoke',disable_caching=True,write_to_movie=True,verbosity='WARNING')):
        scene=ConicSmoke();scene.render()
        movie=Path(scene.renderer.file_writer.movie_file_path)
    evidence=dict(engine_root=str(ROOT/'assets/engine'),engine_hash=engine_hash(ROOT/'assets/engine'),
                  video=str(movie),video_sha256=hashlib.sha256(movie.read_bytes()).hexdigest(),
                  scope='synthetic silent; no production audio alignment',visual_review='pending')
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence))


if __name__=='__main__':main()
