"""<Sound name> - <one line: gameplay use>.

Copy this folder to <skill>/assets/<slug>/ and edit BRIEF, SOURCES and design().
    python build.py takes     generate/refresh the takes of every layer + review pages (src/<layer>/_takes.html)
    python build.py           design + deliver (export/, review/)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1]
sys.path.insert(0, str(SKILL / 'scripts'))
import asset  # noqa: E402
import audio as au  # noqa: E402
import synth as sy  # noqa: E402

BRIEF = dict(
    name='SFX_Thing_Action',          # -> export/SFX_Thing_Action_01.wav ...
    kind='oneshot',                   # oneshot | ui | loop | ambience | music
    sr=48000, bits=24, ch=1,          # mono for world-positional sounds, 2 for UI/ambience/2D
    target_lufs_m=-14,                # one-shots (see reference/delivery.md); loops use target_lufs_i
    ceiling=-1.0,
    fade_out=0.04,
)

# One entry per generated layer. Run `takes`, review, then keep the seeds you want (in variation order).
SOURCES = {
    'body': dict(model='medium', prompt='<source + action, phase by phase>', duration=2.0, seeds=[11, 23, 37, 51]),
    # 'texture': dict(model='sfx', prompt='...', duration=2.0, seeds=[5, 9]),
}
PICK = {'body': [11, 23, 37]}         # seeds used for variations 1..N
SPREAD = [0.0, -0.5, 0.4]             # pitch offset (semitones) per variation


def design(src, i, rng):
    """Variation i (0-based) -> Audio. src[layer] is a list of takes in SOURCES seed order."""
    seeds = SOURCES['body']['seeds']
    body = src['body'][seeds.index(PICK['body'][i])]
    body = au.trim_silence(body)
    body = au.fx(body, [('dcblock',), ('hp', 60, 4), ('pitch', SPREAD[i]), ('comp', -20, 3, 4, 90)])
    return au.mix([
        (body, 0.0, 0),
        (sy.click(0.004, seed=i + 1), 0.0015, -12),    # crisp attack (remove if the take is already sharp)
    ], ch=2)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'takes':
        asset.sources(SOURCES, HERE)
        for layer in SOURCES:
            print(asset.takes(SOURCES, HERE, layer))
    else:
        src = asset.sources(SOURCES, HERE)
        clips = [design(src, i, asset.rng(i)) for i in range(len(PICK['body']))]
        rep = asset.deliver(clips, BRIEF, HERE)
        for row in rep['summary']:
            print(row)
        print('audition:', rep['audition'])
