"""Audio editing + processing for game sound design. Python stdlib + ffmpeg (no numpy).

Sample-exact edits (trim, fades, layering, loops) run in Python on float32 arrays; DSP (EQ, pitch, dynamics,
reverb, modulation, resampling, encoding) runs in ffmpeg through pipes - no temp files.

    au = load('audio')                      # see SKILL.md "Running scripts"
    a = au.read('src/hit_s7.wav')           # -> Audio (float32, interleaved)
    a = au.trim_silence(a)                  # cut lead/tail silence (keeps the attack intact)
    a = au.fx(a, [('hp', 60), ('eq', 3000, -3, 1.2), ('comp', -18, 4, 2, 80), ('reverb', 0.8, 0.12)])
    a = au.fade(a, 0.002, 0.15)
    a = au.normalize(a, lufs_m=-12, ceiling=-1.0)
    au.write(a, 'export/SFX_Sword_Impact_01.wav', sr=48000, bits=24)

Layering:  au.mix([(attack, 0.0, 0), (body, 0.004, -3), (tail, 0.02, -8)])   # (audio, offset s, gain dB)
Loops:     au.make_loop(a, xfade=1.5)  -> seamless (end flows into start); qa.analyze(..., kind='loop') checks it.
"""
import math
import random
import subprocess
import tempfile
from array import array
from pathlib import Path

FFMPEG = 'ffmpeg'
WORK_SR = 48000


class Audio:
    """Interleaved float32 samples. `data` is array('f'); len(data) == frames * ch."""

    def __init__(self, data, sr=WORK_SR, ch=2):
        self.data = data if isinstance(data, array) else array('f', data)
        self.sr, self.ch = int(sr), int(ch)

    @property
    def frames(self):
        return len(self.data) // self.ch

    @property
    def dur(self):
        return self.frames / self.sr

    def copy(self):
        return Audio(array('f', self.data), self.sr, self.ch)

    def channel(self, i):
        return self.data[i::self.ch]

    def __repr__(self):
        return f'<Audio {self.dur:.3f}s {self.sr}Hz {self.ch}ch>'


def silence(dur, sr=WORK_SR, ch=2):
    return Audio(array('f', bytes(4 * int(round(dur * sr)) * ch)), sr, ch)


# ---------------------------------------------------------------- ffmpeg I/O
def _run(args, inp=None):
    r = subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostdin'] + args,
                       input=inp, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError('ffmpeg failed: ' + r.stderr.decode(errors='replace')[-1500:])
    return r.stdout


def _raw_in(a):
    return ['-f', 'f32le', '-ar', str(a.sr), '-ac', str(a.ch), '-i', 'pipe:0']


def _from_bytes(b, sr, ch):
    d = array('f')
    d.frombytes(b[:len(b) - len(b) % (4 * ch)])
    return Audio(d, sr, ch)


def read(path, sr=WORK_SR, ch=2):
    """Decode any audio file to float32 at `sr`/`ch` (None keeps the file's own)."""
    if sr is None or ch is None:
        p = probe(path)
        sr, ch = sr or p['sr'], ch or p['ch']
    b = _run(['-i', str(path), '-f', 'f32le', '-ar', str(sr), '-ac', str(ch),
              '-af', 'aresample=resampler=soxr:precision=28', 'pipe:1'])
    return _from_bytes(b, sr, ch)


