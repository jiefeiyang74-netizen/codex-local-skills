"""Full-tail validation and extraction integration without renderer changes."""
import copy,hashlib,sys,tempfile,unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import av
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/engine'))
from geometry.pipeline import media_validate,extract_frames,validate_and_extract_frames,_KeyframeCollector

class MediaFixture:
    def __init__(self):
        self.video=NS(type='video',width=2880,height=3840,average_rate=60)
        self.audio=NS(type='audio',codec_context=NS(channels=1),rate=48000)
        self.source_audio=copy.deepcopy(self.audio)
        self.frames=[]
        for i in range(480):
            self.frames.append(NS(pts=i,time_base=Fraction(1,60),is_corrupt=False,to_image=lambda i=i:Image.new('RGB',(24,32),(i%256,30,50))))
        self.source_samples=self.output_samples=384000
        self.passes=[];self.decoded=0;self.audio_decoded=[]
    def open(self,path):
        owner=self;source=str(path)=='source.wav'
        class Container:
            streams=NS(video=[] if source else [owner.video],audio=[owner.source_audio if source else owner.audio])
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def decode(self,*a,**kw):
                kind=a[0].type if a else ('video' if 'video' in kw else 'audio')
                owner.passes.append((source,kind))
                if kind=='video':
                    for frame in owner.frames:owner.decoded+=1;yield frame
                else:
                    samples=owner.source_samples if source else owner.output_samples
                    for n in [samples//2,samples-samples//2]:
                        owner.audio_decoded.append((source,n));yield NS(samples=n,sample_rate=48000)
        return Container()

def spec():
    # Last extraction target deliberately precedes the last decoded frame.
    return {'audio_duration':8,'chapters':[{'start':0,'end':8,'actions':[{'type':'formula','at':1.111,'duration':.321},{'type':'move','at':3,'duration':1}]}]}

class SingleDecodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.fixture=MediaFixture()
    def run_combined(self,name='combined'):
        job=self.base/name;job.mkdir()
        with patch.object(av,'open',self.fixture.open):
            return validate_and_extract_frames('movie.mp4','source.wav',2880,3840,60,8,spec(),job)
    def test_one_video_pass_and_two_complete_audio_passes(self):
        validation,frames,sheets=self.run_combined()
        self.assertEqual(self.fixture.passes,[(True,'audio'),(False,'video'),(False,'audio')])
        self.assertEqual(self.fixture.decoded,480);self.assertEqual(validation['frames'],480)
        self.assertEqual(sum(n for src,n in self.fixture.audio_decoded if src),384000)
        self.assertEqual(sum(n for src,n in self.fixture.audio_decoded if not src),384000)
        self.assertLess(frames[-1]['time'],479/60)
        self.assertTrue(sheets)
    def test_corrupt_tail_after_last_target_rejected(self):
        self.fixture.frames[-1].is_corrupt=True
        with self.assertRaisesRegex(ValueError,'corrupt/missing-PTS'):self.run_combined()
        self.assertEqual(self.fixture.decoded,480)
        self.assertGreater(len(list((self.base/'combined/keyframes').glob('*.jpg'))),24)
        self.assertFalse(list((self.base/'combined').glob('contact_sheet*')))
    def test_missing_pts_and_cadence_rejected(self):
        for i,value in enumerate([None,900]):
            self.fixture.frames[-1].pts=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.run_combined(str(i))
    def test_dimensions_fps_and_audio_format_rejected(self):
        mutations=[lambda f:setattr(f.video,'width',720),lambda f:setattr(f.video,'height',720),lambda f:setattr(f.video,'average_rate',30)]
        for i,mutate in enumerate(mutations):
            self.fixture=MediaFixture();mutate(self.fixture)
            with self.assertRaisesRegex(ValueError,'dimensions/fps'):self.run_combined(str(i))
    def test_video_short_long_and_audio_tail_rejected(self):
        for i,kind in enumerate(['short','long','audio']):
            self.fixture=MediaFixture()
            if kind=='short':self.fixture.frames=self.fixture.frames[:-3]
            if kind=='long':
                for n in range(480,620):
                    f=copy.copy(self.fixture.frames[0]);f.pts=n;self.fixture.frames.append(f)
            if kind=='audio':self.fixture.output_samples-=9600
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_combined(str(i))
    def test_audio_channels_and_sample_rate_rejected(self):
        for i,kind in enumerate(['channels','rate']):
            self.fixture=MediaFixture()
            if kind=='channels':self.fixture.audio.codec_context.channels=2
            else:self.fixture.audio.rate=44100
            with self.assertRaisesRegex(ValueError,'audio channels/sample rate'):self.run_combined(str(i))
    def test_legacy_apis_report_frames_and_bytes_identical(self):
        job=self.base/'separate';job.mkdir()
        with patch.object(av,'open',self.fixture.open):
            expected=media_validate('movie.mp4','source.wav',2880,3840,60,8)
            old_frames,old_sheets=extract_frames('movie.mp4',spec(),job)
        actual,frames,sheets=self.run_combined()
        self.assertEqual(expected,actual)
        def identity(items):return [(i['time'],i['requested_time'],Path(i['path']).name,hashlib.sha256(Path(i['path']).read_bytes()).hexdigest()) for i in items]
        self.assertEqual(identity(old_frames),identity(frames))
        self.assertEqual([Path(p).read_bytes() for p in old_sheets],[Path(p).read_bytes() for p in sheets])

    def preview_fixture(self):
        # Same 30fps EOF phase as 423.2098s, using a small mocked clip.
        self.fixture.video.average_rate=30
        self.fixture.frames=self.fixture.frames[:240]
        for frame in self.fixture.frames:frame.time_base=Fraction(1,30)
        self.fixture.source_samples=self.fixture.output_samples=384470
        data=spec();data['audio_duration']=8.0098;data['chapters'][0]['end']=8.0098
        return data

    def test_30fps_eof_target_reuses_final_frame_after_full_validation(self):
        data=self.preview_fixture();job=self.base/'eof';job.mkdir()
        with patch.object(av,'open',self.fixture.open):
            validation,frames,sheets=validate_and_extract_frames(
                'movie.mp4','source.wav',2880,3840,30,8.0098,data,job)
        self.assertEqual(frames[-1]['requested_time'],7.9698)
        self.assertEqual(frames[-1]['time'],239/30)
        self.assertGreater(frames[-1]['requested_time'],frames[-1]['time'])
        self.assertEqual(self.fixture.decoded,240)
        self.assertEqual(self.fixture.passes,[(True,'audio'),(False,'video'),(False,'audio')])
        self.assertEqual(sum(n for src,n in self.fixture.audio_decoded if src),384470)
        self.assertEqual(sum(n for src,n in self.fixture.audio_decoded if not src),384470)
        self.assertTrue(validation['passed']);self.assertTrue(sheets)

    def test_30fps_real_truncation_still_rejected(self):
        for kind in ('video','audio','corrupt'):
            self.fixture=MediaFixture();data=self.preview_fixture()
            if kind=='video':self.fixture.frames=self.fixture.frames[:-2]
            elif kind=='audio':self.fixture.output_samples-=9600
            else:self.fixture.frames[-1].is_corrupt=True
            job=self.base/kind;job.mkdir()
            error={'video':'video duration/tail mismatch','audio':'audio truncated/extended',
                   'corrupt':'corrupt/missing-PTS'}[kind]
            with self.subTest(kind=kind),patch.object(av,'open',self.fixture.open):
                with self.assertRaisesRegex(ValueError,error):
                    validate_and_extract_frames('movie.mp4','source.wav',2880,3840,30,8.0098,data,job)
            self.assertFalse(list(job.glob('contact_sheet*')))

    def test_collector_eof_reuse_is_bounded_by_one_frame(self):
        for gap in (1/30,1/30+.0001,.1):
            job=self.base/str(gap);job.mkdir()
            collector=_KeyframeCollector(spec(),job,30)
            # Isolate the EOF policy from the independent media tail checks.
            collector.targets=[i/10 for i in range(23)]+[3+gap]
            collector.consume(self.fixture.frames[0],3)
            if gap<=1/30:
                frames,_=collector.finish()
                self.assertEqual(frames[-1]['time'],3)
                self.assertAlmostEqual(frames[-1]['requested_time'],3+gap)
            else:
                with self.assertRaisesRegex(ValueError,'exceeds one frame'):collector.finish()
                self.assertFalse(list(job.glob('contact_sheet*')))

    def test_standalone_30fps_eof_uses_stream_rate(self):
        data=self.preview_fixture();job=self.base/'standalone';job.mkdir()
        with patch.object(av,'open',self.fixture.open):
            frames,_=extract_frames('movie.mp4',data,job)
        self.assertEqual(frames[-1]['requested_time'],7.9698)
        self.assertEqual(frames[-1]['time'],239/30)

if __name__=='__main__':unittest.main()
