# Character inspection (library) - step 1 for every new model. Model-agnostic: works from bone hierarchy + geometry,
# not from a particular naming convention.
#   g = {'__file__': p := os.path.join(SKILL, 'scripts', 'inspect_character.py')}; exec(open(p).read(), g)
#   result = g['inspect'](ARM, MESH)              # raw dump: bones, vertex-group bboxes, transforms, units, add-ons
#   result = g['analyze'](ARM, MESH)              # facing, side tokens, height, archetype, limbs, spring candidates
#   g['draft_rig_config'](ARM, MESH, out_path, slug='my_char')   # writes a buildable first-pass rig_config.py
#   g['snapshot'](MESH, out_dir)                  # quick Workbench stills - LOOK at the model before posing it
import bpy, os, math, re
from collections import Counter
from mathutils import Vector

V = Vector
APPENDAGE_KEYS = ('hair', 'pony', 'ponytail', 'braid', 'skirt', 'cape', 'cloak', 'tail', 'ear', 'earing', 'earring', 'ribbon', 'scarf',
                  'tassel', 'belt', 'strap', 'chain', 'feather', 'antenna', 'tentacle', 'whisker', 'pauldron', 'jiggle',
                  'breast', 'belly', 'cloth', 'flap', 'sleeve', 'banner', 'tie', 'plume', 'epaulette')
PROP_KEYS = ('weapon', 'sword', 'staff', 'shield', 'prop', 'gun', 'bow', 'wand', 'mic', 'carrot')
FINGER_KEYS = ('finger', 'thumb', 'index', 'middle', 'ring', 'pinky', 'claw')
HEAD_KEYS = ('head',)
WING_KEYS = ('wing',)


# ---------------------------------------------------------------- raw dump
def inspect(armature, mesh, weight_min=0.3):
    arm = bpy.data.objects[armature]
    me = bpy.data.objects[mesh]
    r3 = lambda v: [round(x, 3) for x in v]
    bones = [dict(name=b.name, parent=b.parent.name if b.parent else None, head=r3(b.head_local), tail=r3(b.tail_local),
                  deform=b.use_deform) for b in arm.data.bones]
    stats = _group_stats(me, weight_min)
    weighted = set(stats)
    return dict(
        blend=bpy.data.filepath or '(unsaved)', blender=bpy.app.version_string,
        fps=bpy.context.scene.render.fps, unit_scale=bpy.context.scene.unit_settings.scale_length,
        arm_xform=dict(loc=r3(arm.location), rot=r3(arm.rotation_euler), scale=r3(arm.scale)),
        mesh_xform=dict(loc=r3(me.location), rot=r3(me.rotation_euler), scale=r3(me.scale), dims=r3(me.dimensions)),
        mesh_parent=me.parent.name if me.parent else None,
        modifiers=[(m.name, m.type) for m in me.modifiers],
        shape_keys=[k.name for k in me.data.shape_keys.key_blocks] if me.data.shape_keys else None,
        materials=[m.name for m in me.data.materials if m],
        n_bones=len(bones), bones=bones,
        vertex_groups={k: dict(verts=v[0], bbox_min=v[1], bbox_max=v[2]) for k, v in stats.items()},
        unweighted_deform_bones=[b['name'] for b in bones if b['deform'] and b['name'] not in weighted],
        existing_actions=[a.name for a in bpy.data.actions],
        better_fbx=hasattr(bpy.ops.better_export, 'fbx'),
        rig_already_built=any(b['name'].startswith('CTRL_') for b in bones),
    )


def _group_stats(me, weight_min=0.3):
    vg = {g.index: g.name for g in me.vertex_groups}
    stats = {}
    for v in me.data.vertices:
        for g in v.groups:
            if g.weight < weight_min or g.group not in vg:
                continue
            s = stats.setdefault(vg[g.group], [0, [1e9] * 3, [-1e9] * 3, V((0, 0, 0))])
            s[0] += 1
            s[3] += v.co
            for i in range(3):
                s[1][i] = min(s[1][i], round(v.co[i], 2))
                s[2][i] = max(s[2][i], round(v.co[i], 2))
    return {k: [v[0], v[1], v[2], v[3] / max(1, v[0])] for k, v in stats.items()}