def write(a, path, sr=None, bits=24, ch=None, quality=6):
    """Write .wav (bits 16/24/32f) or .ogg (Vorbis, quality 0-10). Resamples with soxr when sr differs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    args = _raw_in(a) + ['-y']
    filt = []
    if sr and sr != a.sr:
        filt.append('aresample=resampler=soxr:precision=28:dither_method=triangular')
        args += ['-ar', str(sr)]
    if ch and ch != a.ch:
        args += ['-ac', str(ch)]
    if filt:
        args += ['-af', ','.join(filt)]
    ext = path.suffix.lower()
    if ext == '.wav':
        args += ['-c:a', {16: 'pcm_s16le', 24: 'pcm_s24le', 32: 'pcm_f32le'}[bits], '-rf64', 'never']
    elif ext == '.ogg':
        args += ['-c:a', 'libvorbis', '-q:a', str(quality)]
    elif ext == '.flac':
        args += ['-c:a', 'flac']
    args += ['-map_metadata', '-1', str(path)]
    _run(args, a.data.tobytes())
    return str(path)


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
                          'stream=sample_rate,channels,codec_name,bits_per_sample:format=duration',
                          '-of', 'default=nw=1', str(path)], capture_output=True, text=True).stdout
    kv = dict(l.split('=', 1) for l in out.split() if '=' in l)
    return {'sr': int(kv.get('sample_rate', 0)), 'ch': int(kv.get('channels', 0)),
            'codec': kv.get('codec_name'), 'bits': int(kv.get('bits_per_sample') or 0),
            'dur': float(kv.get('duration', 0))}


# ---------------------------------------------------------------- ffmpeg DSP chain
def _db(x):
    return 10 ** (x / 20)


def _op(op, sr):
    """One chain op -> (ffmpeg filter string, tail seconds to pad before it)."""
    name, *p = op
    if name == 'hp':
        return f'highpass=f={p[0]}:p=2' + (f',highpass=f={p[0]}:p=2' if len(p) > 1 and p[1] >= 4 else ''), 0
    if name == 'lp':
        return f'lowpass=f={p[0]}:p=2' + (f',lowpass=f={p[0]}:p=2' if len(p) > 1 and p[1] >= 4 else ''), 0
    if name == 'bp':                                # center, Q
        return f'bandpass=f={p[0]}:t=q:w={p[1] if len(p) > 1 else 1}', 0
    if name == 'notch':
        return f'bandreject=f={p[0]}:t=q:w={p[1] if len(p) > 1 else 4}', 0
    if name == 'eq':                                # freq, gain dB, Q
        return f'equalizer=f={p[0]}:t=q:w={p[2] if len(p) > 2 else 1}:g={p[1]}', 0
    if name == 'lowshelf':
        return f'lowshelf=f={p[0]}:g={p[1]}', 0
    if name == 'highshelf':
        return f'highshelf=f={p[0]}:g={p[1]}', 0
    if name == 'gain':
        return f'volume={p[0]}dB', 0
    if name == 'pitch':                             # semitones, duration kept (rubberband)
        return f'rubberband=pitch={2 ** (p[0] / 12):.6f}:transients=crisp:formant=shifted', 0
    if name == 'varispeed':                         # semitones, tape-style (duration changes)
        return f'asetrate={sr * 2 ** (p[0] / 12):.3f},aresample={sr}:resampler=soxr', 0
    if name == 'stretch':                           # duration ratio (2 = twice as long), pitch kept
        return f'rubberband=tempo={1 / p[0]:.6f}:transients=crisp', 0
    if name == 'comp':                              # threshold dB, ratio, attack ms, release ms, makeup dB
        th, ra = p[0], p[1] if len(p) > 1 else 4
        at, re_, mk = (p[2] if len(p) > 2 else 5), (p[3] if len(p) > 3 else 80), (p[4] if len(p) > 4 else 0)
        return (f'acompressor=threshold={_db(th):.6f}:ratio={ra}:attack={at}:release={re_}:'
                f'makeup={_db(mk):.4f}:knee=2'), 0
    if name == 'limit':                             # ceiling dBFS
        return f'alimiter=limit={_db(p[0] if p else -1):.6f}:attack=1:release=40:level=0:latency=1', 0
    if name == 'drive':                             # dB into a tanh soft clipper, level-compensated
        d = p[0] if p else 6
        return f'volume={d}dB,asoftclip=type=tanh:oversample=4,volume={-d * 0.75:.2f}dB', 0
    if name == 'crush':                             # bits, sample-hold factor
        return f'acrusher=bits={p[0]}:samples={p[1] if len(p) > 1 else 1}:mode=lin:aa=0.5', 0
    if name == 'delay':                             # ms, feedback 0..0.9, mix 0..1
        ms, fb, mix = p[0], (p[1] if len(p) > 1 else 0.3), (p[2] if len(p) > 2 else 0.3)
        taps = [ms * (i + 1) for i in range(6)]
        decs = [mix * fb ** i for i in range(6)]
        return (f'aecho=1:1:{"|".join(f"{t:g}" for t in taps)}:{"|".join(f"{d:.4f}" for d in decs)}',
                ms * 6 / 1000 + 0.05)
    if name == 'chorus':
        return 'chorus=0.6:0.9:50|60:0.4|0.32:0.25|0.4:2|2.3', 0
    if name == 'flanger':
        return f'flanger=delay={p[0] if p else 2}:depth={p[1] if len(p) > 1 else 3}:speed={p[2] if len(p) > 2 else 0.5}', 0
    if name == 'phaser':
        return f'aphaser=speed={p[0] if p else 0.5}:decay={p[1] if len(p) > 1 else 0.5}', 0
    if name == 'tremolo':                           # Hz, depth 0..1
        return f'tremolo=f={p[0]}:d={p[1] if len(p) > 1 else 0.5}', 0
    if name == 'vibrato':                           # Hz, depth 0..1
        return f'vibrato=f={p[0]}:d={p[1] if len(p) > 1 else 0.3}', 0
    if name == 'freqshift':                         # Hz (inharmonic, metallic / alien)
        return f'afreqshift=shift={p[0]}', 0
    if name == 'ringmod':                           # Hz, mix
        mix = p[1] if len(p) > 1 else 1.0
        return f"aeval='val(ch)*(1-{mix})+val(ch)*{mix}*sin(2*PI*{p[0]}*t)':c=same", 0
    if name == 'reverse':
        return 'areverse', 0
    if name == 'mono':
        return 'pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1', 0
    if name == 'width':                             # 1 = unchanged, 0 = mono, 1.5 = wider
        return f'stereotools=slev={p[0]:.3f}:mlev=1', 0
    if name == 'pan':                               # -1 left .. 1 right (equal power)
        l, r = math.cos((p[0] + 1) * math.pi / 4), math.sin((p[0] + 1) * math.pi / 4)
        return f'pan=stereo|c0={l * 1.4142:.4f}*c0|c1={r * 1.4142:.4f}*c1', 0
    if name == 'denoise':                           # strength 0.00001..10 (try 0.002-0.01)
        return f'anlmdn=s={p[0] if p else 0.005}', 0
    if name == 'declick':
        return 'adeclick', 0
    if name == 'dcblock':
        return 'highpass=f=10:p=1', 0
    if name == 'exciter':                           # amount, freq
        return f'aexciter=amount={p[0] if p else 1.5}:freq={p[1] if len(p) > 1 else 6000}', 0
    if name == 'subboost':                          # dB at cutoff Hz
        return f'asubboost=boost={p[0] if p else 2}:cutoff={p[1] if len(p) > 1 else 100}', 0
    if name == 'raw':                               # any ffmpeg -af string, optional tail seconds
        return p[0], (p[1] if len(p) > 1 else 0)
    raise ValueError(f'unknown fx op {name!r}')


def fx(a, chain):
    """Apply a list of ops (see _op) in order. ('reverb', decay_s, mix, predelay_ms, damp_hz, width) uses a
    generated impulse response; reverbs and delays extend the clip by their tail."""
    out = a
    group, tail = [], 0.0

    def flush():
        nonlocal out, group, tail
        if not group:
            return
        filt = (f'apad=pad_dur={tail:.3f},' if tail else '') + ','.join(group)
        out = _from_bytes(_run(_raw_in(out) + ['-af', filt, '-f', 'f32le', '-ar', str(out.sr),
                                                '-ac', str(out.ch), 'pipe:1'], out.data.tobytes()), out.sr, out.ch)
        group, tail = [], 0.0

    for op in chain:
        if op[0] == 'reverb':
            flush()
            out = reverb(out, *op[1:])
        else:
            f, t = _op(op, out.sr)
            group.append(f)
            tail += t
    flush()
    return out


def impulse(decay=1.2, predelay=0.01, damp=7000, width=1.0, sr=WORK_SR, seed=1):
    """Synthetic stereo room IR: exponentially decaying noise, darker as it decays."""
    rng = random.Random(seed)
    n = int((predelay + decay * 1.1) * sr)
    pd = int(predelay * sr)
    k = math.log(1000) / (decay * sr)               # -60 dB at `decay` seconds
    d = array('f', bytes(4 * n * 2))
    lpL = lpR = 0.0
    for i in range(pd, n):
        t = i - pd
        env = math.exp(-k * t)
        # cutoff falls from damp to damp/4 over the decay
        c = damp * (1 - 0.75 * min(1.0, t / (decay * sr)))
        g = 1 - math.exp(-2 * math.pi * c / sr)
        nl, nr = rng.uniform(-1, 1), rng.uniform(-1, 1)
        nr = nl * (1 - width) + nr * width
        lpL += g * (nl - lpL)
        lpR += g * (nr - lpR)
        d[2 * i], d[2 * i + 1] = lpL * env, lpR * env
    return Audio(d, sr, 2)


def reverb(a, decay=1.2, mix=0.25, predelay=10, damp=7000, width=1.0):
    """Convolution reverb with a generated IR. mix = wet share (0..1); clip grows by the decay."""
    ir = impulse(decay, predelay / 1000, damp, width, a.sr)
    tmp = Path(tempfile.gettempdir()) / 'sound_designer_ir' / f'ir_{decay:g}_{predelay:g}_{damp:g}_{width:g}_{a.sr}.wav'
    if not tmp.exists():
        write(ir, tmp, bits=32)
    src = a if a.ch == 2 else Audio(array('f', [s for s in a.data for _ in (0, 1)]), a.sr, 2)
    fc = (f'[0]apad=pad_dur={decay * 1.1 + predelay / 1000:.3f},asplit[d][w];'
          f'[w][1]afir=dry=1:wet=1:irnorm=1[wet];'
          f"[d][wet]amix=inputs=2:weights='{1 - mix:.4f} {mix:.4f}':normalize=0[o]")
    b = _run(_raw_in(src) + ['-i', str(tmp), '-filter_complex', fc, '-map', '[o]', '-f', 'f32le',
                             '-ar', str(a.sr), '-ac', '2', 'pipe:1'], src.data.tobytes())
    return _from_bytes(b, a.sr, 2)


# ---------------------------------------------------------------- sample-exact edits
def peak(a):
    return max((abs(x) for x in a.data), default=0.0)


def gain(a, db):
    g = _db(db)
    return Audio(array('f', (x * g for x in a.data)), a.sr, a.ch)


def env_frames(a, win=0.002):
    """Per-window peak envelope (linear) over all channels."""
    w = max(1, int(win * a.sr)) * a.ch
    d = a.data
    return [max(map(abs, d[i:i + w])) for i in range(0, len(d), w)], win


def trim_silence(a, head_db=-40, tail_db=-60, pre=0.002, post=0.03, keep_head=False, keep_tail=False):
    """Cut pre-roll before the onset (first window within head_db of the peak - generated audio often has
    a noise bed before the hit) and dead air after the decay falls below tail_db. pre/post keep a margin
    so the attack is never chopped; fade() afterwards removes edge clicks."""
    env, win = env_frames(a)
    top = max(env, default=0) or 1.0
    on = [i for i, v in enumerate(env) if v > top * _db(head_db)]
    alive = [i for i, v in enumerate(env) if v > top * _db(tail_db)]
    if not on:
        return a.copy()
    s = 0 if keep_head else max(0, int((on[0] * win - pre) * a.sr))
    e = a.frames if keep_tail else min(a.frames, int(((alive[-1] + 1) * win + post) * a.sr))
    return crop(a, s / a.sr, e / a.sr)


def crop(a, start=0.0, end=None):
    s = int(round(start * a.sr))
    e = a.frames if end is None else min(a.frames, int(round(end * a.sr)))
    return Audio(a.data[s * a.ch:e * a.ch], a.sr, a.ch)


def pad(a, start=0.0, end=0.0):
    z = lambda t: array('f', bytes(4 * int(round(t * a.sr)) * a.ch))  # noqa: E731
    return Audio(z(start) + a.data + z(end), a.sr, a.ch)


def fade(a, fin=0.0, fout=0.0, curve='exp'):
    """Sample-exact fades. curve: 'lin' | 'exp' (natural decay) | 'cos' (equal power)."""
    d = array('f', a.data)
    shape = {'lin': lambda x: x, 'exp': lambda x: x * x * x, 'cos': lambda x: math.sin(x * math.pi / 2)}[curve]
    n_in, n_out = int(fin * a.sr), int(fout * a.sr)
    for f in range(min(n_in, a.frames)):
        g = shape(f / n_in) if curve != 'exp' else (f / n_in) ** 0.5   # fast-in for attacks
        for c in range(a.ch):
            d[f * a.ch + c] *= g
    for k in range(min(n_out, a.frames)):
        f = a.frames - 1 - k
        g = shape(k / n_out)
        for c in range(a.ch):
            d[f * a.ch + c] *= g
    return Audio(d, a.sr, a.ch)


def conform(a, sr=None, ch=None):
    """Match sample rate / channel count (mono<->stereo) for mixing."""
    if sr and sr != a.sr:
        a = _from_bytes(_run(_raw_in(a) + ['-af', 'aresample=resampler=soxr', '-f', 'f32le', '-ar', str(sr),
                                           '-ac', str(a.ch), 'pipe:1'], a.data.tobytes()), sr, a.ch)
    if ch and ch != a.ch:
        if a.ch == 1 and ch == 2:
            a = Audio(array('f', [s for s in a.data for _ in (0, 1)]), a.sr, 2)
        elif a.ch == 2 and ch == 1:
            a = Audio(array('f', [(a.data[i] + a.data[i + 1]) * 0.5 for i in range(0, len(a.data), 2)]), a.sr, 1)
    return a


def mix(layers, length=None, sr=None, ch=2):
    """layers: [(Audio, offset_s, gain_db)] -> one Audio. Layers are conformed to the first layer's rate."""
    sr = sr or layers[0][0].sr
    ls = [(conform(l, sr, ch), off, g) for l, off, g in layers]
    n = max(int(round(off * sr)) + l.frames for l, off, _ in ls)
    if length:
        n = int(round(length * sr))
    out = array('f', bytes(4 * n * ch))
    for l, off, g in ls:
        o, k = int(round(off * sr)) * ch, _db(g)
        src = l.data
        m = min(len(src), len(out) - o)
        for i in range(max(0, m)):
            out[o + i] += src[i] * k
    return Audio(out, sr, ch)


