# Senior Animator handoff (library): turn a finished model into what the Senior Animator skill starts from - a deform
# skeleton fitted to the model + a skinned mesh in the bind pose + a pose test + handoff notes.
#   ho = lib('handoff')
#   bones = ho['biped'](LM)                                  # landmark dict (metres, character's LEFT side + centre)
#   ho['build_skeleton']('Nutcracker', bones)                -> armature <Name>_SK in collection <Name>_Rig
#   ho['skin_rigid']('Nutcracker', {'Hat*': 'hat', ...})     -> mesh <Name>: one joined mesh, each part 100% on one bone
#   ho['skin_auto']('Nutcracker')                            -> same, automatic (heat) weights for soft characters
#   ho['check']('Nutcracker')                                weights / bones / transforms QA
#   ho['pose_test']('Nutcracker', {'L_upperarm': (0, 0, 40)}, png)   bend joints, render, reset
#   ho['write_handoff']('Nutcracker', slug, info)            assets/<slug>/handoff.md here + <senior-animator>/assets/<slug>/
#                                                            handoff_from_modeler.md (sibling skill found by its SKILL.md name)
#
# Conventions the animator skill expects: faces -Y, Z up, metres, rest pose = bind pose (T or A per the brief),
# side tokens 'L_' / 'R_' as PREFIXES on lowercase names (its analyze() garbles '_l'/'_r' and capital L/R inside
# other names), deform bones only (it adds CTRL_/MCH_/SNAP_ itself), armature + mesh scale 1, no bone at zero length.
# Re-running is safe until the animator has built controls: build_skeleton() refuses to replace an armature that
# already has CTRL_ bones (re-skin only, or pass force=True with the user's OK).
import bpy, bmesh, os, math, fnmatch, json
from mathutils import Vector, Matrix

V = Vector
ANIMATOR_NAME = 'senior-animator'     # sibling skill that receives the handoff (found next to this skill)
try:                                   # libraries are exec'd with {'__file__': path} (SKILL.md "Running scripts")
    _here = os.path.dirname(os.path.abspath(__file__))
except NameError:
    raise RuntimeError("exec this library with g = {'__file__': path_to_this_file}")


def _lib(name):
    """Load a sibling library into a fresh namespace."""
    p = os.path.join(_here, name + '.py')
    g = {'__file__': p}
    exec(open(p, encoding='utf-8').read(), g)
    return g


def animator_dir():
    """Folder of the Senior Animator skill: a sibling of this skill whose SKILL.md says `name: senior-animator`
    (works for the repo layout and for ~/.claude/skills or <project>/.claude/skills installs). None if missing."""
    parent = os.path.dirname(os.path.dirname(_here))
    for d in sorted(os.listdir(parent)):
        sk = os.path.join(parent, d, 'SKILL.md')
        if os.path.isfile(sk):
            head = open(sk, encoding='utf-8').read(600)
            if 'name: %s' % ANIMATOR_NAME in head:
                return os.path.join(parent, d)
    return None


def _parts(asset):
    return [o for o in bpy.data.objects if o.get('gm_asset') == asset and o.type == 'MESH'
            and not o.get('gm_collision') and not o.get('gm_cutter')]


def _coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def posed(point, group_part):
    """Where a point built in the rest/concept pose ends up after model_kit.set_pose/pose_group (uses the part's
    stored gm_rest). Lets landmarks measured in the concept pose follow the bind pose."""
    o = group_part if isinstance(group_part, bpy.types.Object) else bpy.data.objects[group_part]
    bpy.context.view_layer.update()
    if 'gm_rest' not in o:
        return V(point)
    rest = Matrix([o['gm_rest'][i * 4:i * 4 + 4] for i in range(4)])
    return (o.matrix_world @ rest.inverted()) @ V(point)


