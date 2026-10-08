"""Stable Audio 3 generation through the sa3.cpp runtime (local GPU, no PyTorch, no server needed).

Library:   sa3 = load('sa3')  (see SKILL.md "Running scripts")  ->  sa3.generate(...), sa3.batch(...)
CLI:       python sa3.py status
           python sa3.py gen --model sfx --prompt "..." --duration 1.2 --out C:/x/hit.wav [--seeds 1-4]

Runtime location (first hit wins): env SA3_HOME, <skill>/local.json {"sa3_home": "..."}, ~/.sa3.
SA3_HOME holds bin/ (sa3-generate.exe + dlls) and models/ (GGUF sets). Install with setup_sa3.py.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent

# Short names the skill uses -> sa3.cpp variant names.
MODELS = {'sfx': 'small-sfx', 'small-sfx': 'small-sfx', 'medium': 'medium',
          'music': 'small-music', 'small-music': 'small-music'}
DIT_RE = re.compile(r'stable-audio-3-(?P<v>[a-z-]+)-dit-[\d.]+B-v[\d.]+-(?P<e>[A-Z0-9_]+)\.gguf$')
SAME_RE = re.compile(r'stable-audio-3-(?P<v>[a-z-]+)-same-[sl]-v[\d.]+-(?P<e>[A-Z0-9_]+)\.gguf$')
T5_RE = re.compile(r't5gemma-.*-encoder-.*-(?P<e>[A-Z0-9_]+)\.gguf$')
# Preference when several encodings of a component are installed (quality first).
PREF = ['F16', 'Q8_0', 'F32', 'Q5_K_M', 'Q4_K_M']
AE_PREF = ['F32', 'F16', 'Q8_0', 'Q5_K_M', 'Q4_K_M']


def home():
    env = os.environ.get('SA3_HOME')
    if env:
        return Path(env)
    cfg = SKILL / 'local.json'
    if cfg.exists():
        return Path(json.loads(cfg.read_text(encoding='utf-8'))['sa3_home'])
    return Path.home() / '.sa3'


def exe(name='sa3-generate'):
    p = home() / 'bin' / (name + ('.exe' if os.name == 'nt' else ''))
    if not p.exists():
        raise FileNotFoundError(f'{p} not found - run scripts/setup_sa3.py or set SA3_HOME / local.json')
    return p


def available():
    """{variant: {'dit': [ENC..], 'same': [ENC..]}, '_t5': [ENC..]} from the models folder."""
    out = {'_t5': []}
    mdir = home() / 'models'
    for f in (mdir.iterdir() if mdir.exists() else []):
        for rx, key in ((DIT_RE, 'dit'), (SAME_RE, 'same')):
            m = rx.match(f.name)
            if m:
                out.setdefault(m['v'], {'dit': [], 'same': []})[key].append(m['e'])
        m = T5_RE.match(f.name)
        if m:
            out['_t5'].append(m['e'])
    return out


def _pick(have, pref):
    for e in pref:
        if e in have:
            return e
    return have[0] if have else None


def resolve(model):
    """Variant + (dit, ae, t5) encodings that are actually installed."""
    variant = MODELS.get(model, model)
    av = available()
    v = av.get(variant)
    if not v or not v['dit'] or not v['same']:
        installed = sorted(k for k in av if not k.startswith('_'))
        raise RuntimeError(f'model {model!r} ({variant}) is not installed; installed: {installed}. '
                           f'Download it with scripts/setup_sa3.py --variant {variant}')
    if not av['_t5']:
        raise RuntimeError('T5Gemma text encoder missing - run scripts/setup_sa3.py')
    return variant, _pick(v['dit'], PREF), _pick(v['same'], AE_PREF), _pick(av['_t5'], PREF)


def status():
    h = home()
    info = {'sa3_home': str(h), 'bin': (h / 'bin').exists(), 'models': available()}
    try:
        r = subprocess.run([str(exe('sa3-server')), '--props'], capture_output=True, text=True, timeout=60)
        props = json.loads(r.stdout.strip().splitlines()[-1])
        info['devices'] = [d['description'].strip() + f" ({d['backend']})" for d in props.get('devices', [])]
    except Exception as e:  # noqa: BLE001 - status is diagnostic
        info['devices'] = f'unavailable: {e}'
    return info


def generate(prompt, out, model='sfx', duration=2.0, seed=None, steps=8, padding=0.0,
             cfg=None, negative=None, init=None, init_noise=None, inpaint=None,
             peak_db=-1.0, limiter=False, extra=(), quiet=True):
    """Generate one WAV (44.1 kHz stereo 16-bit) and return {'path', 'seed', 'elapsed', 'cmd'}.

    model     'sfx' (small-sfx: effects/foley, fastest) | 'medium' (music, ambience beds, tonal/long) | 'music'
    duration  seconds (exact output length; 0.5..~180)
    padding   schedule headroom in seconds. 0 = the sound may END inside the clip (one-shots, decays).
              ~6 = keeps full energy to the last sample (loops, ambiences, music you will crossfade).
    cfg       None = distilled single pass (default, fast). 2..4 = stronger prompt adherence + negative prompt.
    init      source WAV for audio-to-audio (variation / restyle); init_noise 0.2 subtle .. 1.0 ignore source.
    inpaint   (start, end) seconds: regenerate that span of `init`, keep the rest (end may extend the clip).
    peak_db   peak normalize the raw generation (None = runtime default +2 dB push + limiter).
    """
    variant, dit_e, ae_e, t5_e = resolve(model)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(exe()), '--models-dir', str(home() / 'models'), '--model', variant,
           '--encoding', dit_e.lower(), '--ae-encoding', ae_e.lower(), '--t5-encoding', t5_e.lower(),
           '--prompt', prompt, '--steps', str(steps), '--duration-padding', f'{padding:g}',
           '--out', str(out)]
    if not (init and inpaint):  # inpaint end sets the length
        cmd += ['--duration', f'{duration:g}']
    if seed is not None:
        cmd += ['--seed', str(int(seed))]
    if cfg is not None:
        cmd += ['--cfg-scale', f'{cfg:g}']
        if negative:
            cmd += ['--negative-prompt', negative]
    if init:
        cmd += ['--init', str(init)]
        if init_noise is not None:
            cmd += ['--init-noise-level', f'{init_noise:g}']
        if inpaint:
            cmd += ['--inpaint-start', f'{inpaint[0]:g}', '--inpaint-end', f'{inpaint[1]:g}']
    if peak_db is not None:
        cmd += ['--peak-normalize-db', f'{peak_db:g}']
        if not limiter:
            cmd += ['--no-limiter']
    cmd += list(extra)
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(exe().parent))
    m = re.search(r'seed (\d+)\)', r.stdout + r.stderr)
    if r.returncode != 0 or not out.exists():
        tail = '\n'.join((r.stdout + r.stderr).strip().splitlines()[-8:])
        raise RuntimeError(f'sa3-generate failed ({r.returncode}):\n{tail}')
    res = {'path': str(out), 'seed': int(m[1]) if m else seed, 'elapsed': round(time.time() - t0, 2),
           'model': variant, 'prompt': prompt, 'duration': duration, 'cmd': cmd}
    if not quiet:
        print(f"  [sa3] {out.name}  seed {res['seed']}  {res['elapsed']}s")
    return res


def batch(prompt, out_dir, stem, n=4, seeds=None, **kw):
    """n takes of one prompt -> <out_dir>/<stem>_s<seed>.wav. Pass seeds to reproduce exact takes."""
    seeds = list(seeds) if seeds is not None else [int(time.time() * 1000 + i * 7919) % 2_000_000_000
                                                  for i in range(n)]
    return [generate(prompt, Path(out_dir) / f'{stem}_s{s}.wav', seed=s, **kw) for s in seeds]


def _seeds(text):
    out = []
    for part in text.split(','):
        a, _, b = part.partition('-')
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status')
    g = sub.add_parser('gen')
    g.add_argument('--prompt', required=True)
    g.add_argument('--out', required=True, help='file.wav, or a folder when --seeds/--n is used')
    g.add_argument('--model', default='sfx')
    g.add_argument('--duration', type=float, default=2.0)
    g.add_argument('--seed', type=int)
    g.add_argument('--seeds', help='e.g. 1-4 or 3,9,12 (writes <out>/<stem>_s<seed>.wav)')
    g.add_argument('--n', type=int, help='n random-seed takes into folder <out>')
    g.add_argument('--stem', default='take')
    g.add_argument('--steps', type=int, default=8)
    g.add_argument('--padding', type=float, default=0.0)
    g.add_argument('--cfg', type=float)
    g.add_argument('--negative')
    g.add_argument('--init')
    g.add_argument('--init-noise', type=float)
    a = ap.parse_args()
    if a.cmd == 'status':
        print(json.dumps(status(), indent=2))
        sys.exit(0)
    kw = dict(model=a.model, duration=a.duration, steps=a.steps, padding=a.padding, cfg=a.cfg,
              negative=a.negative, init=a.init, init_noise=a.init_noise, quiet=False)
    if a.seeds or a.n:
        res = batch(a.prompt, a.out, a.stem, n=a.n or 0, seeds=_seeds(a.seeds) if a.seeds else None, **kw)
    else:
        res = [generate(a.prompt, a.out, seed=a.seed, **kw)]
    print(json.dumps([{k: v for k, v in r.items() if k != 'cmd'} for r in res], indent=2))
