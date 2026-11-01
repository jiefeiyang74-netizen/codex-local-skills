import copy,json,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parent
ENGINE=R/'engine' if (R/'engine').is_dir() else R.parent/'assets/engine'
sys.path.insert(0,str(ENGINE))
from geometry.schema import validate_spec,GeometryValidationError
from geometry.runtime import GeometryScene

def trace(spec, style='classic_black'):
 from manim import tempconfig,Text,FadeOut
 rows=[];old_roots=[];exits=[]
 class Probe(GeometryScene):
  selected_style=style
  def write_report(self):pass
  def snapshot(self,stage):
   super().snapshot(stage)
   if stage!='chapter_end':return
   family=self.get_mobject_family_members()
   rows.append(dict(texts=[m.text for m in family if isinstance(m,Text)],opening=len(getattr(self,'opening',[])),old_visible=any(m in family for m in old_roots),old_updaters=sum(len(c.updaters) for m in old_roots for c in m.get_family())))
   old_roots.extend(self.mobs[k] for k in self.live)
   self.previous_names={m:k for k,m in self.mobs.items()}
  def play_to(self,at,*animations):
   for animation in animations:
    if isinstance(animation,FadeOut) and hasattr(self,'previous_names'):
     exits.append([self.previous_names[m] for m in animation.mobject.submobjects if m in self.previous_names])
   return super().play_to(at,*animations)
 Probe.spec=copy.deepcopy(spec)
 with tempfile.TemporaryDirectory(dir=os.environ.get('GEOMETRY_TEST_TMP')) as tmp:
  with tempconfig(dict(dry_run=True,disable_caching=True,pixel_width=320,pixel_height=180,frame_rate=20,media_dir=tmp,progress_bar='none',verbosity='ERROR')):
   scene=Probe();scene.render()
 return rows,exits
def fixture():
 c=dict(id='first',title='观察线段',start=0,end=2,world_bounds=[-2,2,-2,2],problem=[],objects=[dict(id='A',type='point',xy=[-1,0]),dict(id='B',type='point',xy=[1,0]),dict(id='AB',type='line',a='A',b='B')],actions=[dict(type='reveal',at=.5,duration=.5,ids=['AB'],style='draw')],checks=[dict(type='distance',points=['A','B'],value=2)])
 d=copy.deepcopy(c);d.update(id='second',title='正式图',start=2,end=4);d['actions'][0]['at']=2.5
 return dict(schema_version='geometry-1.0',title='线段',audio_duration=4,narration='观察线段，再看正式图。',canvas=dict(width=960,height=720,fps=60),chapters=[c,d])