# ---------------------------------------------------------------- analysis
def _tokens(name):
    n = re.sub(r'([a-z])([A-Z])', r'_', name)
    return [t for t in re.split(r'[^a-zA-Z]+', n.lower()) if t]


def _has(name, keys):
    """Whole-token match for short keys ('bow' must not match 'elbow'), substring for long keys ('backskirt')."""
    toks = _tokens(name)
    low = name.lower()
    return any(k in toks or (len(k) >= 5 and k in low) for k in keys)


def _mirror_pairs(bones, tol):
    pairs = []
    pos = [(b, b.head_local) for b in bones]
    for b, h in pos:
        if h.x <= tol:
            continue
        best = min(((o, (o.head_local - V((-h.x, h.y, h.z))).length) for o, ho in pos if ho.x < -tol), key=lambda t: t[1], default=None)
        if best and best[1] < tol:
            pairs.append((b, best[0]))
    return pairs


def _token_diff(a, b):
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    j = 0
    while j < min(len(a), len(b)) - i and a[-1 - j] == b[-1 - j]:
        j += 1
    return a[i:len(a) - j], b[i:len(b) - j]


def analyze(armature, mesh):
    """Model-agnostic read of the skeleton: facing, character-left/right name tokens, height, archetype, chains."""
    arm = bpy.data.objects[armature]
    me = bpy.data.objects[mesh]
    bones = [b for b in arm.data.bones if b.use_deform and not b.name.startswith(('CTRL_', 'MCH_', 'SNAP_'))]
    zs = [(me.matrix_world @ v.co).z for v in me.data.vertices]
    ground, top = min(zs), max(zs)
    height = top - ground
    stats = _group_stats(me)
    weighted = set(stats)
    tol = 0.02 * height

    # facing: (1) foot geometry ahead of the lowest joints, (2) head ahead of the pelvis for horizontal bodies
    votes = V((0, 0, 0))
    for b in bones:
        if b.head_local.z - ground < 0.15 * height and b.name in stats:
            off = stats[b.name][3] - b.head_local
            votes += V((off.x, off.y, 0)) * stats[b.name][0]
    heads = [b for b in bones if _has(b.name, HEAD_KEYS)]
    if heads:
        centre = sum((b.head_local for b in bones), V((0, 0, 0))) / len(bones)
        d = heads[0].head_local - centre
        if V((d.x, d.y, 0)).length > 0.15 * height:
            votes += V((d.x, d.y, 0)).normalized() * (votes.length + 1.0) * 2
    if votes.length < 1e-6:
        facing, conf = '-Y', 'default (no evidence)'
    else:
        ax = max(((abs(votes.x), 'X', votes.x), (abs(votes.y), 'Y', votes.y)))
        facing = ('+' if ax[2] > 0 else '-') + ax[1]
        conf = round(ax[0] / max(1e-6, votes.length), 2)
    fwd = {'-Y': V((0, -1, 0)), '+Y': V((0, 1, 0)), '-X': V((-1, 0, 0)), '+X': V((1, 0, 0))}[facing]
    left = V((0, 0, 1)).cross(fwd)

    # side tokens from geometric mirror pairs (a = the bone on the character's left)
    pairs = []
    for a, b in _mirror_pairs(bones, tol):
        if a.head_local.dot(left) < b.head_local.dot(left):
            a, b = b, a
        pairs.append((a, b))
    if abs(left.x) < 0.5:                                # side-facing models mirror across Y, rebuild pairs
        pairs = []
        for b in bones:
            m = next((o for o in bones if (o.head_local - V((b.head_local.x, -b.head_local.y, b.head_local.z))).length < tol
                      and o != b), None)
            if m and b.head_local.dot(left) > tol:
                pairs.append((b, m))
    tokens = Counter(_token_diff(a.name, b.name) for a, b in pairs)
    side_tokens = tokens.most_common(1)[0][0] if tokens else ('L_', 'R_')

    # chains: children lists and ground-reaching limbs
    kids = {b.name: [c for c in b.children if c in bones] for b in bones}
    root = next((b for b in bones if b.parent is None or b.parent not in bones), bones[0])

    def chain_from(b):
        out = [b]
        while len(kids[out[-1].name]) == 1:
            out.append(kids[out[-1].name][0])
        return out
    leaves = [b for b in bones if not kids[b.name]]
    ground_leaves = [b for b in leaves if min(b.head_local.z, b.tail_local.z) - ground < 0.12 * height
                     and not _has(b.name, APPENDAGE_KEYS + PROP_KEYS)]
    limbs = []
    for leaf in ground_leaves:
        ch = [leaf]
        p = leaf.parent
        while p and p in bones and len(kids[p.name]) == 1 and not _has(p.name, ('pelvis', 'hip_root', 'spine', 'body', 'chest')):
            ch.insert(0, p)
            p = p.parent
        if p and p in bones and len(ch) < 3 and len(kids[p.name]) > 1:
            pass
        limbs.append([b.name for b in ch])
    n_legs = len(limbs)
    wings = [b.name for b in bones if _has(b.name, WING_KEYS)]
    feet_z = min((arm.data.bones[l[-1]].head_local.z for l in limbs), default=ground)
    if wings:
        archetype = 'winged'
    elif n_legs >= 4:
        archetype = 'quadruped'
    elif n_legs == 2:
        archetype = 'biped'
    else:
        archetype = 'other/hover'
    appendages = [b.name for b in bones if _has(b.name, APPENDAGE_KEYS) and b.name in weighted]
    props = [b.name for b in bones if _has(b.name, PROP_KEYS)]
    fingers = [b.name for b in bones if _has(b.name, FINGER_KEYS)]
    return dict(height=round(height, 3), ground=round(ground, 3), facing=facing, facing_confidence=conf,
                left_axis=tuple(round(x, 3) for x in left), side_tokens=side_tokens,
                mirrored_pairs=len(pairs), archetype=archetype, ground_limbs=limbs, root=root.name,
                spring_candidates=appendages, props=props, fingers=fingers,
                unweighted=[b.name for b in bones if b.name not in weighted],
                scale_hint='use %% of height for distances: stride ~0.4h, crouch ~0.05-0.15h (h=%.2f)' % height)


