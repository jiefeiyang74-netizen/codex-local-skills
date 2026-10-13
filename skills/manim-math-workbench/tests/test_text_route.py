import sys,unittest,copy
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'assets/engine'))
from geometry.runtime import text_motion_position
from geometry.schema import validate_spec
from test_text_transform_state import fixture
class RouteTests(unittest.TestCase):
 def test_exact_route(self):
  a=np.array([-1.8,-4.75,0]);z=np.array([3.2,-4.75,0]);v=[3.2,-6.25]
  for t,p in [(0,a),(.5,np.array([*v,0])),(1,z)]:np.testing.assert_allclose(text_motion_position(a,z,v,t),p)
 def test_sampled_obstacle_screening_is_not_endpoint_only(self):
  start=np.array([-2.,0.,0.]);end=np.array([2.,0.,0.])
  def hits(via):
   return any(abs(p[0])<.5 and abs(p[1])<.4 for p in
              (text_motion_position(start,end,via,t) for t in np.linspace(0,1,61)))
  self.assertTrue(hits(None))
  self.assertFalse(hits([2,-2]))
 def test_schema_accepts_and_rejects(self):
  s=fixture();s['chapters'][0]['actions'][1]['items'][0]['via']=[0,-1];validate_spec(s)
  for invalid in [[float('nan'),0],[0,float('inf')],[100,0],'x+1',[0], [True,0]]:
   bad=copy.deepcopy(s);bad['chapters'][0]['actions'][1]['items'][0]['via']=invalid
   with self.assertRaises((ValueError,TypeError)):validate_spec(bad)
if __name__=='__main__':unittest.main()
