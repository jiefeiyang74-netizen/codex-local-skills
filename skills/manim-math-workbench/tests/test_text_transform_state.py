"""Serial lifecycle regression; intentionally makes no skip/prefix guarantee."""
import copy, os, sys, tempfile, unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from geometry.schema import validate_spec
from geometry.runtime import GeometryScene
from manim import tempconfig

def fixture():
    style=dict(type='text',color='#33CC99',font_size=44,max_width=.9,formula_group='eq')
    objects=[dict(style,id='term',text='(-12345)',position=[-1,0]),
             dict(style,id='copy',text='(-67890)',position=[1,-1])]
    def a(kind,at,**kw):return dict(type=kind,at=at,duration=.5,**kw)
    actions=[a('reveal',.5,ids=['term']),
             a('text_transform',1,items=[dict(id='term',position=[0,0],text='x')]),
             a('text_transform',1.75,items=[dict(id='term',position=[1,0],text='(-67890)')]),
             a('hide',2.5,ids=['term']),a('reveal',3.25,ids=['term']),
             a('text_transform',4,items=[dict(id='term',position=[1,0])]),
             a('translate_copy',4.75,sources=['term'],targets=['copy'],vector=[0,-1],style='continuous')]
    return dict(schema_version='geometry-1.0',title='Serial text lifecycle',narration='Synthetic silent state fixture.',audio_duration=6,
                canvas=dict(width=960,height=540,fps=60),chapters=[dict(id='state',title='Long short long / hide reveal / copy',start=0,end=6,world_bounds=[-5,5,-3,3],plot_rect=[0,0,10,6],problem=[],objects=objects,actions=actions,checks=[])])

class CheckedScene(GeometryScene):
    def construct(self):
        self.identities={};self.observations=[]
        super().construct()
    def perform(self,a):
        super().perform(a)
        for k,m in self.mobs.items():
            self.identities.setdefault(k,id(m))
            if id(m)!=self.identities[k]:raise AssertionError('ID replaced')
        for k in self.live:
            m=self.mobs[k];fresh=self.build(k)
            np.testing.assert_allclose(m.get_all_points(),fresh.get_all_points(),atol=1e-8)
            for actual,wanted in zip(m.family_members_with_points(),fresh.family_members_with_points()):
                np.testing.assert_allclose(actual.get_fill_opacity(),wanted.get_fill_opacity())
                np.testing.assert_allclose(actual.get_fill_color().to_rgb(),wanted.get_fill_color().to_rgb())
            if m.width>.900001:raise AssertionError('width budget changed')
            before=m.get_all_points().copy();m.update(0);m.update(.1)
            np.testing.assert_array_equal(before,m.get_all_points())
        if a['type']=='hide' and self.mobs['term'] in self.get_mobject_family_members():raise AssertionError('hidden object remains')
        self.observations.append(dict(action=a['type'],at=float(self.time),live=sorted(self.live),state=copy.deepcopy(self.active_objects)))

class StateTests(unittest.TestCase):
    def test_serial_long_short_long_reveal_styles_copy(self):
        spec=fixture();validate_spec(spec);original=copy.deepcopy(spec)
        with tempfile.TemporaryDirectory() as directory:
            old=os.environ.get('GEOMETRY_REPORT_PATH')
            os.environ['GEOMETRY_REPORT_PATH']=str(Path(directory)/'state.json')
            try:
                with tempconfig(dict(dry_run=True,pixel_width=320,pixel_height=180,frame_rate=60,media_dir=directory,disable_caching=True,verbosity='ERROR')):
                    scene=CheckedScene();scene.spec=spec;scene.render()
                    self.assertEqual(len(scene.observations),7)
                    self.assertEqual(scene.defs['term']['text'],'(-67890)')
                    self.assertEqual(scene.defs['term']['font_size'],44)
                    self.assertEqual(scene.live,{'term','copy'})
            finally:
                if old is None:os.environ.pop('GEOMETRY_REPORT_PATH',None)
                else:os.environ['GEOMETRY_REPORT_PATH']=old
        self.assertEqual(spec,original)

if __name__=='__main__':unittest.main()
