"""Validate and review sound files: numbers first, then pictures, then ears.

    qa = load('qa')
    r = qa.analyze('export/SFX_Hit_01.wav', kind='oneshot', target_lufs_m=-12)   # dict + r['issues']
    qa.review_png('export/SFX_Hit_01.wav', 'review/SFX_Hit_01.png')             # waveform + spectrogram
    qa.sheet(paths, 'review/sheet.png')                                          # all takes stacked, labelled
    qa.grid([('impact', takes), ('swing', takes2)], 'takes/_grid.png')            # pick sheet: rows x takes
    qa.audition(paths, 'review/audition.html', title='Sword impacts', notes={...}) # play + compare in a browser

CLI:  python qa.py <files or folder> [--kind oneshot|loop|ui|ambience|music] [--sheet out.png] [--html out.html]

kind changes the checks: 'loop' requires a seamless wrap and no fades; 'oneshot'/'ui' require a fast attack
start, a decayed tail and no long silences.
"""
import html
import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio as au  # noqa: E402

DB = lambda x: 20 * math.log10(max(x, 1e-12))  # noqa: E731
BANDS = [('sub', 20, 60), ('low', 60, 250), ('lowmid', 250, 1000), ('mid', 1000, 4000),
         ('presence', 4000, 8000), ('air', 8000, 20000)]


def _bands(a):
    """Relative energy (dB, loudest band = 0) per band - frequency balance at a glance."""
    out = {}
    for name, lo, hi in BANDS:
        filt = f'highpass=f={lo}:p=2,highpass=f={lo}:p=2,lowpass=f={hi}:p=2,lowpass=f={hi}:p=2,astats=metadata=0'
        r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-nostdin'] + au._raw_in(a)
                           + ['-af', filt, '-f', 'null', '-'], input=a.data.tobytes(), capture_output=True)
        log = r.stderr.decode(errors='replace')
        seg = log[log.rfind('Overall'):]
        try:
            out[name] = float(seg.split('RMS level dB:')[1].split()[0])
        except (IndexError, ValueError):
            out[name] = -120.0
    top = max(out.values())
    return {k: round(v - top, 1) for k, v in out.items()}


