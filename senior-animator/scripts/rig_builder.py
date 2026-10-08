# Generic control-rig builder (library). Character configs call build_rig(CFG).
#   g = {'__file__': p := os.path.join(SKILL, 'scripts', 'rig_builder.py')}; exec(open(p).read(), g)
#   g['build_rig'](CFG)
# Safe to re-run: removes CTRL_/MCH_/SNAP_ bones, all pose-bone constraints and constraint drivers, then rebuilds.
#
# Architecture
#   CTRL_*   animator controls (non-deform). World-aligned (bone along +Y, roll 0 -> identity rest rotation), so
#            every control shares world axes: for a -Y facing character +X rot = nose down, +Y = roll top to the
#            character's left (+X), +Z = turn left. Right side mirrors as (x,-y,-z) rot, (-x,y,z) loc.
#   SNAP_<deform>  copy of the deform bone parented to its control; the deform bone Copy-Transforms it ("FK").
#   MCH_IK_* IK chain copies; deform bones get a second Copy Transforms ("IK") driven by a CTRL_Root prop.
#   MCH_<space>_Parent / _Socket  space switch: parent copies a socket under another control, influence = prop.
#   The deform skeleton (hierarchy, rest) is never changed -> export with only-deform-bones.
#
# CFG keys (see assets/*/rig_config.py and templates/new_character/rig_config.py):
#   armature            armature object name
#   settings_bone       control that holds the switch props (default 'CTRL_Root')
#   controls            list of dicts: name, pivot, parent, drives(deform|None), shape, size, offset, rot, palette, wire, collection
#                       pivot  : (x,y,z) | 'head:Bone' | 'tail:Bone' | 'mid:Bone' (bone midpoint)
#                       offset : (x,y,z) | 'seg:A>B' (half vector head A -> head B) | 'half:Bone' (half the bone vector)
#   spaces              list of dicts: name (e.g. 'Mic'), pivot, parent (default parent bone), follow (control), prop, default
#                       -> creates MCH_<name>_Parent / MCH_<name>_Socket; controls use parent='MCH_<name>_Parent'
#   ik                  list of dicts: key, chain[deform...], end(deform), target, target_pivot, target_parent, pole,
#                       pole_pos, pole_parent (default target_parent; use the foot target for knees), root_parent,
#                       prop, default (0 = FK, 1 = IK), palette, collection,
#                       end_mode ('transforms' default | 'rotation' for skeletons with gaps between limb segments),
#                       aligned (True: IK chain built joint->joint with snap children - for game skeletons whose bones do
#                       not point down the limb, e.g. Unreal skeletons imported with automatic bone orientation off)
#   controls may be parented to a deform bone (e.g. fingers/toes/weapon under the deform hand/ankle) so they work in
#   both FK and IK; the anim framework evaluates those detached (no springs on them).
#   collections         {name: visible}  (DEF/MCH are filled automatically)
#   panel               dict(id='MYCHAR', label='MyChar Rig', category='MyChar Rig', action_tag='mychar_anim')
#   widget_prefix       prefix for widget objects, e.g. 'WGT_RR_'
#   facing              character forward axis in armature space: '-Y' (default), '+Y', '-X', '+X'.
#                       Controls are built pointing BACKWARD with roll 0, so for any facing their local frame is
#                       character-relative: local -Y = forward, +X = character's left, +Z = up. All authoring
#                       conventions (r.x+ = nose down, mirroring (x,-y,-z)) then hold for every model.
#   side_tokens         deform name tokens for left/right, e.g. ('L_', 'R_') or ('lf_', 'rt_') - see analyze()
import bpy, math
from mathutils import Vector

V = Vector
PAL = {'C': 'THEME09', 'L': 'THEME04', 'R': 'THEME01', 'IK': 'THEME03', 'MAIN': 'THEME02', 'FX': 'THEME06'}


BACK = {'-Y': (0, 1, 0), '+Y': (0, -1, 0), '-X': (1, 0, 0), '+X': (-1, 0, 0)}


def sides(fn, tokens=('L_', 'R_')):
    """Helper for configs: fn(side, deform_token, sign) -> list; returns L + R results.
    sign is +1 for the character's left; multiply lateral offsets by it."""
    return fn('L', tokens[0], 1) + fn('R', tokens[1], -1)


# ---------------------------------------------------------------- widgets
def _circ(n=32, r=1.0, plane='XY'):
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        c, s = r * math.cos(a), r * math.sin(a)
        out.append({'XY': (c, s, 0), 'XZ': (c, 0, s), 'YZ': (0, c, s)}[plane])
    return out


