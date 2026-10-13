"""C01 regression fixtures are test-only; no production timing claims."""
import copy, hashlib, json, sys, tempfile, unittest, wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from geometry.pipeline import validate_alignment,validate_action_audit,digest

class Provenance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        raw=[{'text':'转','offsets':{'from':100,'to':200}}, {'text':'动','offsets':{'from':200,'to':400}},
             {'text':'。','offsets':{'from':400,'to':400}}, {'text':'结束','offsets':{'from':1200,'to':1800}}]
        p=self.root/'raw.json'; p.write_text(json.dumps({'transcription':[{'tokens':raw}]}),encoding='utf-8')
        anchors=[]
        for i,t in enumerate(raw):
            s,e=t['offsets']['from']/1000,t['offsets']['to']/1000
            anchors.append({'id':i,'text':t['text'],'raw_token':t,'start':s if e>s else None,'end':e if e>s else None,
                            'source':'whisper_cpp','time_source':'original Whisper null if invalid','raw_start':s,'raw_end':e})
        self.data={'duration':2,'source':'whisper_cpp','source_audio_sha256':'audio','canonical_narration_sha256':digest('转动。结束'),
                   'anchors':anchors,'raw_evidence':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]}
    def tearDown(self):self.temp.cleanup()
    def validate(self,d=None):return validate_alignment(d or self.data,'audio','转动。结束',2)
    def test_original_and_null_tokens_pass(self):self.assertEqual(list(self.validate()),['0','1','3'])
    def test_source_label_without_raw_evidence_rejected(self):
        d=copy.deepcopy(self.data); del d['raw_evidence']
        with self.assertRaisesRegex(ValueError,'raw_evidence'):self.validate(d)
    def test_original_file_tamper_rejected(self):
        Path(self.data['raw_evidence'][0]['path']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'SHA'):self.validate()
    def test_token_time_tamper_rejected(self):
        d=copy.deepcopy(self.data); d['anchors'][0]['start']=.11
        with self.assertRaisesRegex(ValueError,'time mismatch'):self.validate(d)
    def test_token_text_tamper_rejected(self):
        d=copy.deepcopy(self.data); d['anchors'][0]['text']='错'
        with self.assertRaisesRegex(ValueError,'raw/text'):self.validate(d)
    def test_null_interpolation_rejected(self):
        d=copy.deepcopy(self.data); d['anchors'][2].update(start=.4,end=.5)
        with self.assertRaisesRegex(ValueError,'time mismatch'):self.validate(d)
    def fixture(self):
        tokens=self.validate(); action={'at':.1,'duration':1.2}
        spec={'narration':'转动。结束','canvas':{'fps':60},'chapters':[{'id':'c','actions':[action]}]}
        entry={'chapter_id':'c','action_index':0,'at':.1,'anchor_ids':[0,1],'master_char_start':0,'master_char_end':2,'anchor_text':'转动',
               'trigger_evidence':{'anchor_ids':[0,1],'alignment_pairs':[{'master_char':0,'expected':'转','raw_token_id':0},{'master_char':1,'expected':'动','raw_token_id':1}]},
               'motion_window':{'master_char_start':0,'master_char_end':5,'text':'转动。结束','anchor_ids':[0,1,3],
                   'source_token_pairs':[{'master_char':0,'expected':'转','raw_token_id':0},{'master_char':1,'expected':'动','raw_token_id':1},
                                         {'master_char':3,'expected':'结','raw_token_id':3},{'master_char':4,'expected':'束','raw_token_id':3}]}}
        audit={'source_audio_sha256':'audio','canonical_narration_sha256':digest(spec['narration']),'alignment_sha256':'align','actions':[entry]}
        return tokens,spec,audit
    def test_motion_may_extend_beyond_keyword(self):
        tokens,spec,audit=self.fixture();validate_action_audit(audit,spec,tokens,'audio','align')
    def test_source_span_out_of_range_rejected(self):
        tokens,spec,audit=self.fixture(); audit['actions'][0]['master_char_end']=99
        with self.assertRaisesRegex(ValueError,'master span'):validate_action_audit(audit,spec,tokens,'audio','align')
    def test_anchor_text_mismatch_rejected(self):
        tokens,spec,audit=self.fixture(); audit['actions'][0]['anchor_text']='静止'
        with self.assertRaisesRegex(ValueError,'text/source'):validate_action_audit(audit,spec,tokens,'audio','align')
    def test_unrelated_future_anchor_rejected(self):
        tokens,spec,audit=self.fixture(); e=audit['actions'][0]; e['anchor_ids']=[3]; e['trigger_evidence']['anchor_ids']=[3]
        for pair in e['trigger_evidence']['alignment_pairs']:pair['raw_token_id']=3
        with self.assertRaisesRegex(ValueError,'real cue'):validate_action_audit(audit,spec,tokens,'audio','align')
    def test_review_string_does_not_allow_future_onset(self):
        tokens,spec,audit=self.fixture(); spec['chapters'][0]['actions'][0]['at']=1.2
        audit['actions'][0].update(at=1.2,reviewed_by='fake',reason='fake',evidence='fake')
        with self.assertRaises(ValueError):validate_action_audit(audit,spec,tokens,'audio','align')
    def test_action_cannot_receive_unverified_dictionary(self):
        tokens,spec,audit=self.fixture()
        with self.assertRaisesRegex(ValueError,'verified original'):validate_action_audit(audit,spec,dict(tokens),'audio','align')
    def test_verified_tokens_cannot_be_mutated_after_validation(self):
        tokens,spec,audit=self.fixture();tokens['0']['start']=.11
        with self.assertRaisesRegex(ValueError,'receipt'):validate_action_audit(audit,spec,tokens,'audio','align')
    def test_fixture_opt_in_not_available_to_production(self):
        tokens,spec,audit=self.fixture(); audit['actions'][0].pop('trigger_evidence'); audit['source']='synthetic_fixture'
        with self.assertRaises(ValueError):validate_action_audit(audit,spec,tokens,'audio','align')
        validate_action_audit(audit,spec,tokens,'audio','align',synthetic_fixture=True)
    def derived(self):
        def wav(path,pcm):
            with wave.open(str(path),'wb') as w:w.setparams((1,2,8000,0,'NONE','not compressed'));w.writeframes(pcm)
        src=self.root/'source.wav'; dst=self.root/'destination.wav'
        pcm=b'\x01\x00'*16000; wav(src,pcm); wav(dst,b'\x00\x00'*8000+pcm)
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        original=copy.deepcopy(self.data); original['source_audio_sha256']=sha(src)
        parent=self.root/'parent.json';parent.write_text(json.dumps(original),encoding='utf-8');ph=sha(parent)
        d=copy.deepcopy(original);d.update(duration=3,source_audio_path=str(dst),source_audio_sha256=sha(dst),
            provenance_sources=[{'alignment_path':str(parent),'alignment_sha256':ph,'source_audio_path':str(src),
                                 'destination_frame_offset':8000,'sample_rate':8000}])
        for t in d['anchors']:
            t['origin']={'alignment_sha256':ph,'token_id':t['id'],'local_start':t['start'],'local_end':t['end'],'frame_offset':8000,'sample_rate':8000}
            for k in ('start','end'):
                if t[k] is not None:t[k]+=1
        return d
    def test_exact_pcm_offset_and_null_preserved(self):
        d=self.derived();self.assertEqual(list(validate_alignment(d,d['source_audio_sha256'],'转动。结束',3)),['0','1','3'])
    def test_forged_pcm_offset_rejected(self):
        d=self.derived();d['provenance_sources'][0]['destination_frame_offset']=0
        with self.assertRaisesRegex(ValueError,'PCM'):validate_alignment(d,d['source_audio_sha256'],'转动。结束',3)
    def test_derived_local_timestamp_tamper_rejected(self):
        d=self.derived();d['anchors'][0]['origin']['local_start']=.12
        with self.assertRaisesRegex(ValueError,'local original'):validate_alignment(d,d['source_audio_sha256'],'转动。结束',3)
    def test_derived_missing_backlink_rejected(self):
        d=self.derived();del d['anchors'][0]['origin']
        with self.assertRaisesRegex(ValueError,'backlink'):validate_alignment(d,d['source_audio_sha256'],'转动。结束',3)
    def test_duplicate_origin_renamed_id_rejected(self):
        d=self.derived();other=copy.deepcopy(d['anchors'][0]);other['id']='new-id';d['anchors'].insert(1,other)
        with self.assertRaisesRegex(ValueError,'duplicate original'):validate_alignment(d,d['source_audio_sha256'],'转动。结束',3)
    def test_original_merge_order_rejected(self):
        d=self.derived();d['anchors'][0],d['anchors'][1]=d['anchors'][1],d['anchors'][0]
        with self.assertRaisesRegex(ValueError,'merge order'):validate_alignment(d,d['source_audio_sha256'],'转动。结束',3)
    def test_future_original_sentence_cannot_expand_motion_window(self):
        rawpath=Path(self.data['raw_evidence'][0]['path']);raw=json.loads(rawpath.read_text())
        extra={'text':'未来','offsets':{'from':4000,'to':4500}}
        raw['transcription'].append({'tokens':[extra]});rawpath.write_text(json.dumps(raw),encoding='utf-8')
        self.data['raw_evidence'][0]['sha256']=hashlib.sha256(rawpath.read_bytes()).hexdigest();self.data['duration']=5
        self.data['anchors'].append({'id':4,'text':'未来','raw_token':extra,'start':4,'end':4.5,'source':'whisper_cpp','time_source':'original Whisper token'})
        tokens=validate_alignment(self.data,'audio','转动。结束',5)
        # Build the same legitimate source-bound cue; only the motion budget is attacked.
        old=self.validate;self.validate=lambda:tokens
        try:_,spec,audit=self.fixture()
        finally:self.validate=old
        audit['actions'][0]['motion_window']['anchor_ids'].append(4);spec['chapters'][0]['actions'][0]['duration']=3
        with self.assertRaisesRegex(ValueError,'unrelated original ASR sentence'):validate_action_audit(audit,spec,tokens,'audio','align')

if __name__=='__main__':unittest.main()
