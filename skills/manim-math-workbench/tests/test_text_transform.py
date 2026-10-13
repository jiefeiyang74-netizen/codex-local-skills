import copy, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from geometry.schema import validate_spec, contract

def fixture():
    return json.loads((ROOT/'examples/text_transform.json').read_text(encoding='utf-8'))

class TextTransformTests(unittest.TestCase):
    def test_fixture_and_purity(self):
        spec=fixture(); before=copy.deepcopy(spec)
        validate_spec(spec)
        self.assertEqual(spec,before)
        self.assertIn('text_transform',contract()['action_fields'])

    def test_bad_items(self):
        changes=[{'position':[True,0]},{'position':[float('nan'),0]},
                 {'position':[0,float('inf')]},{'position':['x+1',0]},
                 {'position':[100,0]},{'position':[1]}, {'id':'missing'},
                 {'id':'clone'},{'id':[]},{'text':''},{'text':'a'*65},
                 {'text':'x\ny'},{'text':'\\input'},{'font_size':50},
                 {'formula_group':'other'},{'python':'eval(1)'}]
        for change in changes:
            for math in [True,False]:
                spec=fixture();spec['chapters'][0]['actions'][1]['items'][0].update(change)
                with self.subTest(change=change,math=math),self.assertRaises(ValueError):
                    validate_spec(spec,run_math=math)

    def test_duplicate_unknown_fields_and_missing(self):
        for kind in ['duplicate','empty','unknown','missing','point']:
            spec=fixture(); ch=spec['chapters'][0]; action=ch['actions'][1]
            if kind=='duplicate': action['items'].append(copy.deepcopy(action['items'][0]))
            if kind=='empty': action['items']=[]
            if kind=='unknown': action['duration_expression']='1+1'
            if kind=='missing': del action['items'][0]['position']
            if kind=='point': ch['objects'][1]={'id':'sign','type':'point','xy':[0,0],'label':'+'}
            with self.subTest(kind=kind),self.assertRaises(ValueError): validate_spec(spec)

    def test_post_transform_copy_state_and_budget(self):
        spec=fixture(); validate_spec(spec)
        spec['chapters'][0]['objects'][-1]['text']='2'
        with self.assertRaisesRegex(ValueError,'content/font_size'):validate_spec(spec)
        spec=fixture(); ch=spec['chapters'][0]
        ch['actions']=ch['actions'][:2]
        ch['actions'][1]['items']=[dict(id=k,position=[0,0],text='a'*64) for k in ['lhs','sign','term','equals']]
        with self.assertRaisesRegex(ValueError,'character budget'):validate_spec(spec)

if __name__=='__main__':unittest.main()
