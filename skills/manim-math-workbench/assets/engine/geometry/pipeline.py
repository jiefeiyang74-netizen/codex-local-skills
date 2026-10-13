"""Audio-clock geometry runner, isolated trusted entry and explicit review gate."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import re
import difflib

from .schema import validate_spec, require, number, CAPABILITY_VERSION, production_limits

RENDER_TIMEOUT_SECONDS = 43200
from v3.partial_cache import retain_config, partial_index

def render_settings(canvas, quality):
    """Keep final canvas; cap preview pixels independently of logical layout."""
    width, height, fps = canvas['width'], canvas['height'], canvas['fps']
    if quality == 'preview':
        divisor = math.gcd(width, height)
        unit_w, unit_h = width // divisor, height // divisor
        # An even multiple preserves the exact aspect ratio and even dimensions.
        multiple = min(divisor, 720 // max(unit_w, unit_h)) // 2 * 2
        if multiple:
            width, height = unit_w * multiple, unit_h * multiple
        else:
            # Unusual ratios may require <2px rounding; report actual dimensions.
            longest = max(width, height)
            width, height = (max(2, value * min(longest, 720) // longest // 2 * 2)
                             for value in (width, height))
        fps = 30
    return width, height, fps

def canonical(text):
    return text.lstrip('\ufeff').replace('\r\n', '\n').strip()

def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def decoded_audio_clock(path):
    """One geometry time reference: decoded samples, never container padding."""
    import av
    with av.open(str(path)) as container:
        require(len(container.streams.audio) > 0, 'source has no audio stream')
        stream = container.streams.audio[0]
        channels, rate = stream.codec_context.channels, stream.rate
        samples, spans = 0, []
        for frame in container.decode(stream):
            require(frame.sample_rate and frame.sample_rate > 0, 'invalid decoded sample rate')
            samples += frame.samples
            spans.append(frame.samples / frame.sample_rate)
    seconds = math.fsum(spans)
    require(samples > 0 and number(seconds) and seconds > 0, 'empty/invalid decoded audio')
    return {'seconds':seconds, 'samples':samples, 'sample_rate':rate, 'channels':channels,
            'reference':'decoded source audio samples'}


def analyze(runner, request_path, job, config, job_root):
    """Keep an attempt-local audit trail even when ASR/alignment validation fails."""
    report = {'status':'analyzing', 'asr_launched':False, 'manual_listening_done':False,
              'invalid_token_count':None, 'usable_token_count':0,
              'analysis_manifest':str(job/'analysis_manifest.json')}
    try:
        result = _analyze(runner, request_path, job, config, job_root, report)
        report.update(result)
    except Exception as exc:
        from v3.audio_timing import _safe_asr_log
        report.update(status='failed', error=_safe_asr_log(str(exc)), error_type=type(exc).__name__)
        raise
    finally:
        evidence = [{'path':str(p), 'sha256':runner._sha256(p)}
                    for p in sorted((job/'whisper_evidence').glob('*/*')) if p.is_file()]
        report['raw_evidence'] = evidence
        report['content_review'] = 'ASR timing evidence only; content requires human/parent review'
        runner._json_dump(job/'analysis_report.json', report)
        runner._json_dump(job/'analysis_manifest.json', {
            'status':report['status'], 'analysis_report':str(job/'analysis_report.json'),
            'source_audio_sha256':report.get('source_audio_sha256'),
            'canonical_narration_sha256':report.get('canonical_narration_sha256'),
            'raw_evidence':evidence, 'candidate_alignment':report.get('candidate_alignment'),
            'alignment_path':report.get('alignment_path'),
        })
    return report


def _analyze(runner, request_path, job, config, job_root, report):
    request, audio = runner._request(request_path)
    narration = canonical(request['narration'])
    original = runner._sha256(audio)
    report.update(source_audio_sha256=original, canonical_narration_sha256=digest(narration))
    from v3.audio_timing import probe_audio
    probe = probe_audio(audio)
    clock = decoded_audio_clock(audio)
    duration = clock['seconds']
    report.update(audio_probe_metadata=probe, audio_clock=clock)
    cache = job_root/'cache'/f'geometry_alignment_{original}_{digest(narration)}.json'
    explicit = request.get('alignment_path')
    source_path = runner._resolve_input(explicit, request_path.parent) if explicit else cache
    source_hash = runner._sha256(source_path) if source_path.is_file() else None
    report.update(source_alignment_path=str(source_path), source_alignment_sha256=source_hash)
    if explicit or cache.is_file():
        report['analysis_source'] = 'external_alignment' if explicit else 'geometry_cache'
        analysis = read(source_path)
        tokens = validate_alignment(analysis, original, narration, duration, ffmpeg=config['ffmpeg_exe'])
        enriched = dict(analysis)
        mode = 'verified_external_alignment' if explicit else 'verified_geometry_cache'
    else:
        report['analysis_source'] = 'existing_local_audio_analysis'
        # Reuse an existing legacy analysis when it has genuine token segments.
        # Fresh geometry analysis uses the same installed Whisper backend, but
        # never uses v3's digit-by-digit/interpolated script matching gate.
        legacy_cache = job_root/'cache'/f'alignment_{original[:16]}_{digest(narration)[:12]}_{runner.RUNNER_VERSION}.json'
        analysis = runner._load_cached_alignment(legacy_cache,original,digest(narration),audio)
        if analysis is None:
            from v3.audio_timing import transcribe_segments
            alignment_input = runner._alignment_audio(audio,Path(config['ffmpeg_exe']),job)
            report['asr_launched'] = True
            segments = transcribe_segments(alignment_input,narration,Path(config['whisper_exe']),Path(config['whisper_model']),timeout=43200,
                                           evidence_dir=job/'whisper_evidence')
            analysis = {'duration':duration,'segments':segments,'engine':'whisper.cpp local original token timestamps','cache_hit':False}
        anchors = []
        previous = -1
        for segment in analysis.get('segments', []):
            for token in segment.get('tokens', []):
                item = {**token,'id':len(anchors),'source':'whisper_cpp','time_source':'whisper.cpp original token offsets'}
                s, e = item.get('start'), item.get('end')
                reason = ('missing_or_nonfinite_time' if not number(s) or not number(e) else
                          'negative_start' if s < 0 else 'end_not_after_start' if e <= s else
                          'beyond_audio_duration' if e > duration else
                          'nonmonotonic_start' if s < previous - .03 else None)
                if reason:
                    item.update(raw_start=s, raw_end=e, start=None, end=None, invalid=True,
                                invalid_reason=reason,
                                time_source='original Whisper token offsets; null if invalid; no clipping or interpolation')
                else:
                    previous = s
                anchors.append(item)
        enriched = {**analysis, 'source_audio_sha256':original,
                    'canonical_narration_sha256':digest(narration), 'source':'whisper_cpp', 'anchors':anchors}
        enriched['raw_evidence'] = [{'path':str(p), 'sha256':runner._sha256(p)}
                                    for p in sorted((job/'whisper_evidence').glob('*/*')) if p.is_file()]
        report.update(invalid_token_count=sum(t.get('invalid', False) for t in anchors),
                      candidate_alignment=str(job/'alignment_candidate.json'))
        # A candidate is diagnostic only; never publish/cache it as a valid attachment.
        runner._json_dump(job/'alignment_candidate.json', enriched)
        tokens = validate_alignment(enriched,original,narration,duration, ffmpeg=config['ffmpeg_exe'])
        # Matching changes character comparisons only; token boundaries stay intact.
        enriched['numeric_matches'] = numeric_matches(narration, list(tokens.values()))
        enriched['matching_rule'] = 'integer cardinal equivalence; separate letter and subscript roles; original whole-token timestamps'
        mode = 'existing_local_audio_analysis'
    enriched.update(canonical_narration_rule='decode utf-8-sig; replace CRLF with LF; strip; encode UTF-8; SHA256',
                    precision_caveat='Original token intervals; no claim of word-level <0.2s accuracy. script_points are not geometry anchors.')
    require(runner._sha256(audio)==original, 'source audio changed during analysis')
    runner._json_dump(job/'alignment.json',enriched)
    runner._json_dump(cache,enriched)
    report = {**report, 'status':'analyzed','alignment_path':str(job/'alignment.json'),'cache_path':str(cache),
              'analysis_source':mode,'usable_token_count':len(tokens), 'source_audio_unchanged':True,
              'source_alignment_sha256':source_hash,
              'invalid_token_count':sum(t.get('start') is None and t.get('end') is None for t in enriched.get('anchors', [])),
              'source_evidence':enriched.get('raw_evidence', []),
              'manual_listening_done':False}
    runner._json_dump(job/'analysis_report.json',report)
    return report

def numeric_matches(narration, tokens):
    """Cardinal equivalence with atomic numeric spans and whole-token timing."""
    digits = {c:i for i,c in enumerate('零一二三四五六七八九')}; digits['两'] = 2
    units = {'十':10,'百':100,'千':1000,'万':10000,'亿':100000000}
    def integer(text):
        if text.isascii() and text.isdigit(): return int(text)
        if not any(c in units for c in text): return int(''.join(str(digits[c]) for c in text))
        total = section = value = 0
        for c in text:
            if c in digits: value = digits[c]
            elif units[c] < 10000: section += (value or 1)*units[c]; value = 0
            else:
                section += value
                if units[c] == 100000000: total = (total + section)*units[c]
                else: total += section*units[c]
                section = value = 0
        return total + section + value
    pattern = re.compile(r'[0-9]+|[零一二三四五六七八九十百千万亿两]+|[A-Za-z\u3400-\u9fff]')
    def spans(text):
        result = []
        for m in pattern.finditer(text):
            x = m.group(); numeric = x[0] in digits or x[0] in units or x[0].isdigit()
            role = 'subscript' if numeric and m.start() and text[m.start()-1].isascii() and text[m.start()-1].isalpha() else 'cardinal'
            result.append((('#'+str(integer(x)),role) if numeric else (x.lower(),'letter_or_text'),m.start(),m.end()))
        return result
    transcript = ''.join(t['text'] for t in tokens)
    char_tokens = [t['id'] for t in tokens for _ in t['text']]
    table = {str(t['id']):t for t in tokens}
    source, observed = spans(narration), spans(transcript)
    matches = []
    matcher = difflib.SequenceMatcher(None,[s[0] for s in source],[s[0] for s in observed],autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            s, t = source[block.a+k], observed[block.b+k]
            if not s[0][0].startswith('#'): continue
            ids = list(dict.fromkeys(char_tokens[t[1]:t[2]]))
            refs = [table[str(i)] for i in ids]
            matches.append({'canonical_text':narration[s[1]:s[2]], 'equivalent_integer':int(s[0][0][1:]),
                            'role':s[0][1], 'asr_text':transcript[t[1]:t[2]], 'token_ids':ids,
                            'start':min(x['start'] for x in refs), 'end':max(x['end'] for x in refs),
                            'time_source':'union of whole original tokens; no token split'})
    return matches

def engine_hash(root):
    files = sorted((root / 'geometry').glob('*.py')) + [root.parents[1] / 'scripts' / 'video.py', root / 'v3' / 'partial_cache.py']
    return digest(''.join(str(p.relative_to(root.parents[1])) + hashlib.sha256(p.read_bytes()).hexdigest() for p in files))

PROVIDER_WORD_SOURCE = 'edge_tts_word_boundary'


def _provider_integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, 'provider invalid integer: ' + name)
    return value


def _provider_file(item, base):
    require(isinstance(item, dict) and isinstance(item.get('path'), str), 'provider artifact needs path/hash')
    path = Path(item['path'])
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    require(path.is_file(), 'provider artifact missing: ' + str(path))
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    require(h.hexdigest() == item.get('sha256'), 'provider artifact hash mismatch: ' + str(path))
    return path


def _provider_pcm(path, accumulate=None):
    import wave
    h = hashlib.sha256()
    with wave.open(str(path), 'rb') as stream:
        require(stream.getcomptype() == 'NONE' and stream.getsampwidth() == 2,
                'provider PCM must be uncompressed signed 16-bit WAV')
        rate, channels, frames = stream.getframerate(), stream.getnchannels(), stream.getnframes()
        require(rate > 0 and channels in (1, 2) and frames > 0, 'provider invalid PCM format')
        size = 0
        for block in iter(lambda: stream.readframes(65536), b''):
            size += len(block)
            h.update(block)
            if accumulate is not None:
                accumulate.update(block)
    require(size == frames * channels * 2, 'provider truncated PCM')
    return {'sha256': h.hexdigest(), 'samples': frames, 'sample_rate': rate, 'channels': channels}


def _provider_decode_hash(ffmpeg, path, rate, channels, speed=None):
    # Executable comes from the trusted runtime caller, never an attachment command.
    # Temporary PCM uses the caller's TEMP/TMP policy; no persistent media overwrite.
    import tempfile
    args = [str(ffmpeg), '-v', 'error', '-nostdin', '-i', str(path), '-vn']
    if speed is not None:
        args += ['-af', 'atempo=' + str(speed)]
    args += ['-ar', str(rate), '-ac', str(channels), '-c:a', 'pcm_s16le', '-f', 's16le', 'pipe:1']
    with tempfile.TemporaryFile(suffix='.provider-validation.pcm') as output:
        result = subprocess.run(args, stdout=output, stderr=subprocess.PIPE, timeout=600,
                                cwd=str(path.parent))
        require(result.returncode == 0, 'provider audio decode/atempo replay failed: ' +
                result.stderr.decode('utf-8', errors='replace')[-2000:])
        output.seek(0)
        h, size = hashlib.sha256(), 0
        for block in iter(lambda: output.read(1024 * 1024), b''):
            h.update(block)
            size += len(block)
    require(size > 0 and size % (2 * channels) == 0, 'provider invalid decoded PCM length')
    return h.hexdigest(), size // (2 * channels)


def _provider_significant(char):
    # Never discard spoken numbers/letters or mathematical operators as punctuation.
    return char.isalnum() or char in '+-−×÷=<>≤≥√∛^/%()[]{}'


def _provider_zero_origin(ffmpeg, encoded):
    probe = Path(ffmpeg).with_name('ffprobe' + Path(ffmpeg).suffix)
    require(probe.is_file(), 'provider trusted runtime ffprobe missing')
    result = subprocess.run([str(probe), '-v', 'error', '-show_streams', '-read_intervals', '%+#1',
                             '-show_packets', '-of', 'json', str(encoded)],
                            capture_output=True, timeout=60, cwd=str(encoded.parent))
    require(result.returncode == 0, 'provider decoder-origin probe failed')
    info = json.loads(result.stdout)
    streams = info.get('streams', [])
    require(len(streams) == 1 and streams[0].get('codec_type') == 'audio', 'provider encoded clip must have one audio stream')
    require(float(streams[0].get('start_time', 0)) == 0 and int(streams[0].get('initial_padding', 0)) == 0,
            'provider signaled decoder origin/padding needs supported calibration')
    require(not any(int(side.get('skip_samples', 0)) for packet in info.get('packets', [])
                    for side in packet.get('side_data_list', [])), 'provider signaled skip samples unsupported')


def _provider_canonical_map(text):
    retained = [(i, c) for i, c in enumerate(text)
                if not (c == '\r' and text[i:i+2] == '\r\n')]
    while retained and (retained[0][1].isspace() or retained[0][1] == '\ufeff'):
        retained.pop(0)
    while retained and retained[-1][1].isspace():
        retained.pop()
    require(''.join(c for _, c in retained) == canonical(text), 'provider canonical span mapping mismatch')
    return {source_index: index for index, (source_index, _) in enumerate(retained)}


def validate_provider_word_alignment(data, audio_hash, narration, duration, *, ffmpeg):
    """Verify captured provider words against their own PCM, not an older equal-length recording."""
    import html
    meta = data.get('metadata', data)
    require(meta.get('source') == PROVIDER_WORD_SOURCE, 'provider source must be explicit')
    require(ffmpeg is not None and Path(ffmpeg).is_absolute() and Path(ffmpeg).is_file(),
            'provider validation needs trusted runtime ffmpeg path')
    ref = meta.get('provider_manifest')
    manifest_path = _provider_file(ref, Path.cwd())
    manifest, base = read(manifest_path), manifest_path.parent
    require(manifest.get('schema_version') == 'edge-word-evidence-1', 'unsupported provider evidence schema')
    require(manifest.get('source') == PROVIDER_WORD_SOURCE, 'provider manifest source mismatch')
    require(hashlib.sha256(Path(ffmpeg).read_bytes()).hexdigest() == manifest.get('ffmpeg_sha256'),
            'provider replay FFmpeg identity mismatch')
    parameters = manifest.get('parameters', {})
    require(parameters.get('boundary') == 'WordBoundary' and
            all(isinstance(parameters.get(k), str) and parameters[k] for k in ('voice', 'rate', 'pitch', 'volume')),
            'provider exact synthesis parameters required')
    script_path = _provider_file(manifest.get('narration'), base)
    script_bytes = script_path.read_bytes()
    script = script_bytes.decode('utf-8-sig')
    require(canonical(script) == canonical(narration), 'provider locked source text mismatch')
    require(manifest.get('canonical_narration_sha256') == digest(canonical(script)), 'provider canonical hash mismatch')
    canonical_map = _provider_canonical_map(script)
    bom = 3 if script_bytes.startswith(b'\xef\xbb\xbf') else 0
    byte_positions, byte_cursor = {bom: 0}, bom
    for i, char in enumerate(script):
        byte_cursor += len(char.encode('utf-8'))
        byte_positions[byte_cursor] = i + 1
    clips = manifest.get('clips')
    require(isinstance(clips, list) and clips, 'provider clips missing')
    require(_provider_integer(manifest.get('clip_count'), 'clip_count', 1) == len(clips), 'provider clip count mismatch')
    concat_hash, sample_origin = hashlib.sha256(), 0
    covered, expected, clip_ids, request_ids = set(), [], set(), set()
    previous_byte, rate, channels, previous_tick_end = bom, None, None, 0
    transform = manifest.get('transform', {})
    speed = transform.get('factor')
    require(transform.get('kind') == 'atempo' and number(speed) and not isinstance(speed, bool) and .5 <= speed <= 2,
            'provider requires explicit supported single atempo factor')
    for clip in clips:
        key = clip.get('id')
        require(isinstance(key, str) and key and key not in clip_ids, 'provider duplicate/missing clip id')
        clip_ids.add(key)
        start = _provider_integer(clip.get('source_byte_start'), 'source_byte_start')
        end = _provider_integer(clip.get('source_byte_end'), 'source_byte_end', 1)
        require(previous_byte <= start < end <= len(script_bytes) and start in byte_positions and end in byte_positions,
                'provider unordered/invalid source byte span')
        previous_byte = end
        text_path = _provider_file(clip.get('text'), base)
        text = text_path.read_bytes().decode('utf-8-sig')
        require(script_bytes[start:end].decode('utf-8') == text, 'provider clip text differs from exact source span')
        source_origin = byte_positions[start]
        encoded = _provider_file(clip.get('encoded_audio'), base)
        pcm_path = _provider_file(clip.get('pcm'), base)
        raw_path = _provider_file(clip.get('raw_events'), base)
        sdk_path = _provider_file(clip.get('sdk_events'), base)
        generation = clip.get('generation', {})
        request_id = generation.get('request_id')
        require(isinstance(request_id, str) and request_id and request_id not in request_ids,
                'provider generation request identity missing/duplicate')
        request_ids.add(request_id)
        require(generation.get('parameters') == parameters, 'provider generation parameters mismatch')
        for field in ('text', 'encoded_audio', 'raw_events', 'sdk_events'):
            require(generation.get(field + '_sha256') == clip[field]['sha256'], 'provider generation artifact binding mismatch')
        info = _provider_pcm(pcm_path, concat_hash)
        if rate is None:
            rate, channels = info['sample_rate'], info['channels']
        require((rate, channels) == (info['sample_rate'], info['channels']), 'provider clip PCM formats differ')
        require(clip.get('pcm_info') == info, 'provider cache PCM identity/sample count mismatch')
        require(_provider_integer(clip.get('concat_start_sample'), 'concat_start_sample') == sample_origin,
                'provider concat sample origin mismatch')
        _provider_zero_origin(ffmpeg, encoded)
        decoded_hash, decoded_samples = _provider_decode_hash(ffmpeg, encoded, rate, channels)
        require((decoded_hash, decoded_samples) == (info['sha256'], info['samples']),
                'provider encoded audio does not decode to its claimed cache PCM')
        raw_events = []
        for line_index, line in enumerate(raw_path.read_text(encoding='utf-8-sig').splitlines()):
            require(bool(line.strip()), 'provider raw JSONL contains empty line')
            record = json.loads(line)
            # Small single-request clips are deliberate. Nonzero compensation needs a separately proved mapping.
            require(_provider_integer(record.get('sdk_offset_compensation_ticks'), 'SDK compensation') == 0,
                    'provider nonzero SDK compensation unsupported')
            payload = json.loads(record['raw_utf8'])
            for event_index, event in enumerate(payload['Metadata']):
                require(event.get('Type') == 'WordBoundary', 'provider raw event is not WordBoundary')
                event_data = event['Data']
                require(event_data['text'].get('BoundaryType') == 'WordBoundary', 'provider boundary type mismatch')
                raw_events.append((line_index, event_index, event_data))
        sdk = [json.loads(line) for line in sdk_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        require(raw_events and len(sdk) == len(raw_events), 'provider raw/SDK event count mismatch')
        cursor, previous_offset = 0, -1
        for (line_index, event_index, event), sdk_event in zip(raw_events, sdk):
            ticks = _provider_integer(event.get('Offset'), 'Offset')
            length = _provider_integer(event.get('Duration'), 'Duration', 1)
            word = html.unescape(event['text']['Text'])
            require(word and ticks >= previous_offset, 'provider word order/text invalid')
            previous_offset = ticks
            require(sdk_event.get('type') == 'WordBoundary' and sdk_event.get('offset') == ticks and
                    sdk_event.get('duration') == length and sdk_event.get('text') == word,
                    'provider raw/SDK word event differs')
            require((ticks + length) / 1e7 <= info['samples'] / rate + 1 / rate,
                    'provider original word event outside its decoded clip')
            local = text.find(word, cursor)
            require(local >= cursor and not any(_provider_significant(c) for c in text[cursor:local]),
                    'provider word/source mismatch or missing mathematical text')
            cursor = local + len(word)
            source_lo, source_hi = source_origin + local, source_origin + cursor
            mapped = [canonical_map[i] for i in range(source_lo, source_hi) if i in canonical_map]
            require(mapped, 'provider word has no canonical source span')
            covered.update(range(source_lo, source_hi))
            word_start = (sample_origin / rate + ticks / 1e7) / speed
            word_end = (sample_origin / rate + (ticks + length) / 1e7) / speed
            require(word_start >= previous_tick_end - .03, 'provider global word clock out of order')
            previous_tick_end = word_start
            expected.append({'id': f'{key}:{line_index}:{event_index}', 'text': word,
                             'source': PROVIDER_WORD_SOURCE, 'time_source': PROVIDER_WORD_SOURCE,
                             'clip_id': key, 'raw_line': line_index, 'raw_event': event_index,
                             'offset_ticks': ticks, 'duration_ticks': length,
                             'source_char_start': source_lo, 'source_char_end': source_hi,
                             'script_char_start': mapped[0], 'script_char_end': mapped[-1] + 1,
                             'start': word_start, 'end': word_end})
        require(not any(_provider_significant(c) for c in text[cursor:]), 'provider trailing source words missing')
        sample_origin += info['samples']
    require(all(i in covered for i, c in enumerate(script) if _provider_significant(c)),
            'provider clips/events do not cover all locked source words')
    concat = _provider_file(manifest.get('concat_audio'), base)
    concat_info = _provider_pcm(concat)
    require(concat_info == {'sha256': concat_hash.hexdigest(), 'samples': sample_origin,
                            'sample_rate': rate, 'channels': channels}, 'provider concat PCM/order mismatch')
    final = _provider_file(manifest.get('final_audio'), base)
    require(manifest['final_audio']['sha256'] == audio_hash, 'provider final audio byte hash mismatch')
    final_info = _provider_pcm(final)
    require((final_info['sample_rate'], final_info['channels']) == (rate, channels), 'provider final PCM format mismatch')
    replay_hash, replay_samples = _provider_decode_hash(ffmpeg, concat, rate, channels, speed)
    require((replay_hash, replay_samples) == (final_info['sha256'], final_info['samples']),
            'provider final audio differs from actual concat/atempo replay')
    require(abs(final_info['samples'] / rate - duration) <= 1 / rate, 'provider final decoded duration mismatch')
    require(number(data.get('duration')) and abs(data['duration'] - duration) <= 1 / rate,
            'provider alignment duration mismatch')
    anchors = data.get('anchors')
    require(isinstance(anchors, list) and len(anchors) == len(expected), 'provider anchor event count mismatch')
    for actual, reconstructed in zip(anchors, expected):
        require(isinstance(actual, dict), 'provider malformed anchor')
        for field, value in reconstructed.items():
            if field in ('start', 'end'):
                require(number(actual.get(field)) and abs(actual[field] - value) <= 1e-8,
                        'provider invented/shifted word time: ' + field)
            else:
                require(actual.get(field) == value, 'provider anchor differs from original event/source: ' + field)
        require(reconstructed['end'] <= duration + 1 / rate, 'provider mapped word outside final audio')
    return {str(token['id']): token for token in anchors}


def validate_alignment(data, audio_hash, narration, duration, *, ffmpeg=None):
    if data.get('timing_source') == 'qwen_forced_aligner':
        from .qwen_provenance import validate_alignment as validate_qwen
        return validate_qwen(data, audio_hash, narration, duration)
    meta = data.get('metadata', data)
    require(meta.get('source_audio_sha256') == audio_hash, 'alignment source_audio_sha256 mismatch')
    require(meta.get('canonical_narration_sha256') == digest(canonical(narration)), 'alignment canonical_narration_sha256 mismatch')
    source = str(meta.get('source', data.get('engine', ''))).lower()
    if source == PROVIDER_WORD_SOURCE:
        return validate_provider_word_alignment(data, audio_hash, narration, duration, ffmpeg=ffmpeg)
    require('whisper' in source and ('local' in source or 'cpp' in source), 'alignment must originate from local Whisper')
    from .whisper_provenance import verify_whisper_provenance
    verified_segments=verify_whisper_provenance(data)
    if 'duration' in data: require(number(data['duration']) and abs(data['duration'] - duration) <= .1, 'alignment duration mismatch')
    tokens = data.get('anchors')
    if tokens is None: tokens = [w for u in data.get('units', []) for w in u.get('words', [])]
    require(isinstance(tokens, list) and tokens, 'alignment needs original token anchors/units; script_points interpolation is insufficient')
    result = {}
    previous = -1
    for token in tokens:
        require(isinstance(token, dict), 'invalid token record')
        s, e = token.get('start'), token.get('end')
        require('whisper' in str(token.get('source', source)).lower() and 'original' in str(token.get('time_source', '')).lower(), 'token lacks original Whisper provenance')
        key = str(token.get('id'))
        require(key != 'None' and isinstance(token.get('text'), str), 'token missing id/text')
        # Explicitly untimed ASR records remain in the saved attachment, but are
        # ineligible action anchors; never invent timing for these records.
        if s is None and e is None:
            require('null' in token.get('time_source','').lower(), 'untimed token needs explicit null provenance')
            continue
        require(number(s) and number(e) and 0 <= s < e <= duration + .03, 'invalid token time range')
        if key in result: require(result[key] == token or all(result[key].get(k) == token.get(k) for k in ('start','end','text')), 'conflicting token id')
        else:
            require(s >= previous - .03, 'invalid token time order')
            previous = s
        result[key] = token
    require(result, 'alignment has no usable original token anchors')
    from .whisper_provenance import VerifiedWhisperTokens
    return VerifiedWhisperTokens(result,audio_hash,digest(canonical(narration)),verified_segments)

def validate_action_audit(audit, spec, tokens, audio_hash, alignment_hash, *, synthetic_fixture=False):
    from .qwen_provenance import VerifiedQwenTokens, validate_audit as validate_qwen_audit
    if isinstance(tokens, VerifiedQwenTokens):
        return validate_qwen_audit(audit, spec, tokens, audio_hash, alignment_hash)
    require(audit.get('source_audio_sha256') == audio_hash and audit.get('canonical_narration_sha256') == digest(canonical(spec['narration'])), 'action audit input binding mismatch')
    require(audit.get('alignment_sha256') == alignment_hash, 'action audit alignment binding mismatch')
    entries = audit.get('actions', [])
    require(isinstance(entries, list), 'audit actions must be list')
    table = {(x.get('chapter_id'), x.get('action_index')): x for x in entries}
    require(len(table) == len(entries), 'duplicate audit action')
    expected = {(c['id'], i) for c in spec['chapters'] for i in range(len(c['actions']))}
    require(set(table) == expected, 'audit must register every action exactly once')
    provider = any(t.get('source') == PROVIDER_WORD_SOURCE for t in tokens.values())
    if synthetic_fixture:
        require(audit.get('source')=='synthetic_fixture','synthetic audit must declare fixture-only source')
    if not provider and not synthetic_fixture:
        from .whisper_provenance import audit_source, verify_action_cue, require_verified_tokens
        require_verified_tokens(tokens,audio_hash,digest(canonical(spec['narration'])))
        audit_master,audit_offset=audit_source(audit,spec)
        previous_cues={}
    if provider:
        require(all(t.get('source') == PROVIDER_WORD_SOURCE for t in tokens.values()), 'mixed provider/ASR action evidence')
        require(audit.get('source') == PROVIDER_WORD_SOURCE, 'provider action audit source must be explicit')
        script = canonical(spec['narration'])
        provider_owners, provider_order = {}, {}
        for order, (key, token) in enumerate(tokens.items()):
            provider_order[str(key)] = order
            for position in range(token['script_char_start'], token['script_char_end']):
                provider_owners.setdefault(position, set()).add(str(key))
    for c in spec['chapters']:
        for i, action in enumerate(c['actions']):
            entry = table[c['id'], i]
            require(entry.get('at') == action['at'], 'audit at does not match action')
            ids = entry.get('anchor_ids', [])
            require(isinstance(ids, list) and ids and all(str(x) in tokens for x in ids), 'audit needs real anchor ids')
            lo = min(tokens[str(x)]['start'] for x in ids); hi = max(tokens[str(x)]['end'] for x in ids)
            if not provider and not synthetic_fixture:
                verify_action_cue(entry,action,tokens,audit_master,audit_offset,spec,previous_cues)
            if provider:
                start = _provider_integer(entry.get('script_char_start'), 'audit script_char_start')
                end = _provider_integer(entry.get('script_char_end'), 'audit script_char_end', 1)
                require(start < end <= len(script) and entry.get('anchor_text') == script[start:end],
                        'provider audit phrase/source span mismatch')
                positions = {j for j in range(start, end) if _provider_significant(script[j])}
                require(positions, 'provider audit needs spoken phrase')
                require(all(provider_owners.get(j) for j in positions), 'provider audit missing mathematical/source words')
                required = sorted(set().union(*(provider_owners[j] for j in positions)), key=provider_order.__getitem__)
                require(required == [str(x) for x in ids],
                        'provider audit dropped/reordered word events or added unrelated nearby evidence')
                require(lo <= action['at'] <= hi, 'provider action start outside original word event envelope')
                require(action['at'] + action['duration'] <= hi + 1 / spec['canvas']['fps'],
                        'provider action duration exceeds evidenced phrase budget')
            if not lo <= action['at'] <= hi:
                require(entry.get('reviewed_by') and entry.get('reason') and entry.get('evidence'), 'action outside token envelope needs explicit timing review evidence')

def render_identity(spec, engine_identity, audio_hash, alignment_hash, audit_hash):
    production_limits(spec)  # reject unknown profiles, never strip the declaration
    return digest(json.dumps(spec, sort_keys=True, ensure_ascii=False, allow_nan=False)
                  + engine_identity + audio_hash + alignment_hash + audit_hash)

def compile_geometry_source(spec, engine_root, *, encoder=None, ffmpeg_exe=None):
    spec = validate_spec(spec)
    code = ('import sys\nsys.path.insert(0, ' + repr(str(engine_root))
            + ')\nfrom geometry.runtime import GeometryScene\nclass GeneratedGeometryVideo(GeometryScene):\n    spec = '
            + repr(spec) + '\n')
    if encoder and encoder.get('profile') != 'software':
        from .native_encoder import encoder_contract
        require(encoder == encoder_contract(encoder.get('profile'), ffmpeg_exe), 'encoder contract mismatch')
        code += ('    _native_encoder = ' + repr(encoder) + '\n'
                 '    _native_ffmpeg = ' + repr(str(ffmpeg_exe)) + '\n')
    return code

def command(args, cwd, log, timeout=RENDER_TIMEOUT_SECONDS):
    """Live append-only session output, including timeout/failure diagnostics."""
    with log.open('w', encoding='utf-8') as out:
        out.write(json.dumps(args, ensure_ascii=False) + '\n'); out.flush()
        proc = subprocess.Popen(args, cwd=str(cwd), stdout=out, stderr=subprocess.STDOUT)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(); out.write('\nTIMEOUT\n'); raise
    require(code == 0, f'command failed ({code}); see {log}')

def mux_audio(ffmpeg, silent, source, output, job):
    """MP4 delivery uses AAC, even when FFmpeg accepts PCM stream copy."""
    import av
    with av.open(str(source)) as container:
        codec = container.streams.audio[0].codec_context.name
    mode = 'copy' if codec == 'aac' else 'aac'
    args = [ffmpeg, '-nostdin', '-y', '-i', str(silent), '-i', str(source),
            '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', mode]
    if mode == 'aac':
        args += ['-b:a', '192k']
    # No -shortest, -t, resampling or audio trimming: preserve source clock.
    command(args + [str(output)], job, job / ('mux_' + mode + '.log'))
    with av.open(str(output)) as container:
        stream = container.streams.audio[0]
        require(stream.codec_context.name == 'aac', 'MP4 delivery audio must be AAC')
        first = last = None
        for packet in container.demux(stream):
            if packet.pts is None:
                continue
            item = {'pts':packet.pts, 'dts':packet.dts, 'duration':packet.duration,
                    'time_base':str(packet.time_base)}
            if first is None:
                first = item
            last = item
        packet_clock = {'first':first, 'last':last, 'stream_start':stream.start_time,
                        'stream_duration':stream.duration, 'time_base':str(stream.time_base)}
    return {'source_codec':codec, 'output_codec':'aac', 'mode':mode,
            'packet_clock':packet_clock,
            'clock_policy':'uncut source; negative packet PTS may carry priming; decoded tail padding is measured by media_validate'}


def media_validate(path, source, width, height, fps, duration, *, _on_frame=None):
    import av
    source_clock = decoded_audio_clock(source)
    channels, rate = source_clock['channels'], source_clock['sample_rate']
    source_seconds = source_clock['seconds']
    with av.open(str(path)) as container:
        require(len(container.streams.video) == 1 and len(container.streams.audio) == 1, 'expected one video and one audio stream')
        video, audio = container.streams.video[0], container.streams.audio[0]
        require((video.width, video.height) == (width, height) and abs(float(video.average_rate) - fps) < .001, 'dimensions/fps mismatch')
        require(audio.codec_context.channels == channels and audio.rate == rate, 'audio channels/sample rate changed')
        previous, count = None, 0
        for frame in container.decode(video):
            require(not frame.is_corrupt and frame.pts is not None, 'corrupt/missing-PTS video frame')
            t = float(frame.pts * frame.time_base)
            require(previous is None or abs(t - previous - 1/fps) < .002, 'broken frame cadence')
            previous = t; count += 1
            if _on_frame is not None:
                _on_frame(frame, t)
        # MP3 container estimates can include encoder padding (and differ by
        # FFmpeg version). The already decoded samples are the actual audio
        # clock; comparing against a padded estimate falsely rejects 60fps.
        require(count > 0 and source_seconds - 1/fps <= count/fps <= source_seconds + 2 + 1/fps,
                f'video duration/tail mismatch: video={count/fps:.6f}s, decoded_audio={source_seconds:.6f}s')
    with av.open(str(path)) as container:
        output_seconds = sum(f.samples/f.sample_rate for f in container.decode(audio=0))
    require(abs(output_seconds - source_seconds) <= .08, 'audio truncated/extended')
    return {'passed': True, 'frames': count, 'video_duration': count/fps, 'source_audio_decoded_seconds': source_seconds,
            'output_audio_decoded_seconds': output_seconds, 'channels': channels, 'sample_rate': rate,
            'dimensions': [width,height], 'fps': fps, 'decode_all_frames': True,
            'duration_reference': 'decoded source audio samples', 'source_container_duration': duration}

def _keyframe_targets(spec):
    duration = spec['audio_duration']
    times = {round(i * max(0, duration - .05) / 23, 4) for i in range(24)}
    for c in spec['chapters']:
        for a in c['actions']:
            if a['type'] in ('text_transform','move','move_on_circle','constrain','reflect_copy','translate_copy','focus','reveal','hide','highlight','set_parameter'):
                times.add(round(a['at'] + a['duration']/2, 4))
            # Review each completed action and chapter at a stable frame as well
            # as the motion midpoint. Formula replacements need a transient frame.
            if a['type'] == 'formula':
                times.add(round(a['at'] + a['duration']/2, 4))
            times.add(round(min(duration - .04, a['at'] + a['duration']), 4))
        times.add(round(max(c['start'], min(duration - .04, c['end'] - .04)), 4))
    return sorted(times)


class _KeyframeCollector:
    """Collect selected frames without owning or ending the video decoder."""

    def __init__(self, spec, job, fps):
        require(number(fps) and fps > 0, 'invalid keyframe fps')
        self.frame_interval = 1 / fps
        self.last_frame = None
        self.last_time = None
        self.targets = _keyframe_targets(spec)
        self.output = []
        self.index = 0
        self.job = job
        self.folder = job / 'keyframes'
        self.folder.mkdir()

    def consume(self, frame, t):
        self.last_frame, self.last_time = frame, t
        while self.index < len(self.targets) and t + .00001 >= self.targets[self.index]:
            self._save(frame, t)

    def _save(self, frame, t):
        target = self.targets[self.index]
        name = self.folder / f'{self.index:04d}_{target:.3f}.jpg'
        frame.to_image().save(name, quality=90)
        self.output.append({'time': t, 'requested_time': target, 'path': str(name)})
        self.index += 1

    def finish(self):
        from PIL import Image, ImageDraw
        # EOF may fall inside the final frame's display interval. Reuse only
        # that actual decoded frame, retaining both requested and actual PTS.
        # The combined caller must finish full media validation before this.
        if self.index < len(self.targets) and self.last_frame is not None:
            gap = self.targets[-1] - self.last_time
            require(gap <= self.frame_interval + 1e-9,
                    f'missing keyframes: last_frame={self.last_time:.6f}s, '
                    f'last_target={self.targets[-1]:.6f}s, gap={gap:.6f}s '
                    f'exceeds one frame ({self.frame_interval:.6f}s)')
            while self.index < len(self.targets):
                self._save(self.last_frame, self.last_time)
        output, job = self.output, self.job
        require(len(output) == len(self.targets) and len(output) >= 24, 'missing keyframes')
        sheets = []
        for offset in range(0, len(output), 48):
            batch = output[offset:offset+48]
            sheet = Image.new('RGB', (6*180, math.ceil(len(batch)/6)*260), '#222222')
            draw = ImageDraw.Draw(sheet)
            for i, entry in enumerate(batch):
                with Image.open(entry['path']) as im:
                    im.thumbnail((180,240)); sheet.paste(im,(i%6*180,i//6*260))
                draw.text((i%6*180+4,i//6*260+242), f"{entry['time']:.3f}s", fill='white')
            p = job / f'contact_sheet_{offset//48:02d}.jpg'; sheet.save(p); sheets.append(str(p))
        return output, sheets


def extract_frames(path, spec, job):
    """Keep the standalone extraction API for existing callers."""
    import av
    with av.open(str(path)) as container:
        collector = _KeyframeCollector(spec, job, float(container.streams.video[0].average_rate))
        for frame in container.decode(video=0):
            collector.consume(frame, float(frame.pts * frame.time_base))
            if collector.index == len(collector.targets):
                break
    return collector.finish()


def validate_and_extract_frames(path, source, width, height, fps, duration, spec, job):
    """One full video decode; source/output audio still fully decoded separately.

    Completing keyframes must never stop validation of the remaining video tail.
    Failure may retain diagnostic JPEGs, but emits no successful result.
    """
    collector = _KeyframeCollector(spec, job, fps)
    validation = media_validate(path, source, width, height, fps, duration,
                                _on_frame=collector.consume)
    frames, sheets = collector.finish()
    return validation, frames, sheets


def run_job(runner, request_path, storyboard_path, job, config, quality, job_root=None):
    root = job_root or job
    manifest = runner._manifest_base(job, quality, request_path, storyboard_path, root)
    manifest.update(storyboard_schema_version='geometry-1.0', capability_version=CAPABILITY_VERSION, local_validation={'passed':False}, visual_review={'status':'not_reviewed'})
    dump = runner._json_dump
    dump(job/'manifest.json', manifest)
    audio = None; original_hash = None
    try:
        request, audio = runner._request(request_path)
        spec = validate_spec(read(storyboard_path))
        manifest.update(production_profile=spec.get('production_profile', 'standard'),
                        production_limits=production_limits(spec), render_timeout_seconds=RENDER_TIMEOUT_SECONDS)
        dump(job/'manifest.json', manifest)
        require(canonical(request['narration']) == canonical(spec['narration']), 'storyboard narration differs from original request')
        original_hash = runner._sha256(audio)
        from v3.audio_timing import probe_audio
        probe = probe_audio(audio)
        clock = decoded_audio_clock(audio)
        manifest.update(audio_probe_metadata=probe, audio_clock=clock)
        require(abs(clock['seconds'] - spec['audio_duration']) <= 1/30, 'spec/audio decoded duration mismatch')
        alignment_value = request.get('alignment_path')
        if not alignment_value:
            manifest['audio_analysis'] = {'manifest':str(job/'analysis_manifest.json'), 'report':str(job/'analysis_report.json')}
            alignment_value = analyze(runner,request_path,job,config,root)['alignment_path']
        alignment_path = runner._resolve_input(alignment_value, request_path.parent)
        analysis = read(alignment_path)
        tokens = validate_alignment(analysis, original_hash, spec['narration'], clock['seconds'], ffmpeg=config['ffmpeg_exe'])
        alignment_hash = runner._sha256(alignment_path)
        audit_value = request.get('action_audit_path')
        require(audit_value, 'geometry requires request.action_audit_path to register absolute action anchors')
        audit_path = runner._resolve_input(audit_value, request_path.parent)
        audit = read(audit_path)
        validate_action_audit(audit, spec, tokens, original_hash, alignment_hash)
        dump(job/'alignment.json', analysis); dump(job/'action_audit.json', audit)
        cache = root / 'cache'; cache.mkdir(exist_ok=True)
        dump(cache/f'geometry_alignment_{original_hash}_{digest(canonical(spec["narration"]))}.json', analysis)
        dump(job/'request.json', request); dump(job/'storyboard_normalized.json', spec)
        identity = render_identity(spec, engine_hash(runner.ENGINE_ROOT), original_hash, alignment_hash, runner._sha256(audit_path))
        manifest.update(identity=identity, inputs={'audio_sha256':original_hash, 'alignment_sha256':alignment_hash}, engine_version=engine_hash(runner.ENGINE_ROOT), timing_source=analysis.get('timing_source', analysis.get('source', analysis.get('engine'))))
        preview = None
        for p in sorted((root/'runs').glob('*/manifest.json'), reverse=True):
            candidate = read(p)
            if candidate.get('identity') == identity and candidate.get('quality') == 'preview' and candidate.get('local_validation',{}).get('passed') is True:
                movie = Path(candidate['artifacts']['video'])
                if movie.is_file() and runner._sha256(movie) == candidate.get('video_sha256'):
                    preview = (p, candidate); break
        if quality == 'final':
            require(preview is not None, 'matching validated preview required before final')
            review_path = runner._resolve_input(request['visual_review_path'], request_path.parent) if request.get('visual_review_path') else preview[0].parent/'visual_review.json'
            review = read(review_path)
            require(review.get('status') == 'passed' and review.get('identity') == identity and review.get('preview_sha256') == preview[1]['video_sha256'] and review.get('reviewer') and review.get('reviewed_at') and review.get('evidence'), 'manual preview review gate incomplete or mismatched')
            for item in review['evidence']:
                ep = runner._resolve_input(item['path'], review_path.parent)
                require(ep.is_file() and runner._sha256(ep) == item['sha256'], 'manual review evidence hash mismatch')
            manifest['preview_visual_review'] = review
        canvas = spec.get('canvas', {'width':1920,'height':1080,'fps':60})
        width,height,fps = render_settings(canvas, quality)
        from .native_encoder import encoder_contract, encoder_cache_identity
        # Preview keeps software; an explicit final request alone opts into GPU.
        selected_encoder = request.get('final_encoder_profile', 'software')
        encoder_contract(selected_encoder, config['ffmpeg_exe'])  # reject unknown names
        encoder = encoder_contract(selected_encoder if quality == 'final' else 'software', config['ffmpeg_exe'])
        if encoder['profile'] != 'software':
            require(fps == 60, 'fixed native NVENC profile requires 60 fps')
        encoding_identity = encoder_cache_identity(identity, encoder)
        manifest.update(encoder=encoder, encoding_identity=encoding_identity)
        # Spec is a validated fixed literal; -I and explicit engine import exclude user modules.
        code = compile_geometry_source(spec, runner.ENGINE_ROOT, encoder=encoder, ffmpeg_exe=config['ffmpeg_exe'])
        code_path = job/'generated_geometry_video.py'; code_path.write_text(code, encoding='utf-8')
        output = job/f'{quality}.mp4'
        reused = False
        for p in sorted((root/'runs').glob('*/manifest.json'), reverse=True):
            old = read(p)
            if old.get('identity') == identity and old.get('encoding_identity', old.get('identity')) == encoding_identity and old.get('quality') == quality and old.get('local_validation',{}).get('passed') is True:
                source = Path(old['artifacts']['video'])
                if source.is_file() and runner._sha256(source) == old.get('video_sha256'):
                    import shutil
                    shutil.copy2(source, output)
                    manifest['partial_index'] = old.get('partial_index')
                    manifest['audio_mux'] = old.get('audio_mux')
                    reused=True; break
        if not reused:
            cache_config = retain_config(job)
            command([config['python_exe'],'-I','-m','manim','--renderer','cairo','--disable_caching','--config_file',str(cache_config),'--media_dir',str(job/'media'),'-r',f'{width},{height}','--fps',str(fps),'-o','geometry_silent',str(code_path),'GeneratedGeometryVideo'],runner.ENGINE_ROOT,job/'manim.session.log', timeout=RENDER_TIMEOUT_SECONDS)
            manifest['partial_index'] = str(partial_index(job/'media'))
            dump(job/'manifest.json', manifest)
            movies = list((job/'media').rglob('geometry_silent.mp4'))
            require(len(movies) == 1, 'missing/ambiguous silent render')
            manifest['audio_mux'] = mux_audio(config['ffmpeg_exe'], movies[0], audio, output, job)
        validation,frames,sheets = validate_and_extract_frames(
            output,audio,width,height,fps,probe['duration'],spec,job)
        dump(job/'keyframes.json',frames)
        require(runner._sha256(audio) == original_hash, 'original audio changed')
        manifest.update(status='local_validation_passed', finished_at=runner._now(), local_validation=validation,
                        visual_review={'status':'not_reviewed','contact_sheets':sheets}, cache_hit=reused,
                        video_sha256=runner._sha256(output), artifacts={'video':str(output),'keyframes':str(job/'keyframes.json'),'contact_sheets':sheets,'alignment':str(job/'alignment.json'),'code':str(code_path)})
        dump(job/'manifest.json',manifest)
        report = {'passed':True,'status':'local_validation_passed','local_validation':validation,'visual_review':manifest['visual_review'],'manifest':str(job/'manifest.json'),'artifacts':manifest['artifacts'], 'audio_analysis':manifest.get('audio_analysis')}
        report.update(production_profile=manifest['production_profile'], production_limits=manifest['production_limits'], render_timeout_seconds=RENDER_TIMEOUT_SECONDS)
        dump(job/'report.json',report)
        return report
    except Exception as exc:
        if audio and original_hash: manifest['source_audio_unchanged'] = runner._sha256(audio) == original_hash
        runner._failure(job,manifest,exc)
        raise
