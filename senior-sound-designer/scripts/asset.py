"""Per-asset pipeline used by assets/<slug>/build.py: cached source generation -> design -> deliver.

    src = asset.sources(SOURCES, HERE)            # generate (or reuse) every take, returns {layer: [Audio..]}
    clips = [design(src, i, rng) for i ...]       # your recipe (in build.py)
    asset.deliver(clips, BRIEF, HERE)             # normalize, fade-check, export, QA, sheet, audition, report

Folder layout it writes (all inside the asset folder):
    src/<layer>/<layer>_s<seed>.wav   raw generations (never edited - non-destructive; delete to regenerate)
    export/<Name>_NN.wav              game-ready files
    review/sheet.png, review/audition.html, review/img/*.png, review/qa.json
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio as au  # noqa: E402
import qa  # noqa: E402
import sa3  # noqa: E402


def sources(spec, here, verbose=True):
    """spec: {layer: dict(prompt, model='sfx', duration, seeds=[...], **sa3.generate kwargs)}.
    Existing files are reused, so re-running build.py never regenerates unless you delete src/<layer>/
    or change the seeds. Returns {layer: [Audio, ...]} in seed order (+ '<layer>_paths')."""
    out = {}
    for layer, s in spec.items():
        s = dict(s)
        seeds = s.pop('seeds')
        d = Path(here) / 'src' / layer
        clips, paths = [], []
        for seed in seeds:
            p = d / f'{layer}_s{seed}.wav'
            if not p.exists():
                sa3.generate(out=p, seed=seed, quiet=not verbose, **s)
            clips.append(au.read(p))
            paths.append(p)
        out[layer], out[layer + '_paths'] = clips, paths
    return out


def takes(spec, here, layer, title=None):
    """Audition page + sheet of the raw takes of one layer - pick seeds before designing."""
    d = Path(here) / 'src' / layer
    paths = sorted(d.glob('*.wav'))
    qa.sheet(paths, d / '_takes.png')
    return qa.audition(paths, d / '_takes.html', title or f'{layer} takes', kind='oneshot')


def deliver(clips, brief, here, notes=None):
    """brief keys: name, kind ('oneshot'|'ui'|'loop'|'ambience'|'music'), sr, bits, ch, fmt ('wav'|'ogg'),
    target_lufs_m (one-shots) or target_lufs_i (loops), ceiling (dBTP), max_gr (limiter dB, default 6),
    fade_out (s, one-shots)."""
    here = Path(here)
    kind = brief.get('kind', 'oneshot')
    loopish = kind in ('loop', 'ambience', 'music')
    exp, rev = here / 'export', here / 'review'
    for old in exp.glob(f"{brief['name']}*"):  # stale variations from a previous run with more clips
        old.unlink()
    paths, results = [], []
    for i, c in enumerate(clips, 1):
        if not loopish:
            c = au.fade(c, brief.get('fade_in', 0.001), brief.get('fade_out', 0.02))
        if brief.get('ch') == 1:
            c = au.conform(c, ch=1)
        c = au.normalize(c, lufs_m=None if loopish else brief.get('target_lufs_m', -14),
                         lufs_i=brief.get('target_lufs_i', -24) if loopish else None,
                         ceiling=brief.get('ceiling', -1.0), max_gr=brief.get('max_gr', 6.0))
        if not loopish:   # the limiter can leave a non-zero last sample - re-fade sample-exact
            c = au.fade(c, 0.0005, min(0.005, brief.get('fade_out', 0.02)))
        suffix = f'_{i:02d}' if len(clips) > 1 or brief.get('number_single') else ''
        p = exp / f"{brief['name']}{suffix}.{brief.get('fmt', 'wav')}"
        au.write(c, p, sr=brief.get('sr', 48000), bits=brief.get('bits', 24))
        paths.append(p)
        results.append(qa.analyze(p, kind=kind, ceiling=brief.get('ceiling', -1.0),
                                  target_lufs_m=None if loopish else brief.get('target_lufs_m'),
                                  target_lufs_i=brief.get('target_lufs_i') if loopish else None))
    rev.mkdir(parents=True, exist_ok=True)
    qa.sheet(paths, rev / 'sheet.png')
    qa.audition(paths, rev / 'audition.html', brief.get('title', brief['name']), notes, kind, results)
    (rev / 'qa.json').write_text(json.dumps(results, indent=1), encoding='utf-8')
    worst = {r['file']: [x['msg'] for x in r['issues'] if x['sev'] in ('error', 'warn')] for r in results}
    return {'exported': [str(p) for p in paths], 'sheet': str(rev / 'sheet.png'),
            'audition': str(rev / 'audition.html'),
            'summary': [{'file': Path(r['file']).name, 'dur': r['dur'], 'tp': r['true_peak'],
                         'lufs': r['lufs_i'] if loopish else r['lufs_m_max'], 'attack_ms': r['attack_ms'],
                         'issues': worst[r['file']]} for r in results]}


def rng(seed):
    return random.Random(seed)
