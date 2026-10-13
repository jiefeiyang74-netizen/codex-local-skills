"""Changed text must contain exactly one unwarped glyph family per frame."""
import sys, unittest, tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'assets/engine'))
from geometry.runtime import GeometryScene, ReadableTextReplace
from manim import tempconfig, linear

class ReadabilityTests(unittest.TestCase):
    def test_changed_text_has_no_padded_or_interpolated_glyphs(self):
        with tempfile.TemporaryDirectory() as directory, tempconfig(dict(media_dir=directory)):
            scene=GeometryScene();scene.text_cache={}
            pairs=[('C 的坐标关系','C 的坐标：((a+b)/2，(a−b)/2)'),
                   ('((6+2)/2,(6−2)/2)','(4,2)'),
                   ('(-123456)','x'),('x','(-678901)')]
            for before,after in pairs:
                source=scene.text(before,32,'#33CC99',4).move_to([-1,-4,0])
                target=scene.text(after,32,'#33CC99',4).move_to([1,-5,0])
                original=source.copy();root=id(source)
                updater=lambda m,dt: None
                source.add_updater(updater)
                animation=ReadableTextReplace(source,target,rate_func=linear)
                animation.begin()
                family_ids=[id(x) for x in source.get_family()]
                for alpha in np.linspace(0,1,61):
                    animation.interpolate(float(alpha))
                    expected=(original if alpha<.5 else target).copy()
                    expected.move_to((1-alpha)*original.get_center()+alpha*target.get_center())
                    branch=animation.old_text if alpha<.5 else animation.new_text
                    np.testing.assert_allclose(branch.get_all_points(),expected.get_all_points(),atol=1e-8)
                    self.assertEqual([id(x) for x in source.get_family()],family_ids)
                    self.assertEqual(id(source),root)
                    self.assertIn(updater,source.updaters)
                    self.assertAlmostEqual(branch.get_fill_opacity(),abs(2*alpha-1))
                animation.finish()
                self.assertFalse(source.updating_suspended)
                self.assertAlmostEqual(animation.new_text.get_fill_opacity(),1)

if __name__=='__main__':unittest.main()
