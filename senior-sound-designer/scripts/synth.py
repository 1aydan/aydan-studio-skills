"""Procedural synthesis (stdlib only) for the parts generative models are bad at: exact UI tones, clean
transients, sub drops, tonal sweeps, risers. Everything returns a mono audio.Audio at 48 kHz.

    sy = load('synth')
    click = sy.click()                                    # 4 ms transient to sharpen a generated impact
    sub = sy.sub_drop(80, 35, 0.6)                        # weight under explosions / heavy hits
    ok = sy.ui_confirm()                                  # two-note rising confirm
    zap = sy.tone((2400, 300, 'exp'), 0.25, 'saw') ; zap = sy.lowpass(zap, (9000, 1200)) ; zap = sy.decay(zap, 0.2)

Frequencies / cutoffs accept a number or a sweep (start, end[, 'lin'|'exp']).
"""
import math
import random
import sys
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio import Audio, WORK_SR  # noqa: E402

TAU = 2 * math.pi


def _sweep(v, n):
    """Number or (a, b[, curve]) -> per-sample value function."""
    if isinstance(v, (int, float)):
        return lambda i: v
    a, b, *c = v
    curve = c[0] if c else 'exp'
    if curve == 'exp' and a > 0 and b > 0:
        r = math.log(b / a)
        return lambda i: a * math.exp(r * i / max(1, n - 1))
    return lambda i: a + (b - a) * i / max(1, n - 1)


def tone(freq, dur, wave='sine', amp=0.8, sr=WORK_SR, phase=0.0):
    n = int(dur * sr)
    f = _sweep(freq, n)
    out = array('f', bytes(4 * n))
    ph = phase
    for i in range(n):
        ph = (ph + f(i) / sr) % 1.0
        if wave == 'sine':
            s = math.sin(TAU * ph)
        elif wave == 'square':
            s = 1.0 if ph < 0.5 else -1.0
        elif wave == 'saw':
            s = 2 * ph - 1
        elif wave == 'tri':
            s = 4 * abs(ph - 0.5) - 1
        else:
            raise ValueError(wave)
        out[i] = s * amp
    return Audio(out, sr, 1)


def fm(freq, dur, ratio=2.0, index=3.0, amp=0.8, sr=WORK_SR):
    """2-operator FM; index may sweep (bright -> dull bells, metallic hits, sci-fi)."""
    n = int(dur * sr)
    f, ix = _sweep(freq, n), _sweep(index, n)
    out = array('f', bytes(4 * n))
    pc = pm = 0.0
    for i in range(n):
        fc = f(i)
        pm = (pm + fc * ratio / sr) % 1.0
        pc = (pc + fc / sr) % 1.0
        out[i] = amp * math.sin(TAU * pc + ix(i) * math.sin(TAU * pm))
    return Audio(out, sr, 1)


def noise(dur, color='white', amp=0.8, sr=WORK_SR, seed=1):
    rng = random.Random(seed)
    n = int(dur * sr)
    out = array('f', bytes(4 * n))
    b = [0.0] * 7
    br = 0.0
    for i in range(n):
        w = rng.uniform(-1, 1)
        if color == 'white':
            s = w
        elif color == 'pink':   # Paul Kellet's filter
            b[0] = 0.99886 * b[0] + w * 0.0555179
            b[1] = 0.99332 * b[1] + w * 0.0750759
            b[2] = 0.96900 * b[2] + w * 0.1538520
            b[3] = 0.86650 * b[3] + w * 0.3104856
            b[4] = 0.55000 * b[4] + w * 0.5329522
            b[5] = -0.7616 * b[5] - w * 0.0168980
            s = (sum(b[:6]) + b[6] + w * 0.5362) * 0.11
            b[6] = w * 0.115926
        else:                   # brown
            br = (br + 0.02 * w) / 1.02
            s = br * 3.5
        out[i] = s * amp
    return Audio(out, sr, 1)


def _onepole(a, cutoff, high=False):
    n = a.frames
    c = _sweep(cutoff, n)
    out = array('f', bytes(4 * n))
    y = 0.0
    for i in range(n):
        g = 1 - math.exp(-TAU * c(i) / a.sr)
        y += g * (a.data[i] - y)
        out[i] = a.data[i] - y if high else y
    return Audio(out, a.sr, 1)


def lowpass(a, cutoff, poles=2):
    for _ in range(poles):
        a = _onepole(a, cutoff)
    return a


