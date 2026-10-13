"""Verify local Whisper evidence and exact PCM transforms. No inferred clocks."""
import hashlib
import json
import math
import wave
import unicodedata
import ctypes
import re
from pathlib import Path
from .schema import require, number

class VerifiedWhisperTokens(dict):
    """In-process proof receipt; serialized token dictionaries are not receipts."""
    def __init__(self,tokens,audio_hash,narration_hash,segments):
        super().__init__(tokens)
        self.audio_hash=audio_hash; self.narration_hash=narration_hash
        self.segments={key:segments[key] for key in self}
        self.receipt=self.signature()
    def signature(self):
        return hashlib.sha256(json.dumps({'tokens':self,'segments':self.segments},sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def require_verified_tokens(tokens,audio_hash,narration_hash):
    require(isinstance(tokens,VerifiedWhisperTokens),'action audit needs tokens returned by verified original Whisper alignment')
    require(tokens.audio_hash==audio_hash and tokens.narration_hash==narration_hash and tokens.receipt==tokens.signature(),
            'action audit verified token receipt changed or source mismatch')

def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def load_bound(item,path_key='path',hash_key='sha256'):
    path=Path(item.get(path_key,''))
    require(path.is_absolute() and path.is_file(),'Whisper original evidence file missing')
    require(file_sha(path)==item.get(hash_key),'Whisper original evidence SHA mismatch')
    return json.loads(path.read_text(encoding='utf-8-sig'))

def verify_pcm(source,destination,offset,rate,source_frames=None):
    require(type(offset) is int and offset>=0 and type(rate) is int and rate>0,'invalid exact PCM frame offset')
    with wave.open(str(source),'rb') as src, wave.open(str(destination),'rb') as dst:
        require(src.getframerate()==dst.getframerate()==rate and src.getnchannels()==dst.getnchannels()
                and src.getsampwidth()==dst.getsampwidth(),'PCM provenance format mismatch')
        first,last=source_frames if source_frames is not None else (0,src.getnframes())
        require(type(first) is int and type(last) is int and 0<=first<last<=src.getnframes(),'invalid source PCM frame range')
        require(offset+last-first<=dst.getnframes(),'PCM source exceeds destination bounds')
        src.setpos(first);remaining=last-first
        dst.setpos(offset)
        while remaining:
            data=src.readframes(min(65536,remaining))
            require(data,'truncated original PCM source')
            count=len(data)//(src.getnchannels()*src.getsampwidth())
            require(dst.readframes(count)==data,'PCM frame offset/content mismatch')
            remaining-=count

def verify_whisper_provenance(data, *, depth=0, cache=None):
    require(depth<=3,'Whisper provenance chain too deep')
    cache={} if cache is None else cache
    anchors=data.get('anchors'); require(isinstance(anchors,list) and anchors,'Whisper anchors missing')
    ids=[str(t.get('id')) for t in anchors]
    require(len(ids)==len(set(ids)),'duplicate original Whisper token id')
    sources=data.get('provenance_sources')
    if sources is not None:
        require(isinstance(sources,list) and sources,'derived Whisper requires original alignment sources')
        destination=Path(data.get('source_audio_path',''))
        require(destination.is_file() and file_sha(destination)==data.get('source_audio_sha256'),'derived Whisper destination audio mismatch')
        parents={}
        for item in sources:
            key=item.get('alignment_sha256'); require(key not in parents,'duplicate derived alignment source')
            parent=load_bound(item,'alignment_path','alignment_sha256')
            if key not in cache:
                cache[key]=verify_whisper_provenance(parent,depth=depth+1,cache=cache)
            source=Path(item.get('source_audio_path',''))
            require(source.is_file() and file_sha(source)==parent.get('source_audio_sha256'),'original alignment audio mismatch')
            verify_pcm(source,destination,item.get('destination_frame_offset'),item.get('sample_rate'),item.get('source_frame_range'))
            parents[key]=(item,{str(t['id']):t for t in parent['anchors']},
                          {str(t['id']):i for i,t in enumerate(parent['anchors'])},cache[key])
        identities=set(); order={}; verified={}; raw_identities=set()
        for token in anchors:
            origin=token.get('origin',{}); key=origin.get('alignment_sha256')
            require(key in parents,'derived token has no original alignment backlink')
            item,table,indices,segments=parents[key]; original_id=str(origin.get('token_id')); original=table.get(original_id)
            require(original is not None,'derived token original id missing')
            identity=(key,original_id,item['destination_frame_offset'])
            require(identity not in identities,'duplicate original token identity under a new derived ID');identities.add(identity)
            group=(key,item['destination_frame_offset']); position=indices[original_id]
            require(position>order.get(group,-1),'derived original token merge order changed');order[group]=position
            require(token.get('text')==original.get('text') and token.get('raw_token')==original.get('raw_token'),'derived token raw text/object mutated')
            require(origin.get('frame_offset')==item['destination_frame_offset'] and origin.get('sample_rate')==item['sample_rate'],'derived token PCM offset differs from verified source')
            for field in ('start','end'):
                local=original.get(field); require(origin.get('local_'+field)==local,'derived local original time mutated')
                crop_start=item.get('source_frame_range',[0])[0]
                if local is not None and 'source_frame_range' in item:
                    require(item['source_frame_range'][0]/item['sample_rate']<=local<=item['source_frame_range'][1]/item['sample_rate'],
                            'original token outside verified PCM source crop')
                expected=None if local is None else local+(item['destination_frame_offset']-crop_start)/item['sample_rate']
                require(token.get(field)==expected,'derived token shifted/invented original time')
            meta=segments[original_id]; shift=(item['destination_frame_offset']-item.get('source_frame_range',[0])[0])/item['sample_rate']
            origin_identity=(meta['raw_document_sha256'],meta['raw_token_index'],meta['raw_offset_seconds']+shift)
            require(origin_identity not in raw_identities,'duplicate original raw sample identity through different alignment chains');raw_identities.add(origin_identity)
            verified[str(token['id'])]={**meta,'segment_start':meta['segment_start']+shift,'segment_end':meta['segment_end']+shift,
                'raw_offset_seconds':meta['raw_offset_seconds']+shift,
                'audio_offsets':{**{h:v+shift for h,v in meta['audio_offsets'].items()},data['source_audio_sha256']:0}}
        return verified
    evidence=data.get('raw_evidence')
    require(isinstance(evidence,list) and evidence,'Whisper raw_evidence files required; source label is insufficient')
    transcripts=[]
    for item in evidence:
        path=Path(item.get('path',''))
        require(path.is_absolute() and path.is_file(),'Whisper original evidence file missing')
        require(file_sha(path)==item.get('sha256'),'Whisper original evidence SHA mismatch')
        if path.suffix.lower()=='.json':
            raw=json.loads(path.read_text(encoding='utf-8-sig'))
            if isinstance(raw,dict) and isinstance(raw.get('transcription'),list):transcripts.append((raw,item['sha256']))
    require(len(transcripts)==1,'Whisper needs exactly one original full-json transcription per direct alignment')
    expected=[]; previous=-1; duration=data.get('duration')
    require(number(duration) and duration>0,'original Whisper duration missing')
    for segment_index,segment in enumerate(transcripts[0][0]['transcription']):
        segment_tokens=segment.get('tokens',[])
        raw_times=[float(v)/1000 for t in segment_tokens for v in (t.get('offsets',{}).get('from'),t.get('offsets',{}).get('to'))
                   if type(v) in (int,float) and math.isfinite(v) and v>=0]
        segment_start=min(raw_times,default=0);segment_end=max(raw_times,default=0)
        for raw in segment.get('tokens',[]):
            text=str(raw.get('text',''))
            if text.startswith('[_') or not text.strip():continue
            off=raw.get('offsets') or {}
            def seconds(value):return float(value)/1000 if type(value) in (int,float) and math.isfinite(value) else None
            s,e=seconds(off.get('from')),seconds(off.get('to'))
            invalid=not number(s) or not number(e) or s<0 or e<=s or e>duration or s<previous-.03
            if not invalid:previous=s
            expected.append((raw,text,None if invalid else s,None if invalid else e,s,e,segment_index,segment_start,segment_end))
    require(len(anchors)==len(expected),'Whisper original token count mismatch')
    verified={}
    for i,(token,(raw,text,s,e,rs,re,segment_index,segment_start,segment_end)) in enumerate(zip(anchors,expected)):
        require(str(token.get('id'))==str(i),'Whisper original token order/id mismatch')
        require(token.get('raw_token')==raw and token.get('text')==text,'Whisper original token raw/text mismatch')
        require(token.get('start')==s and token.get('end')==e,'Whisper original token time mismatch')
        if s is None:require(token.get('raw_start')==rs and token.get('raw_end')==re,'Whisper invalid token raw time mismatch')
        verified[str(token['id'])]={'raw_document_sha256':transcripts[0][1],'raw_token_index':i,'segment_index':segment_index,
            'segment_start':segment_start,'segment_end':segment_end,'raw_offset_seconds':0,
            'audio_offsets':{data['source_audio_sha256']:0}}
    return verified

def match_text(text):
    text=unicodedata.normalize('NFKC',text)
    if hasattr(ctypes,'windll') and text:
        fn=ctypes.windll.kernel32.LCMapStringEx
        fn.argtypes=[ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_wchar_p,ctypes.c_int,ctypes.c_wchar_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_longlong]
        fn.restype=ctypes.c_int; buf=ctypes.create_unicode_buffer(len(text)*3+8)
        require(fn('zh-CN',0x02000000,text,len(text),buf,len(buf),None,None,0)>0,'audit match normalization failed')
        text=buf.value
    def integer_reading(match):
        value=int(match.group()); digits='零一二三四五六七八九'
        if value==0:return '零'
        out=''; zero=False
        for power,suffix in ((1000,'千'),(100,'百'),(10,'十'),(1,'')):
            n,value=divmod(value,power)
            if n:
                if zero:out+='零'
                out+=digits[n]+suffix;zero=False
            elif out and value:zero=True
        return out[1:] if out.startswith('一十') else out
    text=re.sub(r'(?<![\d.])\d{1,4}(?![\d.])',integer_reading,text)
    return ''.join(c.upper() for c in text if c.isalnum() or c in '+-−=<>≤≥≠±√*/÷×^%')

def audit_source(audit,spec):
    offset=audit.get('narration_master_char_start',0)
    require(type(offset) is int and offset>=0,'invalid narration master offset')
    if 'source_document' in audit:
        doc=audit['source_document']; path=Path(doc.get('path',''))
        require(path.is_absolute() and path.is_file() and file_sha(path)==doc.get('sha256'),'audit source document SHA mismatch')
        master=path.read_text(encoding='utf-8-sig').replace('\r\n','\n')
        require(master[offset:offset+len(spec['narration'])]==spec['narration'],'audit narration master range mismatch')
    else:
        require(offset==0,'global audit spans require bound source document')
        master=spec['narration']
    return master,offset

def verify_action_cue(entry,action,tokens,master,offset,spec,previous):
    lo,hi=entry.get('master_char_start'),entry.get('master_char_end')
    require(type(lo) is int and type(hi) is int and offset<=lo<hi<=offset+len(spec['narration']), 'audit master span outside narration')
    require(entry.get('anchor_text')==master[lo:hi],'audit anchor text/source span mismatch')
    trigger=entry.get('trigger_evidence',{})
    pairs=trigger.get('alignment_pairs',[]); cue_ids=trigger.get('anchor_ids',[])
    require(isinstance(pairs,list) and pairs and isinstance(cue_ids,list) and cue_ids,'audit requires local real cue trigger evidence')
    require(all(str(x) in tokens and x in entry['anchor_ids'] for x in cue_ids),'trigger anchors unrelated to declared anchor ids')
    exact=[]
    for pair in pairs:
        pos=pair.get('master_char'); key=str(pair.get('raw_token_id'))
        require(type(pos) is int and lo<=pos<hi and key in tokens and key in {str(x) for x in cue_ids},'trigger pair outside source cue or token set')
        expected=match_text(master[pos]); raw=match_text(tokens[key]['text'])
        require(expected and expected in raw and pair.get('expected')==master[pos], 'trigger pair does not match real cue token')
        exact.append(pos)
    significant=[i for i in range(lo,hi) if match_text(master[i])]
    # Source-bound cue positions are checked above. Do not invent a fixed
    # four-character cutoff: leading function words may have genuine null times.
    require(exact,'trigger has no original source cue evidence')
    require(len(set(exact))>=(min(2,len(significant)) if len(significant)<=2 else 1),'trigger needs disambiguating cue evidence')
    require({str(x) for x in cue_ids}=={str(p['raw_token_id']) for p in pairs},'trigger contains unrelated token ids')
    cue=match_text(master[lo:hi]); numeric=set('零一二三四五六七八九十百千万两+-−=<>≤≥≠±√*/÷×^%')
    if cue and all(c in numeric for c in cue):
        require(cue==match_text(''.join(tokens[str(x)]['text'] for x in cue_ids)),'numeric trigger value/sign mismatch')
    t0=min(tokens[str(x)]['start'] for x in cue_ids); t1=max(tokens[str(x)]['end'] for x in cue_ids)
    window=entry.get('motion_window',{}); wlo,whi=window.get('master_char_start'),window.get('master_char_end')
    require(type(wlo) is int and type(whi) is int and offset<=wlo<=lo<whi<=offset+len(spec['narration'])
            and all(wlo<=pos<whi for pos in exact), 'motion window source range invalid')
    require(window.get('text')==master[wlo:whi] and whi-wlo<=1000,'motion window text mismatch or unbounded range')
    require(sum(c in '。！？；\n' for c in master[wlo:whi])<=3,'motion window exceeds local sentence continuation')
    mids=window.get('anchor_ids',[])
    require(mids and all(str(x) in tokens for x in mids),'motion window requires real token ids')
    links=window.get('source_token_pairs',[])
    require(isinstance(links,list) and links,'motion window needs local source/raw links, not only a maximum token end')
    linked_segments=set(); last_position=-1;last_time=-1
    def segment_key(meta):return (meta['raw_document_sha256'],meta['segment_index'],meta['raw_offset_seconds'])
    for link in links:
        pos=link.get('master_char_start',link.get('master_char'))
        stop=link.get('master_char_end',pos+1 if type(pos) is int else None)
        tids=[str(x) for x in link.get('raw_token_ids',[link.get('raw_token_id')])]
        require(type(pos) is int and type(stop) is int and wlo<=pos<stop<=whi and tids
                and all(tid in tokens and tid in {str(x) for x in mids} for tid in tids),'motion source/raw link outside declared sentence')
        expected=match_text(master[pos:stop]);actual=match_text(''.join(tokens[tid]['text'] for tid in tids))
        matches=expected==actual if 'raw_token_ids' in link else expected in actual
        require(link.get('expected')==master[pos:stop] and expected and matches,
                'motion source/raw link text mismatch')
        require(pos>=last_position and tokens[tids[0]]['start']>=last_time-.03
                and all(tokens[y]['start']>=tokens[x]['start']-.03 for x,y in zip(tids,tids[1:])), 'motion source/raw links are not monotone')
        last_position=pos;last_time=tokens[tids[-1]]['start']
        linked_segments.update(segment_key(tokens.segments[tid]) for tid in tids)
    require(all(segment_key(tokens.segments[str(tid)]) in linked_segments for tid in mids),
            'motion token belongs to an unrelated original ASR sentence')
    chunk_ref=window.get('pcm_chunk')
    if chunk_ref:
        info=load_bound(chunk_ref,'manifest_path','manifest_sha256')
        choices=[c for c in info.get('chunk_frame_offsets',[]) if c.get('id')==chunk_ref.get('chunk_id')]
        require(len(choices)==1,'motion PCM chunk identity missing')
        chunk=choices[0];cl,ch=chunk['master_unicode_range'];f0,f1=chunk['frame_range'];rate=info['rate']
        require(cl<=wlo<whi<=ch and hashlib.sha256(master[cl:ch].encode()).hexdigest()==chunk['exacttext_sha256'],
                'motion source window is outside actual TTS chunk text')
        for tid in mids:
            meta=tokens.segments[str(tid)]; audiohash=info.get('audio_sha256')
            require(audiohash in meta['audio_offsets'],'motion chunk audio not in verified PCM source chain')
            shift=meta['audio_offsets'][audiohash]
            require(shift+f0/rate<=tokens[str(tid)]['start']<tokens[str(tid)]['end']<=shift+f1/rate,
                    'motion token outside actual TTS PCM chunk')
    end=max(tokens[str(x)]['end'] for x in mids)
    require(action['at']+action['duration']<=end+1/spec['canvas']['fps'],'motion exceeds evidenced sentence window')
    group=(lo,hi,tuple(str(x) for x in cue_ids))
    if not t0<=action['at']<=t1+1/spec['canvas']['fps']:
        require(group in previous and action['at']>=previous[group] and action['at']-t1<=10,
                'delayed start needs a preceding action on this same real cue')
        require(entry.get('reviewed_by') and entry.get('reason') and entry.get('evidence'),'delayed same-cue action requires explicit bounded review')
    previous[group]=action['at']+action['duration']