def _loop(start, n):
    return [(start + i, start + (i + 1) % n) for i in range(n)]


def build_widgets(prefix, coll_name):
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        coll = bpy.data.collections.new(coll_name)
        bpy.context.scene.collection.children.link(coll)
    coll.hide_render = True
    for lc in bpy.context.view_layer.layer_collection.children:
        if lc.collection == coll:
            lc.exclude = True

    def widget(name, verts, edges):
        name = prefix + name
        me = bpy.data.meshes.get(name) or bpy.data.meshes.new(name)
        me.clear_geometry()
        me.from_pydata(verts, edges, [])
        ob = bpy.data.objects.get(name)
        if ob is None:
            ob = bpy.data.objects.new(name, me)
            coll.objects.link(ob)
        ob.data = me
        return ob

    W = {}
    W['ring_xy'] = widget('ring_xy', _circ(32, 1, 'XY'), _loop(0, 32))
    W['ring_xz'] = widget('ring_xz', _circ(32, 1, 'XZ'), _loop(0, 32))
    W['ring_yz'] = widget('ring_yz', _circ(32, 1, 'YZ'), _loop(0, 32))
    W['sphere'] = widget('sphere', _circ(24, 1, 'XY') + _circ(24, 1, 'XZ') + _circ(24, 1, 'YZ'),
                         _loop(0, 24) + _loop(24, 24) + _loop(48, 24))
    W['diamond'] = widget('diamond', [(1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)],
                          [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4), (0, 5), (1, 5), (2, 5), (3, 5)])
    cube = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    W['cube'] = widget('cube', cube, [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3), (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7)])
    rp = _circ(48, 1, 'XY') + [(0, -1.35, 0), (-0.15, -1.1, 0), (0.15, -1.1, 0)]      # arrow points -Y (forward)
    W['root'] = widget('root', rp, _loop(0, 48) + [(48, 49), (48, 50), (49, 50)])
    arrows, ae = [], []
    for k in range(4):
        a = k * math.pi / 2
        ca, sa = math.cos(a), math.sin(a)
        rot = lambda x, y: (x * ca - y * sa, x * sa + y * ca, 0)
        b = len(arrows)
        arrows += [rot(0.25, 0.08), rot(0.75, 0.08), rot(0.75, 0.2), rot(1.0, 0), rot(0.75, -0.2), rot(0.75, -0.08), rot(0.25, -0.08)]
        ae += [(b + i, b + i + 1) for i in range(6)]
    W['hover'] = widget('hover', arrows, ae)
    sq = []
    for i in range(40):
        a = 2 * math.pi * i / 40
        c, s = math.cos(a), math.sin(a)
        sq.append((math.copysign(abs(c) ** 0.25, c), math.copysign(abs(s) ** 0.25, s), 0))
    W['cog'] = widget('cog', sq, _loop(0, 40))
    return W


# ---------------------------------------------------------------- panel template
UI_TEMPLATE = r'''
import bpy

ARM = "%(armature)s"
SETTINGS = "%(settings_bone)s"
COLLS = %(colls)r
IK_PROPS = %(ik_props)r
SPACE_PROPS = %(space_props)r
TAG = "%(action_tag)s"


def action_items(self, context):
    return [(a.name, a.name, "") for a in sorted(bpy.data.actions, key=lambda a: a.name)
            if a.get(TAG)] or [("NONE", "No actions", "")]


class %(ID)s_OT_set_action(bpy.types.Operator):
    """Play an action on the rig and set the scene range to it"""
    bl_idname = "%(id)s.set_action"
    bl_label = "Set Animation"
    bl_options = {"REGISTER", "UNDO"}
    action: bpy.props.EnumProperty(items=action_items)

    def execute(self, context):
        act = bpy.data.actions.get(self.action)
        arm = bpy.data.objects.get(ARM)
        if not act or not arm:
            return {"CANCELLED"}
        ad = arm.animation_data or arm.animation_data_create()
        ad.action = act
        if ad.action_slot is None and act.slots:
            ad.action_slot = act.slots[0]
        sc = context.scene
        sc.frame_start, sc.frame_end = int(act.frame_range[0]), int(act.frame_range[1])
        sc.frame_set(sc.frame_start)
        return {"FINISHED"}


class %(ID)s_PT_rig(bpy.types.Panel):
    bl_label = "%(label)s"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "%(category)s"

    @classmethod
    def poll(cls, context):
        return bpy.data.objects.get(ARM) is not None

    def draw(self, context):
        arm = bpy.data.objects[ARM]
        lay = self.layout
        lay.operator_menu_enum("%(id)s.set_action", "action", text="Animation", icon="ACTION")
        root = arm.pose.bones.get(SETTINGS)
        if root is None:
            lay.label(text="Build the rig first")
            return
        if IK_PROPS:
            box = lay.box()
            box.label(text="IK / FK  (1 = IK)")
            for p in IK_PROPS:
                box.prop(root, '["%%s"]' %% p, text=p.replace("_", " "), slider=True)
        if SPACE_PROPS:
            box = lay.box()
            box.label(text="Spaces")
            for p in SPACE_PROPS:
                box.prop(root, '["%%s"]' %% p, text=p.replace("_", " "), slider=True)
        box = lay.box()
        box.label(text="Bone Collections")
        col = box.column(align=True)
        for c in COLLS:
            bc = arm.data.collections.get(c)
            if bc:
                col.prop(bc, "is_visible", text=c, toggle=True)


def register():
    for c in (%(ID)s_OT_set_action, %(ID)s_PT_rig):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
        bpy.utils.register_class(c)


register()
'''


