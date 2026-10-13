"""Known-text acoustic evidence. Qwen is never represented as Whisper.

Raw inference documents remain immutable. Only envelopes with direct endpoint
slots are eligible; repaired interior slots do not invalidate such envelopes.
"""
import hashlib
from bisect import bisect_left, bisect_right
import json
import math
import wave
from pathlib import Path
from .schema import require
from .whisper_provenance import file_sha, verify_pcm

SOURCE = 'qwen_forced_aligner'

def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def canonical(text):
    return text.lstrip('\ufeff').replace('\r\n', '\n').strip()

def load_bound(item):
    path = Path(item['path'])
    require(path.is_absolute() and path.is_file() and file_sha(path) == item['sha256'], 'Qwen artifact identity mismatch')
    return json.loads(path.read_text(encoding='utf-8-sig'))

def official_fix(raw):
    """Official nondecreasing LIS and anomaly repair, including stable ties."""
    n=len(raw); require(n>0, 'Qwen empty timestamps')
    dp=[1]*n; parent=[-1]*n
    for i in range(1,n):
        for j in range(i):
            if raw[j]<=raw[i] and dp[j]+1>dp[i]: dp[i]=dp[j]+1;parent[i]=j
    mask=[False]*n; k=dp.index(max(dp))
    while k!=-1: mask[k]=True;k=parent[k]
    result=list(raw);i=0
    while i<n:
        if mask[i]: i+=1;continue
        j=i
        while j<n and not mask[j]: j+=1
        left=result[i-1] if i else None;right=result[j] if j<n else None
        for k in range(i,j):
            if left is None: result[k]=right
            elif right is None: result[k]=left
            elif j-i<=2: result[k]=left if k-(i-1)<=j-k else right
            else: result[k]=left+(right-left)/(j-i+1)*(k-i+1)
        i=j
    return [int(x) for x in result],mask

class VerifiedQwenTokens(dict):
    def __init__(self, records, audio_hash, narration_hash, master, origin, chunks):
        super().__init__(records)
        self.audio_hash=audio_hash;self.narration_hash=narration_hash
        self.master=master;self.origin=origin;self.chunks=chunks
        self.ordered=list(self.values())
        self.word_starts=[min(t['indices']) for t in self.ordered]
        self.word_ends=[max(t['indices'])+1 for t in self.ordered]
        self.receipt=self.signature()
    def signature(self):
        return digest(json.dumps([self,self.chunks,self.origin,self.master],sort_keys=True,ensure_ascii=False,allow_nan=False))

def verify_chunk(raw, master):
    lo,hi=raw['exactsource_char_span'];text=master[lo:hi]
    require(text==raw['exact_input_text'] and digest(text)==raw['text_sha256'], 'Qwen exact master text mismatch')
    audio=Path(raw['audio_path'])
    require(file_sha(audio)==raw['audio_sha256'], 'Qwen actual chunk audio SHA mismatch')
    with wave.open(str(audio),'rb') as stream:
        require(stream.getframerate()==raw['sample_rate'] and stream.getnframes()==raw['frames'], 'Qwen original PCM clock mismatch')
        h=hashlib.sha256()
        while block:=stream.readframes(65536): h.update(block)
    require(h.hexdigest()==raw['pcm_sha256'], 'Qwen PCM SHA mismatch')
    bins=raw['raw_model_timestamp_bins'];ms=raw['fix_timestamp_input_ms']
    require(len(bins)==len(ms)==2*len(raw['words']), 'Qwen timestamp slot count mismatch')
    require(all(type(b) is int and b>=0 for b in bins), 'Qwen invalid raw model bin')
    require(all(abs(b*raw['timestamp_segment_time_ms']-t)<1e-5 for b,t in zip(bins,ms)), 'Qwen raw bins/input changed')
    fixed,mask=official_fix(ms)
    require(fixed==raw['fix_timestamp_output_ms'], 'Qwen official processed output mismatch')
    require(len(raw['slots'])==len(mask), 'Qwen repaired mask missing')
    for i,slot in enumerate(raw['slots']):
        require(slot['slot_index']==i and slot['model_bin']==bins[i] and slot['raw_ms']==ms[i] and slot['upstream_ms']==fixed[i], 'Qwen slot differs from original inference')
        require(slot['lis_anchor']==mask[i] and slot['provenance']==('model_direct' if mask[i] else 'upstream_repaired'), 'Qwen repaired slot mislabeled direct')
    owners={}
    for i,w in enumerate(raw['words']):
        require(w['word_index']==i and w['start_slot']==2*i and w['end_slot']==2*i+1, 'Qwen word slot mapping changed')
        indices=w['source_char_indices']
        require(indices and indices==sorted(set(indices)) and all(lo<=p<hi for p in indices), 'Qwen source indices invalid')
        require(''.join(master[p] for p in indices)==w['text'], 'Qwen word/source text changed')
        require(w['exactsource_char_span']==[indices[0],indices[-1]+1], 'Qwen word exact range mismatch')
        require(w['chunk_char_span']==[indices[0]-lo,indices[-1]+1-lo], 'Qwen chunk range mismatch')
        for p in indices:
            require(p not in owners, 'Qwen duplicate source character');owners[p]=i
        require(w['start_seconds']==fixed[2*i]/1000 and w['end_seconds']==fixed[2*i+1]/1000, 'Qwen word timing changed')
        require(w['raw_start_seconds']==ms[2*i]/1000 and w['raw_end_seconds']==ms[2*i+1]/1000, 'Qwen raw word timing changed')
        require(w['zero_duration']==(fixed[2*i]==fixed[2*i+1]), 'Qwen zero slot flag mismatch')
    mapping=raw['input_to_output_mapping']
    require(len(mapping)==len(text), 'Qwen incomplete input mapping')
    for i,m in enumerate(mapping):
        require(m['chunk_char_index']==i and m['source_char_index']==lo+i and m['char']==text[i] and m['output_word_index']==owners.get(lo+i), 'Qwen input mapping changed')
        require(not text[i].isalnum() or lo+i in owners, 'Qwen unmapped spoken source character')
    return mask