# ---------------------------------------------------------------- skeleton
def biped(lm, arm_segments=2, leg_segments=2, fingers=False, extra=(), prebend=0.025):
    """Bone list for a biped from landmarks (metres). Centre: root, pelvis, spine, chest, neck, head, head_top.
    Left side (mirrored to R_): clavicle (inner end), shoulder, elbow, wrist, hand_tip, hip, knee, ankle, ball, toe.
    arm_segments/leg_segments=1 for rigid toys whose arm/leg is ONE piece (no elbow/knee bend inside a part).
    extra: dicts (name, head, tail, parent) for hats, jaws, tails, props (left-side extras ending in L_ are mirrored).
    prebend: knees move FORWARD and elbows BACK by this fraction of the limb length. A perfectly straight 2-bone chain
    gives IK no bend direction (knees buckle sideways, the rig builder reports ~90 deg pole errors)."""
    lm = dict(lm)
    if prebend and leg_segments == 2:
        lm['knee'] = tuple(V(lm['knee']) + V((0, -1, 0)) * prebend * (V(lm['hip']) - V(lm['ankle'])).length)
    if prebend and arm_segments == 2:
        lm['elbow'] = tuple(V(lm['elbow']) + V((0, 1, 0)) * prebend * (V(lm['shoulder']) - V(lm['wrist'])).length)
    g = lambda k: V(lm[k])
    B = [dict(name='root', head=(0, 0, 0), tail=(0, -0.1 * g('head_top').z, 0), parent=None),
         dict(name='pelvis', head=g('pelvis'), tail=g('spine'), parent='root'),
         dict(name='spine', head=g('spine'), tail=g('chest'), parent='pelvis'),
         dict(name='chest', head=g('chest'), tail=g('neck'), parent='spine'),
         dict(name='neck', head=g('neck'), tail=g('head'), parent='chest'),
         dict(name='head', head=g('head'), tail=g('head_top'), parent='neck')]
    side = [dict(name='L_clavicle', head=g('clavicle'), tail=g('shoulder'), parent='chest')]
    if arm_segments == 2:
        side += [dict(name='L_upperarm', head=g('shoulder'), tail=g('elbow'), parent='L_clavicle'),
                 dict(name='L_lowerarm', head=g('elbow'), tail=g('wrist'), parent='L_upperarm')]
        hand_parent = 'L_lowerarm'
    else:
        side += [dict(name='L_arm', head=g('shoulder'), tail=g('wrist'), parent='L_clavicle')]
        hand_parent = 'L_arm'
    side += [dict(name='L_hand', head=g('wrist'), tail=g('hand_tip'), parent=hand_parent)]
    if leg_segments == 2:
        side += [dict(name='L_thigh', head=g('hip'), tail=g('knee'), parent='pelvis'),
                 dict(name='L_calf', head=g('knee'), tail=g('ankle'), parent='L_thigh')]
        foot_parent = 'L_calf'
    else:
        side += [dict(name='L_leg', head=g('hip'), tail=g('ankle'), parent='pelvis')]
        foot_parent = 'L_leg'
    side += [dict(name='L_foot', head=g('ankle'), tail=g('ball'), parent=foot_parent),
             dict(name='L_ball', head=g('ball'), tail=g('toe'), parent='L_foot')]
    B += [dict(b) for b in extra if not b['name'].startswith('L_')]
    side += [dict(b) for b in extra if b['name'].startswith('L_')]
    B += side + [_mirror(b) for b in side]
    return B


def _mirror(b):
    m = lambda p: (-p[0], p[1], p[2])
    return dict(b, name='R_' + b['name'][2:], head=m(tuple(b['head'])), tail=m(tuple(b['tail'])),
                parent=('R_' + b['parent'][2:]) if b.get('parent', '') and b['parent'].startswith('L_') else b.get('parent'))