def concat(clips, gap=0.0):
    out = array('f')
    for i, c in enumerate(clips):
        out += c.data
        if gap and i < len(clips) - 1:
            out += array('f', bytes(4 * int(gap * c.sr) * c.ch))
    return Audio(out, clips[0].sr, clips[0].ch)


def make_loop(a, xfade=1.0):
    """Seamless loop: the last `xfade` seconds are crossfaded (equal power) into the head and removed.
    Result length = dur - xfade; sample N-1 flows into sample 0 with no seam."""
    n = int(xfade * a.sr)
    if n * 2 >= a.frames:
        raise ValueError('xfade too long for clip')
    ch, d = a.ch, a.data
    body = array('f', d[n * ch:(a.frames - n) * ch])
    head = array('f', bytes(4 * n * ch))
    tail0 = (a.frames - n) * ch
    for f in range(n):
        x = f / n
        gi, go = math.sin(x * math.pi / 2), math.cos(x * math.pi / 2)
        for c in range(ch):
            head[f * ch + c] = d[f * ch + c] * gi + d[tail0 + f * ch + c] * go
    # body ends on d[L-n-1]; the head starts on d[L-n] (fully tail-weighted) -> continuous wrap
    return Audio(head + body, a.sr, ch)


def reverse(a):
    ch = a.ch
    frames = [a.data[i * ch:(i + 1) * ch] for i in range(a.frames)]
    out = array('f')
    for fr in reversed(frames):
        out += fr
    return Audio(out, a.sr, ch)