def validate_alignment(data,audio_hash,narration,duration):
    require(data.get('timing_source')==SOURCE and data.get('source')==SOURCE,'Qwen source must be explicit')
    require(data['source_audio_sha256']==audio_hash and file_sha(data['source_audio_path'])==audio_hash,'Qwen destination audio mismatch')
    require(data['canonical_narration_sha256']==digest(canonical(narration)),'Qwen narration hash mismatch')
    doc=data['source_document'];require(file_sha(doc['path'])==doc['sha256'],'Qwen master file hash mismatch')
    master=Path(doc['path']).read_text(encoding='utf-8-sig').replace('\r\n','\n')
    origin=data['master_char_start'];end=data['master_char_end']
    require(canonical(master[origin:end])==canonical(narration),'Qwen narration exact range mismatch')
    with wave.open(data['source_audio_path'],'rb') as dst:
        rate=dst.getframerate();frames=dst.getnframes()
    require(abs(frames/rate-duration)<1e-6,'Qwen destination duration mismatch')
    tokens={};chunks=[];next_frame=0;next_char=origin;checked_artifacts=set()
    for ref in data['chunks']:
        raw=load_bound(ref);mask=verify_chunk(raw,master)
        require(raw['exactsource_char_span'][0]==next_char and ref['destination_frame_offset']==next_frame,'Qwen chunk coverage/order/offset mismatch')
        require(raw['sample_rate']==rate,'Qwen chunk/destination sample rate mismatch')
        # Artifact files are bound independently of the chunk JSON itself.
        require(ref.get('model_artifacts') and ref.get('official_source'),'Qwen original model/source artifacts missing')
        for artifact in ref['model_artifacts']+[ref['official_source']]:
            key=(artifact['path'],artifact['sha256'])
            if key not in checked_artifacts:
                require(Path(artifact['path']).is_file() and file_sha(artifact['path'])==artifact['sha256'],'Qwen raw model/source artifact SHA mismatch')
                checked_artifacts.add(key)
        require(ref.get('source_revision')==raw['source_revision'] and ref.get('model_identity')==raw['model_identity'],'Qwen inference model/source identity mismatch')
        verify_pcm(raw['audio_path'],data['source_audio_path'],next_frame,rate)
        offset=next_frame/rate
        chunk={'id':raw['chunk_id'],'range':raw['exactsource_char_span'],'start':offset,'end':offset+raw['frames']/rate,'raw_sha256':ref['sha256']}
        chunks.append(chunk)
        for w in raw['words']:
            key=f"{raw['chunk_id']}:{w['word_index']}"
            a,b=w['start_slot'],w['end_slot'];s=w['start_seconds'];e=w['end_seconds']
            require(0<=s<=e<=raw['frames']/rate+.08,'Qwen word outside acoustic chunk')
            tokens[key]={'id':key,'source':SOURCE,'text':w['text'],'indices':w['source_char_indices'],
                'start':offset+s if e>s else None,'end':offset+e if e>s else None,
                'raw_start':offset+w['raw_start_seconds'],'raw_end':offset+w['raw_end_seconds'],
                'start_direct':mask[a],'end_direct':mask[b],'zero_duration':w['zero_duration'],'chunk':chunk['id']}
        next_frame+=raw['frames'];next_char=raw['exactsource_char_span'][1]
    require(next_frame==frames and next_char==end,'Qwen chunks do not exactly cover destination PCM/source')
    return VerifiedQwenTokens(tokens,audio_hash,digest(canonical(narration)),master,origin,chunks)

