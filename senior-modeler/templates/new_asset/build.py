# <ASSET> - geometry. Re-runnable: deletes and rebuilds only the parts it tagged (or only ONLY = ['Lid', ...]).
#   p = r"<skill>\assets\<slug>\build.py"; g = {'__file__': p, 'ONLY': None}; exec(open(p).read(), g); g['BUILT']
# Every number should come from the brief or a concept measurement (comment the source). Faces -Y, base on z=0.
import os

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brief.py'), encoding='utf-8').read(), globals())
lib('model_kit', into=globals())
mt = lib('materials')

B = BRIEF
H = B['height_m']
begin(B['name'], style=B['style'], size=H, only=globals().get('ONLY'))

# palette: name -> colour (sRGB hex, e.g. from concept_match.color_regions) [, recipe, kwargs]; recipe None = style default
M = mt['palette'](B['name'], {
    'Wood': '#8A5A33',
    'Metal': ('#6E7378', 'pbr', dict(metallic=1.0, roughness=0.4)),
}, style=B['style'], size=H)

# ---- primary forms (TODO replace this example crate)
W = 0.9 * H
if not skip('Body'):
    box('Body', (W, W, 0.82 * H), base=True, mat=M['Wood'])
if not skip('Lid'):
    box('Lid', (W * 1.04, W * 1.04, 0.18 * H), loc=(0, 0, 0.82 * H), base=True, mat=M['Wood'])
# ---- secondary forms
for i, z in enumerate((0.15, 0.62)):
    n = 'Band_%d' % i
    if not skip(n):
        box(n, (W * 1.02, W * 1.02, 0.07 * H), loc=(0, 0, z * H), base=True, mat=M['Metal'])
# ---- game helpers
if B['export'].get('collision') and not skip('Collision'):
    collision([p for p in parts()], kind=B['export']['collision'] if B['export']['collision'] in ('box', 'convex') else 'box')

BUILT = sorted(o.get('gm_part') for o in parts(include_helpers=True))
print('built', BUILT)
