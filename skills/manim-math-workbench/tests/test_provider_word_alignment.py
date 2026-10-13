"""Offline contract fixtures, NOT provider or voice accuracy certification.

Run with trusted FFmpeg/FFprobe on PATH. All scratch obeys TEMP/TMP.
Real captured provider evidence is verified separately by production import.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/engine'))
from geometry import pipeline as p


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def ref(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


@unittest.skipUnless(shutil.which('ffmpeg'), 'trusted FFmpeg required for PCM/replay tests')
class ProviderWords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='provider-contract-test-')
        cls.root = Path(cls.tmp.name); cls.ffmpeg = Path(shutil.which('ffmpeg')).resolve()
        cls.params = {'voice': 'synthetic-offline-fixture', 'rate': '+0%', 'pitch': '+0Hz', 'volume': '+0%', 'boundary': 'WordBoundary'}
        cls.text = '负二。加三。'; (cls.root / 'source.txt').write_text(cls.text, encoding='utf-8')
        clips, anchors, blocks = [], [], []
        for n, words in enumerate([['负', '二'], ['加', '三']]):
            base = cls.root / str(n); base.mkdir()
            (base / 'text.txt').write_text(''.join(words) + '。', encoding='utf-8')
            pcm = b''.join(struct.pack('<h', int(7000 * math.sin(i * (n + 1) * .03))) for i in range(24000))
            blocks.append(pcm)
            with wave.open(str(base / 'audio.wav'), 'wb') as w:
                w.setparams((1, 2, 24000, 0, 'NONE', 'not compressed')); w.writeframes(pcm)
            raws, sdk = [], []
            for i, word in enumerate(words):
                ticks = 1000000 + i * 2000000; length = 1000000
                event = {'Type': 'WordBoundary', 'Data': {'Offset': ticks, 'Duration': length,
                         'text': {'Text': word, 'Length': 1, 'BoundaryType': 'WordBoundary'}}}
                raws.append({'sdk_offset_compensation_ticks': 0, 'raw_utf8': json.dumps({'Metadata': [event]}, ensure_ascii=False)})
                sdk.append({'type': 'WordBoundary', 'offset': ticks, 'duration': length, 'text': word})
                anchors.append({'id': f'clip{n}:{i}:0', 'text': word, 'source': p.PROVIDER_WORD_SOURCE,
                    'time_source': p.PROVIDER_WORD_SOURCE, 'clip_id': f'clip{n}', 'raw_line': i, 'raw_event': 0,
                    'offset_ticks': ticks, 'duration_ticks': length, 'source_char_start': n * 3 + i,
                    'source_char_end': n * 3 + i + 1, 'script_char_start': n * 3 + i, 'script_char_end': n * 3 + i + 1,
                    'start': (n + ticks / 1e7) / 1.1, 'end': (n + (ticks + length) / 1e7) / 1.1})
            for name, rows in [('raw.jsonl', raws), ('sdk.jsonl', sdk)]:
                (base / name).write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in rows), encoding='utf-8')
            refs = {'text': ref(base / 'text.txt'), 'encoded_audio': ref(base / 'audio.wav'), 'pcm': ref(base / 'audio.wav'),
                    'raw_events': ref(base / 'raw.jsonl'), 'sdk_events': ref(base / 'sdk.jsonl')}
            clips.append({'id': f'clip{n}', **refs, 'source_byte_start': n * 9, 'source_byte_end': (n + 1) * 9,
                'concat_start_sample': n * 24000, 'pcm_info': p._provider_pcm(base / 'audio.wav'),
                'generation': {'request_id': f'offline-test-{n}', 'parameters': cls.params,
                    **{k + '_sha256': refs[k]['sha256'] for k in ('text', 'encoded_audio', 'raw_events', 'sdk_events')}}})
        with wave.open(str(cls.root / 'concat.wav'), 'wb') as w:
            w.setparams((1, 2, 24000, 0, 'NONE', 'not compressed')); w.writeframes(b''.join(blocks))
        subprocess.run([str(cls.ffmpeg), '-v', 'error', '-nostdin', '-i', str(cls.root / 'concat.wav'),
                        '-af', 'atempo=1.1', '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', str(cls.root / 'final.wav')], check=True)
        cls.duration = p._provider_pcm(cls.root / 'final.wav')['samples'] / 24000
        cls.manifest = {'schema_version': 'edge-word-evidence-1', 'source': p.PROVIDER_WORD_SOURCE,
            'parameters': cls.params, 'ffmpeg_sha256': ref(cls.ffmpeg)['sha256'], 'narration': ref(cls.root / 'source.txt'),
            'canonical_narration_sha256': p.digest(cls.text), 'clip_count': 2, 'clips': clips,
            'concat_audio': ref(cls.root / 'concat.wav'), 'final_audio': ref(cls.root / 'final.wav'), 'transform': {'kind': 'atempo', 'factor': 1.1}}
        cls.alignment = {'source': p.PROVIDER_WORD_SOURCE, 'source_audio_sha256': cls.manifest['final_audio']['sha256'],
            'canonical_narration_sha256': p.digest(cls.text), 'duration': cls.duration, 'anchors': anchors}

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def setUp(self):
        self.m = copy.deepcopy(self.manifest); self.a = copy.deepcopy(self.alignment)

    def check(self):
        path = self.root / 'manifest.json'; save(path, self.m); self.a['provider_manifest'] = ref(path)
        return p.validate_alignment(self.a, self.a['source_audio_sha256'], self.text, self.duration, ffmpeg=self.ffmpeg)

    def test_valid_pcm_concat_replay_and_words(self):
        self.assertEqual(len(self.check()), 4)

    def test_old_equal_duration_audio_rejected(self):
        target = self.root / 'different-same-length.wav'
        data = bytearray((self.root / 'final.wav').read_bytes()); data[-2] ^= 1; target.write_bytes(data)
        self.m['final_audio'] = ref(target); self.a['source_audio_sha256'] = ref(target)['sha256']
        with self.assertRaisesRegex(ValueError, 'atempo replay'): self.check()

    def test_wrong_clip_pcm_rejected(self):
        self.m['clips'][0]['pcm'] = self.m['clips'][1]['pcm']
        self.m['clips'][0]['pcm_info'] = self.m['clips'][1]['pcm_info']
        with self.assertRaisesRegex(ValueError, 'claimed cache PCM'): self.check()

    def test_reordered_concat_rejected(self):
        self.m['concat_audio'] = self.m['clips'][0]['pcm']
        with self.assertRaisesRegex(ValueError, 'concat PCM/order'): self.check()

    def test_dropped_clip_rejected(self):
        self.m['clips'].pop(); self.m['clip_count'] = 1
        with self.assertRaisesRegex(ValueError, 'cover all locked'): self.check()

    def test_source_byte_span_rejected(self):
        self.m['clips'][0]['source_byte_end'] -= 1
        with self.assertRaisesRegex(ValueError, 'source byte span'): self.check()

    def test_shifted_word_time_rejected(self):
        self.a['anchors'][0]['start'] += .01
        with self.assertRaisesRegex(ValueError, 'invented/shifted'): self.check()

    def test_fake_math_word_rejected(self):
        self.a['anchors'][1]['text'] = '六'
        with self.assertRaisesRegex(ValueError, 'original event/source'): self.check()

    def test_bad_raw_hash_rejected(self):
        self.m['clips'][0]['raw_events']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'artifact hash'): self.check()

    def test_fake_factor_rejected(self):
        self.m['transform']['factor'] = 1.0
        with self.assertRaisesRegex(ValueError, 'atempo replay'): self.check()

    def test_exact_provider_action_math_coverage(self):
        tokens = {t['id']: t for t in self.a['anchors']}
        spec = {'narration': self.text, 'canvas': {'fps': 60}, 'chapters': [{'id': 's', 'actions': [{'at': .1, 'duration': .1}]}]}
        audit = {'source': p.PROVIDER_WORD_SOURCE, 'source_audio_sha256': 'audio', 'alignment_sha256': 'alignment',
                 'canonical_narration_sha256': p.digest(self.text), 'actions': [{'chapter_id': 's', 'action_index': 0,
                 'at': .1, 'anchor_ids': ['clip0:0:0', 'clip0:1:0'], 'script_char_start': 0, 'script_char_end': 2, 'anchor_text': '负二'}]}
        p.validate_action_audit(audit, spec, tokens, 'audio', 'alignment')
        audit['actions'][0]['anchor_ids'].pop()
        with self.assertRaisesRegex(ValueError, 'dropped/reordered'): p.validate_action_audit(audit, spec, tokens, 'audio', 'alignment')

    def test_provider_review_cannot_override_outside_envelope(self):
        tokens = {t['id']: t for t in self.a['anchors']}
        spec = {'narration': self.text, 'canvas': {'fps': 60}, 'chapters': [{'id': 's', 'actions': [{'at': .8, 'duration': .1}]}]}
        audit = {'source': p.PROVIDER_WORD_SOURCE, 'source_audio_sha256': 'a', 'alignment_sha256': 'b',
                 'canonical_narration_sha256': p.digest(self.text), 'actions': [{'chapter_id': 's', 'action_index': 0,
                 'at': .8, 'anchor_ids': ['clip0:0:0', 'clip0:1:0'], 'script_char_start': 0, 'script_char_end': 2,
                 'anchor_text': '负二', 'reviewed_by': 'fake', 'reason': 'fake', 'evidence': ['fake']}]}
        with self.assertRaisesRegex(ValueError, 'outside original'): p.validate_action_audit(audit, spec, tokens, 'a', 'b')

    def test_canonical_crlf_bom_source_offsets(self):
        self.assertEqual(p._provider_canonical_map('\ufeff \r\n负二。\r\n加三。\r\n'), {4: 0, 5: 1, 6: 2, 8: 3, 9: 4, 10: 5, 11: 6})


class WhisperCompatibility(unittest.TestCase):
    def test_original_and_null_provenance_unchanged(self):
        data = {'source': 'whisper_cpp', 'source_audio_sha256': 'a', 'canonical_narration_sha256': p.digest('二'),
                'anchors': [{'id': 0, 'text': '二', 'source': 'whisper_cpp', 'time_source': 'original token', 'start': 0, 'end': .1},
                            {'id': 1, 'text': '。', 'source': 'whisper_cpp', 'time_source': 'original null token', 'start': None, 'end': None}]}
        with self.assertRaisesRegex(ValueError, 'raw_evidence'): p.validate_alignment(data, 'a', '二', 1)
        data['source'] = 'external_fake'
        with self.assertRaisesRegex(ValueError, 'local Whisper'): p.validate_alignment(data, 'a', '二', 1)


if __name__ == '__main__': unittest.main()