def build_skeleton(name, bones, force=False):
    """Create/replace the deform armature <Name>_SK (object at origin, scale 1, rest = bind pose)."""
    an = '%s_SK' % name
    ob = bpy.data.objects.get(an)
    if ob is not None:
        if any(b.name.startswith(('CTRL_', 'MCH_', 'SNAP_')) for b in ob.data.bones) and not force:
            raise RuntimeError('%s already has animator controls - re-skin only (skin_*), or force=True with the '
                               "user's OK (that deletes the animator's rig)" % an)
        data = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.armatures.remove(data)
    arm = bpy.data.armatures.new(an)
    ob = bpy.data.objects.new(an, arm)
    _coll('%s_Rig' % name).objects.link(ob)
    arm.display_type = 'STICK'
    ob.show_in_front = True
    vl = bpy.context.view_layer
    keep = (vl.objects.active, [o for o in vl.objects if o.select_get()])
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in vl.objects:
        o.select_set(False)
    vl.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        eb = {}
        for b in bones:
            e = arm.edit_bones.new(b['name'])
            e.head, e.tail = V(b['head']), V(b['tail'])
            if (e.tail - e.head).length < 1e-4:
                e.tail = e.head + V((0, 0, 0.02))
            e.use_deform = b.get('deform', True)
            eb[b['name']] = e
        for b in bones:
            if b.get('parent'):
                eb[b['name']].parent = eb[b['parent']]
                eb[b['name']].use_connect = False
        # roll: Z-up / forward-facing bone rolls so rotations read the same on both sides
        for e in arm.edit_bones:
            e.align_roll(V((0, -1, 0)) if abs((e.tail - e.head).normalized().z) > 0.7 else V((0, 0, 1)))
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
        for o in vl.objects:
            o.select_set(o in keep[1])
        vl.objects.active = keep[0]
    ob['gm_asset_rig'] = name
    return ob


# ---------------------------------------------------------------- skinning
def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-12)))
    return (a + ab * t - p).length


def nearest_bone(arm_ob, point):
    bs = [b for b in arm_ob.data.bones if b.use_deform]
    mw = arm_ob.matrix_world
    return min(bs, key=lambda b: _seg_dist(point, mw @ b.head_local, mw @ b.tail_local)).name


def part_map(asset, rules=None, arm=None):
    """{part object name: bone}: fnmatch rules on the PART name (without the asset prefix) first, else the nearest
    deform bone to the part's centre. Print it, sanity-check it, then pass it to skin_rigid."""
    arm = arm or bpy.data.objects['%s_SK' % asset]
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for o in _parts(asset):
        pn = o.get('gm_part', o.name)
        bone = next((b for pat, b in (rules or {}).items() if fnmatch.fnmatch(pn, pat)), None)
        if bone is None:
            ev = o.evaluated_get(dg)
            c = sum((ev.matrix_world @ V(x) for x in ev.bound_box), V()) / 8
            bone = nearest_bone(arm, c)
        out[o.name] = bone
    return out