def range_tokens(tokens,lo,hi):
    if hasattr(tokens,'ordered') and len(tokens.ordered)==len(tokens):
        return tokens.ordered[bisect_right(tokens.word_ends,lo):bisect_left(tokens.word_starts,hi)]
    return [t for t in tokens.values() if any(lo<=p<hi for p in t['indices'])]

def envelope(tokens,lo,hi):
    selected=range_tokens(tokens,lo,hi)
    require(selected,'Qwen phrase has no mapped spoken units')
    starts=[t for t in selected if t['start_direct'] and not t['zero_duration']]
    ends=[t for t in selected if t['end_direct'] and not t['zero_duration']]
    require(starts and ends,'Qwen phrase has no direct positive acoustic envelope')
    first,last=starts[0],ends[-1]
    a,b=first['raw_start'],last['raw_end']
    require(a<b and not (len(selected)==1 and first['zero_duration']),'Qwen zero-length envelope is untimed')
    return {'start':a,'end':b,'anchor_ids':[t['id'] for t in selected], 'direct_endpoint_ids':[first['id'],last['id']], 'master_char_start':lo,'master_char_end':hi,'text':tokens.master[lo:hi]}

def sentence_budget(tokens,lo,hi):
    result=envelope(tokens,lo,hi)
    following=next((t for t in range_tokens(tokens,hi,len(tokens.master)) if t['start_direct'] and not t['zero_duration']),None)
    boundary=following['raw_start'] if following else tokens.chunks[-1]['end']
    # Official processor may emit one indivisible Latin unit across punctuation,
    # e.g. F。P -> FP. Stop at that unit's direct onset rather than borrowing its
    # tail from the next sentence or splitting a timestamp between characters.
    require(boundary>result['start'],'Qwen sentence lacks a positive bounded acoustic interval')
    result.update(spoken_end=result['end'],speech_envelope_end=result['end'],end=boundary,
        motion_deadline_source='audio_pause' if boundary>=result['end'] else 'shared_model_word_onset_conservative',
        trailing_pause_boundary={'kind':'next_direct_word_start' if following else 'actual_pcm_end',
            'token_id':following['id'] if following else None,'time':boundary,
            'shared_model_word_across_sentence':bool(following and min(following['indices'])<hi)},
        policy='actual trailing pause may finish motion; never consume next spoken sentence')
    return result

def cue_evidence(tokens,lo,hi,sentence_lo,sentence_hi):
    """Nearest acoustic neighbors, not a whole-sentence onset fallback.

    earliest_start is an animation scheduling constraint, never a word timestamp.
    All-zero cues use the right real boundary conservatively to avoid early answers.
    """
    words=range_tokens(tokens,sentence_lo,sentence_hi)
    indices=[i for i,t in enumerate(words) if any(lo<=p<hi for p in t['indices'])]
    require(indices,'Qwen cue has no known-text mapping')
    first,last=min(indices),max(indices);target=words[first:last+1]
    timed=[t for t in target if not t['zero_duration'] and t['start'] is not None]
    if not timed:
        left=next((t for t in reversed(words[:first]) if t['end_direct'] and not t['zero_duration']),None)
        right=next((t for t in words[last+1:] if t['start_direct'] and not t['zero_duration']),None)
        require(left is not None and right is not None,'Qwen zero cue lacks neighboring direct boundaries; retry affected acoustic region')
        require(left['raw_end']<=right['raw_start'],'Qwen neighboring acoustic boundaries reversed')
        a=min(left['indices']);b=max(right['indices'])+1
        selected=words[words.index(left):words.index(right)+1]
        return {'kind':'uncertain_zero_cue_between_direct_neighbors','source_range':[a,b],
            'target_range':[lo,hi],'anchor_ids':[t['id'] for t in selected],
            'direct_endpoint_ids':[left['id'],right['id']],
            'start':left['raw_end'],'end':right['raw_start'],'earliest_start':right['raw_start'],
            'uncertain':True,'word_timestamp_invented':False,
            'policy':'continue prior state through uncertain interval; reveal no earlier than real right neighbor onset'}
    # Expand only as far as the closest usable start/end around the target.
    left=first
    while left>=0 and (not words[left]['start_direct'] or words[left]['zero_duration']):left-=1
    right=last
    while right<len(words) and (not words[right]['end_direct'] or words[right]['zero_duration']):right+=1
    # Direct internal target units can still locate a cue whose outer slots are repaired.
    if left<0:left=next((i for i in indices if words[i]['start_direct'] and not words[i]['zero_duration']),-1)
    if right>=len(words):right=next((i for i in reversed(indices) if words[i]['end_direct'] and not words[i]['zero_duration']),len(words))
    require(0<=left<=right<len(words),'Qwen cue lacks local direct envelope; retry affected acoustic region')
    a=min(lo,min(words[left]['indices']));b=max(hi,max(words[right]['indices'])+1)
    start=words[left]['raw_start'];end=words[right]['raw_end']
    require(start<end,'Qwen cue has no positive neighboring envelope')
    target_onset=min(t['start'] for t in timed)
    # The 0.2s margin constrains scheduling; it does not modify acoustic evidence.
    earliest=max(start,target_onset-.2)
    return {'kind':'direct_target_or_nearest_phrase','source_range':[a,b],'target_range':[lo,hi],
        'anchor_ids':[t['id'] for t in words[left:right+1]],
        'direct_endpoint_ids':[words[left]['id'],words[right]['id']],
        'start':start,'end':end,'earliest_start':earliest,'nearest_target_timed_start':target_onset,
        'uncertain':a!=lo or b!=hi or any(not t['start_direct'] or not t['end_direct'] for t in target),
        'word_timestamp_invented':False}

