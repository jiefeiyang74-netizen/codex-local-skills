import copy,json,os,sys,tempfile,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ENGINE=Path(os.environ.get('GEOMETRY_TEST_ENGINE',str(HERE/'candidate-engine' if (HERE/'candidate-engine').exists() else HERE.parent/'assets/engine')))
sys.path.insert(0,str(ENGINE))
from geometry.schema import validate_spec,GeometryValidationError,validate_layout_style,panel_bounds
from geometry.runtime import GeometryScene
from geometry.pipeline import compile_geometry_source

def fixture():
 c=dict(id='one',title='Test',start=0,end=2,world_bounds=[-2,2,-2,2],plot_rect=[-3,0,4,4],problem=[],objects=[dict(id='P',type='panel',rect=[3,0,3,2],shadow=True,accent='#46857D'),dict(id='T',type='text',text='Step',position=[3,0],font_size=36)],actions=[dict(type='reveal',at=.5,duration=.3,ids=['T','P']),dict(type='hide',at=1,duration=.2,ids=['P']),dict(type='reveal',at=1.4,duration=.2,ids=['P'])],checks=[],proof_layout='steps')
 return dict(schema_version='geometry-1.0',title='Test',audio_duration=2,narration='Synthetic fixture',chapters=[c])

def render(spec,style='paper_guided'):
 from manim import tempconfig,Text,Rectangle
 rows=[];previous=[]
 class Probe(GeometryScene):
  selected_style=style
  def write_report(self):pass
  def snapshot(self,stage):
   super().snapshot(stage)
   family=self.get_mobject_family_members()
   rows.append(dict(stage=stage,chapter=self.chapter['id'],snapshot=self.snapshots[-1],opening=len(getattr(self,'opening',[])),old_visible=any(m in family for m in previous),old_updaters=sum(len(c.updaters) for m in previous for c in m.get_family()),auto_cards=sum(isinstance(m,Rectangle) for m in self.board.get_family()),texts=[m.text for m in family if isinstance(m,Text)],panels={k:dict(children=len(m.submobjects),z=[c.z_index for c in m.submobjects],opacity=[float(c.family_members_with_points()[0].get_fill_opacity()) for c in m.submobjects]) for k,m in self.mobs.items() if self.defs[k]['type']=='panel' and k in self.live}))
   if stage=='chapter_end':previous.extend(self.mobs[k] for k in self.live)
 Probe.spec=copy.deepcopy(spec)
 with tempfile.TemporaryDirectory(dir=os.environ.get('GEOMETRY_TEST_TMP')) as tmp:
  with tempconfig(dict(dry_run=True,disable_caching=True,pixel_width=320,pixel_height=180,frame_rate=20,media_dir=tmp,progress_bar='none',verbosity='ERROR')):Probe().render()
 return rows

