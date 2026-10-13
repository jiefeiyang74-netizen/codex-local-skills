"""Synthetic conic math, strict rejection, clipping and updater regression."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'assets/engine'))
from geometry.conic import conic_state, conic_paths, position_derivative
from geometry.math2d import resolve_points
from geometry.schema import validate_spec, contract


def affine(parameter='t', scale=1, offset=0):
    return dict(parameter=parameter, scale=scale, offset=offset)


def fixture():
    objects = [dict(id='c', type='conic', kind='ellipse', center=[0,0], a=3, b=2, color='#52C7EA'),
               dict(id='h', type='conic', kind='hyperbola', center=[0,0], a=1.2, b=.8, branch='both', color='#666666'),
               dict(id='q', type='conic', kind='parabola', center=[-2,0], p=.5, color='#777744'),
               dict(id='P', type='point', derive=dict(type='on_conic', curve='c', t=affine()), label='P'),
               dict(id='T', type='point', derive=dict(type='conic_tangent', source='P', scale=affine('v')), label='T'),
               dict(id='A', type='point', derive=dict(type='translate', source='P', vector=[1,0])),
               dict(id='H', type='point', derive=dict(type='project', source='T', line=['P','A'])),
               dict(id='R', type='point', derive=dict(type='rotate', source='T', center='P', angle=180)),
               dict(id='N', type='point', derive=dict(type='rotate', source='T', center='P', angle=90)),
               dict(id='velocity', type='line', a='P', b='T', arrow=True, color='#FFD166'),
               dict(id='projection', type='line', a='P', b='H', arrow=True, color='#FF6688'),
               dict(id='normal', type='line', a='P', b='N', arrow=True, color='#66CC88')]
    actions = [dict(type='reveal',at=.5,duration=.8,ids=['c','h','q','P','velocity','projection','normal'],style='draw'),
               dict(type='set_parameter',at=1.4,duration=1,parameter='t',value=1.2),
               dict(type='set_parameter',at=2.5,duration=.5,parameter='v',value=0),
               dict(type='set_parameter',at=3.1,duration=.5,parameter='v',value=-.5),
               dict(type='set_parameter',at=3.7,duration=1,parameter='t',value=-1.2)]
    return dict(schema_version='geometry-1.0',title='Conic capability',audio_duration=5,
                narration='Synthetic silent conic fixture.',canvas=dict(width=1280,height=720,fps=60),
                chapters=[dict(id='conics', title='Analytic tangent and signed projection',start=0,end=5,
                               world_bounds=[-4,4,-3,3], plot_rect=[0,-.3,10,6],problem=[],
                               parameters=dict(t=0,v=.5),objects=objects,actions=actions,checks=[])])


class ConicTests(unittest.TestCase):
    def test_contract(self):
        validate_spec(fixture())
        self.assertEqual(contract()['conic_rules']['kinds'], ['ellipse', 'hyperbola', 'parabola'])
        self.assertIn('on_conic', contract()['point_derivations'])

    def test_existing_action_audit_and_engine_identity(self):
        from geometry.pipeline import validate_action_audit, engine_hash, digest, canonical
        spec=fixture();c=spec['chapters'][0]
        tokens={str(i):dict(start=a['at'],end=a['at']+.1) for i,a in enumerate(c['actions'])}
        audit=dict(source='synthetic_fixture',source_audio_sha256='synthetic',alignment_sha256='synthetic',
                   canonical_narration_sha256=digest(canonical(spec['narration'])),
                   actions=[dict(chapter_id=c['id'],action_index=i,at=a['at'],anchor_ids=[str(i)]) for i,a in enumerate(c['actions'])])
        validate_action_audit(audit,spec,tokens,'synthetic','synthetic',synthetic_fixture=True)
        audit['actions'][0]['anchor_ids']=[]
        with self.assertRaises(ValueError):validate_action_audit(audit,spec,tokens,'synthetic','synthetic',synthetic_fixture=True)
        # Independently assemble the current pipeline's ordered identity inputs.
        import hashlib
        engine=ROOT/'assets/engine'
        files=sorted((engine/'geometry').glob('*.py'))+[ROOT/'scripts/video.py',engine/'v3/partial_cache.py']
        self.assertIn(engine/'geometry/conic.py',files)
        self.assertIn(engine/'geometry/conic_runtime.py',files)
        expected=digest(''.join(str(p.relative_to(ROOT))+hashlib.sha256(p.read_bytes()).hexdigest() for p in files))
        self.assertEqual(engine_hash(engine),expected)

    def test_three_curves_focus_and_derivatives(self):
        for kind, props in [('ellipse',dict(a=3,b=2)), ('ellipse',dict(a=2,b=3)),
                            ('hyperbola',dict(a=2,b=1,branch='both')), ('parabola',dict(p=.7)), ('parabola',dict(p=-.7))]:
            s=conic_state(dict(id='c',type='conic',kind=kind,center=[.3,-.2],**props))
            for branch in ['positive_x','negative_x'] if kind=='hyperbola' else [None]:
                for t in np.linspace(-2,2,21):
                    p,d=position_derivative(s,float(t),branch);x,y=p-s['center']
                    numerical=(position_derivative(s,float(t)+1e-6,branch)[0]-position_derivative(s,float(t)-1e-6,branch)[0])/2e-6
                    np.testing.assert_allclose(d,numerical,atol=1e-8)
                    if kind=='ellipse':
                        a,b=s['a'],s['b'];self.assertAlmostEqual(x*x/a/a+y*y/b/b,1)
                        f=math.sqrt(abs(a*a-b*b));axis=np.array([f,0] if a>=b else [0,f])
                        self.assertAlmostEqual(np.linalg.norm([x,y]-axis)+np.linalg.norm([x,y]+axis),2*max(a,b))
                    elif kind=='hyperbola':
                        a,b=s['a'],s['b'];self.assertAlmostEqual(x*x/a/a-y*y/b/b,1)
                        f=math.hypot(a,b)
                        self.assertAlmostEqual(abs(math.hypot(x-f,y)-math.hypot(x+f,y)),2*a)
                        self.assertEqual(x>0,branch=='positive_x')
                    else:
                        self.assertAlmostEqual(y*y,4*s['p']*x)
                        self.assertAlmostEqual(math.hypot(x-s['p'],y),abs(x+s['p']))

    def test_signed_projection_zero_and_rotation(self):
        c=fixture()['chapters'][0]
        for t in [-1.,0.,1.]:
            for v in [-.5,0.,.5]:
                p=resolve_points(c['objects'],parameters=dict(t=t,v=v))
                np.testing.assert_allclose(p['T']-p['P'],v*np.array([-3*math.sin(t),2*math.cos(t)]),atol=1e-12)
                np.testing.assert_allclose(p['H']-p['P'],[-3*v*math.sin(t),0],atol=1e-12)
                np.testing.assert_allclose(p['R']-p['P'],-(p['T']-p['P']),atol=1e-12)
                self.assertAlmostEqual(float(np.dot(p['N']-p['P'],p['T']-p['P'])),0)

    def test_strict_rejection(self):
        mutations=[(0,{'p':1}),(0,{'a':0}),(0,{'a':True}),(0,{'a':1e-9}),
                   (0,{'a':affine()}),(0,{'center':'P'}),(0,{'center':[False,0]}),
                   (0,{'rotation':20}),(0,{'kind':'circle'}),(0,{'tolerance':0}),
                   (1,{'branch':'t'}),(2,{'p':0}),(9,{'kind':'ray'}),(9,{'arrow':1})]
        for index,change in mutations:
            for run_math in [True,False]:
                s=fixture();s['chapters'][0]['objects'][index].update(change)
                with self.subTest(change=change),self.assertRaises(ValueError):validate_spec(s,run_math=run_math)
        for index,change in [(3,{'t':True}),(3,{'t':'t+1'}),(3,{'t':affine('missing')}),
                             (3,{'t':affine(scale=1e308)}),(3,{'t':float('inf')}),
                             (3,{'branch':'positive_x'}),(3,{'curve':'P'}),(3,{'extra':1}),
                             (4,{'source':'A'}),(4,{'source':'T'}),(4,{'scale':'+inf'}),
                             (4,{'scale':10001}),(4,{'scale':dict(parameter='v',scale=1,offset=0,extra=1)})]:
            for run_math in [True,False]:
                s=fixture();s['chapters'][0]['objects'][index]['derive'].update(change)
                with self.subTest(change=change),self.assertRaises(ValueError):validate_spec(s,run_math=run_math)

    def test_fixed_branch_and_transition(self):
        s=fixture();c=s['chapters'][0];d=c['objects'][3]['derive'];d.update(curve='h',branch='negative_x')
        validate_spec(s)
        for t in np.linspace(-3,3,31):
            self.assertLess(resolve_points(c['objects'],parameters=dict(t=float(t),v=.2))['P'][0],0)
        c['objects'][1]['branch']='positive_x'
        with self.assertRaises(ValueError):validate_spec(s)
        c['objects'][1]['branch']='both';del d['branch']
        with self.assertRaises(ValueError):validate_spec(s)
        d['branch']='negative_x';c['actions'][1]['value']=13
        with self.assertRaises(ValueError):validate_spec(s,run_math=False)

    def test_clip_paths_no_bridge_and_error(self):
        for obj in fixture()['chapters'][0]['objects'][:3]:
            for bounds in [[-4,4,-3,3],[-2,2,-.4,.4],[2,4,-3,3],[10,11,10,11]]:
                paths=conic_paths(obj,bounds)
                for path in paths:
                    p=np.array(path)
                    self.assertTrue(np.isfinite(p).all())
                    self.assertTrue(((p[:,0]>=bounds[0])&(p[:,0]<=bounds[1])&(p[:,1]>=bounds[2])&(p[:,1]<=bounds[3])).all())
                    if obj['kind']=='hyperbola':self.assertTrue((p[:,0]>0).all() or (p[:,0]<0).all())
        obj=fixture()['chapters'][0]['objects'][0]
        self.assertEqual(len(conic_paths(obj,[-4,4,-.4,.4])),3)
        path=np.array(conic_paths(obj,[-4,4,-3,3])[0]);mid=(path[:-1]+path[1:])/2
        angles=np.unwrap(np.arctan2(path[:,1]/2,path[:,0]/3));t=(angles[:-1]+angles[1:])/2
        exact=np.array([3*np.cos(t),2*np.sin(t)]).T
        self.assertLessEqual(np.max(np.linalg.norm(mid-exact,axis=1)),.00100001)
        obj['tolerance']=1e-8
        with self.assertRaisesRegex(ValueError,'budget'):conic_paths(obj,[-4,4,-3,3])

    def test_original_derive_regression(self):
        objects=[dict(id=k,type='point',xy=v) for k,v in [('A',[0,0]),('B',[2,0]),('C',[1,2]),('D',[1,-2])]]
        for key,d in [('F',dict(type='reflect',source='C',axis=['A','B'])),('I',dict(type='intersect',lines=[['A','B'],['C','D']])),('H',dict(type='project',source='C',line=['A','B']))]:
            objects.append(dict(id=key,type='point',derive=d))
        p=resolve_points(objects)
        np.testing.assert_allclose(p['F'],[1,-2]);np.testing.assert_allclose(p['I'],[1,0]);np.testing.assert_allclose(p['H'],[1,0])

    def test_runtime_empty_reentry_signature_and_create(self):
        from geometry.runtime import GeometryScene
        from manim import ValueTracker,config,Create
        config.media_dir=tempfile.mkdtemp(prefix='conic-test-')
        c=fixture()['chapters'][0];scene=GeometryScene()
        scene.active_objects=c['objects'];scene.defs={o['id']:o for o in c['objects']}
        scene.parameters={k:ValueTracker(v) for k,v in c['parameters'].items()};scene.trackers={};scene.transient={}
        scene._points_signature=None;scene.runtime_stats=dict(point_resolutions=0,geometry_rebuilds=0)
        scene.bounds=c['world_bounds'];scene.scale=.7;scene.center=np.array([0,0]);scene.plot_rect=[0,0,8,6]
        scene.label_offsets={};scene.text_cache={};scene.merge_locked=set();scene.mobs={}
        for key in ['c','h','q','velocity','projection','P']:
            mob=scene.build(key);mob._geometry_signature=scene.geometry_signature(key);scene.mobs[key]=mob
        for t,v in [(0,.5),(1,.5),(1,0),(-1,-.5),(0,0),(1,.5)]:
            scene.parameters['t'].set_value(t);scene.parameters['v'].set_value(v)
            for key,mob in scene.mobs.items():scene.update_geometry(mob,key)
            for key,end in [('velocity','T'),('projection','H')]:
                mob=scene.mobs[key];p=scene.points()
                if np.linalg.norm(p[end]-p['P'])<=1e-10:self.assertEqual(len(mob),0)
                else:
                    self.assertEqual(len(mob),2)
                    np.testing.assert_allclose(mob[0].get_end(),scene.mapped(p[end]),atol=1e-10)
        for key in ['c','h','velocity']:
            animation=Create(scene.mobs[key]);animation.begin()
            for alpha in [0,.2,.5,.9,1]:
                animation.interpolate(alpha)
                self.assertTrue(np.isfinite(scene.mobs[key].get_all_points()).all())
            animation.finish()


if __name__=='__main__':unittest.main()
