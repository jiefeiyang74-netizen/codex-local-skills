"""Verify the actual highlight pulse keeps opaque masks fixed, with visible glyphs."""
import sys,tempfile,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from manim import BackgroundRectangle,Dot,Text,Line,VGroup,Indicate,tempconfig
from manim.utils.color import ManimColor
from geometry.runtime import MaskSafeIndicate

class HighlightMaskTests(unittest.TestCase):
 def setUp(self):
  self.config=tempconfig({'media_dir':tempfile.mkdtemp(prefix='highlight-test-')})
  self.config.__enter__();self.addCleanup(self.config.__exit__,None,None,None)
 def masked_text(self,value):
  text=Text(value,font='Microsoft YaHei',font_size=32,color='#FFFFFF')
  text.set_z_index(10);text.add_background_rectangle(color='#000000',opacity=1,buff=.04);text.background_rectangle.set_z_index(9)
  return text
 def assert_mask_and_pulse(self,mob):
  original=mob.copy();masks=[x for x in mob.get_family() if isinstance(x,BackgroundRectangle)]
  self.assertTrue(masks)
  states=[(x.points.copy(),x.fill_rgbas.copy(),x.stroke_rgbas.copy(),x.z_index) for x in masks]
  pulse=MaskSafeIndicate(mob,color='#FFD166',scale_factor=1);pulse.begin()
  for alpha in [0,.125,.25,.5,.75,.875,1]:
   pulse.interpolate(alpha)
   for mask,(points,fill,stroke,z) in zip(masks,states):
    np.testing.assert_allclose(mask.points,points,atol=1e-12);np.testing.assert_allclose(mask.fill_rgbas,fill,atol=1e-12);np.testing.assert_allclose(mask.stroke_rgbas,stroke,atol=1e-12);self.assertEqual(mask.z_index,z)
   if alpha==.5:
    for node in mob.family_members_with_points():
     if isinstance(node,BackgroundRectangle):continue
     if node.get_fill_opacity()>0:np.testing.assert_allclose(node.fill_rgbas[0,:3],ManimColor('#FFD166').to_rgb(),atol=1e-12)
    self.assertTrue(any(not np.allclose(now.fill_rgbas,old.fill_rgbas) for now,old in zip(mob.get_family(),original.get_family()) if now.has_points() and not isinstance(now,BackgroundRectangle)))
   for now,old in zip(mob.get_family(),original.get_family()):np.testing.assert_allclose(now.points,old.points,atol=1e-12)
  pulse.finish()
  self.assertEqual(len(mob.get_family()),len(original.get_family()))
  for now,old in zip(mob.get_family(),original.get_family()):
   np.testing.assert_allclose(now.points,old.points,atol=1e-12)
   if now.has_points():np.testing.assert_allclose(now.fill_rgbas,old.fill_rgbas,atol=1e-12);np.testing.assert_allclose(now.stroke_rgbas,old.stroke_rgbas,atol=1e-12)
 def test_point_and_label_mask_survive_entire_pulse_and_repeat(self):
  text=self.masked_text('R').shift([.3,.35,0]);group=VGroup(Dot(color='#52C7EA'),text)
  self.assert_mask_and_pulse(group);self.assert_mask_and_pulse(group)
 def test_standalone_background_text_and_nested_group(self):
  self.assert_mask_and_pulse(self.masked_text('QP'))
  self.assert_mask_and_pulse(VGroup(VGroup(self.masked_text('H')),Line([-1,-1,0],[1,-1,0])))
 def test_original_indicate_reproduces_colored_scaled_mask(self):
  text=self.masked_text('R');mask=text.background_rectangle;before=mask.copy();anim=Indicate(text,color='#FFD166',scale_factor=1.04);anim.begin();anim.interpolate(.5)
  self.assertFalse(np.allclose(mask.fill_rgbas,before.fill_rgbas));self.assertFalse(np.allclose(mask.points,before.points))
 def test_unmasked_line_matches_original_animation(self):
  a=Line([-1,0,0],[1,0,0],color='#52C7EA');b=a.copy();x=MaskSafeIndicate(a,color='#FFD166',scale_factor=1);y=Indicate(b,color='#FFD166',scale_factor=1);x.begin();y.begin()
  for alpha in [0,.25,.5,.75,1]:
   x.interpolate(alpha);y.interpolate(alpha);np.testing.assert_allclose(a.points,b.points);np.testing.assert_allclose(a.stroke_rgbas,b.stroke_rgbas)
if __name__=='__main__':unittest.main()
