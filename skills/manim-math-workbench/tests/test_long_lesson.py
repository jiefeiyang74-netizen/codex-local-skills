"""Bounded profile, compiler identity and streaming reports; synthetic only."""
import ast,copy,inspect,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from geometry.schema import validate_spec,production_limits,contract
from geometry.pipeline import render_identity,compile_geometry_source,RENDER_TIMEOUT_SECONDS,command

def fixture(duration=4,count=1,actions=0,profile=None):
    result={'schema_version':'geometry-1.0','title':'合成边界测试','audio_duration':duration,
      'narration':'仅合成能力夹具，不是正式口播。','canvas':{'width':3840,'height':2160,'fps':60},'chapters':[]}
    if profile is not None: result['production_profile']=profile
    for i in range(count):
        start=duration*i/count; end=duration*(i+1)/count
        n=min(500,actions); actions-=n
        result['chapters'].append({'id':f'c{i}','title':'合成章','start':start,'end':end,
          'world_bounds':[-1,1,-1,1],'problem':[],'objects':[],'checks':[],
          'actions':[{'type':'hold','at':start+.6+j*.01,'duration':.005} for j in range(n)]})
    assert actions==0
    return result

class LongLesson(unittest.TestCase):
    def test_default_limits_unchanged(self):
        validate_spec(fixture(7200,100,3000))
        for args in [(7200.001,1,0),(7200,101,0),(7200,7,3001)]:
            with self.assertRaises(ValueError): validate_spec(fixture(*args))
    def test_explicit_standard_same_guards(self):
        validate_spec(fixture(7200,100,3000,'standard'))
        with self.assertRaises(ValueError): validate_spec(fixture(7201,1,0,'standard'))
    def test_long_max_boundaries_valid(self):
        validate_spec(fixture(14400,512,12000,'long_lesson'))
    def test_long_overflow_rejected(self):
        for args in [(14400.001,1,0),(14400,513,0),(14400,25,12001)]:
            with self.assertRaises(ValueError): validate_spec(fixture(*args,'long_lesson'))
    def test_unknown_profiles_rejected(self):
        for value in ['LONG_LESSON','',True,None,{},[],1]:
            spec=fixture(); spec['production_profile']=value
            with self.assertRaises(ValueError): validate_spec(spec)
    def test_object_and_action_guard_not_relaxed(self):
        spec=fixture(14400,1,0,'long_lesson')
        spec['chapters'][0]['objects']=[{'id':f'p{i}','type':'point','xy':[0,0]} for i in range(121)]
        with self.assertRaises(ValueError): validate_spec(spec)
        spec=fixture(14400,1,500,'long_lesson'); spec['chapters'][0]['actions'].append({'type':'hold','at':10,'duration':1})
        with self.assertRaises(ValueError): validate_spec(spec)
    def test_math_lifecycle_unchanged(self):
        spec=json.loads((ROOT/'examples/geometry_minimal.json').read_text(encoding='utf-8')); spec['production_profile']='long_lesson'
        spec['chapters'][0]['checks'][0]['value']=6
        with self.assertRaises(ValueError): validate_spec(spec)
        spec=json.loads((ROOT/'examples/geometry_minimal.json').read_text(encoding='utf-8')); spec['production_profile']='long_lesson'
        spec['chapters'][0]['actions'][0]['type']='hide'; spec['chapters'][0]['actions'][0].pop('style')
        with self.assertRaises(ValueError): validate_spec(spec)
    def test_profile_survives_normalization_and_compile(self):
        spec=fixture(profile='long_lesson'); result=validate_spec(spec)
        self.assertEqual(result['production_profile'],'long_lesson')
        tree=ast.parse(compile_geometry_source(spec,ROOT/'assets/engine'))
        compiled=ast.literal_eval(tree.body[-1].body[0].value)
        self.assertEqual(compiled,spec)
        invalid=copy.deepcopy(spec); invalid['production_profile']='unknown'
        with self.assertRaises(ValueError): compile_geometry_source(invalid,ROOT)
    def test_profile_changes_actual_cache_identity(self):
        spec=fixture(); old=render_identity(spec,'engine','audio','alignment','audit')
        long=copy.deepcopy(spec); long['production_profile']='long_lesson'
        self.assertNotEqual(old,render_identity(long,'engine','audio','alignment','audit'))
        self.assertEqual(old,render_identity(spec,'engine','audio','alignment','audit'))
    def test_contract_and_timeout(self):
        self.assertEqual(contract()['production_profiles']['long_lesson'],{'max_duration':14400,'max_chapters':512,'max_total_actions':12000})
        self.assertEqual(RENDER_TIMEOUT_SECONDS,43200)
        self.assertEqual(inspect.signature(command).parameters['timeout'].default,43200)
    def test_long_report_streams_without_retaining_snapshots(self):
        from geometry.runtime import GeometryScene
        with tempfile.TemporaryDirectory() as temp:
            scene=object.__new__(GeometryScene); scene.spec=fixture(profile='long_lesson')
            scene.events=[{'type':'synthetic'}]; scene.runtime_stats={}
            path=Path(temp)/'report.geometry.json'; scene._report_path=lambda:path
            scene._snapshot_spool=Path(temp)/'snapshots.jsonl'; scene._snapshot_spool.write_text('',encoding='utf-8')
            scene.snapshots=[{'chapter':'c0','checks':[{'passed':True}]}]
            scene._flush_snapshot_spool(); self.assertEqual(scene.snapshots,[])
            scene.snapshots=[{'chapter':'c1','checks':[{'passed':True}]}]; scene.write_report()
            out=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(out['production_profile'],'long_lesson')
            self.assertEqual([s['chapter'] for s in out['snapshots']],['c0','c1'])
            self.assertEqual(scene.snapshots,[])
    def test_standard_report_keeps_prior_shape(self):
        from geometry.runtime import GeometryScene
        with tempfile.TemporaryDirectory() as temp:
            scene=object.__new__(GeometryScene); scene.spec=fixture(); scene.events=[]; scene.runtime_stats={}
            scene.snapshots=[{'chapter':'c0'}]; scene._snapshot_spool=None
            path=Path(temp)/'report.geometry.json'; scene._report_path=lambda:path; scene.write_report()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['snapshots'],scene.snapshots)

if __name__=='__main__': unittest.main()
