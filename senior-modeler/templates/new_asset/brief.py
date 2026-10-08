# <ASSET> - brief: the single source of truth that build.py / surface.py / review.py / export.py read.
# Fill it from the intake answers (SKILL.md section 0). Copy templates/new_asset/ to assets/<slug>/ first.
# Every other script execs this file first: it defines HERE / SKILL / SLUG and lib().
import os

HERE = os.path.dirname(os.path.abspath(__file__))  # this asset's folder: assets/<slug>/ - every output lands here
SKILL = os.path.dirname(os.path.dirname(HERE))     # the skill folder (scripts/, reference/, assets/)
SLUG = os.path.basename(HERE)


def lib(name, into=None):
    """Load <skill>/scripts/<name>.py into a new dict, or into=globals() (model_kit builds into the caller)."""
    p = os.path.join(SKILL, 'scripts', name + '.py')
    g = {} if into is None else into
    keep = g.get('__file__')
    g['__file__'] = p
    exec(open(p, encoding='utf-8').read(), g)
    if keep is not None:
        g['__file__'] = keep
    return g


BRIEF = dict(
    name='TodoAsset',                     # PascalCase, used in every name: <Name>_<Part>, SM_<Name>, T_<Name>_*, M_<Name>
    style='stylized',                     # stylized | realistic | low_poly | cartoon | anime (reference/styles/)
    asset_type='prop',                    # prop | environment | character | weapon | vehicle (reference/asset_types/)
    textures='pbr',                       # pbr (baked set) | palette (swatch texture) | none (UVs + flat materials)
    target='game', engine='unreal',       # game: unreal | unity | godot | generic ; or target='render' / 'print'
    tri_budget=(300, 2000),               # (min, max) triangles, from the style + asset type guides
    height_m=0.6,                         # real size; or size_m=(x, y, z)
    origin='base', ground=True,           # pivot: base | center | world ; rests on z=0
    texture_res=1024, margin_px=8, texel_px_m=512,
    allow_uv_overlap=False,
    pose=None,                            # characters: 'A' | 'T'
    deforming=False,                      # characters with skinned (not rigid) meshes
    print3d=False,
    concept=None,                         # {'front': r"...\concept\front.png"} or {'front': (path, crop)}; see concept_to_3d.md
    export=dict(fmt='fbx', join=True, collision='box', lods=(), exporter='auto', opts={}),
    out_root=HERE,                        # renders/, textures/, export/ and the .blend live in this asset folder
)
