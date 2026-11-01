"""Positive homothety, strict validation and existing renderer integration."""
import copy, json, math, sys, tempfile, unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from geometry.schema import validate_spec, contract
from geometry.math2d import resolve_points, scale_factor, point_depends_on, circle_motion_parameters, evaluate_checks, curved_region_geometry

def fixture():
    return json.loads((ROOT/'examples/scale_points.json').read_text())

def derive(s):
    return next(o for o in s['chapters'][0]['objects'] if o['id']=='Q')['derive']

class ScaleTests(unittest.TestCase):
    def test_contract(self):
        validate_spec(fixture())
        self.assertEqual(contract()['point_derivations']['scale']['required'],['type','source','center','factor'])

    def test_fixed_affine_and_live_sources(self):
        c=fixture()['chapters'][0]
        for factor in [1e-12,.25,1,2,10000]:
            for a,p in [([0,0],[3,0]),([1,-1],[2,1])]:
                state=resolve_points(c['objects'],{'A':a,'P':p},{'theta':90,'s':factor})
                delta=np.array(p)-a
                expected=np.array(a)+factor*np.array([-delta[1],delta[0]])
                np.testing.assert_allclose(state['Q'],expected,atol=1e-10)
        for factor in [.5,2,10000]:
            s=fixture();derive(s)['factor']=factor;validate_spec(s)
        self.assertTrue(point_depends_on(c['objects'],'Q','A'))
        self.assertTrue(point_depends_on(c['objects'],'Q','P'))

    def test_rejection_matrix(self):
        bad=[0,-1,10001,True,None,float('nan'),float('inf'),float('-inf'),'+inf','s*2',{},
             {'parameter':'missing','scale':1,'offset':0}, {'parameter':'s','scale':1},
             {'parameter':'s','scale':1,'offset':0,'extra':1},
             {'parameter':'s','scale':True,'offset':0}, {'parameter':'s','scale':1e308,'offset':1e308}]
        updates=[{'factor':x} for x in bad]+[{'unknown':0},{'source':'missing'},{'center':'missing'},
                 {'source':'disk'},{'center':'disk'},{'source':[]},{'center':{}},{'source':'Q'},{'center':'Q'}]
        for update in updates:
            for run_math in [False,True]:
                s=fixture();derive(s).update(update)
                with self.subTest(update=update,run_math=run_math),self.assertRaises(ValueError):validate_spec(s,run_math=run_math)
        for key in ['type','source','center','factor']:
            s=fixture();del derive(s)[key]
            with self.assertRaises(ValueError):validate_spec(s)
        for x in bad:
            d=dict(type='scale',source='P',center='A',factor=x)
            with self.assertRaises(ValueError):scale_factor(d,{'s':1})

    def test_cycles_and_same_point(self):
        s=fixture();derive(s)['source']='A';validate_spec(s)
        p=resolve_points(s['chapters'][0]['objects'],parameters={'s':2,'theta':0})
        np.testing.assert_array_equal(p['Q'],p['A'])
        s=fixture();c=s['chapters'][0];next(o for o in c['objects'] if o['id']=='RP')['derive']['center']='Q'
        with self.assertRaises(ValueError):validate_spec(s,run_math=False)
        with self.assertRaises(ValueError):resolve_points(c['objects'],parameters=c['parameters'])

    def test_parameters_endpoints_and_intermediate(self):
        for value in [0,-1,10001,float('nan'),float('inf')]:
            s=fixture();c=s['chapters'][0];c['actions'][2]['value']=value
            with self.assertRaises(ValueError):validate_spec(s,run_math=False)
            with self.assertRaises(ValueError):evaluate_checks(c['objects'],[c['actions'][2]],[],c['parameters'])
        c=fixture()['chapters'][0]
        for s in np.linspace(.75,1.5,61):
            pars={'s':float(s),'theta':45}
            p=resolve_points(c['objects'],parameters=pars)
            disk=curved_region_geometry(next(o for o in c['objects'] if o['id']=='disk'),p['SC'],pars)
            self.assertAlmostEqual(np.linalg.norm(p['Q']-p['SC']),disk['radius'])
            self.assertAlmostEqual(disk['area'],math.pi*s*s)

    def test_constraint_and_motion_guards(self):
        s=fixture();c=s['chapters'][0];q=next(o for o in c['objects'] if o['id']=='Q');d=q.pop('derive');q['xy']=[3,0]
        c['actions'].insert(1,dict(type='constrain',at=.7,duration=.2,point='Q',derive=d));validate_spec(s)
        c['actions'][1]['derive']['extra']=0
        with self.assertRaises(ValueError):validate_spec(s)
        s=fixture();c=s['chapters'][0];c['actions'][3]['positions']={'Q':[2,0]}
        with self.assertRaises(ValueError):validate_spec(s)
        c=fixture()['chapters'][0];c['objects'].append(dict(id='circle',type='circle',center='Q',radius=1))
        with self.assertRaisesRegex(ValueError,'center cannot depend'):circle_motion_parameters(c['objects'],{},'A','circle',1,c['parameters'])
        with self.assertRaisesRegex(ValueError,'free point'):circle_motion_parameters(c['objects'],{},'Q','circle',1,c['parameters'])

    def test_runtime_points_labels_edge_and_disk(self):
        from geometry.runtime import GeometryScene
        from manim import ValueTracker,config,Text
        config.media_dir=tempfile.mkdtemp(prefix='scale-runtime-')
        c=fixture()['chapters'][0];scene=GeometryScene();scene.active_objects=c['objects'];scene.defs={o['id']:o for o in c['objects']}
        scene.parameters={k:ValueTracker(v) for k,v in c['parameters'].items()}
        scene.trackers={o['id']:[ValueTracker(v) for v in o['xy']] for o in c['objects'] if 'xy' in o}
        scene.transient={};scene._points_signature=None;scene._points_cache={};scene.runtime_stats={'point_resolutions':0,'geometry_rebuilds':0}
        scene.bounds=c['world_bounds'];scene.scale=.7;scene.center=np.array([0,0]);scene.plot_rect=[0,0,8,6];scene.label_offsets={};scene.text_cache={};scene.merge_locked=set();scene.mobs={}
        for key in ['SC','Q','disk','edge']:
            m=scene.build(key);m._geometry_signature=scene.geometry_signature(key);scene.mobs[key]=m
        for factor,theta,ax,px in [(1,0,0,3),(1,45,0,3),(1.25,45,0,3),(1.5,45,0,3),(.75,45,-.5,3.5)]:
            scene.parameters['s'].set_value(factor);scene.parameters['theta'].set_value(theta)
            scene.trackers['A'][0].set_value(ax);scene.trackers['P'][0].set_value(px)
            for key,m in scene.mobs.items():scene.update_geometry(m,key)
            p=scene.points()
            for key in ['SC','Q']:
                m=scene.mobs[key];np.testing.assert_allclose(m[0].get_center(),scene.mapped(p[key]),atol=1e-10)
                label=next(x for x in m.get_family() if isinstance(x,Text))
                np.testing.assert_allclose(label.get_center()-m[0].get_center(),[.25,.25,0],atol=1e-10)
            np.testing.assert_allclose(scene.mobs['edge'].get_start(),scene.mapped(p['SC']),atol=1e-10)
            np.testing.assert_allclose(scene.mobs['edge'].get_end(),scene.mapped(p['Q']),atol=1e-10)
            np.testing.assert_allclose(scene.mobs['disk'].get_center(),scene.mapped(p['SC']),atol=1e-8)
            self.assertAlmostEqual(scene.mobs['disk'].width,2*factor*scene.scale,places=6)

if __name__=='__main__':unittest.main()