# ---------------------------------------------------------------- build
def build_rig(CFG):
    arm = bpy.data.objects[CFG['armature']]
    amt = arm.data
    SET = CFG.get('settings_bone', 'CTRL_Root')
    controls = CFG['controls']
    spaces = CFG.get('spaces', [])
    iks = CFG.get('ik', [])
    back = V(BACK[CFG.get('facing', '-Y')])

    bpy.context.view_layer.objects.active = arm
    for o in bpy.context.view_layer.objects:
        o.select_set(o == arm)
    bpy.ops.object.mode_set(mode='POSE')
    for p in arm.pose.bones:
        for c in list(p.constraints):
            p.constraints.remove(c)
    if arm.animation_data:
        for d in list(arm.animation_data.drivers):
            if 'constraints' in d.data_path:
                arm.animation_data.drivers.remove(d)

    bpy.ops.object.mode_set(mode='EDIT')
    eb = amt.edit_bones
    for b in [b for b in eb if b.name.startswith(('CTRL_', 'MCH_', 'SNAP_'))]:
        eb.remove(b)
    DEFORM = [b.name for b in eb]
    H = {b.name: b.head.copy() for b in eb}
    T = {b.name: b.tail.copy() for b in eb}

    def pos(spec):
        if isinstance(spec, str):
            kind, bone = spec.split(':')
            return {'head': H[bone], 'tail': T[bone], 'mid': (H[bone] + T[bone]) * 0.5}[kind].copy()
        return V(spec)

    def new_bone(name, head, length=0.12, src=None):
        b = eb.new(name)
        if src:
            s = eb[src]
            b.head, b.tail, b.roll = s.head.copy(), s.tail.copy(), s.roll
        else:
            b.head = V(head)
            b.tail = V(head) + back * length              # backward + roll 0 -> character-relative local frame
            b.roll = 0.0
        b.use_deform = False
        b.use_connect = False
        return b

    for c in controls:
        new_bone(c['name'], pos(c['pivot']), c.get('length', 0.12))
    for s in spaces:
        new_bone('MCH_%s_Parent' % s['name'], pos(s['pivot']), 0.1)
        new_bone('MCH_%s_Socket' % s['name'], pos(s['pivot']), 0.1)
    for ik in iks:
        new_bone(ik['target'], pos(ik['target_pivot']), 0.12)
        new_bone(ik['pole'], pos(ik['pole_pos']), 0.08)
    for c in controls:
        if c.get('parent'):
            eb[c['name']].parent = eb[c['parent']]
        if c.get('drives'):
            snap = new_bone('SNAP_' + c['drives'], None, src=c['drives'])
            snap.parent = eb[c['name']]
    for s in spaces:
        if s.get('parent'):
            eb['MCH_%s_Parent' % s['name']].parent = eb[s['parent']]
        eb['MCH_%s_Socket' % s['name']].parent = eb[s['follow']]
    for ik in iks:
        prev = ik['root_parent']
        chain_end = ik['chain'] + [ik['end']]
        for i, d in enumerate(chain_end):
            if ik.get('aligned') and d != ik['end']:
                # limb-aligned IK bone (joint -> next joint) + a snap child holding the deform bone's own rest frame:
                # IK works whatever way the game skeleton's bones point (e.g. unoriented engine joints)
                b = new_bone('MCH_IK_' + d, H[d], 0.1)
                b.tail = H[chain_end[i + 1]]
                b.roll = 0.0
                s_ = new_bone('MCH_IKS_' + d, None, src=d)
                s_.parent = b
            else:
                b = new_bone('MCH_IK_' + d, None, src=d)
            b.parent = eb[prev]
            prev = b.name
        eb[ik['target']].parent = eb[ik.get('target_parent', 'CTRL_Root')]
        eb[ik['pole']].parent = eb[ik.get('pole_parent', ik.get('target_parent', 'CTRL_Root'))]
        t = new_bone('MCH_IKT_' + ik['end'], None, src=ik['end'])
        t.parent = eb[ik['target']]

    bpy.ops.object.mode_set(mode='POSE')
    pb = arm.pose.bones
    bones = amt.bones

    # settings props
    root = pb[SET]
    props = [(ik['prop'], ik.get('default', 0.0)) for ik in iks] + [(s['prop'], s.get('default', 1.0)) for s in spaces]
    for prop, dflt in props:
        if prop not in root:
            root[prop] = dflt
        root.id_properties_ui(prop).update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, default=dflt)

    def drive(con, prop):
        fc = con.driver_add('influence')
        dr = fc.driver
        dr.type = 'AVERAGE'
        for v in list(dr.variables):
            dr.variables.remove(v)
        var = dr.variables.new()
        var.name = 'v'
        var.type = 'SINGLE_PROP'
        var.targets[0].id = arm
        var.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (SET, prop)

    for c in controls:
        if c.get('drives'):
            con = pb[c['drives']].constraints.new('COPY_TRANSFORMS')
            con.name = 'FK'
            con.target, con.subtarget = arm, 'SNAP_' + c['drives']
    for s in spaces:
        con = pb['MCH_%s_Parent' % s['name']].constraints.new('COPY_TRANSFORMS')
        con.name = 'Follow'
        con.target, con.subtarget = arm, 'MCH_%s_Socket' % s['name']
        drive(con, s['prop'])
    for ik in iks:
        chain, end = ik['chain'], ik['end']
        con = pb['MCH_IK_' + chain[-1]].constraints.new('IK')
        con.target, con.subtarget = arm, ik['target']
        con.pole_target, con.pole_subtarget = arm, ik['pole']
        con.chain_count = len(chain)
        con.use_tail = True
        # end_mode 'rotation': the end bone keeps its place on the chain and only takes the target's rotation -
        # needed when limb segments are not connected (gap between lower bone tail and end head), otherwise the
        # hand/foot slides off the forearm/shin whenever the wrist/ankle rotates.
        # aligned chains end exactly on the end bone's head, so the end keeps its place and takes rotation only
        rot_only = ik.get('end_mode') == 'rotation' or ik.get('aligned')
        c2 = pb['MCH_IK_' + end].constraints.new('COPY_ROTATION' if rot_only else 'COPY_TRANSFORMS')
        c2.target, c2.subtarget = arm, 'MCH_IKT_' + end
        for d in chain + [end]:
            c3 = pb[d].constraints.new('COPY_TRANSFORMS')
            c3.name = 'IK'
            c3.target, c3.subtarget = arm, ('MCH_IKS_' if ik.get('aligned') and d != end else 'MCH_IK_') + d
            drive(c3, ik['prop'])

    # pole angles: sweep so the IK chain matches rest when the target sits at rest
    for p in pb:
        p.location = (0, 0, 0); p.rotation_quaternion = (1, 0, 0, 0); p.rotation_euler = (0, 0, 0); p.scale = (1, 1, 1)

    def chain_err(chain):
        bpy.context.view_layer.update()
        e = 0.0
        for d in chain:
            m = pb['MCH_IK_' + d].matrix.to_3x3().normalized().to_quaternion()
            r = bones['MCH_IK_' + d].matrix_local.to_3x3().normalized().to_quaternion()   # == deform rest unless aligned
            ang = m.rotation_difference(r).angle
            e += min(ang, 2 * math.pi - ang)              # q and -q are the same rotation
        return e

    poles = {}
    for ik in iks:
        con = pb['MCH_IK_' + ik['chain'][-1]].constraints['IK']

        def err(a):
            con.pole_angle = math.radians(a)
            return chain_err(ik['chain'])
        best = min(range(-180, 180, 5), key=err)
        best = min([best + x * 0.25 for x in range(-20, 21)], key=err)
        best = min([best + x * 0.02 for x in range(-13, 14)], key=err)     # bent rest chains need a fine pole
        con.pole_angle = math.radians(best)
        poles[ik['key']] = (best, math.degrees(chain_err(ik['chain'])))

    for c in controls:
        pb[c['name']].rotation_mode = 'XYZ'
    for ik in iks:
        pb[ik['target']].rotation_mode = 'XYZ'

    # shapes
    W = build_widgets(CFG.get('widget_prefix', 'WGT_RIG_'), CFG.get('widget_collection', 'WGT_Rig'))

    def offset(spec, ctrl):
        if isinstance(spec, str):                      # world-derived offsets -> the control's local frame
            kind, rest = spec.split(':')
            if kind == 'seg':
                a, b = rest.split('>')
                w = (H[b] - H[a]) * 0.5
            elif kind == 'half':
                w = (T[rest] - H[rest]) * 0.5
            return tuple(bones[ctrl].matrix_local.to_3x3().inverted() @ w)
        return tuple(spec or (0, 0, 0))                 # tuples are already character-local

    def shape(name, w, size, off=(0, 0, 0), rot=(0, 0, 0), pal='C', wire=1.6):
        p = pb[name]
        p.custom_shape = W[w]
        p.use_custom_shape_bone_size = False
        p.custom_shape_scale_xyz = size if isinstance(size, (tuple, list)) else (size, size, size)
        p.custom_shape_translation = offset(off, name)
        p.custom_shape_rotation_euler = rot
        p.custom_shape_wire_width = wire
        p.color.palette = PAL.get(pal, pal)

    for c in controls:
        if c.get('shape'):
            shape(c['name'], c['shape'], c.get('size', 0.2), c.get('offset'), c.get('rot', (0, 0, 0)), c.get('palette', 'C'), c.get('wire', 1.6))
    for ik in iks:
        shape(ik['target'], 'cube', ik.get('target_size', 0.12), pal='IK', wire=2)
        shape(ik['pole'], 'diamond', ik.get('pole_size', 0.07), pal='IK')

    # bone collections
    groups = {}
    for c in controls:
        groups.setdefault(c.get('collection', 'Controls'), []).append(c['name'])
    for ik in iks:
        groups.setdefault(ik.get('collection', 'Legs IK'), []).extend([ik['target'], ik['pole']])
    groups['MCH'] = [b.name for b in bones if b.name.startswith(('MCH_', 'SNAP_'))]
    groups['DEF'] = DEFORM
    for g in groups:
        if g not in amt.collections:
            amt.collections.new(g)
    for b in bones:
        for c in list(b.collections):
            c.unassign(b)
    for g, names in groups.items():
        for n in names:
            amt.collections[g].assign(bones[n])
    vis = dict({g: True for g in groups}, MCH=False, DEF=False)
    vis.update(CFG.get('collections', {}))
    for g, v in vis.items():
        if g in amt.collections:
            amt.collections[g].is_visible = v
    amt.show_bone_colors = True
    arm.show_in_front = True

    # sidebar panel stored in the .blend (re-registers on load when scripts are trusted)
    panel = dict(dict(id='RIG', label='Rig', category='Rig', action_tag='anim_clip'), **CFG.get('panel', {}))
    ui = UI_TEMPLATE % dict(armature=arm.name, settings_bone=SET, colls=tuple(g for g in groups),
                            ik_props=tuple(ik['prop'] for ik in iks), space_props=tuple(s['prop'] for s in spaces),
                            action_tag=panel['action_tag'], ID=panel['id'].upper(), id=panel['id'].lower(),
                            label=panel['label'], category=panel['category'])
    tname = '%s_rig_ui.py' % panel['id'].lower()
    txt = bpy.data.texts.get(tname) or bpy.data.texts.new(tname)
    txt.clear()
    txt.write(ui)
    txt.use_module = True
    exec(compile(ui, tname, 'exec'), {'__name__': tname[:-3]})
    bpy.context.view_layer.update()
    return verify_rig(arm, poles)


def verify_rig(arm, poles=None):
    """Rest check: every deform bone must sit exactly at rest. Returns a report dict."""
    pb = arm.pose.bones
    bpy.context.view_layer.update()
    bad = {}
    for b in arm.data.bones:
        if not b.use_deform:
            continue
        m = pb[b.name].matrix
        ang = m.to_quaternion().rotation_difference(b.matrix_local.to_quaternion()).angle
        e = min(ang, 2 * math.pi - ang) + (m.translation - b.matrix_local.translation).length   # q == -q
        if e > 1e-3:
            bad[b.name] = round(e, 4)
    return {'rest_errors': bad, 'poles_deg_err': poles or {},
            'n_controls': len([b for b in arm.data.bones if b.name.startswith('CTRL_')]),
            'n_deform': len([b for b in arm.data.bones if b.use_deform])}
