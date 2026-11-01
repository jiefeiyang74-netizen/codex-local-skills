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
    spec=json.loads((ROOT/'examples/scale_points.json').read_text(encoding='utf-8'))
    validate_spec(spec)
    (out/'spec.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    os.environ['GEOMETRY_REPORT_PATH']=str(out/'geometry-report.json')
    class ScaleSmoke(GeometryScene):pass
    ScaleSmoke.spec=spec
    with tempconfig(dict(pixel_width=640,pixel_height=360,frame_rate=12,media_dir=str(out/'media'),
                         output_file='scale_smoke',disable_caching=True,write_to_movie=True,verbosity='WARNING')):
        scene=ScaleSmoke();scene.render()
        movie=Path(scene.renderer.file_writer.movie_file_path)
    evidence=dict(engine_root=str(ROOT/'assets/engine'),engine_hash=engine_hash(ROOT/'assets/engine'),
                  video=str(movie),video_sha256=hashlib.sha256(movie.read_bytes()).hexdigest(),
                  scope='synthetic silent; no production audio alignment',visual_review='pending')
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence))


if __name__=='__main__':main()
