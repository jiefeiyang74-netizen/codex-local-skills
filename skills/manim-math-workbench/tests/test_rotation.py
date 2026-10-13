"""Synthetic rotation math, strict contract and live renderer regressions."""
import copy, json, math, sys, tempfile, unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from geometry.schema import validate_spec,contract
from geometry.math2d import resolve_points,rotated_position,point_depends_on,circle_motion_parameters

def fixture():
    return json.loads((ROOT/'examples/rotation_points.json').read_text(encoding='utf-8'))
def affine(p='theta',scale=1,offset=0):
    return dict(parameter=p,scale=scale,offset=offset)
def derived(spec,key='Q'):
    return next(o for o in spec['chapters'][0]['objects'] if o['id']==key)['derive']

class RotationTests(unittest.TestCase):
    def test_contract_fixture(self):
        validate_spec(fixture())
        self.assertEqual(contract()['point_derivations']['rotate']['required'],['type','source','center','angle'])

    def test_requested_coordinates_and_midpoint(self):
        root=math.sqrt(3)
        np.testing.assert_allclose(rotated_position([2*root,0],[0,0],-60),[root,-3],atol=1e-12)
        np.testing.assert_allclose(rotated_position([root,1],[0,0],-60),[root,-1],atol=1e-12)
        np.testing.assert_allclose(rotated_position([2*root,0],[0,0],-30),[3,-root],atol=1e-12)
        np.testing.assert_allclose(rotated_position([root,1],[0,0],-30),[2,0],atol=1e-12)

    def test_rigid_triangles_parameters_and_dynamic_dependencies(self):
        c=fixture()['chapters'][0]
        for angle in np.linspace(-360,360,121):
            for xy in ([1,1],[2,1],[-1,2]):
                p=resolve_points(c['objects'],{'P':xy,'O':[.5,-.2]},{'theta':float(angle)})
                for a,b,ra,rb in [('O','C','S','R'),('C','P','R','Q'),('P','O','Q','S')]:
                    self.assertAlmostEqual(np.linalg.norm(p[a]-p[b]),np.linalg.norm(p[ra]-p[rb]),places=11)
                np.testing.assert_allclose(p['F'],rotated_position(xy,p['O'],-60),atol=1e-12)
        d=derived({'chapters':[c]});d['angle']=affine(scale=-2,offset=30)
        p=resolve_points(c['objects'],parameters={'theta':30})
        np.testing.assert_allclose(p['Q'],rotated_position(p['P'],p['O'],-30))
        self.assertTrue(point_depends_on(c['objects'],'Q','O'))
        self.assertTrue(point_depends_on(c['objects'],'Q','P'))

    def test_same_source_center_and_signed_zero(self):
        for a in [0,60,-60,720,1e308]:
            np.testing.assert_allclose(rotated_position([1,2],[1,2],a),[1,2])
        s=fixture();derived(s)['source']='O';validate_spec(s)
        np.testing.assert_allclose(rotated_position([1,0],[0,0],90),[0,1],atol=1e-12)

    def test_reject_bad_derivations_and_cycles(self):
        mutations=[{'extra':1},{'angle':float('inf')},{'angle':float('nan')},{'angle':True},{'angle':'theta*2'},{'angle':'+inf'},{'angle':'-inf'}, {'source':'missing'},{'center':'missing'},{'center':'edge'},{'source':'edge'},{'source':'Q'},{'center':'Q'},{'source':[]},{'center':{}},{'angle':affine('missing')},{'angle':dict(parameter='theta',scale=1)},{'angle':dict(parameter='theta',scale=1,offset=0,extra=1)},{'angle':affine(scale=True)},{'angle':affine(offset=float('inf'))}]
        for update in mutations:
            for run_math in [True,False]:
                s=fixture();derived(s).update(update)
                with self.subTest(update=update,run_math=run_math),self.assertRaises(ValueError):validate_spec(s,run_math=run_math)
        for field in ['type','source','center','angle']:
            s=fixture();del derived(s)[field]
            with self.assertRaises(ValueError):validate_spec(s)
        s=fixture();derived(s)['source']='R';derived(s,'R')['center']='Q'
        with self.assertRaises(ValueError):validate_spec(s)
        with self.assertRaises(ValueError):resolve_points(s['chapters'][0]['objects'],parameters={'theta':0})

    def test_parameter_overflow_rejected_and_cannot_move_derived(self):
        s=fixture();derived(s)['angle']=affine(scale=1e308)
        with self.assertRaises(ValueError):validate_spec(s)
        s=fixture();s['chapters'][0]['actions'][1]=dict(type='move',at=1,duration=2,positions={'Q':[1,1]})
        with self.assertRaises(ValueError):validate_spec(s)

    def test_constrain_validation_and_dependency_guard(self):
        s=fixture();c=s['chapters'][0];q=next(o for o in c['objects'] if o['id']=='Q');d=q.pop('derive');q['xy']=[1,1]
        c['actions'].insert(1,dict(type='constrain',point='Q',derive=d,at=.8,duration=.2));validate_spec(s)
        c['actions'][1]['derive']['unknown']=1
        with self.assertRaises(ValueError):validate_spec(s)
        c=fixture()['chapters'][0];c['objects'].append(dict(id='circle',type='circle',center='Q',radius=1))
        with self.assertRaisesRegex(ValueError,'center cannot depend'):
            circle_motion_parameters(c['objects'],{},'O','circle',1,{'theta':0})

    def test_runtime_updaters_follow_point_labels_edges_polygons(self):
        from geometry.runtime import GeometryScene
        from manim import ValueTracker,config,Text
        config.media_dir=tempfile.mkdtemp(prefix='rotation-runtime-')
        c=fixture()['chapters'][0];scene=GeometryScene();scene.active_objects=c['objects'];scene.defs={o['id']:o for o in c['objects']}
        scene.parameters={'theta':ValueTracker(0)};scene.trackers={o['id']:[ValueTracker(v) for v in o['xy']] for o in c['objects'] if 'xy' in o}
        scene.transient={};scene._points_signature=None;scene._points_cache={};scene.runtime_stats={'point_resolutions':0,'geometry_rebuilds':0}
        scene.bounds=c['world_bounds'];scene.scale=.7;scene.center=np.array([0,0]);scene.plot_rect=[0,0,8,6];scene.label_offsets={};scene.text_cache={};scene.merge_locked=set();scene.mobs={}
        for key in ['Q','R','S','F','edge','triangle']:
            m=scene.build(key);m._geometry_signature=scene.geometry_signature(key);scene.mobs[key]=m
        for angle,px,ox in [(0,1,0),(-30,1,0),(-60,1,0),(-90,2,0),(60,2,.5)]:
            scene.parameters['theta'].set_value(angle);scene.trackers['P'][0].set_value(px);scene.trackers['O'][0].set_value(ox)
            for key,m in scene.mobs.items():scene.update_geometry(m,key)
            p=scene.points()
            for key in ['Q','R','S','F']:
                m=scene.mobs[key];np.testing.assert_allclose(m[0].get_center(),scene.mapped(p[key]),atol=1e-10)
                label=next(x for x in m.get_family() if isinstance(x,Text))
                np.testing.assert_allclose(label.get_center()-m[0].get_center(),[*scene.defs[key]['label_offset'],0],atol=1e-10)
            np.testing.assert_allclose(scene.mobs['edge'].get_start(),scene.mapped(p['R']),atol=1e-10)
            np.testing.assert_allclose(scene.mobs['edge'].get_end(),scene.mapped(p['Q']),atol=1e-10)
            np.testing.assert_allclose(scene.mobs['triangle'].get_vertices(),[scene.mapped(p[k]) for k in ['S','R','Q']],atol=1e-10)

if __name__=='__main__':unittest.main()