# ---------------------------------------------------------------- loudness
def loudness(a):
    """EBU R128 via ffmpeg: integrated LUFS, max momentary (400 ms), max short-term (3 s), true peak dBTP."""
    r = subprocess.run([FFMPEG, '-hide_banner', '-nostats', '-nostdin'] + _raw_in(a)
                       + ['-af', 'apad=pad_dur=0.4,ebur128=peak=true', '-f', 'null', '-'],
                       input=a.data.tobytes(), capture_output=True)
    log = r.stderr.decode(errors='replace')
    mmax = smax = -120.0
    for line in log.splitlines():
        if ' M:' in line and ' S:' in line:
            try:
                m = float(line.split(' M:')[1].split()[0])
                s = float(line.split(' S:')[1].split()[0])
                mmax, smax = max(mmax, m), max(smax, s)
            except (ValueError, IndexError):
                pass
    summ = log[log.rfind('Summary:'):]

    def grab(key):
        try:
            return float(summ.split(key)[1].split()[0])
        except (IndexError, ValueError):
            return None
    return {'lufs_i': grab('I:'), 'lufs_m_max': round(mmax, 1), 'lufs_s_max': round(smax, 1),
            'lra': grab('LRA:'), 'true_peak': grab('Peak:')}


def tp_limit(a, ceiling=-1.0):
    """True-peak limiter: limit at 4x oversampling (catches inter-sample peaks), then trim any residue."""
    up = a.sr * 4
    out = _from_bytes(_run(_raw_in(a) + ['-af', f'aresample={up}:resampler=soxr,alimiter=limit={_db(ceiling - 0.2):.6f}:'
                                         f'attack=0.5:release=30:level=0:latency=1,aresample={a.sr}:resampler=soxr',
                                         '-f', 'f32le', '-ar', str(a.sr), '-ac', str(a.ch), 'pipe:1'],
                           a.data.tobytes()), a.sr, a.ch)
    for _ in range(3):
        tp = loudness(out)['true_peak']
        if tp is None or tp <= ceiling:
            break
        out = gain(out, ceiling - tp - 0.05)
    return out