# ---------------------------------------------------------------- draft rig config
def _clean(name, tokens):
    n = name
    side = ''
    for t, s in ((tokens[0], 'L'), (tokens[1], 'R')):
        if t and t in n:
            n = n.replace(t, '_', 1)
            side = s
            break
    n = re.sub(r'(?i)(_?jnt|_?joint|_?bone|_?bn|\.\d+)$', '', n)
    parts = [p for p in re.split(r'[_.\s]+', n) if p]
    base = ''.join(p[:1].upper() + p[1:] for p in parts) or 'Bone'
    return 'CTRL_' + base + ('_' + side if side else '')


def draft_rig_config(armature, mesh, out_path, slug='character'):
    """Write a first-pass rig_config.py for ANY skeleton: one world-aligned (character-relative) FK control per weighted
    deform bone, COG over the pelvis, IK on ground-reaching limbs, shapes sized from the skin, collections by role.
    Review and edit it (names, shapes, which chains get IK, spaces for props) before building."""
    A = analyze(armature, mesh)
    arm = bpy.data.objects[armature]
    me = bpy.data.objects[mesh]
    bones = [b for b in arm.data.bones if b.use_deform and not b.name.startswith(('CTRL_', 'MCH_', 'SNAP_'))]
    bset = set(bones)
    stats = _group_stats(me)
    tokens = A['side_tokens']
    h = A['height']
    limb_bones = {n for l in A['ground_limbs'] for n in l}

    def needed(b):                                       # weighted, or has weighted descendants
        return b.name in stats or any(needed(c) for c in b.children if c in bset)
    keep = [b for b in bones if needed(b)]
    names = {}
    for b in keep:
        n = _clean(b.name, tokens)
        while n in names.values():
            n += 'X'
        names[b.name] = n
    root = arm.data.bones[A['root']]
    # pelvis = deepest common ancestor of the ground limbs (or the root's first weighted child)
    pelvis = None
    if A['ground_limbs']:
        anc = None
        for l in A['ground_limbs']:
            chain = []
            p = arm.data.bones[l[0]].parent
            while p:
                chain.append(p.name)
                p = p.parent
            anc = chain if anc is None else [x for x in anc if x in chain]
        pelvis = anc[0] if anc else None
    if pelvis is None or pelvis == root.name:
        pelvis = next((c.name for c in root.children if c in bset), root.name)

    def role(b):
        if b.name in limb_bones:
            return 'Legs FK'
        if _has(b.name, FINGER_KEYS):
            return 'Fingers'
        if _has(b.name, APPENDAGE_KEYS):
            return 'Secondary'
        if _has(b.name, PROP_KEYS):
            return 'Props'
        if _has(b.name, ('arm', 'shoulder', 'clav', 'elbow', 'hand', 'wrist', 'wing')):
            return 'Arms FK'
        return 'Body'

    def shape_for(b):
        d = (b.tail_local - b.head_local)
        d = d.normalized() if d.length > 1e-6 else V((0, 0, 1))
        ax = max(range(3), key=lambda i: abs(d[i]))
        w = ['ring_yz', 'ring_xz', 'ring_xy'][ax]
        if b.name in stats:
            bb = stats[b.name]
            ext = [bb[2][i] - bb[1][i] for i in range(3) if i != ax]
            size = max(0.02 * h, min(0.25 * h, 0.6 * max(ext)))
        else:
            size = max(0.02 * h, 0.4 * b.length)
        return w, round(size, 3)

    lines = []
    ctrl_of = {}
    lines.append("    dict(name='CTRL_Root', pivot=(0, 0, 0), parent=None, drives=%r, shape='root', size=%.3f, palette='MAIN', collection='Main', wire=2.5, length=%.3f)," % (root.name if root.name in names else None, 0.35 * h, 0.08 * h))
    ctrl_of[root.name] = 'CTRL_Root'
    lines.append("    dict(name='CTRL_Hover', pivot=(0, 0, 0), parent='CTRL_Root', shape='hover', size=%.3f, offset=(0, 0, %.3f), palette='MAIN', collection='Main', wire=2.2)," % (0.3 * h, 0.03 * h))
    lines.append("    dict(name='CTRL_COG', pivot='head:%s', parent='CTRL_Hover', drives=%r, shape='cog', size=%.3f, palette='MAIN', collection='Main', wire=2.5)," % (pelvis, pelvis if pelvis != root.name else None, 0.18 * h))
    ctrl_of[pelvis] = 'CTRL_COG'
    ik_end = {}
    for l in A['ground_limbs']:
        foot = l[-2] if (len(l) >= 4 and arm.data.bones[l[-1]].head_local.z - A['ground'] < 0.06 * h) else l[-1]
        i = l.index(foot)
        if i >= 2:
            ik_end[foot] = l[i - 2:i]
    for b in keep:
        if b.name in ctrl_of:
            continue
        p = b.parent
        while p and p.name not in ctrl_of and p in bset:
            p = p.parent
        par = ctrl_of.get(p.name, 'CTRL_COG') if p else 'CTRL_Root'
        # children of an IK foot follow the deform foot (works in IK and FK)
        q = b.parent
        if q and q.name in ik_end:
            par = q.name
        w, size = shape_for(b)
        side = names[b.name][-2:] if names[b.name][-2:] in ('_L', '_R') else ''
        pal = side[1:] if side else 'C'
        lines.append("    dict(name=%r, pivot='head:%s', parent=%r, drives=%r, shape=%r, size=%s, offset='half:%s', palette=%r, collection=%r)," % (
            names[b.name], b.name, par, b.name, w, size, b.name, pal, role(b)))
        ctrl_of[b.name] = names[b.name]
    ik_lines = []
    for foot, chain in ik_end.items():
        fb = arm.data.bones[foot]
        side = names.get(foot, '')[-2:]
        key = 'Leg' + (side if side in ('_L', '_R') else '_%d' % len(ik_lines))
        top, mid = arm.data.bones[chain[0]], arm.data.bones[chain[1]]
        line = fb.head_local - top.head_local
        bend = (mid.head_local - top.head_local)
        bend = bend - line * (bend.dot(line) / max(1e-9, line.dot(line)))
        if bend.length < 1e-3:
            fwd = {'-Y': V((0, -1, 0)), '+Y': V((0, 1, 0)), '-X': V((-1, 0, 0)), '+X': V((1, 0, 0))}[A['facing']]
            bend = fwd
        pole = mid.head_local + bend.normalized() * 0.35 * line.length
        root_par = top.parent.name if top.parent else root.name
        ik_lines.append("    dict(key=%r, chain=%r, end=%r, target='CTRL_IK_%s', target_size=%.3f, target_pivot='head:%s', target_parent='CTRL_Root',\n"
                        "         pole='CTRL_Pole_%s', pole_pos=(%.3f, %.3f, %.3f), pole_parent='CTRL_IK_%s', root_parent='SNAP_%s', prop='IK_%s', default=1.0, collection='Legs IK')," % (
                            key, chain, foot, key, 0.035 * h, foot, key, pole.x, pole.y, pole.z, key, root_par, key))
    src = '''# %(slug)s - DRAFT control rig config generated by inspect_character.draft_rig_config(). Review before building:
#   names / which chains get IK / shapes / space switches for props. Then:
#   p = r"%(path)s"; g = {'__file__': p}; exec(open(p).read(), g); g['REPORT']   -> rest_errors must be {}
# analyze(): facing %(facing)s (confidence %(conf)s), archetype %(arch)s, height %(h).2f, side tokens %(tok)r
# spring candidates: %(spr)r
# props (consider a space switch): %(props)r
import os

HERE = os.path.dirname(os.path.abspath(__file__))  # this character's folder: assets/<slug>/
SKILL = os.path.dirname(os.path.dirname(HERE))
lib = {'__file__': os.path.join(SKILL, 'scripts', 'rig_builder.py')}
exec(open(lib['__file__'], encoding='utf-8').read(), lib)

CONTROLS = [
%(controls)s
]
SPACES = []
IK = [
%(ik)s
]
CFG = dict(
    armature=%(arm)r,
    facing=%(facing)r,
    side_tokens=%(tok)r,
    settings_bone='CTRL_Root',
    controls=CONTROLS,
    spaces=SPACES,
    ik=IK,
    collections={'Legs FK': False},
    panel=dict(id=%(pid)r, label=%(plabel)r, category=%(plabel)r, action_tag=%(tag)r),
    widget_prefix=%(wp)r,
    widget_collection=%(wc)r,
)

REPORT = lib['build_rig'](CFG)
print('rig report', REPORT)
''' % dict(slug=slug, path=out_path, facing=A['facing'], conf=A['facing_confidence'], arch=A['archetype'], h=h,
           tok=tuple(tokens), spr=A['spring_candidates'], props=A['props'], controls='\n'.join(lines),
           ik='\n'.join(ik_lines), arm=armature, pid=re.sub(r'\W', '', slug).upper()[:16] or 'RIG',
           plabel=slug.replace('_', ' ').title() + ' Rig', tag=re.sub(r'\W', '', slug).lower() + '_anim',
           wp='WGT_%s_' % re.sub(r'\W', '', slug).upper()[:6], wc='WGT_' + re.sub(r'\W', '', slug).title())
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write(src)
    return dict(path=out_path, controls=len(lines), ik=list(ik_end), analysis=A)


