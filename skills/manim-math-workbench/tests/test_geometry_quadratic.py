"""Analytic quadratics, clipped curves and strict declarative rejection paths."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets' / 'engine'))
from geometry.quadratic import (quadratic_state, quadratic_value, quadratic_segments,
                                feature_state, validate_quadratic_transition)
from geometry.math2d import evaluate_checks
from geometry.schema import validate_spec, contract, GeometryValidationError


def curve(a=1, h=0, k=-1):
    return {'id': 'q', 'type': 'quadratic', 'a': a, 'h': h, 'k': k}


def affine(name, scale=1, offset=0):
    return {'parameter': name, 'scale': scale, 'offset': offset}


def fixture():
    return {'schema_version': 'geometry-1.0', 'title': 'Quadratic',
            'audio_duration': 4, 'narration': 'Quadratic graph.', 'chapters': [{
                'id': 'q1', 'title': 'Graph', 'start': 0, 'end': 4,
                'world_bounds': [-4, 4, -3, 7], 'problem': [],
                'parameters': {'a': 1, 'h': 0, 'k': -1, 'x': 1},
                'objects': [
                    {'id': 'axes', 'type': 'coordinate_axes', 'x_ticks': [-2, 0, 2],
                     'y_ticks': [-2, 0, 2, 4, 6], 'grid': True},
                    curve(affine('a'), affine('h'), affine('k')),
                    {'id': 'v', 'type': 'quadratic_feature', 'curve': 'q', 'kind': 'vertex'},
                    {'id': 'p', 'type': 'quadratic_feature', 'curve': 'q', 'kind': 'point', 'x': affine('x')},
                ],
                'actions': [],
                'checks': [{'type': 'quadratic_state', 'curve': 'q', 'vertex': [0,-1],
                            'roots': [-1,1], 'coefficients': [1,0,-1], 'y_intercept': -1},
                           {'type': 'quadratic_point', 'feature': 'p', 'value': [1,0]}],
            }]}


def bezier(points, t):
    p = np.array(points)
    return (1-t)**3*p[0] + 3*(1-t)**2*t*p[1] + 3*(1-t)*t*t*p[2] + t**3*p[3]


class QuadraticMathTests(unittest.TestCase):
    def test_vertex_form_coefficients_and_both_given_examples(self):
        first = quadratic_state(curve(2,3,5), {})
        self.assertEqual((first['b'],first['c'],first['discriminant']), (-12,23,-40))
        self.assertEqual(first['vertex'], [3,5])
        self.assertEqual(first['roots'], [])
        second = quadratic_state(curve(3,-4,-1), {})
        self.assertEqual((second['b'],second['c'],second['discriminant']), (24,47,12))
        np.testing.assert_allclose(second['roots'], [-4-1/math.sqrt(3), -4+1/math.sqrt(3)])

    def test_root_multiplicity_and_small_nonzero_discriminants(self):
        for a in (1, -1):
            self.assertEqual(quadratic_state(curve(a,2,0), {})['roots'], [2])
            self.assertEqual(len(quadratic_state(curve(a,0,-a*1e-24), {})['roots']), 2)
            self.assertEqual(quadratic_state(curve(a,0,a*1e-24), {})['roots'], [])
        self.assertEqual(quadratic_state(curve(1,2,-1), {})['roots'], [1,3])
        self.assertEqual(quadratic_state(curve(-1,2,-1), {})['roots'], [])

    def test_affine_state_and_features_share_the_same_values(self):
        obj = curve(affine('a',2,1), affine('h',-1,3), affine('k'))
        parameters = {'a': .5, 'h': 2, 'k': -2, 'x': 3}
        state = quadratic_state(obj, parameters)
        self.assertEqual(state['vertex'], [1,-2])
        self.assertEqual(state['roots'], [0,2])
        for kind, expected in [('vertex',[[1,-2]]), ('roots',[[0,0],[2,0]]), ('y_intercept',[[0,0]])]:
            self.assertEqual(feature_state({'kind':kind},obj,parameters)['points'], expected)
        self.assertEqual(feature_state({'kind':'axis'},obj,parameters)['axis_x'],1)
        self.assertEqual(feature_state({'kind':'point','x':affine('x')},obj,parameters)['points'],[[3,6]])

    def test_bezier_matches_polynomial_for_wide_narrow_and_negative_curves(self):
        bounds = [-4,4,-3,7]
        for a in (-1e12,-2,-1e-12,1e-12,1,1e12):
            for h,k in [(0,0),(1,-2),(-2,1)]:
                obj = curve(a,h,k)
                pieces = quadratic_segments(obj,{},bounds)
                self.assertLessEqual(len(pieces),2)
                for points in pieces:
                    self.assertEqual(np.array(points).shape,(4,2))
                    for t in np.linspace(0,1,51):
                        x,y = bezier(points,float(t))
                        self.assertTrue(bounds[0]-1e-9<=x<=bounds[1]+1e-9)
                        self.assertTrue(bounds[2]-1e-8<=y<=bounds[3]+1e-8)
                        self.assertAlmostEqual(y,quadratic_value(obj,{},float(x)),delta=1e-8)

    def test_disconnected_arms_never_get_joined_across_clipped_vertex(self):
        parts = quadratic_segments(curve(1,0,-3),{},[-4,4,1,6])
        self.assertEqual(len(parts),2)
        np.testing.assert_allclose(parts[0][0],[-3,6])
        np.testing.assert_allclose(parts[0][-1],[-2,1])
        np.testing.assert_allclose(parts[1][0],[2,1])
        np.testing.assert_allclose(parts[1][-1],[3,6])
        self.assertLess(parts[0][-1][0], parts[1][0][0])
        np.testing.assert_allclose(quadratic_state(curve(1,0,-3),{})['roots'],[-math.sqrt(3),math.sqrt(3)])

    def test_clipping_tangency_and_invisible_curves(self):
        for obj,bounds,point in [(curve(1,0,1),[-2,2,-1,1],[0,1]),
                                 (curve(-1,0,-1),[-2,2,-1,1],[0,-1])]:
            self.assertEqual(quadratic_segments(obj,{},bounds),[[point]*4])
        self.assertEqual(quadratic_segments(curve(1,0,2),{},[-2,2,-1,1]),[])
        self.assertEqual(quadratic_segments(curve(-1,0,-2),{},[-2,2,-1,1]),[])
        self.assertEqual(quadratic_segments(curve(1,100,0),{},[-2,2,-1,1]),[])

    def test_exact_cubic_is_not_a_polyline(self):
        points = quadratic_segments(curve(1,0,0),{},[-1,1,-1,2])[0]
        self.assertAlmostEqual(bezier(points,.5)[1],0)
        self.assertEqual(points[0][1],1)
        self.assertEqual(points[-1][1],1)
        self.assertLess(points[1][1],0)

    def test_extremely_narrow_offset_curve_keeps_its_visible_height(self):
        points=quadratic_segments(curve(1e32,1,0),{},[-2,2,-1,7])[0]
        self.assertAlmostEqual(points[0][1],7)
        self.assertAlmostEqual(points[-1][1],7)
        self.assertAlmostEqual(bezier(points,.5)[1],0)

    def test_discriminant_product_does_not_create_false_zero(self):
        state=quadratic_state(curve(1e-200,0,-1e-123),{})
        self.assertGreater(state['discriminant'],0)
        self.assertEqual(len(state['roots']),2)
        with self.assertRaisesRegex(ValueError,'below finite numeric resolution'):
            quadratic_state(curve(1e-200,0,1e-200),{})

    def test_nonfinite_expression_and_zero_a_are_rejected(self):
        for invalid in [0,True,float('nan'),float('inf'),'-inf','x*x',{'parameter':'a','scale':1},
                        {'parameter':'a','scale':1,'offset':0,'expression':'exec'},affine('unknown')]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                quadratic_state(curve(invalid),{'a':1})

    def test_crossing_zero_is_rejected_without_tolerance_or_sampling_loopholes(self):
        for before,after,obj in [({'a':1},{'a':-1},curve(affine('a'))),
                                 ({'a':1e-200},{'a':-1e-200},curve(affine('a'))),
                                 ({'a':0},{'a':2},curve(affine('a',2,-3)))]:
            with self.assertRaisesRegex(ValueError,'cross zero'):
                validate_quadratic_transition([obj],before,after)
        validate_quadratic_transition([curve(affine('a'))],{'a':1},{'a':.5})


class QuadraticContractTests(unittest.TestCase):
    def test_contract_fixture_and_real_motion_example(self):
        current = contract()
        self.assertEqual(current['schema_version'], 'geometry-1.0')
        self.assertRegex(current['capability_version'], r'^geometry-1\.\d+(?:\.\d+)?$')
        version = tuple(map(int, current['capability_version'].removeprefix('geometry-').split('.')))
        version += (0,) * (3 - len(version))
        self.assertGreaterEqual(version, (1, 3, 0))
        # Assert the quadratic capability itself, not one unrelated patch ID.
        for kind, required in [('quadratic', {'id', 'type', 'a', 'h', 'k'}),
                               ('quadratic_feature', {'id', 'type', 'curve', 'kind'})]:
            self.assertTrue(required <= set(current['object_fields'][kind][0].split()))
        self.assertTrue({'at', 'duration', 'type', 'parameter', 'value'} <=
                        set(current['action_fields']['set_parameter'][0].split()))
        spec = fixture()
        self.assertEqual(validate_spec(spec),spec)
        path = ROOT/'examples'/'quadratic_motion.json'
        self.assertTrue(path.is_file(), 'Bundled quadratic motion example is required')
        validate_spec(json.loads(path.read_text(encoding='utf-8-sig')))

    def test_parameter_actions_update_checks_and_feature_points(self):
        spec = fixture(); ch = spec['chapters'][0]
        ch['actions'] = [{'type':'set_parameter','at':.5,'duration':1,'parameter':'h','value':2},
                         {'type':'set_parameter','at':1.5,'duration':1,'parameter':'x','value':3}]
        ch['checks'] = [{'type':'quadratic_state','curve':'q','vertex':[2,-1],'roots':[1,3],
                         'coefficients':[1,-4,3],'y_intercept':3},
                        {'type':'quadratic_point','feature':'p','value':[3,0]}]
        validate_spec(spec)
        self.assertTrue(all(r['passed'] for r in evaluate_checks(ch['objects'],ch['actions'],ch['checks'],ch['parameters'])))

    def test_wrong_root_count_and_wrong_values_fail_checks(self):
        for expected in [[],[0],[-1,2]]:
            spec = fixture(); spec['chapters'][0]['checks']=[{'type':'quadratic_state','curve':'q','roots':expected}]
            with self.assertRaises(GeometryValidationError): validate_spec(spec)

    def test_strict_fields_tick_budget_and_feature_shape(self):
        changes = [
            (0,'grid','yes'),(0,'x_ticks',[1,1]),(0,'x_ticks',[5]),(0,'y_ticks',list(range(22))),
            (0,'expression','x'),(1,'a',0),(1,'formula','x*x'),(2,'curve','axes'),
            (2,'x',1),(2,'kind','unknown'),(2,'show_label','false'),(2,'label',False),
            (3,'x','+inf'),(3,'x',{'parameter':'missing','scale':1,'offset':0}),
        ]
        for index,key,value in changes:
            with self.subTest(index=index,key=key,value=value):
                spec = fixture(); spec['chapters'][0]['objects'][index][key]=value
                with self.assertRaises(ValueError): validate_spec(spec)
        spec=fixture(); del spec['chapters'][0]['objects'][3]['x']
        with self.assertRaises(ValueError): validate_spec(spec)

    def test_all_through_a_validation_also_runs_when_run_math_is_false(self):
        for run_math in (False,True):
            for value in (0,-1):
                spec=fixture(); spec['chapters'][0]['actions']=[{
                    'type':'set_parameter','at':1,'duration':1,'parameter':'a','value':value}]
                with self.assertRaises(ValueError): validate_spec(spec,run_math=run_math)

    def test_features_cannot_bypass_point_reference_rules(self):
        spec=fixture(); ch=spec['chapters'][0]
        ch['objects'].append({'id':'line','type':'line','a':'v','b':'p'})
        with self.assertRaisesRegex(ValueError,'point reference'): validate_spec(spec)

    def test_check_shapes_and_expected_fields_are_strict(self):
        invalid = [
            {'type':'quadratic_state','curve':'q'},
            {'type':'quadratic_state','curve':'q','roots':[1,-1]},
            {'type':'quadratic_state','curve':'q','roots':[0,0]},
            {'type':'quadratic_state','curve':'q','coefficients':[1,0]},
            {'type':'quadratic_state','curve':'q','vertex':[True,0]},
            {'type':'quadratic_state','curve':'axes','roots':[]},
            {'type':'quadratic_point','feature':'q','value':[0,0]},
            {'type':'quadratic_point','feature':'p','value':0},
            {'type':'quadratic_point','feature':'p','value':[1,0],'tolerance':0},
        ]
        for check in invalid:
            spec=fixture();spec['chapters'][0]['checks']=[check]
            with self.subTest(check=check),self.assertRaises(ValueError): validate_spec(spec)

    def test_state_checks_do_not_mutate_input(self):
        spec=fixture();before=copy.deepcopy(spec)
        validate_spec(spec)
        self.assertEqual(spec,before)


if __name__=='__main__':
    unittest.main()
