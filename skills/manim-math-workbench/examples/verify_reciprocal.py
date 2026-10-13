from pathlib import Path
import sys,json,copy,math,unittest
import numpy as np
root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'assets/engine'))
from geometry.schema import validate_spec, contract
from geometry.math2d import resolve_points,evaluate_checks
from geometry.reciprocal import reciprocal_segments,reciprocal_point,validate_reciprocal_transition
fixture=json.loads((root/'examples/reciprocal_motion.json').read_text(encoding='utf8'))
class ReciprocalTests(unittest.TestCase):
 def test_examples_regression(self):
  for p in root.glob('examples/*.json'):
   with self.subTest(example=p.name):validate_spec(json.loads(p.read_text(encoding='utf8')))
 def test_zero_nonfinite_and_expression(self):
  for field in ('k','x'):
   for value in (0,False,float('inf'),float('-inf'),float('nan'),'1/x',{'parameter':'x','scale':0,'offset':0}):
    s=copy.deepcopy(fixture);c=s['chapters'][0]
    if field=='k':c['objects'][1]['k']=value
    else:c['objects'][5]['derive']['x']=value
    with self.subTest(field=field,value=value), self.assertRaises(ValueError):validate_spec(s)
 def test_crossing_zero(self):
  for name in ('x','k'):
   for finish in (0,-2):
    s=copy.deepcopy(fixture);c=s['chapters'][0];c['actions']=[{'at':.6,'duration':1,'type':'set_parameter','parameter':name,'value':finish}]
    with self.subTest(name=name,finish=finish),self.assertRaises(ValueError):validate_spec(s)
 def test_affine_crossing(self):
  s=copy.deepcopy(fixture);c=s['chapters'][0];c['objects'][5]['derive']['x']={'parameter':'x','scale':2,'offset':-2};c['actions']=[{'at':.6,'duration':1,'type':'set_parameter','parameter':'x','value':2}]
  with self.assertRaises(ValueError):validate_spec(s)
 def test_moving_points_area_symmetries(self):
  objs=fixture['chapters'][0]['objects'];defs={o['id']:o for o in objs}
  for k in (-7,-3,-.1,.1,2,5,7):
   for x in np.linspace(.4,4,51):
    for sign in (-1,1):
     x=float(x)*sign;p=resolve_points(objs,parameters={'x':x,'k':k})
     self.assertAlmostEqual(float(np.prod(p['P'])),k)
     area=abs(p['H'][0]*p['V'][1]);self.assertAlmostEqual(area,abs(k))
     self.assertAlmostEqual(p['H'][1],0);self.assertAlmostEqual(p['V'][0],0)
     px,py=p['P']
     for xx,yy in ((-px,-py),(py,px),(-py,-px)):self.assertAlmostEqual(xx*yy,k)
 def test_clipping_and_error(self):
  for k in (-7,-.1,.1,2,7):
   for bounds in ([-5,5,-5,5],[1,4,1,4],[-4,-1,-4,-1],[-5,0,-5,5],[-4,4,0,3],[2,3,20,30]):
    with self.subTest(k=k,bounds=bounds):
     groups=reciprocal_segments({'k':k},{},bounds)
     for group in groups:
      for ctrl in group:
       c=np.array(ctrl);self.assertTrue(np.all(c[:,0]*c[0,0]>0));self.assertTrue(np.all(c[:,1]*c[0,1]>0))
       self.assertTrue(np.all((c[:,0]>=bounds[0])&(c[:,0]<=bounds[1])&(c[:,1]>=bounds[2])&(c[:,1]<=bounds[3])))
       for t in np.linspace(0,1,17):
        p=(1-t)**3*c[0]+3*(1-t)**2*t*c[1]+3*(1-t)*t*t*c[2]+t**3*c[3]
        self.assertLessEqual(abs(p[1]-k/p[0]),.001000001)
 def test_invalid_bounds(self):
  for b in ([0,0,-1,1],[1,-1,-1,1],[0,1,float('nan'),1],[1,2,3]):
   with self.assertRaises(ValueError):reciprocal_segments({'k':2},{},b)
 def test_free_move_rejected(self):
  s=copy.deepcopy(fixture);s['chapters'][0]['actions']=[{'at':.6,'duration':1,'type':'move','positions':{'P':[1,2]}}]
  with self.assertRaises(ValueError):validate_spec(s)
 def test_constrain_then_cross_rejected(self):
  s=copy.deepcopy(fixture);c=s['chapters'][0];p=c['objects'][5];d=p.pop('derive');p['xy']=[1,2]
  c['actions']=[{'at':.6,'duration':.5,'type':'constrain','point':'P','derive':d},{'at':1.2,'duration':1,'type':'set_parameter','parameter':'x','value':-1}]
  with self.assertRaises(ValueError):validate_spec(s)
 def test_reflection_dependencies(self):
  objs=copy.deepcopy(fixture['chapters'][0]['objects'])
  objs += [{'id':'D','type':'point','xy':[1,1]}, {'id':'E','type':'point','xy':[1,-1]}]
  for key,axis in [('Rdiag',['O','D']),('Ranti',['O','E']),('Rx',['O','X'])]:
   objs.append({'id':key,'type':'point','derive':{'type':'reflect','source':'P','axis':axis}})
  objs.append({'id':'Rorigin','type':'point','derive':{'type':'reflect','source':'Rx','axis':['O','Y']}})
  for k in (-7,3):
   p=resolve_points(objs,parameters={'x':1.3,'k':k})
   for key in ('Rdiag','Ranti','Rorigin'):self.assertAlmostEqual(float(np.prod(p[key])),k)
 def test_circle_copy_with_parameter_point(self):
  from geometry.math2d import circle_motion_parameters,circular_position
  objs=copy.deepcopy(fixture['chapters'][0]['objects'])
  objs += [{'id':'copy','type':'point','xy':[1,2]}, {'id':'orbit','type':'circle','center':'O','radius':math.sqrt(5)}]
  start,center=circle_motion_parameters(objs,{},'copy','orbit',math.pi,{'x':1,'k':2})
  self.assertTrue(np.allclose(circular_position(start,center,math.pi,1),[-1,-2]))
 def test_4k_preserved(self):
  s=copy.deepcopy(fixture);s['canvas']={'width':2880,'height':3840,'fps':60};validate_spec(s)
print('Loaded',root)
unittest.main(argv=[sys.argv[0]],verbosity=2)