# ---------------------------------------------------------------- stills
def snapshot(mesh, out_dir, views=(('front', (0.3, -1, 0.15)), ('side', (1, 0, 0.1)), ('back3q', (-0.6, 1, 0.3))), target=None, res=800):
    """Temporary camera stills so you SEE the model before posing. Removes its camera afterwards."""
    sc = bpy.context.scene
    me = bpy.data.objects[mesh]
    os.makedirs(out_dir, exist_ok=True)
    bb = [me.matrix_world @ V(c) for c in me.bound_box]
    if target is None:
        target = sum(bb, V()) / 8
    size = max((bb[6] - bb[0]).length, 1e-3)
    cd = bpy.data.cameras.new('TMP_inspect_cam')
    cam = bpy.data.objects.new('TMP_inspect_cam', cd)
    sc.collection.objects.link(cam)
    keep = (sc.camera, sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.filepath)
    out = []
    try:
        sc.camera = cam
        sc.render.engine = 'BLENDER_WORKBENCH'
        sc.render.resolution_x = sc.render.resolution_y = res
        for name, d in views:
            cam.location = V(target) + V(d).normalized() * size * 2.2
            cam.rotation_euler = (V(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
            sc.render.filepath = os.path.join(out_dir, 'inspect_%s.png' % name)
            bpy.ops.render.render(write_still=True)
            out.append(sc.render.filepath)
    finally:
        sc.camera, sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.filepath = keep
        bpy.data.objects.remove(cam)
        bpy.data.cameras.remove(cd)
    return out