def analyze(path, kind='oneshot', target_lufs_m=None, target_lufs_i=None, ceiling=-1.0, bands=True):
    p = au.probe(path)
    a = au.read(path, sr=None, ch=None)
    d, ch, n = a.data, a.ch, a.frames
    pk = au.peak(a)
    rms = math.sqrt(sum(x * x for x in d) / max(1, len(d)))
    dc = [sum(d[c::ch]) / max(1, n) for c in range(ch)]
    clipped = sum(1 for x in d if abs(x) >= 0.999)
    env, win = au.env_frames(a, 0.001)
    on = [i for i, v in enumerate(env) if v > pk * 10 ** (-35 / 20)]      # onset: within 35 dB of peak
    alive = [i for i, v in enumerate(env) if v > pk * 10 ** (-55 / 20)]   # still audible
    lead = (on[0] * win) if on else a.dur
    tail = ((len(env) - 1 - alive[-1]) * win) if alive else a.dur
    body = [i for i, v in enumerate(env) if v > pk * 10 ** (-30 / 20)]     # the audible event
    body_ms = round((body[-1] - on[0]) * win * 1000, 1) if on and body else 0.0
    attack_ms = None
    if on:   # onset -> 90% of peak
        hit = next((i for i, v in enumerate(env) if v >= 0.9 * pk), on[0])
        attack_ms = round((hit - on[0]) * win * 1000, 1)
    first = max(abs(d[c]) for c in range(ch))
    last = max(abs(d[(n - 1) * ch + c]) for c in range(ch))
    # loop seam: jump across the wrap vs the typical sample-to-sample step
    steps = [abs(d[i + ch] - d[i]) for i in range(0, min(len(d) - ch, 48000 * ch), ch)]
    typ = sorted(steps)[int(len(steps) * 0.99)] if steps else 0
    wrap = max(abs(d[c] - d[(n - 1) * ch + c]) for c in range(ch))
    L = au.loudness(a)
    r = {'file': str(path), 'dur': round(a.dur, 3), 'sr': p['sr'], 'ch': ch, 'bits': p['bits'],
         'codec': p['codec'], 'peak_db': round(DB(pk), 2), 'true_peak': L['true_peak'],
         'rms_db': round(DB(rms), 1), 'lufs_i': L['lufs_i'], 'lufs_m_max': L['lufs_m_max'],
         'lufs_s_max': L['lufs_s_max'], 'lra': L['lra'], 'dc': [round(x, 5) for x in dc], 'clipped': clipped,
         'lead_ms': round(lead * 1000, 1), 'body_ms': body_ms, 'tail_ms': round(tail * 1000, 1), 'attack_ms': attack_ms,
         'edge_db': [round(DB(first), 1), round(DB(last), 1)], 'wrap_jump': round(wrap / (typ or 1e-9), 2)}
    if bands:
        r['bands'] = _bands(a)
    issues = []
    add = lambda sev, msg: issues.append({'sev': sev, 'msg': msg})  # noqa: E731
    if clipped:
        add('error', f'{clipped} clipped samples')
    if r['true_peak'] is not None and r['true_peak'] > ceiling + 0.05:
        add('error', f"true peak {r['true_peak']} dBTP > ceiling {ceiling}")
    if max(abs(x) for x in dc) > 0.005:
        add('warn', f'DC offset {r["dc"]} (add ("dcblock",))')
    if pk < 1e-4:
        add('error', 'silent file')
    if kind == 'loop' or kind == 'ambience':
        if r['wrap_jump'] > 4:
            add('error', f'loop seam: wrap jump {r["wrap_jump"]}x the typical step (use make_loop)')
        if lead > 0.05 or tail > 0.05:
            add('warn', f'loop has silence at edges (lead {r["lead_ms"]} ms, tail {r["tail_ms"]} ms)')
    else:
        if r['edge_db'][0] > -60:
            add('warn', f'starts at {r["edge_db"][0]} dBFS - edge click risk (fade in 1-3 ms)')
        if r['edge_db'][1] > -60:
            add('error' if r['edge_db'][1] > -40 else 'warn',
                f'ends at {r["edge_db"][1]} dBFS - cut-off tail / click (fade out)')
        if lead > (0.005 if kind == 'ui' else 0.015):
            add('warn', f'{r["lead_ms"]} ms of silence before the sound - feels laggy (trim_silence)')
        if tail > 0.25:
            add('warn', f'{r["tail_ms"]} ms of dead air at the end (trim_silence)')
        if kind == 'ui' and a.dur > 1.0:
            add('warn', f'UI sound is {a.dur:.2f}s - UI feedback usually 0.05-0.6 s')
    peak_bound = r['true_peak'] is not None and r['true_peak'] >= ceiling - 0.8
    for tgt, key, label in ((target_lufs_m, 'lufs_m_max', 'momentary max'), (target_lufs_i, 'lufs_i', 'integrated')):
        if tgt is None or L[key] is None or abs(L[key] - tgt) <= 1.0:
            continue
        if L[key] < tgt and peak_bound:
            add('info', f'peak-bound: {label} {L[key]} LUFS vs target {tgt} (transient hits the ceiling first'
                        + (', and clips < 0.4 s read low in a 400 ms window' if a.dur < 0.4 else '') + ')')
        else:
            add('warn', f'{label} {L[key]} LUFS vs target {tgt}')
    if bands and kind not in ('loop', 'ambience', 'music'):
        b = r['bands']
        if b['presence'] > -1 and b['mid'] > -2 and b['low'] < -12:
            add('info', 'bright/thin: little low end, strong 4-8 kHz (harsh in a busy mix?)')
        if b['sub'] > -3 and kind == 'ui':
            add('warn', 'UI sound with strong sub energy - muddies the mix, high-pass ~150 Hz')
    r['issues'] = issues
    return r