def normalize(a, lufs_m=None, lufs_i=None, peak_db=None, ceiling=-1.0, max_gr=6.0):
    """Gain to ONE target, then true-peak-limit to `ceiling` dBTP.
    lufs_m: max momentary loudness (one-shots - consistent perceived punch across a set)
    lufs_i: integrated (loops, ambiences, music, VO)
    peak_db: sample peak (UI ticks, sources for layering).
    The limiter never takes more than `max_gr` dB: very transient sounds then land under a loudness target
    ("peak-bound") instead of having their attack crushed - qa.analyze reports that as info."""
    if peak_db is not None:
        p = peak(a) or 1e-9
        return tp_limit(gain(a, peak_db - 20 * math.log10(p)), ceiling)
    L = loudness(a)
    cur = L['lufs_m_max'] if lufs_m is not None else L['lufs_i']
    tgt = lufs_m if lufs_m is not None else lufs_i
    if cur is None or cur < -100:
        return a.copy()
    g = tgt - cur
    tp = (L['true_peak'] if L['true_peak'] is not None else 20 * math.log10(peak(a) or 1e-9)) + g
    if tp <= ceiling:          # no limiter at all (keeps loops sample-exact at the wrap point)
        return gain(a, g)
    if tp - ceiling > max_gr:
        g -= (tp - ceiling) - max_gr
    return tp_limit(gain(a, g), ceiling)
