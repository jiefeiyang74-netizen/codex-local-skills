"""Opt-in emphasis: style restoration, no geometry/layer changes, strict schema."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/engine'))
from manim import BackgroundRectangle, Dot, Line, Text, VGroup, tempconfig
from geometry.runtime import GeometryScene, MaskSafeEmphasis, MaskSafeIndicate
from geometry.schema import validate_spec, GeometryValidationError


class EmphasisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = tempconfig({'media_dir': self.tmp.name})
        self.cfg.__enter__()
        self.addCleanup(self.cfg.__exit__, None, None, None)

    def test_repeat_restores_exact_style_and_preserves_masks_layers_and_geometry(self):
        label = Text('A', font='Microsoft YaHei', font_size=28).set_z_index(10)
        label.add_background_rectangle(color='#F6F4EC', opacity=1)
        label.background_rectangle.set_z_index(9)
        line = Line([-1, 0, 0], [1, 0, 0], color='#9EAEA5', stroke_width=3)
        line.set_stroke(opacity=.37).set_z_index(2)
        absent = line.copy().set_stroke(opacity=0)
        dot = Dot([0, 1, 0], color='#AAB8AE').set_z_index(4)
        ticks = VGroup(*[Line([x, -.1, 0], [x, .1, 0], color='#B64A35', stroke_width=2)
                        for x in (-.08, .08)]).set_z_index(3)
        mob = VGroup(line, absent, dot, label, ticks)
        original = mob.copy()
        for repeat in range(2):
            anim = MaskSafeEmphasis(mob, color='#244F46', scale_factor=1)
            anim.begin()
            for alpha in (0, .125, .25, .5, .75, .875, 1):
                anim.interpolate(alpha)
                for now, old in zip(mob.get_family(), original.get_family()):
                    np.testing.assert_allclose(now.points, old.points, atol=1e-12)
                    self.assertEqual(now.z_index, old.z_index)
                    np.testing.assert_allclose(now.fill_rgbas[:, 3], old.fill_rgbas[:, 3])
                    np.testing.assert_allclose(now.stroke_rgbas[:, 3], old.stroke_rgbas[:, 3])
                    if isinstance(old, BackgroundRectangle):
                        np.testing.assert_allclose(now.fill_rgbas, old.fill_rgbas)
                        np.testing.assert_allclose(now.stroke_rgbas, old.stroke_rgbas)
                        self.assertEqual(now.stroke_width, old.stroke_width)
                if alpha == .5:
                    self.assertAlmostEqual(line.get_stroke_width(), 4.35)
                    self.assertAlmostEqual(absent.get_stroke_width(), 3)
            anim.finish()
            for now, old in zip(mob.get_family(), original.get_family()):
                np.testing.assert_allclose(now.fill_rgbas, old.fill_rgbas)
                np.testing.assert_allclose(now.stroke_rgbas, old.stroke_rgbas)
                np.testing.assert_allclose(now.stroke_width, old.stroke_width)

    def test_dispatch_default_and_hidden_objects(self):
        class Harness:
            perform = GeometryScene.perform
            def __init__(self):
                self.mobs = {'shown': Line(), 'hidden': Dot()}
                self.defs = {k: {'type': 'line'} for k in self.mobs}
                self.live = {'shown'}
                self.paper = True
                self.time = 0
                self.animations = []
            def play_to(self, end, *animations):
                self.animations = animations
                self.time = end
            def record(self, *args): pass
            def until(self, at): self.time = at
        h = Harness()
        for style, expected in ((None, MaskSafeIndicate), ('emphasis', MaskSafeEmphasis)):
            a = dict(type='highlight', at=h.time, duration=1, ids=['shown', 'hidden'])
            if style: a['style'] = style
            h.perform(a)
            self.assertEqual(len(h.animations), 1)
            self.assertIs(type(h.animations[0]), expected)
            self.assertEqual(h.live, {'shown'})

    def test_contract_rejects_unknown_style_and_hidden_target(self):
        spec = json.loads((ROOT / 'examples/rotation_points.json').read_text())
        chapter = spec['chapters'][0]
        chapter['actions'] = chapter['actions'][:1] + [
            dict(type='highlight', at=1, duration=1, ids=['edge'], style='emphasis')]
        validate_spec(spec)
        for value in ('draw', 'pulse', None, True, {}, []):
            bad = copy.deepcopy(spec)
            bad['chapters'][0]['actions'][1]['style'] = value
            with self.assertRaises(GeometryValidationError): validate_spec(bad)
        bad = copy.deepcopy(spec)
        bad['chapters'][0]['actions'][1]['ids'] = ['O']
        with self.assertRaises(GeometryValidationError): validate_spec(bad)


if __name__ == '__main__': unittest.main()