class FreeformTests(unittest.TestCase):
 def test_default_unchanged(self):
  s=fixture();old=copy.deepcopy(s);validate_spec(s);GeometryScene._validate_clock(SimpleNamespace(spec=s));self.assertEqual(s,old)
 def test_opt_in_and_exit_use_explicit_clock(self):
  s=fixture();s['chapters'][0]['presentation']='freeform';s['chapters'][0]['actions'][0]['at']=.08;s['chapters'][1]['actions'][0]['at']=2
  validate_spec(s);GeometryScene._validate_clock(SimpleNamespace(spec=s))
 def test_standard_still_reserves_heading(self):
  s=fixture();s['chapters'][1]['actions'][0]['at']=2
  with self.assertRaises(GeometryValidationError):validate_spec(s)
  with self.assertRaises(ValueError):GeometryScene._validate_clock(SimpleNamespace(spec=s))
 def test_reject_unknown_and_wrong_type(self):
  for bad in [None,True,0,{},[], 'automatic', 'free_form']:
   s=fixture();s['chapters'][0]['presentation']=bad
   with self.subTest(bad=bad),self.assertRaises(GeometryValidationError):validate_spec(s)
 def test_freeform_does_not_relax_overlap_or_math(self):
  s=fixture();s['chapters'][0]['presentation']='freeform';s['chapters'][0]['actions'].append(dict(type='hold',at=.75,duration=.5))
  with self.assertRaises(GeometryValidationError):validate_spec(s)
  s=fixture();s['chapters'][0]['presentation']='freeform';s['chapters'][0]['checks'][0]['value']=3
  with self.assertRaises((GeometryValidationError,ValueError)):validate_spec(s)
 def test_large_text_only_not_point_labels(self):
  s=fixture();s['chapters'][0]['objects'].append(dict(id='big',type='text',text='线段',position=[0,1],font_size=76,max_width=5))
  validate_spec(s)
  s['chapters'][0]['objects'][0]['font_size']=76
  with self.assertRaises(GeometryValidationError):validate_spec(s)
 def test_classic_title_restoration_in_actual_construct(self):
  for same in [True,False]:
   for incoming in ['standard','freeform']:
    s=fixture();s['heading_mode']='standard'
    s['chapters'][0]['presentation']='freeform' if incoming=='standard' else 'standard'
    s['chapters'][1]['presentation']=incoming
    if same:s['chapters'][1]['title']=s['chapters'][0]['title']
    rows,_=trace(s)
    with self.subTest(same=same,incoming=incoming):
     self.assertEqual(s['title'] in rows[1]['texts'],incoming=='standard')
     self.assertFalse(rows[1]['old_visible']);self.assertEqual(rows[1]['opening'],0)
 def test_empty_transition_consumed_in_own_chapter(self):
  for style in ['classic_black','paper_guided']:
   for previous,incoming in [('freeform','standard'),('standard','freeform'),('freeform','freeform')]:
    s=fixture();s['chapters'][0]['presentation']=previous;s['chapters'][1]['presentation']=incoming;s['chapters'][1]['actions']=[]
    validate_spec(s);rows,_=trace(s,style)
    with self.subTest(style=style,previous=previous,incoming=incoming):
     self.assertFalse(rows[1]['old_visible']);self.assertEqual(rows[1]['opening'],0);self.assertEqual(rows[1]['old_updaters'],0)
     self.assertEqual(bool(rows[1]['texts']),incoming=='standard')
 def test_empty_short_and_subframe_transitions(self):
  for duration in [.1,.001]:
   s=fixture();s['chapters'][0]['presentation']='freeform';s['chapters'][1]['actions']=[];s['chapters'][1]['end']=2+duration;s['audio_duration']=2+duration
   validate_spec(s);rows,_=trace(s)
   self.assertFalse(rows[1]['old_visible']);self.assertEqual(rows[1]['opening'],0)
   self.assertIn(s['title'],rows[1]['texts'])
 def test_empty_transition_does_not_leak_into_following_standard(self):
  s=fixture();s['chapters'][0]['presentation']='freeform';s['chapters'][1]['actions']=[]
  third=copy.deepcopy(s['chapters'][0]);third.update(id='third',start=4,end=6,presentation='standard');third['actions'][0]['at']=4.5
  s['chapters'].append(third);s['audio_duration']=6
  validate_spec(s);rows,_=trace(s)
  for row in rows[1:]:self.assertFalse(row['old_visible']);self.assertEqual(row['opening'],0)
 def test_hold_consumes_opening(self):
  s=fixture();s['chapters'][0]['presentation']='freeform';s['chapters'][1]['actions']=[dict(type='hold',at=2,duration=.4)]
  validate_spec(s);rows,_=trace(s)
  self.assertFalse(rows[1]['old_visible']);self.assertEqual(rows[1]['opening'],0)
 def test_exit_uses_live_order_after_hide_reveal_and_text_transform(self):
  s=fixture();c=s['chapters'][0];c['presentation']='freeform';c['checks']=[]
  c['objects']=[dict(id=k,type='text',text=k,position=[i-1,0]) for i,k in enumerate(['A','B','C'])]
  c['actions']=[dict(type='reveal',at=.1,duration=.2,ids=['C','A','B']),dict(type='hide',at=.4,duration=.2,ids=['A']),dict(type='reveal',at=.7,duration=.2,ids=['A']),dict(type='text_transform',at=1.1,duration=.3,items=[dict(id='B',text='New',position=[0,0])])]
  validate_spec(s);rows,exits=trace(s)
  self.assertEqual(exits[0],['C','B','A']);self.assertFalse(rows[1]['old_visible']);self.assertEqual(rows[1]['old_updaters'],0)
if __name__=='__main__':unittest.main()