def _joined_copy(asset, name, groups):
    """World-baked evaluated copies of the parts, each with its vertex-group weights, joined into <Name>."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    coll = _coll('%s_Rig' % asset)
    old = bpy.data.objects.get(name)
    if old is not None:
        me = old.data
        bpy.data.objects.remove(old)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    baked = bpy.data.materials.get('M_%s' % asset)
    copies = []
    for o in _parts(asset):
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        me.transform(o.matrix_world)
        bm = bmesh.new()                                   # n-gons block tangent export (normal maps) in FBX
        bm.from_mesh(me)
        ngons = [f for f in bm.faces if len(f.verts) > 4]
        if ngons:
            bmesh.ops.triangulate(bm, faces=ngons, quad_method='BEAUTY', ngon_method='BEAUTY')
            bm.to_mesh(me)
        bm.free()
        c = bpy.data.objects.new('%s_tmp_%s' % (name, o.name), me)
        coll.objects.link(c)
        g = groups.get(o.name)
        if g:
            vg = c.vertex_groups.new(name=g)
            vg.add(list(range(len(me.vertices))), 1.0, 'REPLACE')
        copies.append(c)
    with bpy.context.temp_override(active_object=copies[0], object=copies[0], selected_objects=copies,
                                   selected_editable_objects=copies):
        bpy.ops.object.join()
    ob = copies[0]
    ob.name = ob.data.name = name
    if baked is not None:                                        # one engine material (the baked texture set)
        ob.data.materials.clear()
        ob.data.materials.append(baked)
        for p in ob.data.polygons:
            p.material_index = 0
    ob['gm_skin_of'] = asset
    return ob


def _bind(ob, arm):
    md = ob.modifiers.get('Armature') or ob.modifiers.new('Armature', 'ARMATURE')
    md.object = arm
    ob.parent = arm
    ob.matrix_parent_inverse = arm.matrix_world.inverted()


def _hide_parts(asset, hide=True):
    """Source parts stay editable but hidden once the skinned mesh exists; tagged so model_export still finds them."""
    for o in _parts(asset):
        o.hide_set(hide)
        o.hide_render = hide
        o['gm_skin_hidden'] = hide


def skin_rigid(asset, rules=None, mesh_name=None):
    """Rigid skin: every part's vertices 100% on one bone (wooden toys, robots, armour). Source parts stay as the
    editable model (hidden); re-run after model changes."""
    arm = bpy.data.objects['%s_SK' % asset]
    pm = part_map(asset, rules, arm)
    ob = _joined_copy(asset, mesh_name or asset, pm)
    _bind(ob, arm)
    _hide_parts(asset)
    return dict(mesh=ob.name, parts=len(pm), bones_used=sorted(set(pm.values())), map=pm)


def skin_auto(asset, mesh_name=None):
    """Soft skin: automatic (bone heat) weights on the joined mesh. Check the pose test - heat weighting fails on
    non-manifold or intersecting parts; fix those or fall back to skin_rigid for the offending parts."""
    arm = bpy.data.objects['%s_SK' % asset]
    ob = _joined_copy(asset, mesh_name or asset, {})
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(o in (ob, arm))
    vl.objects.active = arm
    with bpy.context.temp_override(active_object=arm, object=arm, selected_objects=[ob, arm],
                                   selected_editable_objects=[ob, arm]):
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    _hide_parts(asset)
    return dict(mesh=ob.name)


# ---------------------------------------------------------------- QA
def check(asset, mesh_name=None, rigid=None):
    me_ob = bpy.data.objects[mesh_name or asset]
    arm = bpy.data.objects['%s_SK' % asset]
    me = me_ob.data
    names = {g.index: g.name for g in me_ob.vertex_groups}
    deform = {b.name for b in arm.data.bones if b.use_deform}
    unweighted, multi, used = 0, 0, set()
    for v in me.vertices:
        ws = [(names[g.group], g.weight) for g in v.groups if g.weight > 1e-4 and names.get(g.group) in deform]
        if not ws:
            unweighted += 1
        if len(ws) > 1:
            multi += 1
        used |= {n for n, _ in ws}
    errors, warnings = [], []
    if unweighted:
        errors.append('%d vertices without deform weights' % unweighted)
    if rigid and multi:
        errors.append('%d vertices on more than one bone (rigid skin expected)' % multi)
    if any(abs(s - 1) > 1e-4 for s in list(arm.scale) + list(me_ob.scale)):
        errors.append('armature/mesh scale is not 1')
    if arm.matrix_world != Matrix.Identity(4):
        warnings.append('armature object is not at the origin with identity rotation')
    short = [b.name for b in arm.data.bones if b.length < 0.005]
    if short:
        errors.append('near-zero-length bones %s' % short)
    unused = sorted(deform - used - {'root'})
    if unused:
        warnings.append('deform bones without vertices (fine for root/helpers): %s' % unused)
    leaked = [b.name for b in arm.data.bones if b.name.startswith(('CTRL_', 'MCH_', 'SNAP_'))]
    tokens = sorted({b.name[:2] for b in arm.data.bones if b.name[:2] in ('L_', 'R_')})
    return dict(ok=not errors, errors=errors, warnings=warnings, bones=len(arm.data.bones), deform_bones=len(deform),
                verts=len(me.vertices), tris=sum(len(p.vertices) - 2 for p in me.polygons), side_tokens=tokens,
                animator_controls_present=bool(leaked))


def pose_test(asset, poses, path, views=('front', 'front3q', 'left'), mesh_name=None):
    """Rotate bones (degrees, pose-bone local Euler XYZ), render a clay sheet through the Preview stage, reset."""
    arm = bpy.data.objects['%s_SK' % asset]
    rs = {}
    rs.update(_lib('review_stage'))
    rs['setup']([mesh_name or asset], asset=asset)
    keep = {}
    try:
        for bn, rot in poses.items():
            pb = arm.pose.bones[bn]
            keep[bn] = (pb.rotation_mode, tuple(pb.rotation_euler))
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = [math.radians(a) for a in rot]
        bpy.context.view_layer.update()
        r = rs['sheet'](path, views=views, mode='clay', label='%s  pose test' % asset)
    finally:
        for bn, (mode, eul) in keep.items():
            pb = arm.pose.bones[bn]
            pb.rotation_euler = eul
            pb.rotation_mode = mode
    return r


# ---------------------------------------------------------------- notes
def write_handoff(asset, slug, info, asset_dir=None):
    """assets/<slug>/handoff.md (modeler side) + <senior-animator>/assets/<slug>/handoff_from_modeler.md (the
    animator's own notes.md is never touched). If the animator skill is not installed next to this one, only the
    modeler copy is written and `animator` is None - tell the user where to put the skill."""
    arm = bpy.data.objects['%s_SK' % asset]
    lines = ['# %s - handoff to Senior Animator' % asset, '',
             '- File: `%s`' % (bpy.data.filepath or '(unsaved - save first)'),
             '- Armature: `%s` (%d deform bones), mesh: `%s`, collection `%s_Rig`' % (
                 arm.name, len([b for b in arm.data.bones if b.use_deform]), info.get('mesh', asset), asset),
             '- Facing -Y, Z up, metres, height %.3f m, bind pose: %s' % (info.get('height', 0), info.get('pose', '?')),
             '- Side tokens: `L_` / `R_` prefixes (lowercase bone names). FACING = \'-Y\', SIDE_TOKENS = (\'L_\', \'R_\')',
             '- Skin: %s' % info.get('skin', '?'),
             '- Style: %s (animation style still to be chosen in the animator intake)' % info.get('style', '?'), '',
             '## Bones', '']
    for b in arm.data.bones:
        lines.append('- `%s` <- %s' % (b.name, b.parent.name if b.parent else '(root)'))
    for title, key in (('Part -> bone map', 'map'), ('Spring / secondary candidates', 'springs'),
                       ('Notes for the animator', 'notes')):
        val = info.get(key)
        if val:
            lines += ['', '## ' + title, '']
            lines += ['- %s: %s' % (k, v) for k, v in sorted(val.items())] if isinstance(val, dict) else ['- ' + x for x in val]
    lines += ['', '## Next (Senior Animator skill)', '',
              '1. `inspect_character.analyze(\'%s\', \'%s\')` + `snapshot()` - confirm facing -Y and side tokens L_/R_.' % (arm.name, info.get('mesh', asset)),
              '2. `draft_rig_config(...)` into `assets/%s/rig_config.py`; IK on legs (and arms if needed).' % slug,
              '3. Ask the animation style + clip list, then clips.py / export.py (SK_%s.fbx first).' % asset]
    text = '\n'.join(lines) + '\n'
    asset_dir = asset_dir or os.path.join(os.path.dirname(_here), 'assets', slug)
    p1 = os.path.join(asset_dir, 'handoff.md')
    with open(p1, 'w', encoding='utf-8') as fh:
        fh.write(text)
    adir = animator_dir()
    p2 = None
    if adir:
        cdir = os.path.join(adir, 'assets', slug)
        os.makedirs(cdir, exist_ok=True)
        p2 = os.path.join(cdir, 'handoff_from_modeler.md')
        with open(p2, 'w', encoding='utf-8') as fh:
            fh.write(text)
    return dict(modeler=p1, animator=p2)
