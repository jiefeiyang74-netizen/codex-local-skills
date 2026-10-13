"""Circle contract and trajectory tests, independent of Manim and any one video."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets' / 'engine'))
from geometry.math2d import (circle_motion_parameters, circular_position,
                            evaluate_checks, resolve_points)
from geometry.schema import GeometryValidationError, contract, validate_spec


def example():
    return {
        'schema_version': 'geometry-1.0', 'title': 'Circle',
        'audio_duration': 5, 'narration': 'Move and project the point.',
        'chapters': [{
            'id': 'c1', 'title': 'Circle', 'start': 0, 'end': 5,
            'world_bounds': [-3, 5, -3, 5], 'problem': [],
            'objects': [
                {'id': 'O', 'type': 'point', 'xy': [0, 0]},
                {'id': 'A', 'type': 'point', 'xy': [1, 0]},
                {'id': 'C', 'type': 'point', 'xy': [0, 0]},
                {'id': 'B', 'type': 'point', 'xy': [2, 0]},
                {'id': 'F', 'type': 'point', 'derive': {
                    'type': 'project', 'source': 'A', 'line': ['C', 'B']}},
                {'id': 'orbit', 'type': 'circle', 'center': 'O', 'radius': 1},
            ],
            'actions': [{'at': 1, 'duration': 1, 'type': 'move_on_circle',
                         'point': 'A', 'circle': 'orbit', 'angle': math.pi / 2}],
            'checks': [{'type': 'distance', 'points': ['A', 'O'], 'value': 1},
                       {'type': 'collinear', 'points': ['C', 'F', 'B']}],
        }],
    }


class CircleTests(unittest.TestCase):
    def test_legacy_schema_remains_accepted_and_capability_is_versioned(self):
        legacy = json.loads((ROOT / 'examples' / 'geometry_minimal.json').read_text(encoding='utf-8'))
        self.assertEqual(validate_spec(legacy), legacy)
        self.assertEqual(contract()['schema_version'], 'geometry-1.0')
        capability = contract()['capability_version']
        self.assertRegex(capability, r'^geometry-1\.\d+(?:\.\d+)?$')
        version = tuple(map(int, capability.removeprefix('geometry-').split('.')))
        version += (0,) * (3 - len(version))
        self.assertGreaterEqual(version, (1, 1, 0))
        # Later minor releases may reset patch to zero, but must retain the
        # actual circle geometry and motion contract introduced in 1.1.
        self.assertTrue({'id', 'type', 'center', 'radius'} <=
                        set(contract()['object_fields']['circle'][0].split()))
        self.assertTrue({'at', 'duration', 'type', 'point', 'circle', 'angle'} <=
                        set(contract()['action_fields']['move_on_circle'][0].split()))
        self.assertEqual(validate_spec(example()), example())

    def test_declared_circle_styles_are_accepted(self):
        spec = example()
        spec['chapters'][0]['objects'][-1].update(
            color='#FFDD00', stroke_width=2.5, dashed=True, fill_opacity=0.1)
        self.assertEqual(validate_spec(spec), spec)

    def test_direction_and_endpoints(self):
        center = [2, -3]
        np.testing.assert_allclose(circular_position([4, -3], center, math.pi / 2, 1), [2, -1], atol=1e-12)
        np.testing.assert_allclose(circular_position([4, -3], center, -math.pi / 2, 1), [2, -5], atol=1e-12)
        np.testing.assert_allclose(circular_position([4, -3], center, 8 * math.pi, 1), [4, -3], atol=1e-12)
        np.testing.assert_array_equal(circular_position([4, -3], center, math.pi, 0), [4, -3])

    def test_every_sample_preserves_radius_and_projection(self):
        chapter = example()['chapters'][0]
        center = np.array([8 / 3, 0.0])
        start = center + [0, 4 / 3]
        chapter['objects'][0]['xy'] = center.tolist()
        chapter['objects'][1]['xy'] = start.tolist()
        chapter['objects'][-1]['radius'] = 4 / 3
        for angle in (-8 * math.pi, -1.37, math.pi, 8 * math.pi):
            begin, origin = circle_motion_parameters(chapter['objects'], {}, 'A', 'orbit', angle)
            for fraction in np.linspace(0, 1, 1001):
                position = circular_position(begin, origin, angle, float(fraction))
                points = resolve_points(chapter['objects'], {'A': position})
                self.assertAlmostEqual(np.linalg.norm(points['A'] - center), 4 / 3, places=12)
                self.assertAlmostEqual(points['F'][0], points['A'][0], places=12)
                self.assertAlmostEqual(points['F'][1], 0, places=12)
                self.assertAlmostEqual(np.linalg.norm(points['A'] - points['C']),
                                       2 * np.linalg.norm(points['A'] - points['B']), places=12)

    def test_quarter_arc_midpoint_is_on_arc_not_on_chord(self):
        midpoint = circular_position([1, 0], [0, 0], math.pi / 2, 0.5)
        np.testing.assert_allclose(midpoint, [math.sqrt(0.5), math.sqrt(0.5)], atol=1e-12)
        self.assertGreater(np.linalg.norm(midpoint - np.array([0.5, 0.5])), 0.25)

    def test_move_circle_move_state_and_final_checks(self):
        spec = example()
        ch = spec['chapters'][0]
        ch['objects'][1]['xy'] = [-1, 0]
        ch['actions'] = [
            {'at': 1, 'duration': 1, 'type': 'move', 'positions': {'A': [1, 0]}},
            {'at': 2, 'duration': 1, 'type': 'move_on_circle', 'point': 'A',
             'circle': 'orbit', 'angle': math.pi / 2},
            {'at': 3, 'duration': 1, 'type': 'move', 'positions': {'A': [3, 4]}},
        ]
        ch['checks'] = [{'type': 'distance', 'points': ['A', 'O'], 'value': 5},
                        {'type': 'distance', 'points': ['F', 'C'], 'value': 3}]
        validate_spec(spec)
        self.assertTrue(all(check['passed'] for check in evaluate_checks(ch['objects'], ch['actions'], ch['checks'])))

    def test_consecutive_arcs_use_current_state(self):
        spec = example()
        ch = spec['chapters'][0]
        ch['actions'].append({'at': 2, 'duration': 1, 'type': 'move_on_circle',
                              'point': 'A', 'circle': 'orbit', 'angle': math.pi / 2})
        ch['checks'].append({'type': 'distance', 'points': ['A', 'B'], 'value': 3})
        validate_spec(spec)

    def test_moved_center_uses_current_overrides(self):
        spec = example()
        ch = spec['chapters'][0]
        ch['actions'].insert(0, {'at': 0.5, 'duration': 0.5, 'type': 'move',
                                'positions': {'O': [1, 0], 'A': [2, 0]}})
        ch['checks'].append({'type': 'distance', 'points': ['F', 'C'], 'value': 1})
        validate_spec(spec)

    def test_invalid_radius_and_angles_are_rejected(self):
        for radius in (0, -1, 10001, float('nan'), float('inf'), True):
            with self.subTest(radius=radius):
                spec = example()
                spec['chapters'][0]['objects'][-1]['radius'] = radius
                with self.assertRaises(ValueError):
                    validate_spec(spec)
        for angle in (0, 8 * math.pi + 0.001, -8 * math.pi - 0.001,
                      float('nan'), float('inf'), True, '1'):
            with self.subTest(angle=angle):
                spec = example()
                spec['chapters'][0]['actions'][0]['angle'] = angle
                with self.assertRaises(ValueError):
                    validate_spec(spec)

    def test_non_circle_reference_and_derived_moving_point_are_rejected(self):
        for field, value in [('circle', 'B'), ('circle', 'missing'), ('point', 'F')]:
            with self.subTest(field=field, value=value):
                spec = example()
                spec['chapters'][0]['actions'][0][field] = value
                with self.assertRaises(GeometryValidationError):
                    validate_spec(spec)

    def test_off_circle_start_and_small_radius_mismatch_are_rejected(self):
        for declared, actual in [(1, 1.000001), (1e-8, 2e-8)]:
            spec = example()
            ch = spec['chapters'][0]
            ch['objects'][-1]['radius'] = declared
            ch['objects'][1]['xy'] = [actual, 0]
            with self.assertRaisesRegex(ValueError, 'start on circle'):
                validate_spec(spec)

    def test_direct_and_indirect_moving_center_cycles_are_rejected(self):
        for indirect in (False, True):
            spec = example()
            ch = spec['chapters'][0]
            center = ch['objects'][0]
            center.pop('xy')
            center['derive'] = {'type': 'translate', 'source': 'T' if indirect else 'A',
                                'vector': [1, 0]}
            if indirect:
                ch['objects'].append({'id': 'T', 'type': 'point', 'derive': {
                    'type': 'translate', 'source': 'A', 'vector': [0, 0]}})
            for run_math in (False, True):
                with self.assertRaisesRegex(ValueError, 'center cannot depend'):
                    validate_spec(spec, run_math=run_math)

    def test_circular_helper_rejects_invalid_progress(self):
        for fraction in (-0.01, 1.01, float('nan'), float('inf'), True, 1j):
            with self.assertRaises(ValueError):
                circular_position([1, 0], [0, 0], math.pi, fraction)
        with self.assertRaises(ValueError):
            circular_position([0, 0], [0, 0], math.pi, 0.5)

    def test_constrain_state_is_used_for_freedom_and_center_dependencies(self):
        for point, derive in [
            ('A', {'type': 'project', 'source': 'B', 'line': ['C', 'B']}),
            ('O', {'type': 'translate', 'source': 'A', 'vector': [-1, 0]}),
        ]:
            spec = example()
            ch = spec['chapters'][0]
            ch['actions'].insert(0, {'at': 0.5, 'duration': 0.5,
                                    'type': 'constrain', 'point': point, 'derive': derive})
            with self.assertRaises(GeometryValidationError):
                validate_spec(spec)

    def test_validation_does_not_mutate_input(self):
        spec = example()
        before = copy.deepcopy(spec)
        validate_spec(spec)
        self.assertEqual(before, spec)


if __name__ == '__main__':
    unittest.main()
