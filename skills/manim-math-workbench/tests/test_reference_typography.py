import copy,json,os,sys,tempfile,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ENGINE=Path(os.environ.get('GEOMETRY_TEST_ENGINE',str(HERE/'candidate-engine' if (HERE/'candidate-engine').exists() else HERE.parent/'assets/engine')))
sys.path.insert(0,str(ENGINE))
from geometry.schema import validate_spec,GeometryValidationError,panel_bounds,validate_layout_style
from geometry.pipeline import compile_geometry_source
from geometry.runtime import GeometryScene
from manim import tempconfig,BackgroundRectangle,Text

def fixture():
 c=dict(id='one',title='One',start=0,end=2,world_bounds=[-2,2,-2,2],plot_rect=[0,0,4,4],problem=[],objects=[dict(id='P',type='point',xy=[-1,0],label='P',typography='math',label_mask=False),dict(id='T',type='text',text='△ABC≅△DEF',position=[1,1],typography='math'),dict(id='S',type='text',text='SAS（边角边）',position=[1,-1],typography='serif')],actions=[dict(type='reveal',at=.1,duration=.3,ids=['P','T','S'])],checks=[],proof_layout='steps',presentation='freeform')
 return dict(schema_version='geometry-1.0',title='Test',audio_duration=2,narration='Synthetic typography fixture',paper_palette='reference_yellow',chapters=[c])

def scene_for(spec):
 class Probe(GeometryScene):
  selected_style='paper_guided'
  def write_report(self):pass
 Probe.spec=spec
 return Probe()

def glyph_coverage():
 import ctypes
 from ctypes import wintypes as w
 g=ctypes.WinDLL('gdi32',use_last_error=True)
 g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
 g.CreateFontW.argtypes=[ctypes.c_int]*5+[w.DWORD]*8+[w.LPCWSTR];g.CreateFontW.restype=w.HANDLE
 g.SelectObject.argtypes=[w.HDC,w.HANDLE];g.SelectObject.restype=w.HANDLE
 g.GetGlyphIndicesW.argtypes=[w.HDC,w.LPCWSTR,ctypes.c_int,ctypes.POINTER(w.WORD),w.DWORD];g.GetGlyphIndicesW.restype=w.DWORD
 g.GetTextFaceW.argtypes=[w.HDC,ctypes.c_int,w.LPWSTR];g.GetTextFaceW.restype=ctypes.c_int
 g.DeleteObject.argtypes=[w.HANDLE];g.DeleteDC.argtypes=[w.HDC]
 rows=[]
 for font,italic,chars in [('Cambria',1,'ABCDEFxyzSAS123'),('Cambria Math',0,'△∠≅≥≤∥⊥=+−×÷√'),('SimSun',0,'已知边角边（），判定')]:
  dc=g.CreateCompatibleDC(None);hf=g.CreateFontW(-32,0,0,0,400,italic,0,0,1,0,0,0,0,font)
  if not dc or not hf:raise RuntimeError('GDI font allocation failed')
  previous=g.SelectObject(dc,hf)
  try:
   face=ctypes.create_unicode_buffer(128);g.GetTextFaceW(dc,128,face)
   indices=(w.WORD*len(chars))();result=g.GetGlyphIndicesW(dc,chars,len(chars),indices,1)
   rows.append(dict(font=font,resolved_face=face.value,italic=bool(italic),chars=chars,missing=[c for c,i in zip(chars,indices) if i==0xFFFF],api_ok=result!=0xFFFFFFFF))
  finally:g.SelectObject(dc,previous);g.DeleteObject(hf);g.DeleteDC(dc)
 return rows

class ReferenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('GEOMETRY_TEST_TMP'))
  self.cfg=tempconfig(dict(dry_run=True,disable_caching=True,pixel_width=320,pixel_height=180,frame_rate=20,media_dir=self.tmp.name,progress_bar='none',verbosity='ERROR'));self.cfg.__enter__()
 def tearDown(self):self.cfg.__exit__(None,None,None);self.tmp.cleanup()
 def test_schema_and_style_boundaries(self):
  validate_spec(fixture());compile_geometry_source(fixture(),ENGINE,selected_style='paper_guided')
  for key,vals in [('paper_palette',[None,True,{},'other'])]:
   for v in vals:
    s=fixture();s[key]=v
    with self.assertRaises(GeometryValidationError):validate_spec(s)
  for v in [None,True,[],{},'font_name']:
   s=fixture();s['chapters'][0]['objects'][1]['typography']=v
   with self.assertRaises(GeometryValidationError):validate_spec(s)
  for v in [None,1,'false']:
   s=fixture();s['chapters'][0]['objects'][0]['label_mask']=v
   with self.assertRaises(GeometryValidationError):validate_spec(s)
  s=fixture();s['chapters'][0]['objects'][1]['label_mask']=False
  with self.assertRaises(GeometryValidationError):validate_spec(s)
  with self.assertRaises(GeometryValidationError):compile_geometry_source(fixture(),ENGINE,selected_style='classic_black')
  s=fixture();s.pop('paper_palette')
  with self.assertRaises(GeometryValidationError):compile_geometry_source(s,ENGINE,selected_style='classic_black')
 def test_cache_fonts_mixed_and_mask(self):
  scene=scene_for(fixture());scene.render()
  point=scene.mobs['P'];self.assertFalse(any(isinstance(m,BackgroundRectangle) for m in point.get_family()))
  t=scene.mobs['T'];self.assertEqual(t.font,'Cambria');self.assertEqual(t.slant,'ITALIC')
  self.assertEqual(t.t2f['△'],'Cambria Math');self.assertEqual(t.t2s['≅'],'NORMAL')
  mixed=scene.text('SAS（边角边）≥1',typography='math')
  self.assertEqual(mixed.t2f['边'],'SimSun');self.assertEqual(mixed.t2s['边'],'NORMAL')
  self.assertEqual(scene.mobs['S'].font,'SimSun')
  a=scene.text('ABC',typography='body');b=scene.text('ABC',typography='math');c=scene.text('ABC',typography='serif')
  self.assertEqual([a.font,b.font,c.font],['Microsoft YaHei','Cambria','SimSun'])
  s=fixture();s['chapters'][0]['objects'][0].pop('label_mask');other=scene_for(s);other.render()
  self.assertTrue(any(isinstance(m,BackgroundRectangle) for m in other.mobs['P'].get_family()))
 def test_transform_and_continuous_copy(self):
  s=fixture();c=s['chapters'][0];c['objects'].append(dict(id='U',type='text',text='∠ABC=∠DEF',position=[2,1],typography='math'))
  c['actions'] += [dict(type='text_transform',at=.6,duration=.3,items=[dict(id='T',text='∠ABC=∠DEF',position=[1,1])]),dict(type='translate_copy',at=1.1,duration=.3,sources=['T'],targets=['U'],vector=[1,0],style='continuous')]
  validate_spec(s);scene=scene_for(s);scene.render();self.assertEqual(scene.mobs['T'].font,'Cambria');self.assertEqual(scene.mobs['U'].font,'Cambria')
  self.assertEqual(scene.mobs['T'].text,'∠ABC=∠DEF')
  c['objects'][-1]['typography']='serif'
  with self.assertRaises(GeometryValidationError):validate_spec(s)
 def test_point_copy_mask_and_typography(self):
  s=fixture();c=s['chapters'][0];c['objects'].append(dict(id='Q',type='point',xy=[0,0],label='Q',typography='math',label_mask=False))
  c['actions'].append(dict(type='translate_copy',at=.7,duration=.3,sources=['P'],targets=['Q'],vector=[1,0]))
  validate_spec(s);scene=scene_for(s);scene.render()
  self.assertFalse(any(isinstance(m,BackgroundRectangle) for m in scene.mobs['Q'].get_family()))
  for key,val in [('label_mask',True),('typography','body')]:
   trial=copy.deepcopy(s);trial['chapters'][0]['objects'][-1][key]=val
   with self.assertRaises(GeometryValidationError):validate_spec(trial)
 def test_outline_bounds_and_soft_default(self):
  p=dict(id='B',type='panel',rect=[0,0,3,2],shadow=True,shadow_style='outline')
  s=fixture();s['chapters'][0]['objects'].append(p);validate_spec(s)
  scene=scene_for(s);scene.render();panel=scene.mobs['B'];shadow=panel[0]
  self.assertEqual(float(shadow.get_fill_opacity()),0);self.assertEqual(float(shadow.get_stroke_width()),1)
  self.assertEqual(shadow.get_stroke_color().to_hex().upper(),'#7C7965')
  self.assertAlmostEqual(float(shadow.get_center()[0]),.0375);self.assertAlmostEqual(float(shadow.get_center()[1]),-.0375)
  self.assertEqual(panel_bounds(p),[-1.51,1.5475,-1.5475+0.5,1.01])
  for key,val in [('shadow',False),('shadow_style',None),('shadow_style','other')]:
   trial=copy.deepcopy(s);trial['chapters'][0]['objects'][-1][key]=val
   with self.assertRaises(GeometryValidationError):validate_spec(trial)
 def test_freeform_steps_budget(self):
  s=fixture();s['chapters'][0]['objects'] += [dict(id=f'X{i}',type='point',xy=[0,0]) for i in range(141)];validate_spec(s)
  s['chapters'][0]['objects'].append(dict(id='overflow',type='point',xy=[0,0]))
  with self.assertRaises(GeometryValidationError):validate_spec(s)
 def test_heavy_headline_typography(self):
  s=fixture();s['chapters'][0]['objects'].append(dict(id='H',type='text',text='倒着想',position=[0,0],font_size=72,typography='heavy'))
  validate_spec(s);compile_geometry_source(s,ENGINE,selected_style='paper_guided')
  scene=scene_for(s);scene.render();h=scene.text('倒着想',72,typography='heavy');self.assertEqual((h.font,h.weight),('Microsoft YaHei','BOLD'))
  self.assertEqual(scene.text('倒着想',72,typography='body').weight,'NORMAL')      # 旧字重规则不变
  self.assertEqual(scene.text('数学',36,typography='body').weight,'BOLD')
  with self.assertRaises(GeometryValidationError):compile_geometry_source(s,ENGINE,selected_style='classic_black')
  trial=copy.deepcopy(s);trial['chapters'][0]['objects'][0]['typography']='heavy'
  with self.assertRaises(GeometryValidationError):validate_spec(trial)          # 点名不能用 heavy
  scene.paper=False
  with self.assertRaises(ValueError):scene.text('X',72,typography='heavy')
 @unittest.skipUnless(sys.platform=='win32','Windows installed-font audit')
 def test_required_glyphs_exist(self):
  for row in glyph_coverage():
   self.assertTrue(row['api_ok']);self.assertFalse(row['missing'])
   self.assertIn(row['resolved_face'],[row['font'],'宋体'] if row['font']=='SimSun' else [row['font']])
if __name__=='__main__':unittest.main()
