"""Synthetic contract, point solver, and renderer dependency regression."""
import copy,json,sys,math,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from geometry.schema import validate_spec,GeometryValidationError
from geometry.math2d import resolve_points,circle_motion_parameters,circular_position
from geometry.quadratic import quadratic_point,validate_quadratic_transition

def fixture():return json.loads((ROOT/'examples/quadratic_derived_points.json').read_text(encoding='utf-8'))
def affine(p,scale=1,offset=0):return dict(parameter=p,scale=scale,offset=offset)
class DerivedQuadraticTests(unittest.TestCase):
 def test_example_and_existing_examples(self):
  validate_spec(fixture())
  for name in ['geometry_minimal.json','circle_projection.json','reciprocal_motion.json','reciprocal_branches.json','quadratic_motion.json']:
   validate_spec(json.loads((ROOT/'examples'/name).read_text(encoding='utf-8-sig')))
 def test_strict_rejections(self):
  mutations=[lambda q:q.update(extra=2),lambda q:q.update(curve='A'),lambda q:q.update(curve='missing'),lambda q:q.update(x=float('inf')),lambda q:q.update(x=float('nan')),lambda q:q.update(x=True),lambda q:q.update(x='t+1'),lambda q:q.update(x={'parameter':'t','scale':1,'offset':0,'extra':1}),lambda q:q.update(x=affine('missing')),lambda q:q.update(x=affine('t',float('inf'))),lambda q:q.update(x=1e308)]
  for mutate in mutations:
   s=fixture();q=next(o for o in s['chapters'][0]['objects'] if o['id']=='Q')['derive'];mutate(q)
   with self.subTest(q=q),self.assertRaises(ValueError):validate_spec(s)
  for val in [10001,-10001,float('inf'),True]:
   for initial in [True,False]:
    s=fixture();c=s['chapters'][0]
    if initial:c['parameters']['t']=val
    else:c['actions'][1]['value']=val
    with self.subTest(val=val,initial=initial),self.assertRaises(ValueError):validate_spec(s)
 def test_parameter_coefficients_and_many_midframes(self):
  s=fixture();c=s['chapters'][0];f=next(o for o in c['objects'] if o['id']=='f')
  f.update(a=affine('a'),h=affine('h',.5,.25),k=affine('k',2,-.5))
  for a in [.25,2,-.25,-3]:
   for t in np.linspace(-1,2,61):
    params=dict(a=a,h=.6,k=-.25,t=float(t));p=resolve_points(c['objects'],parameters=params)
    for key,off in [('Q',0),('Q1',-.35),('Q2',.35)]:
     x=t+off;np.testing.assert_allclose(p[key],[x,a*(x-.55)**2-1],atol=1e-12)
    v=p['B']-p['A'];expected=p['A']+v*np.dot(p['Q']-p['A'],v)/np.dot(v,v)
    np.testing.assert_allclose(p['H'],expected);np.testing.assert_allclose(p['T'],p['Q']+[0,1]);np.testing.assert_allclose(p['R'],2*expected-p['Q']);np.testing.assert_allclose(p['M'],[t,.5*t+3]);self.assertAlmostEqual(float(np.dot(p['Q']-p['H'],v)),0,places=10)
 def test_a_zero_and_crossing_rejected(self):
  for a in [0,affine('t')]:
   s=fixture();next(o for o in s['chapters'][0]['objects'] if o['id']=='f')['a']=a
   with self.assertRaises(ValueError):validate_spec(s)
 def test_feature_is_not_point_and_derived_cannot_move(self):
  s=fixture();c=s['chapters'][0];c['objects'].append(dict(id='feat',type='quadratic_feature',kind='point',curve='f',x=0));next(o for o in c['objects'] if o['id']=='QH')['a']='feat'
  with self.assertRaises(ValueError):validate_spec(s)
  s=fixture();s['chapters'][0]['actions'][1]=dict(type='move',at=1.5,duration=4,positions={'Q':[0,0]})
  with self.assertRaises(ValueError):validate_spec(s)
 def test_constrain_and_old_circle_direction_pattern(self):
  s=fixture();c=s['chapters'][0];q=next(o for o in c['objects'] if o['id']=='Q');derive=q.pop('derive');q['xy']=[-1,-.5];c['actions'].insert(1,dict(type='constrain',point='Q',derive=derive,at=1.1,duration=.3));validate_spec(s)
  c=fixture()['chapters'][0];c['objects'].append(dict(id='E',type='point',xy=[2,1.35]));start,center=circle_motion_parameters(c['objects'],{},'E','circle',.6,{'t':2})
  for fraction in np.linspace(0,1,15):
   pos=circular_position(start,center,.6,float(fraction));self.assertAlmostEqual(float(np.linalg.norm(pos-center)),.35)
 def test_constrain_reuses_strict_validation(self):
  invalid=[dict(type='on_quadratic',curve='f',x=0,extra=1),dict(type='on_quadratic',curve='A',x=0),dict(type='on_quadratic',curve='f',x=float('inf')),dict(type='on_quadratic',curve='f',x={'parameter':'t','scale':1,'offset':0,'extra':1}),dict(type='on_quadratic',curve='f',x='t+1')]
  for derive in invalid:
   s=fixture();c=s['chapters'][0];q=next(o for o in c['objects'] if o['id']=='Q');q.pop('derive');q['xy']=[-1,-.5];c['actions'].insert(1,dict(type='constrain',point='Q',derive=derive,at=1.1,duration=.3))
   with self.subTest(derive=derive),self.assertRaises(ValueError):validate_spec(s)
 def test_runtime_dependency_geometry(self):
  from geometry.runtime import GeometryScene
  import tempfile
  from manim import ValueTracker,config
  config.media_dir=tempfile.mkdtemp(prefix="manim-quadratic-test-")
  c=fixture()['chapters'][0];scene=GeometryScene();scene.active_objects=c['objects'];scene.defs={o['id']:o for o in c['objects']};scene.parameters={'t':ValueTracker(-1)};scene.trackers={o['id']:[ValueTracker(v) for v in o['xy']] for o in c['objects'] if 'xy' in o};scene.transient={};scene._points_signature=None;scene._points_cache={};scene.runtime_stats={'point_resolutions':0};scene.bounds=c['world_bounds'];scene.scale=.7;scene.center=np.array([1,2]);scene.plot_rect=[0,0,6,6];scene.label_offsets={};scene.text_cache={}
  previous={}
  for t in [-1,-.5,0,.5,1,1.5,2]:
   scene.parameters['t'].set_value(t);p=scene.points()
   for key in ['Q','Q1','Q2','H','M','QH','QM','circle','square','triangle']:
    mob=scene.build(key);sig=scene.geometry_signature(key)
    if key in previous:self.assertNotEqual(sig,previous[key])
    previous[key]=sig
    if key=='circle':np.testing.assert_allclose(mob.get_center(),scene.mapped(p['Q']),atol=1e-10)
    if key=='QH':np.testing.assert_allclose(mob.get_start(),scene.mapped(p['Q']));np.testing.assert_allclose(mob.get_end(),scene.mapped(p['H']))
if __name__=='__main__':unittest.main()
