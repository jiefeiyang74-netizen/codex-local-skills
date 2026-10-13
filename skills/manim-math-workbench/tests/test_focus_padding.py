"""Real glyph/box geometry checks; no Scene.render or video generation."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from manim import FadeIn, FadeOut, Text, VGroup, tempconfig, LEFT, RIGHT

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/engine'))
from geometry.runtime import GeometryScene


class FocusPaddingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.context = tempconfig(dict(media_dir=self.tmp.name))
        self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def fixture(self, neighbor_text, terms, gap):
        selected = VGroup(*[Text(s, font='Microsoft YaHei', font_size=44) for s in terms])
        selected.arrange(RIGHT, buff=.10)
        neighbor = Text(neighbor_text, font='Microsoft YaHei', font_size=44)
        neighbor.next_to(selected, LEFT, buff=gap)
        mobs = {'neighbor': neighbor, **{f'e{i}': m for i, m in enumerate(selected)}}
        scene = SimpleNamespace(mobs=mobs, live=set(mobs), focus_box=None,
                                time=0., runtime_stats={'focus_rebuilds': 0})
        scene.calls = []
        def play_to(at, *animations):
            scene.calls.extend(animations)
            scene.time = at
        scene.play_to = play_to
        scene.until = lambda at: setattr(scene, 'time', at)
        scene.remove = lambda *mobs: None
        scene.record = lambda *args: None
        GeometryScene.perform(scene, dict(type='focus', ids=[f'e{i}' for i in range(len(selected))],
                                         at=0., duration=.5))
        return scene, selected, neighbor

    def assert_clear_and_enclosed(self, box, selected, neighbor):
        # Conservative stroke allowance at 4K portrait, 16 scene units high.
        stroke_margin = 2 * 16 / 3840
        self.assertGreater(box.get_left()[0] - neighbor.get_right()[0], stroke_margin)
        self.assertGreater(selected.get_left()[0] - box.get_left()[0], stroke_margin)
        self.assertGreater(box.get_right()[0] - selected.get_right()[0], stroke_margin)
        # Entire glyph bounding rectangle fits below the rounded corner region.
        self.assertGreater(box.get_top()[1] - selected.get_top()[1], .15 + stroke_margin)
        self.assertGreater(selected.get_bottom()[1] - box.get_bottom()[1], .15 + stroke_margin)
        self.assertAlmostEqual(box.width, selected.width + .16)
        self.assertAlmostEqual(box.height, selected.height + .4)
        self.assertEqual(len(box.submobjects), 36)
        for dash in box.submobjects:
            self.assertAlmostEqual(dash.get_stroke_width(), 2)
            self.assertEqual(dash.get_color().to_hex().upper(), '#FF5252')

    def test_neighbor_eight_and_minus_clear_with_complete_selected_glyphs(self):
        for neighbor, terms, gap in [('8', ['+4a/b', '+3b/a'], .12),
                                      ('−', ['(t−5)²'], .14)]:
            with self.subTest(neighbor=neighbor):
                scene, selected, glyph = self.fixture(neighbor, terms, gap)
                # Regression setup: the old 0.2-side border cuts the neighbor bbox.
                old_left = selected.get_left()[0] - .2
                self.assertLess(glyph.get_left()[0], old_left)
                self.assertLess(old_left, glyph.get_right()[0])
                self.assert_clear_and_enclosed(scene.focus_box, selected, glyph)
                self.assertTrue(any(isinstance(a, FadeIn) for a in scene.calls))

    def test_focus_tracks_translation_and_resizing_without_widening_padding(self):
        scene, selected, glyph = self.fixture('−', ['(t−5)²'], .14)
        box = scene.focus_box
        for scale, shift in [(1.1, [.2, .1, 0]), (.9, [-.3, -.1, 0])]:
            selected.scale(scale).shift(shift)
            glyph.next_to(selected, LEFT, buff=.14)
            box.update(0)
            self.assert_clear_and_enclosed(box, selected, glyph)
            np.testing.assert_allclose(box.get_center(), selected.get_center(), atol=1e-8)
        self.assertEqual(scene.runtime_stats['focus_rebuilds'], 2)
        box.update(0)
        self.assertEqual(scene.runtime_stats['focus_rebuilds'], 2)

    def test_focus_replacement_and_clear_preserve_fade_and_updater_cleanup(self):
        scene, _, _ = self.fixture('8', ['+4a/b', '+3b/a'], .12)
        old = scene.focus_box
        GeometryScene.perform(scene, dict(type='focus', ids=['e1'], at=.5, duration=.5))
        self.assertFalse(old.updaters)
        self.assertIsNot(scene.focus_box, old)
        self.assertTrue(any(isinstance(a, FadeOut) for a in scene.calls))
        current = scene.focus_box
        GeometryScene.perform(scene, dict(type='focus', ids=[], at=1., duration=.5))
        self.assertIsNone(scene.focus_box)
        self.assertFalse(current.updaters)


if __name__ == '__main__':
    unittest.main()