class PaperStepsTests(unittest.TestCase):
 def test_valid_and_strict_panel_fields(self):
  validate_spec(fixture())
  bad=[('rect',[0,0,0,2]),('rect',[0,0,-1,2]),('rect',[0,0,True,2]),('rect',[0,0,2]),('rect',[0,0,float('nan'),2]),('rect',[0,0,float('inf'),2]),('shadow',1),('shadow','true'),('accent',None),('accent','red'),('fill_color','#FFF'),('fill_opacity',1.1),('stroke_width',False),('stroke_width',0),('text','bad'),('z_index',3)]
  for key,value in bad:
   s=fixture();s['chapters'][0]['objects'][0][key]=value
   with self.subTest(key=key,value=value),self.assertRaises(GeometryValidationError):validate_spec(s)
 def test_canvas_includes_shadow_and_stroke(self):
  s=fixture();p=s['chapters'][0]['objects'][0];p['rect']=[6.55,0,2,2];validate_spec(s)
  p['rect']=[6.57,0,2,2]
  with self.assertRaises(GeometryValidationError):validate_spec(s)
  s=fixture();s['chapters'][0]['objects'][0]['rect']=[3,3.8,3,1]
  with self.assertRaises(GeometryValidationError):validate_spec(s)
 def test_invalid_layout_combinations(self):
  for v in [None,True,1,{},[],'other']:
   s=fixture();s['chapters'][0]['proof_layout']=v
   with self.subTest(value=v),self.assertRaises(GeometryValidationError):validate_spec(s)
  s=fixture();s['chapters'][0]['presentation']='freeform'
  validate_spec(s);compile_geometry_source(s,ENGINE,selected_style='paper_guided')
  s=fixture()
  with self.assertRaises(GeometryValidationError):compile_geometry_source(s,ENGINE,selected_style='classic_black')
  class Classic(GeometryScene):spec=s
  with self.assertRaises(GeometryValidationError):Classic()
  compile_geometry_source(s,ENGINE,selected_style='paper_guided')
 def test_budget_opt_in_is_bounded(self):
  s=fixture();c=s['chapters'][0]
  c['objects'] += [dict(id=f'X{i}',type='point',xy=[0,0]) for i in range(142)]
  validate_spec(s)
  c['proof_layout']='single'
  with self.assertRaises(GeometryValidationError):validate_spec(s)
  c['proof_layout']='steps';c['objects'].append(dict(id='overflow',type='point',xy=[0,0]))
  with self.assertRaises(GeometryValidationError):validate_spec(s)
 def test_panel_action_restrictions(self):
  for action in [dict(type='highlight',at=1,duration=.2,ids=['P']),dict(type='focus',at=1,duration=.2,ids=['P'])]:
   s=fixture();s['chapters'][0]['actions']=s['chapters'][0]['actions'][:1]+[action]
   with self.assertRaises(GeometryValidationError):validate_spec(s)
  s=fixture();s['chapters'][0]['actions'][0]['style']='draw'
  with self.assertRaises(GeometryValidationError):validate_spec(s)
 def test_real_panel_bounds_layers_and_reveal_hide(self):
  s=fixture();rows=render(s)
  self.assertNotIn('P',rows[1]['snapshot']['objects'])
  for row in [rows[0],rows[2]]:
   obj=row['snapshot']['objects']['P'];self.assertTrue(obj['safe'])
   for a,b in zip(obj['bounds'],panel_bounds(s['chapters'][0]['objects'][0])):self.assertAlmostEqual(a,b)
   self.assertEqual(row['panels']['P']['z'],[-3,-2,-1]);self.assertAlmostEqual(row['panels']['P']['opacity'][0],.1)
   self.assertAlmostEqual(row['panels']['P']['opacity'][1],1);self.assertEqual(row['auto_cards'],0)
  self.assertGreater(rows[0]['snapshot']['objects']['P']['bounds'][0],-1)
 def test_freeform_steps_standard_head_tail(self):
  s=fixture();step=s['chapters'][0];step['start']=2;step['end']=4
  for a in step['actions']:a['at']+=2
  intro=copy.deepcopy(step);intro.update(id='intro',start=0,end=2,presentation='freeform');intro.pop('proof_layout');intro['actions']=[dict(type='reveal',at=.1,duration=.3,ids=['T'])]
  tail=copy.deepcopy(step);tail.update(id='tail',start=4,end=6,proof_layout='single');tail['actions']=[dict(type='hold',at=4.5,duration=.3)]
  s.update(audio_duration=6,chapters=[intro,step,tail]);validate_spec(s)
  rows=[r for r in render(s) if r['stage']=='chapter_end']
  self.assertEqual([r['auto_cards'] for r in rows],[0,0,1])
  for row in rows[1:]:self.assertFalse(row['old_visible']);self.assertEqual(row['old_updaters'],0);self.assertEqual(row['opening'],0);self.assertIn('Test',row['texts'])
 def test_transparent_panel_shadow_does_not_tint_face(self):
  for width,height in [(3,2),(.02,.02)]:
   p=dict(id='P',type='panel',rect=[0,0,width,height],fill_opacity=0,shadow=True)
   scene=GeometryScene.__new__(GeometryScene);scene.defs={'P':p};scene.points=lambda:{}
   panel=scene.build('P');shadow=panel[0]
   for part in shadow.family_members_with_points():
    self.assertTrue(part.get_left()[0]>=width/2-1e-8 or part.get_top()[1]<=-height/2+1e-8)
    self.assertAlmostEqual(float(part.get_fill_opacity()),.1)
if __name__=='__main__':unittest.main()
