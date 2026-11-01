"""成片动效音效：按分镜真实动作时间合成音效并混入已验收成片的音轨，视频流原样复制。

音效全部由本脚本程序合成（无外部素材、无版权依赖），时间只取自 storyboard 动作的 at/duration，
因此与画面动作逐帧对应。原成片不改，另存为新文件；报告写出每个音效的时间、类型和来源动作。

用法（runtime venv 的 python，需 numpy）：
  python add_sfx.py --storyboard 规范化分镜.json --video final.mp4 --out 成片_音效版.mp4 --runtime-config runtime.json
可选：--gain-db（音效总增益，默认 -12）、--min-gap（相邻音效最小间隔秒，默认 .22）、--no-<类型> 关闭某类音效。
"""
import argparse, hashlib, json, math, subprocess, tempfile, wave
from pathlib import Path
import numpy as np

SR = 44100
RNG = np.random.default_rng(38)

# ---------------------------------------------------------------- 合成音色
def env_exp(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))
def lowpass(x, cutoff):
    """一阶低通；cutoff 可为常数或逐样本数组（Hz）。"""
    c = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = 1 - np.exp(-2 * np.pi * c / SR)
    y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc); y[i] = acc
    return y
def fade(x, ms=4):
    k = min(len(x) // 2, int(SR * ms / 1000))
    if k: x[:k] *= np.linspace(0, 1, k); x[-k:] *= np.linspace(1, 0, k)
    return x

def pop(_d):        # 文字/点出现：短促上扬的“啵”
    n = int(.07 * SR); t = np.arange(n) / SR
    f = 620 + 420 * (t / t[-1])
    return fade(.5 * np.sin(2 * np.pi * np.cumsum(f) / SR) * env_exp(n, .018))
def tick(_d):       # 文字变换：清脆“嗒”
    n = int(.03 * SR); t = np.arange(n) / SR
    return fade(.32 * np.sin(2 * np.pi * 2400 * t) * env_exp(n, .006))
def ding(_d):       # 强调：轻铃
    n = int(.7 * SR); t = np.arange(n) / SR
    s = np.sin(2 * np.pi * 1318.5 * t) + .35 * np.sin(2 * np.pi * 2637 * t) + .12 * np.sin(2 * np.pi * 3955 * t)
    return fade(.38 * s / 1.47 * env_exp(n, .16))
def thump(_d):      # 片头粗体大字落下：低频“咚”+ 轻擦
    n = int(.22 * SR); t = np.arange(n) / SR
    f = 120 * np.exp(-t / .08) + 55
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_exp(n, .07)
    click = lowpass(RNG.standard_normal(n), 3000) * env_exp(n, .004)
    return fade(.85 * body + .25 * click)
def whoosh(d):      # 参数运动/移动：随动作时长的风声，滤波截止先升后降
    d = min(max(d, .25), 1.8); n = int(d * SR); p = np.linspace(0, 1, n)
    x = lowpass(RNG.standard_normal(n), 300 + 2600 * np.sin(np.pi * p) ** 1.5)
    return fade(.55 * x / (np.abs(x).max() + 1e-9) * np.sin(np.pi * p) ** 2, 10)
def pencil(d):      # 画线/画圆：铅笔划纸的沙沙声，长度随绘制
    d = min(max(d, .15), .9); n = int(d * SR); p = np.linspace(0, 1, n)
    x = RNG.standard_normal(n); x = x - lowpass(x, 1800)                    # 高通
    grain = .6 + .4 * np.abs(np.sin(2 * np.pi * 23 * p * d + RNG.uniform(0, 6)))
    return fade(.16 * x / (np.abs(x).max() + 1e-9) * grain * np.sin(np.pi * p) ** .5, 8)
def paper(_d):      # 面板/卡片出现：纸张轻拍
    n = int(.12 * SR)
    x = lowpass(RNG.standard_normal(n), 900) * env_exp(n, .03)
    return fade(.5 * x / (np.abs(x).max() + 1e-9))

SYNTH = dict(pop=pop, tick=tick, ding=ding, thump=thump, whoosh=whoosh, pencil=pencil, paper=paper)
PRIORITY = dict(ding=6, thump=6, whoosh=5, pencil=4, paper=3, pop=2, tick=1)

# ---------------------------------------------------------------- 动作 → 音效
def classify(action, objs):
    kind = action['type']; ids = action.get('ids') or [i['id'] for i in action.get('items', [])]
    o = [objs[i] for i in ids if i in objs]
    heavy = any(x.get('type') == 'text' and x.get('typography') == 'heavy' for x in o)
    if kind == 'reveal':
        if action.get('style') == 'draw': return 'pencil'
        if heavy: return 'thump'
        if o and all(x.get('type') == 'panel' for x in o): return 'paper'
        if any(x.get('type') in ('text', 'point') for x in o): return 'pop'
        return None                                              # 纯填充/角标淡入保持安静
    if kind == 'highlight': return 'ding'
    if kind in ('set_parameter', 'move', 'move_on_circle', 'translate_copy', 'reflect_copy', 'rotate', 'constrain'): return 'whoosh'
    if kind == 'text_transform': return 'tick'
    return None                                                  # hide 等不配音，避免杂乱

def plan(spec, min_gap, disabled):
    cues = []
    for ch in spec['chapters']:
        objs = {o['id']: o for o in ch.get('objects', [])}
        for idx, a in enumerate(ch.get('actions', [])):
            k = classify(a, objs)
            if k and k not in disabled:
                cues.append(dict(t=float(a['at']), d=float(a.get('duration', .3)), kind=k,
                                 chapter=ch.get('id'), action_index=idx, action_type=a['type']))
    cues.sort(key=lambda c: (c['t'], -PRIORITY[c['kind']]))
    kept = []
    for c in cues:                                   # 间隔内只留优先级最高的一个
        if kept and c['t'] - kept[-1]['t'] < min_gap:
            if PRIORITY[c['kind']] > PRIORITY[kept[-1]['kind']]: kept[-1] = c
            continue
        kept.append(c)
    return kept

# ---------------------------------------------------------------- 混音与封装
def read_wav(p):
    with wave.open(str(p)) as w:
        assert w.getsampwidth() == 2 and w.getframerate() == SR
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        return x.reshape(-1, w.getnchannels())
def write_wav(p, x):
    with wave.open(str(p), 'wb') as w:
        w.setnchannels(x.shape[1]); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
rms_db = lambda x: 20 * math.log10(float(np.sqrt(np.mean(x ** 2))) + 1e-12)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--storyboard', required=True); ap.add_argument('--video', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--runtime-config', required=True)
    ap.add_argument('--gain-db', type=float, default=-12); ap.add_argument('--min-gap', type=float, default=.22)
    for k in SYNTH: ap.add_argument(f'--no-{k}', action='store_true')
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists(): raise SystemExit('输出已存在，不覆盖：' + str(out))
    ffmpeg = json.loads(Path(a.runtime_config).read_text(encoding='utf-8-sig'))['ffmpeg_exe']
    spec = json.loads(Path(a.storyboard).read_text(encoding='utf-8-sig'))
    disabled = {k for k in SYNTH if getattr(a, 'no_' + k)}
    cues = plan(spec, a.min_gap, disabled)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', a.video, '-vn', '-ac', '2', '-ar', str(SR), '-c:a', 'pcm_s16le', str(td / 'voice.wav')], check=True)
        voice = read_wav(td / 'voice.wav')
        fx = np.zeros(len(voice), dtype=np.float32)
        for c in cues:
            s = SYNTH[c['kind']](c['d']).astype(np.float32); i = int(round(c['t'] * SR))
            j = min(len(fx), i + len(s))
            if i < len(fx): fx[i:j] += s[:j - i]
        fx *= 10 ** (a.gain_db / 20)
        mix = voice + fx[:, None]
        peak = float(np.abs(mix).max())
        if peak > .98: mix *= .98 / peak                         # 只在会削波时整体压低，不改变相对响度
        write_wav(td / 'mix.wav', mix)
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', a.video, '-i', str(td / 'mix.wav'), '-map', '0:v', '-map', '1:a',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', str(out)], check=True)
        voice_db = rms_db(voice[np.abs(voice).max(axis=1) > .02]) if (np.abs(voice) > .02).any() else None
        fx_db = rms_db(fx[np.abs(fx) > 1e-4]) if (np.abs(fx) > 1e-4).any() else None
    counts = {k: sum(1 for c in cues if c['kind'] == k) for k in SYNTH}
    report = dict(source_video=str(Path(a.video).resolve()), source_video_sha256=sha(a.video),
                  storyboard=str(Path(a.storyboard).resolve()), output=str(out.resolve()), output_sha256=sha(out),
                  video_stream='copied unchanged', gain_db=a.gain_db, min_gap=a.min_gap, disabled=sorted(disabled),
                  counts=counts, voice_active_rms_db=voice_db, sfx_active_rms_db=fx_db, limiter_scale=min(1.0, .98 / peak),
                  sfx_source='程序合成（add_sfx.py），无外部音频素材', cues=cues,
                  caveat='音效时间来自分镜动作 at；未经人工试听，响度需用户听后反馈调整 --gain-db。')
    out.with_suffix('.sfx_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('output', 'counts', 'voice_active_rms_db', 'sfx_active_rms_db', 'limiter_scale')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