def highpass(a, cutoff, poles=2):
    for _ in range(poles):
        a = _onepole(a, cutoff, high=True)
    return a


def envelope(a, attack=0.002, decay=0.1, sustain=0.0, release=0.05, hold=0.0):
    """ADSR over the clip (sustain level 0..1 lasts until release starts at the end)."""
    n, sr = a.frames, a.sr
    na, nd, nh, nr = (int(x * sr) for x in (attack, decay, hold, release))
    out = array('f', a.data)
    for i in range(n):
        if i < na:
            g = i / na
        elif i < na + nh:
            g = 1.0
        elif i < na + nh + nd:
            g = 1 - (1 - sustain) * ((i - na - nh) / nd)
        else:
            g = sustain
        if i >= n - nr:
            g *= (n - i) / nr
        out[i] *= g
    return Audio(out, sr, 1)


def decay(a, t60, attack=0.001):
    """Exponential decay reaching -60 dB at t60 seconds (natural ring-out)."""
    k = math.log(1000) / (t60 * a.sr)
    na = max(1, int(attack * a.sr))
    out = array('f', a.data)
    for i in range(a.frames):
        out[i] *= min(1.0, i / na) * math.exp(-k * i)
    return Audio(out, a.sr, 1)


def add(*clips):
    n = max(c.frames for c in clips)
    out = array('f', bytes(4 * n))
    for c in clips:
        for i in range(c.frames):
            out[i] += c.data[i]
    return Audio(out, clips[0].sr, 1)


# ------------------------------------------------------------ ready-made elements
def click(dur=0.004, bright=8000, seed=3):
    """Short noise transient - layer at t=0 to give a soft generated hit a crisp, readable attack."""
    return decay(highpass(noise(dur + 0.002, seed=seed), 1500, 1), dur / 2.5, 0.0002)


def thump(freq=90, dur=0.18):
    """Pitched-down sine kick for body/weight."""
    return decay(tone((freq * 2.2, freq, 'exp'), dur, 'sine', 0.9), dur * 0.8, 0.001)


def sub_drop(f0=80, f1=35, dur=0.6):
    return decay(tone((f0, f1, 'exp'), dur, 'sine', 0.9), dur, 0.003)


def whoosh(dur=0.5, f0=400, f1=3000, color='pink', seed=2):
    """Band-limited noise with rising cutoff and a swell - add ('pan', ...) moves outside."""
    n = noise(dur, color, seed=seed)
    n = lowpass(highpass(n, (f0 * 0.5, f1 * 0.5)), (f0, f1), 2)
    return envelope(n, attack=dur * 0.55, decay=dur * 0.45, sustain=0.0, release=0.01)


def riser(dur=1.5, f0=200, f1=2400):
    body = tone((f0, f1, 'exp'), dur, 'saw', 0.35)
    air = highpass(noise(dur, 'white', 0.25), (2000, 8000))
    return envelope(add(lowpass(body, (f0 * 4, f1 * 4)), air), attack=dur * 0.95, decay=0.01, release=0.04)


def blip(freq=1200, dur=0.06, wave='sine'):
    return envelope(tone(freq, dur, wave, 0.7), 0.002, dur * 0.8, 0.0, 0.005)


def ui_hover(freq=2200):
    return blip(freq, 0.035)


def ui_confirm(f=880, interval=1.498):          # up a fifth
    a, b = blip(f, 0.07), blip(f * interval, 0.11)
    gap = int(0.06 * a.sr)
    out = array('f', bytes(4 * (gap + b.frames)))
    for i in range(a.frames):
        out[i] += a.data[i]
    for i in range(b.frames):
        out[gap + i] += b.data[i]
    return Audio(out, a.sr, 1)


def ui_back(f=880):
    a = ui_confirm(f * 1.498, 1 / 1.498)
    return a


def ui_error(f=180, dur=0.22):
    buzz = add(tone(f, dur, 'square', 0.25), tone(f * 1.06, dur, 'square', 0.25))   # beating, dissonant
    return envelope(lowpass(buzz, 2500), 0.003, dur * 0.3, 0.6, 0.04)


def zap(dur=0.25, f0=2400, f1=200):
    z = tone((f0, f1, 'exp'), dur, 'saw', 0.6)
    return decay(lowpass(z, (12000, 900)), dur, 0.001)