def validate_audit(audit,spec,tokens,audio_hash,alignment_hash):
    require(isinstance(tokens,VerifiedQwenTokens) and tokens.receipt==tokens.signature(),'Qwen verified receipt changed')
    require(tokens.audio_hash==audio_hash and tokens.narration_hash==digest(canonical(spec['narration'])),'Qwen audit receipt input mismatch')
    require(audit.get('timing_source')==SOURCE and audit.get('source')==SOURCE,'Qwen action source must be explicit')
    require(audit['source_audio_sha256']==audio_hash and audit['alignment_sha256']==alignment_hash and audit['canonical_narration_sha256']==tokens.narration_hash,'Qwen audit input binding mismatch')
    table={(e['chapter_id'],e['action_index']):e for e in audit['actions']}
    expected={(c['id'],i) for c in spec['chapters'] for i in range(len(c['actions']))}
    require(len(table)==len(audit['actions']) and set(table)==expected,'Qwen audit must cover every action once')
    previous=-1
    for c in spec['chapters']:
        for i,action in enumerate(c['actions']):
            e=table[c['id'],i];lo,hi=e['master_char_start'],e['master_char_end']
            require(tokens.master[lo:hi]==e['anchor_text'],'Qwen cue exact source mismatch')
            if 'original_plan_anchor' in e:
                original=e['original_plan_anchor'];x,y=original['master_char_start'],original['master_char_end']
                require(x<=lo<hi<=y and tokens.master[x:y]==original['text'],'Qwen original plan context changed')
            w=e['motion_window'];a,b=w['master_char_start'],w['master_char_end']
            require(a<=lo<hi<=b and not any(x in tokens.master[a:b].rstrip('。！？\n') for x in '。！？\n'),'Qwen motion window crosses narration sentence')
            env=sentence_budget(tokens,a,b)
            require(w['anchor_ids']==env['anchor_ids'],'Qwen motion envelope identities changed')
            require(w.get('trailing_pause_boundary')==env['trailing_pause_boundary'],'Qwen trailing pause boundary changed')
            require(e['at']==action['at'] and e['duration']==action['duration'],'Qwen audit/action clock mismatch')
            require(action['at']>=previous-1e-7 and env['start']<=action['at']+1e-7 and action['at']+action['duration']<=env['end']+1e-7,'Qwen motion exceeds direct sentence budget')
            previous=action['at']+action['duration']
            cue=cue_evidence(tokens,lo,hi,a,b);cue_lo,cue_hi=cue['source_range']
            # One official Latin unit may include source indices on both sides
            # of punctuation. Preserve its whole real source range; the motion
            # clock remains separately bounded by the current sentence above.
            require(cue_lo<=lo<hi<=cue_hi and e['anchor_ids']==cue['anchor_ids'] and e['cue_timing_evidence']==cue,'Qwen cue evidence mismatch')
            require(action['at']>=cue['earliest_start']-1e-7,'Qwen action begins before nearest target acoustic evidence')