def review_png(path, out, width=1000, title=None):
    """Waveform (top) + log-frequency spectrogram (bottom) with a label - LOOK at it after every pass."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    label = (title or Path(path).name).replace('\\', '/').replace(':', r'\:').replace("'", '')
    font = 'C\\:/Windows/Fonts/consola.ttf' if os.name == 'nt' else 'DejaVuSansMono.ttf'
    fc = (f'[0:a]asplit[a][b];'
          f'[a]showwavespic=s={width}x140:split_channels=0:colors=0x3fb6ff:scale=sqrt,'
          f"drawtext=fontfile='{font}':text='{label}':x=8:y=6:fontsize=16:fontcolor=white:box=1:boxcolor=0x000000AA,format=rgb24[w];"
          f'[b]showspectrumpic=s={width}x260:legend=0:fscale=log:scale=log:color=magma:drange=96,format=rgb24[s];'
          f'[w][s]vstack,format=rgb24[o]')
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(path), '-filter_complex', fc,
                    '-map', '[o]', '-frames:v', '1', '-update', '1', str(out)], check=True)
    return str(out)


def sheet(paths, out, width=1000):
    """Stack review images of several files (variations, A/B passes) into one PNG."""
    out = Path(out)
    tmp = out.parent / '_sheet_tmp'
    imgs = [review_png(p, tmp / f'{i:02d}.png', width) for i, p in enumerate(paths)]
    args = sum((['-i', i] for i in imgs), [])
    fc = ''.join(f'[{i}:v]' for i in range(len(imgs))) + f'vstack=inputs={len(imgs)}[o]' if len(imgs) > 1 else '[0:v]null[o]'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y'] + args +
                   ['-filter_complex', fc, '-map', '[o]', '-frames:v', '1', '-update', '1', str(out)], check=True)
    for i in imgs:
        os.remove(i)
    tmp.rmdir()
    return str(out)


def grid(rows, out, w=300):
    """Pick sheet: rows = [(row_label, [paths])] -> one PNG, one row per sound, one column per take.
    Read it to compare takes side by side (onset, envelope, decay, noise beds, unwanted events)."""
    out = Path(out)
    tmp = out.parent / '_grid_tmp'
    cols = max(len(ps) for _, ps in rows)
    ims = []
    for label, ps in rows:
        for j in range(cols):
            p = Path(ps[min(j, len(ps) - 1)])
            ims.append(review_png(p, tmp / f'{len(ims):03d}.png', w, f'{label} {p.parent.name}/{p.stem}'))
    lay = '|'.join(f'{(i % cols) * w}_{(i // cols) * 400}' for i in range(len(ims)))
    fc = (''.join(f'[{i}:v]' for i in range(len(ims))) + f'xstack=inputs={len(ims)}:layout={lay}[o]'
          if len(ims) > 1 else '[0:v]null[o]')
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y'] + sum((['-i', i] for i in ims), []) +
                   ['-filter_complex', fc, '-map', '[o]', '-frames:v', '1', '-update', '1', str(out)], check=True)
    for i in ims:
        os.remove(i)
    tmp.rmdir()
    return str(out)


def audition(paths, out, title='Audition', notes=None, kind='oneshot', results=None, images=True):
    """Self-contained review page next to the files: player, waveform/spectrogram, metrics, issues.
    Relative links, so the folder can be zipped and sent. Keyboard: 1-9 play a take, space = stop."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    notes = notes or {}
    results = results or [analyze(p, kind=kind) for p in paths]
    rows = []
    for i, (p, r) in enumerate(zip(paths, results)):
        p = Path(p)
        rel = os.path.relpath(p, out.parent).replace('\\', '/')
        img = ''
        if images:
            ip = out.parent / 'img' / (p.stem + '.png')
            review_png(p, ip, 900, p.name)
            img = f'<img src="{os.path.relpath(ip, out.parent).replace(chr(92), "/")}" alt="">'
        iss = ''.join(f'<li class="{x["sev"]}">{html.escape(x["msg"])}</li>' for x in r['issues']) or \
            '<li class="ok">no issues</li>'
        loopish = kind in ('loop', 'ambience', 'music') or '_loop' in p.stem.lower()
        lufs = r['lufs_i'] if loopish else r['lufs_m_max']
        rows.append(f'''<section><h2><kbd>{i + 1}</kbd> {html.escape(p.name)}</h2>
<p class="note">{html.escape(notes.get(p.name, ''))}</p>
<audio controls preload="auto" src="{rel}" {'loop' if loopish else ''}></audio>
<table><tr><td>{r['dur']} s</td><td>{r['sr']} Hz · {r['ch']} ch · {r['bits'] or r['codec']}</td>
<td>peak {r['peak_db']} dB · TP {r['true_peak']} dBTP</td><td>{'LUFS-I' if loopish else 'LUFS-M max'} {lufs}</td>
<td>attack {r['attack_ms']} ms · lead {r['lead_ms']} ms</td></tr></table>
{img}<ul>{iss}</ul></section>''')
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root{{--bg:#111418;--fg:#e6e9ee;--mut:#9aa4b1;--card:#1a1f26;--line:#2a313b;--err:#ff6b6b;--warn:#f5b84a;--ok:#5fd38d}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}}
main{{max-width:960px;margin:auto}} h1{{font-size:20px}} h2{{font-size:15px;margin:0 0 6px}}
section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin:12px 0}}
audio{{width:100%}} img{{width:100%;border-radius:6px;margin-top:8px}} .note{{color:var(--mut);margin:0 0 6px}}
table{{width:100%;color:var(--mut);font-size:12px;border-collapse:collapse}} td{{padding:4px 6px 0 0}}
ul{{margin:8px 0 0;padding-left:18px}} .error{{color:var(--err)}} .warn{{color:var(--warn)}} .ok{{color:var(--ok)}} .info{{color:var(--mut)}}
kbd{{background:var(--line);border-radius:4px;padding:0 6px;font-size:12px}}
</style></head><body><main><h1>{html.escape(title)}</h1>
<p class="note">Keys 1-9 play a take, space stops. Listen on headphones AND small speakers; A/B at matched level.</p>
{''.join(rows)}</main><script>
const a=[...document.querySelectorAll('audio')];
a.forEach(x=>x.addEventListener('play',()=>a.forEach(y=>{{if(y!==x)y.pause()}})));
addEventListener('keydown',e=>{{const i=+e.key-1;if(i>=0&&i<a.length){{a[i].currentTime=0;a[i].play()}}
if(e.key===' '){{e.preventDefault();a.forEach(y=>y.pause())}}}});
</script></body></html>'''
    out.write_text(page, encoding='utf-8')
    return str(out)


def _collect(args):
    files = []
    for x in args:
        p = Path(x)
        files += sorted(p.glob('*.wav')) + sorted(p.glob('*.ogg')) if p.is_dir() else [p]
    return files


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+')
    ap.add_argument('--kind', default='oneshot')
    ap.add_argument('--target-lufs-m', type=float)
    ap.add_argument('--target-lufs-i', type=float)
    ap.add_argument('--sheet')
    ap.add_argument('--html')
    ap.add_argument('--title', default='Audition')
    a = ap.parse_args()
    fs = _collect(a.files)
    res = [analyze(f, a.kind, a.target_lufs_m, a.target_lufs_i) for f in fs]
    for r in res:
        print(json.dumps(r))
    if a.sheet:
        print('sheet:', sheet(fs, a.sheet))
    if a.html:
        print('audition:', audition(fs, a.html, a.title, kind=a.kind, results=res))
