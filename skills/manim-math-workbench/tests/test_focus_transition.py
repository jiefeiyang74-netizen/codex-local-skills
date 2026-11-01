"""Sample real Manim animations in memory, without rendering a video."""
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from manim import FadeIn, FadeOut, tempconfig, config
from manim.animation.animation import prepare_animation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/engine'))
from geometry.runtime import GeometryScene


class Harness:
    text = GeometryScene.text
    perform = GeometryScene.perform

    def __init__(self, labels, positions, at):
        self.paper = False
        self.text_cache = {}
        self.defs = {f'e{i}': dict(type='text', text=t, font_size=32, position=[x, 0])
                     for i, (t, x) in enumerate(zip(labels, positions))}
        self.mobs = {k: self.text(o['text'], 32).move_to([*o['position'], 0])
                     for k, o in self.defs.items()}
        self.live = set(self.mobs)
        self.focus_box = None
        self.time = round(at * config.frame_rate) / config.frame_rate
        self.runtime_stats = {'focus_rebuilds': 0}
        self.phases = []
        self.removed = []
        self.events = []
        self.expect_hidden_motion = True

    def remove(self, *mobs):
        self.removed.extend(mobs)

    def add(self, *mobs):
        pass

    def until(self, at):
        self.time = round(at * config.frame_rate) / config.frame_rate

    def record(self, *args):
        self.events.append(args)

    def play_to(self, at, *animations):
        end = round(at * config.frame_rate) / config.frame_rate
        frames = round((end - self.time) * config.frame_rate)
        assert frames >= 1
        animations = [prepare_animation(a) for a in animations]
        boxes = [a.mobject for a in animations if isinstance(a, (FadeIn, FadeOut))]
        initial = [b.get_all_points().copy() for b in boxes]
        for a in animations:
            a.begin()
        samples = []
        for i in range(frames + 1):
            for a in animations:
                a.interpolate(i / frames)
            if self.focus_box is not None:
                self.focus_box.update(0)
            for b, points in zip(boxes, initial):
                np.testing.assert_allclose(b.get_all_points(), points, atol=1e-8)
            if not boxes and self.expect_hidden_motion:
                assert self.focus_box is None, 'Visible focus during glyph transformation'
            samples.append([max(float(d.get_stroke_opacity()) for d in b.submobjects) for b in boxes])
        for a in animations:
            a.finish()
            a.clean_up_from_scene(self)
        self.phases.append((animations, samples, end))
        self.time = end


class FocusTransitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ctx = tempconfig(dict(media_dir=self.tmp.name))
        self.ctx.__enter__()
        self.addCleanup(self.ctx.__exit__, None, None, None)

    def test_four_boundary_transitions_at_preview_and_final_rates(self):
        cases = [
            (30.200, 29.30, .9, ['(2+3b/a)', '×', '(1+2a/b)'],
             [-1.179238, 0, 1.179238], ['2+6', '+4a/b', '+3b/a'],
             [-1.41791, -.221094, 1.196816]),
            (177.583, 176.72, .85, ['(x+1)²', '/', '(x−2)'],
             [-.801895, .09502, .896914], ['(t+3)²', '/', 't'],
             [-.33207, .514844, .846914]),
            (371.550, 370.79, .75, ['(x+4/x)', '×', '(10−x−4/x)'],
             [-1.454238, -.425, 1.029238], ['t', '×', '(10−t)'],
             [-.879238, -.544824, .334414]),
            (373.700, 373.24, .45, ['t', '×', '(10−t)'],
             [-.879238, -.544824, .334414], ['10t', '−', 't²'],
             [-.418594, .155469, .574063]),
        ]
        for fps in (30, 60):
            with tempconfig(dict(frame_rate=fps)):
                for timestamp, at, duration, before, positions, after, targets in cases:
                    with self.subTest(fps=fps, boundary=timestamp):
                        h = Harness(before, positions, at)
                        old = GeometryScene._make_focus_box(h, [h.mobs['e2']])
                        h.focus_box = old
                        h.perform(dict(type='text_transform', at=at, duration=duration,
                                       items=[dict(id=f'e{i}', text=t, position=[x, 0],
                                                   via=[positions[i], 0])
                                              for i, (t, x) in enumerate(zip(after, targets))]))
                        self.assertEqual(len(h.phases), 3)
                        self.assertIsInstance(h.phases[0][0][0], FadeOut)
                        self.assertIsInstance(h.phases[-1][0][0], FadeIn)
                        self.assertAlmostEqual(h.phases[0][1][-1][0], 0)
                        self.assertAlmostEqual(h.phases[-1][1][0][0], 0)
                        self.assertAlmostEqual(h.phases[-1][1][-1][0], 1)
                        self.assertIn(old, h.removed)
                        self.assertFalse(old.updaters)
                        self.assertTrue(all(d.get_stroke_opacity() == 0 for d in old.submobjects))
                        self.assertLessEqual(abs(h.time - (at + duration)), .5/fps + 1e-8)
                        self.assertEqual(h.time, round((at + duration)*fps)/fps)
                        box = h.focus_box
                        self.assertGreater(box.get_left()[0], max(h.mobs[k].get_right()[0] for k in ('e0', 'e1')))
                        fresh = GeometryScene._make_focus_box(h, [h.mobs['e2']])
                        np.testing.assert_allclose(box.get_all_points(), fresh.get_all_points(), atol=1e-8)
                        points = box.get_all_points().copy()
                        box.update(0)
                        np.testing.assert_allclose(box.get_all_points(), points, atol=1e-8)

    def test_different_targets_never_translate_a_visible_box(self):
        h = Harness(['left', 'middle', 'right'], [-3, 0, 3], 0)
        h.perform(dict(type='focus', ids=['e0'], at=0, duration=.5))
        self.assertEqual(len(h.phases), 1)  # Initial appearance unchanged.
        old = h.focus_box
        h.perform(dict(type='focus', ids=['e2'], at=.5, duration=.5))
        self.assertEqual(len(h.phases), 3)
        self.assertIn(old, h.removed)
        self.assertFalse(old.updaters)
        self.assertAlmostEqual(h.time, 1)
        self.assertGreater(h.focus_box.get_left()[0], h.mobs['e1'].get_right()[0])
        h.perform(dict(type='focus', ids=['e2'], at=1, duration=.5))
        self.assertEqual(len(h.phases), 5)  # Preserve same-target fade behavior.
        self.assertAlmostEqual(h.time, 1.5)

    def test_unchanged_text_keeps_active_focus(self):
        h = Harness(['left', '+', 'right'], [-3, 0, 3], 0)
        h.expect_hidden_motion = False
        old = GeometryScene._make_focus_box(h, [h.mobs['e2']])
        h.focus_box = old
        h.perform(dict(type='text_transform', at=0, duration=.5,
                       items=[dict(id='e2', text='right', position=[3, 0])]))
        self.assertIs(h.focus_box, old)
        self.assertEqual(len(h.phases), 1)
        self.assertFalse(h.removed)
        self.assertAlmostEqual(h.time, .5)

    def test_too_short_budget_fails_before_hiding_focus(self):
        with tempconfig(dict(frame_rate=30)):
            h = Harness(['left', '+', 'right'], [-3, 0, 3], 0)
            old = GeometryScene._make_focus_box(h, [h.mobs['e2']])
            h.focus_box = old
            with self.assertRaisesRegex(ValueError, 'at least three frames'):
                h.perform(dict(type='text_transform', at=0, duration=2/30,
                               items=[dict(id='e2', text='new', position=[3, 0])]))
            self.assertIs(h.focus_box, old)
            self.assertTrue(old.updaters)
            self.assertFalse(h.phases)
            self.assertEqual(h.time, 0)


if __name__ == '__main__':
    unittest.main()
