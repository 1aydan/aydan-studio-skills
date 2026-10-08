# Generic clip-authoring framework (library) for rigs built with rig_builder.py.
# A character's clips.py execs this file INTO ITS OWN GLOBALS, calls configure(...), defines clips with @clip,
# then calls build_all():
#   exec(open(os.path.join(SKILL, 'scripts', 'anim_framework.py')).read(), globals())
#   configure(armature='X_SK', meshes=['X_mesh'], base_pose={...}, springs={...}, action_tag='x_anim')
#
# Workflow per clip
#   1. Primary motion = sparse pose-to-pose keys on CTRL_* bones (editable Bezier / eased curves).
#   2. Spring pass = follow-through / overlap: configured controls are simulated against the evaluated primary motion
#      and per-frame rotation keys are baked on them (parents first, so overlap cascades down chains).
#   Loops: primary curves get a Cycles modifier; springs pre-roll 3 cycles so frame N == frame 0.
#
# Conventions (world-aligned controls, Euler XYZ, degrees in the authoring API):
#   character faces -Y, its left is +X, up is +Z
#   r.x + : nose dips / hanging limbs swing back      r.x - : nose up / limbs swing forward
#   r.y + : top rolls to character's left (+X); hanging limbs swing to its right (-X)
#   r.z + : nose turns to character's left
#   Short names: 'COG' == 'CTRL_COG'. '_X' suffix in pose dicts = both sides, right mirrored (x,-y,-z) rot, (-x,y,z) loc.
import bpy, math
from mathutils import Vector, Matrix, Euler, Quaternion
from bpy_extras import anim_utils

D = math.radians
V = Vector
CH = ('l', 'r', 's')
DEFAULT = {'l': (0.0, 0.0, 0.0), 'r': (0.0, 0.0, 0.0), 's': (1.0, 1.0, 1.0)}
PATH = {'l': 'location', 'r': 'rotation_euler', 's': 'scale'}
IP = {  # how a key leaves toward the next key
    'B': ('BEZIER', None), 'L': ('LINEAR', None), 'C': ('CONSTANT', None),
    'qi': ('QUAD', 'EASE_IN'), 'qo': ('QUAD', 'EASE_OUT'), 'qio': ('QUAD', 'EASE_IN_OUT'),
    'ci': ('CUBIC', 'EASE_IN'), 'co': ('CUBIC', 'EASE_OUT'), 'cio': ('CUBIC', 'EASE_IN_OUT'),
    'xi': ('EXPO', 'EASE_IN'), 'xo': ('EXPO', 'EASE_OUT'),
    'bo': ('BACK', 'EASE_OUT'), 'bi': ('BACK', 'EASE_IN'),
    'eo': ('ELASTIC', 'EASE_OUT'), 'so': ('SINE', 'EASE_OUT'), 'si': ('SINE', 'EASE_IN'), 'sio': ('SINE', 'EASE_IN_OUT'),
}
FW = {}          # framework state, filled by configure()
CLIPS = []


def full(n):
    return n if n.startswith('CTRL_') else 'CTRL_' + n


def other(n):
    if n.endswith('_L'):
        return n[:-2] + '_R'
    if n.endswith('_R'):
        return n[:-2] + '_L'
    return n


def configure(armature, meshes=(), base_pose=None, springs=None, action_tag='anim_clip', fps=30,
              settings_bone='CTRL_Root', exclude_prefixes=('CTRL_IK_', 'CTRL_Pole_'), props=None, follow=None,
              colliders=None, collide=None, floor=None, upper_split=None, interpolation=None):
    """springs: {ctrl: (freq_hz, damping_ratio, weight, max_deg, tip_vector|None[, gravity])}; '_L' entries auto-mirror.
    exclude_prefixes: controls never keyed (pass () for rigs that animate IK targets, e.g. planted biped feet).
    props: {settings_bone custom prop: default} keyed in every clip (IK/FK, space switches); per clip via A.prop().
    follow: {ctrl: [dict(pivot_ctrl, pivot=(x,y,z) rest world point, target=ctrl, w=(wx,wy,wz), clamp=((lo,hi),)*3)]}
            adds the swing (deg, in pivot_ctrl's frame) of the line pivot->target to ctrl's rotation before springs.
            Use for skirts pushed by thighs, pauldrons/clavicles lifted by arms.
    colliders: {name: (ctrl_a, rest_point_a, ctrl_b, rest_point_b, radius)} capsules riding body controls
               (ctrl_b may equal ctrl_a; e.g. thigh = ('Hips', hip_point, 'IK_Foot_L', ankle_point, r)), or
               {name: ('bone', deform_bone, radius)} = the deform bone's head->tail sampled from Blender's evaluated
               pose (IK solved) - use this for limbs driven by IK (upper arms, forearms, thighs, shins).
    collide:   {spring_ctrl: [collider names]} - spring tips are pushed out of these capsules during the bake
               (hair over the back/shoulders, skirts over the thighs). '_L' keys auto-mirror only if listed both sides.
    upper_split: dict(root='COG', branch='Spine') for upper-body-only clips (Anim(..., upper_body=True)): branch must
               be a direct child of root; controls not under the branch (deform or control hierarchy) are 'lower'.
    floor:     ground height, or (height, strand_thickness) - spring tips never sink below it (hair/cloth on the
               floor in deaths, kneels). Default thickness 0.1.
    interpolation: e.g. 'BEZIER' - after each clip is built, EVERY key (authored, eased, baked springs, switch props)
               is converted to it (project preference); None keeps the per-key easing."""
    arm = bpy.data.objects[armature]
    bones = arm.data.bones
    if settings_bone not in bones:
        raise RuntimeError('Build the rig first (rig_builder.py)')
    ctrl = [b.name for b in bones if b.name.startswith('CTRL_') and not b.name.startswith(tuple(exclude_prefixes))]
    sp = arm.pose.bones
    parent = {}
    for n in ctrl:
        p = bones[n].parent
        # space switch: MCH_*_Parent copying a socket -> treat the socket's parent as the effective parent
        if p and p.name.startswith('MCH_'):
            con = next((c for c in sp[p.name].constraints if c.type == 'COPY_TRANSFORMS'), None)
            sw_val = 1.0
            if con and con.subtarget and arm.animation_data:
                for d in arm.animation_data.drivers:
                    if d.data_path == 'pose.bones["%s"].constraints["%s"].influence' % (p.name, con.name):
                        sw_val = d.driver.variables[0].targets[0].id.path_resolve(d.driver.variables[0].targets[0].data_path)
            if con and con.subtarget and sw_val >= 0.5:
                p = bones[con.subtarget].parent
            else:
                p = p.parent
        # controls parented to a deform/MCH bone (fingers, toes, weapon) are evaluated detached (no springs on them)
        parent[n] = p.name if (p and p.name in ctrl) else None

    def depth(n):
        return 0 if parent[n] is None else 1 + depth(parent[n])
    followers = {full(k) for k in (follow or {})}
    ctrl.sort(key=lambda n: 2 * depth(n) + (1 if n in followers else 0))   # followers after same-depth targets
    def_of = {b.parent.name: b.name[5:] for b in bones if b.name.startswith('SNAP_') and b.parent}
    spr = dict(springs or {})
    for k in list(spr):
        if k.endswith('_L'):
            spr.setdefault(k[:-2] + '_R', spr[k])
    FW.update(arm=arm, meshes=[bpy.data.objects[m] for m in meshes], pb=arm.pose.bones, bones=bones,
              CTRL=ctrl, PARENT=parent, PIV={n: bones[n].head_local.copy() for n in ctrl}, DEF_OF=def_of,
              REST={n: bones[n].matrix_local.copy() for n in ctrl},
              FPS=fps, BASE={}, SPRING={full(k): v for k, v in spr.items()}, TAG=action_tag,
              SET=settings_bone, PROPS=dict(props or {}),
              FOLLOW={full(k): [dict(e, pivot_ctrl=full(e['pivot_ctrl']), target=full(e['target'])) for e in v]
                      for k, v in (follow or {}).items()},
              COLL={k: (v if v[0] == 'bone' else (full(v[0]), V(v[1]), full(v[2]), V(v[3]), v[4]))
                    for k, v in (colliders or {}).items()},
              COLLIDE={full(k): list(v) for k, v in (collide or {}).items()},
              UPPER=(None if not upper_split else dict(root=full(upper_split['root']), branch=full(upper_split['branch']))),
              FLOOR=(None if floor is None else (tuple(floor) if isinstance(floor, (tuple, list)) else (floor, 0.1))),
              INTERP=interpolation)
    E = expand(base_pose or {})
    FW['BASE'] = {k: v for k, v in E.items() if k[1] != 'world'}
    FW['BASE'] = resolve_world(E, lambda c, ch: FW['BASE'].get((c, ch), DEFAULT[ch]))
    return FW


def dvec(ctrl):
    d = FW['DEF_OF'].get(ctrl)
    if d is None:
        return V((0, 0, 0.3))
    b = FW['bones'][d]
    return b.tail_local - b.head_local


def expand(Pd):
    """{'COG': {'r': (..)}, 'Shoulder_X': {...}} -> {('CTRL_COG','r'): (x,y,z), ...} with mirroring."""
    out = {}
    for k, chans in Pd.items():
        names = [k] if not k.endswith('_X') else [k[:-2] + '_L', k[:-2] + '_R']
        for n in names:
            if chans.get('world'):
                out[(full(n), 'world')] = True
            for c, v in chans.items():
                if c == 'world':
                    continue
                if c == 's' and not isinstance(v, (tuple, list)):
                    v = (v, v, v)
                v = tuple(float(x) for x in v)
                if k.endswith('_X') and n.endswith('_R'):
                    if c == 'r':
                        v = (v[0], -v[1], -v[2])
                    elif c == 'l':
                        v = (-v[0], v[1], v[2])
                out[(full(n), c)] = v
    return out


def _m(l, r_deg, s=(1, 1, 1)):
    return Matrix.Translation(V(l)) @ Euler([D(x) for x in r_deg], 'XYZ').to_matrix().to_4x4() @ \
        Matrix.Diagonal((s[0], s[1], s[2], 1.0))


def world_to_local(ctrl, point, rot_deg, getv):
    """Local loc/rot (deg) for ctrl so its pivot sits at `point` with world rotation `rot_deg` (root space),
    given the pose of its ancestors: getv(ctrl, chan) -> values."""
    PAR, REST = FW['PARENT'], FW['REST']
    chain, p = [], PAR[ctrl]
    while p:
        chain.append(p)
        p = PAR[p]
    W, prev = Matrix.Identity(4), None
    for c in reversed(chain):
        W = W @ _rel(c, prev) @ _m(getv(c, 'l'), getv(c, 'r'), getv(c, 's'))
        prev = c
    W = W @ _rel(ctrl, prev)
    rest_rot = REST[ctrl].to_quaternion().to_matrix().to_4x4()
    loc, q, _ = (W.inverted() @ _m(point, rot_deg) @ rest_rot).decompose()
    e = q.to_euler('XYZ', Euler([D(x) for x in rot_deg], 'XYZ'))
    return tuple(loc), tuple(math.degrees(x) for x in e)


def _rel(c, par):
    """Rest transform of control c relative to its (effective) parent - Blender's parent_rest^-1 @ rest."""
    REST = FW['REST']
    return REST[c].copy() if par is None else REST[par].inverted() @ REST[c]


def resolve_world(E, getv):
    """Convert expanded entries flagged ('CTRL_x','world') from world (rest/root-space point + world rotation) to local."""
    for (c, ch) in [k for k in E if k[1] == 'world']:
        del E[(c, ch)]
        pt = E.get((c, 'l'), (0.0, 0.0, 0.0))
        rt = E.get((c, 'r'), (0.0, 0.0, 0.0))

        def gv(cc, chan, E=E):
            return E.get((cc, chan), getv(cc, chan))
        l, r = world_to_local(c, pt, rt, gv)
        E[(c, 'l')], E[(c, 'r')] = l, r
    return E


def P(*dicts, **kw):
    """Merge pose dicts (later wins per channel)."""
    out = {}
    for d in dicts:
        for k, v in d.items():
            out.setdefault(k, {}).update(v)
    for k, v in kw.items():
        out.setdefault(k, {}).update(v)
    return out


def base_val(ctrl, chan):
    return FW['BASE'].get((full(ctrl), chan), DEFAULT[chan])


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


class Anim:
    def __init__(self, name, length, loop=False, upper_body=False):
        """upper_body=True: layered upper-body clip. After authoring, the lower body (everything not under the
        configured branch) is held at the base pose and the root's rotation is transferred onto the branch, so the
        upper body keeps its authored orientation. Root translation is dropped (it belongs to the locomotion layer)."""
        self.name, self.n, self.loop, self.upper_body = name, length, loop, upper_body
        self.base = dict(FW['BASE'])
        self.keys = {}        # (ctrl, chan, axis) -> {frame: (value, ip)}
        self.spring = {}      # per-clip spring overrides {ctrl: tuple}
        self.markers = {}
        self._poses = []
        self.props = {}       # settings-bone custom prop -> {frame: (value, ip)}
        self.hooks = []       # fn(action, anim) run after the bake with the action assigned (world-space fixes)

    def prop(self, name, f, val, ip='C'):
        """Key a settings-bone custom prop (IK/FK blend, space switch). Default interpolation: constant."""
        self.props.setdefault(name, {})[f] = (float(val), ip)

    def after(self, fn):
        self.hooks.append(fn)
        return fn

    def set(self, Pd):
        """Change this clip's base pose (absolute values). Controls flagged world=True are given in world space."""
        E = expand(Pd)
        self.base.update({k: v for k, v in E.items() if k[1] != 'world'})
        self.base.update(resolve_world(E, self.bval))

    def set_raw(self, ctrl, chan, val):
        """Set one control's clip base without mirroring."""
        self.base[(full(ctrl), chan)] = tuple(val)

    def bval(self, ctrl, chan):
        return self.base.get((full(ctrl), chan), DEFAULT[chan])

    def pose(self, f, Pd=None, ip='B'):
        """Blocking key: every channel named in ANY pose of the clip is keyed here; unnamed ones take the clip base."""
        self._poses.append((f, resolve_world(expand(Pd or {}), self.bval), ip))

    def key(self, name, chan, f, val, ip='B', axes=None):
        fn = full(name)
        if chan == 's' and not isinstance(val, (tuple, list)):
            val = (val, val, val)
        if isinstance(val, (int, float)):
            assert axes is not None and len(axes) == 1
            vals = {axes[0]: float(val)}
        else:
            vals = {i: float(v) for i, v in enumerate(val) if axes is None or i in axes}
        for a, v in vals.items():
            self.keys.setdefault((fn, chan, a), {})[f] = (v, ip)

    def keyx(self, name, chan, f, val, ip='B'):
        """Key both sides of a pair (name without _L/_R) with mirroring."""
        for n, sgn in ((name + '_L', 1), (name + '_R', -1)):
            v = tuple(val) if isinstance(val, (tuple, list)) else val
            if sgn < 0 and chan == 'r':
                v = (v[0], -v[1], -v[2])
            if sgn < 0 and chan == 'l':
                v = (-v[0], v[1], v[2])
            self.key(n, chan, f, v, ip)

    def wave(self, name, chan, axis, amp, period, phase=0.0, center=None):
        """Sine around the clip base (or center): keys at every extreme + clip ends (cyclic-friendly)."""
        fn = full(name)
        c = self.bval(fn, chan)[axis] if center is None else center
        w = 2 * math.pi / period
        fs = {0.0, float(self.n)}
        k = -4
        while True:
            f = phase + period / 4 + k * period / 2
            k += 1
            if f > self.n:
                break
            if f > 0:
                fs.add(round(f, 3))
        d = self.keys.setdefault((fn, chan, axis), {})
        for f in sorted(fs):
            d[f] = (c + amp * math.sin(w * (f - phase)), 'B')

    def mark(self, f, name):
        self.markers[name] = f

    def resolve(self):
        named = set()
        for f, Pd, ip in self._poses:
            named |= set(Pd)
        out = {k: dict(v) for k, v in self.keys.items()}
        for f, Pd, ip in self._poses:
            for (ctrl, chan) in named:
                val = Pd.get((ctrl, chan), self.bval(ctrl, chan))
                for a in range(3):
                    d = out.setdefault((ctrl, chan, a), {})
                    if f not in d:                         # explicit key() wins
                        d[f] = (val[a], ip)
        for ctrl in FW['CTRL']:                            # every channel keyed -> no residue between clips
            for chan in CH:
                b = self.bval(ctrl, chan)
                for a in range(3):
                    d = out.setdefault((ctrl, chan, a), {})
                    if not d:
                        d[0] = (b[a], 'B')
                    if self.loop and 0 in d and self.n not in d:
                        d[self.n] = d[0]
        return out

    def mirrored(self, name):
        """Left/right mirror of the whole clip (e.g. move_right from move_left)."""
        m = Anim(name, self.n, self.loop)
        sign = {('r', 1): -1, ('r', 2): -1, ('l', 0): -1}

        def mv(chan, v):
            return tuple(x * sign.get((chan, i), 1) for i, x in enumerate(v))
        m.base = {(other(c), ch): mv(ch, v) for (c, ch), v in self.base.items()}
        for (ctrl, chan, a), d in self.keys.items():
            s = sign.get((chan, a), 1)
            m.keys[(other(ctrl), chan, a)] = {f: (v * s, ip) for f, (v, ip) in d.items()}
        m._poses = [(f, {(other(c), ch): mv(ch, v) for (c, ch), v in Pd.items()}, ip) for f, Pd, ip in self._poses]
        m.markers = dict(self.markers)
        m.spring = {other(k): v for k, v in self.spring.items()}
        m.props = {other(k): dict(v) for k, v in self.props.items()}
        return m


def clip(fn):
    CLIPS.append(fn)
    return fn


# ---------------------------------------------------------------- action writing (Blender 4.4+/5.x slotted actions)
def new_action(name):
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    act[FW['TAG']] = True
    slot = act.slots.new(id_type='OBJECT', name=FW['arm'].name)
    cb = anim_utils.action_ensure_channelbag_for_slot(act, slot)
    return act, slot, cb


def get_fc(cb, ctrl, chan, a):
    path = 'pose.bones["%s"].%s' % (ctrl, PATH[chan])
    fc = cb.fcurves.find(path, index=a)
    if fc is None:
        fc = cb.fcurves.new(path, index=a)
        fc.group = cb.groups.get(ctrl) or cb.groups.new(ctrl)
    return fc


def write_keys(fc, d, cyclic, rot):
    fc.keyframe_points.clear()
    for f in sorted(d):
        v, ip = d[f]
        kp = fc.keyframe_points.insert(f, D(v) if rot else v, options={'FAST'})
        it, ease = IP[ip]
        kp.interpolation = it
        if ease:
            kp.easing = ease
        if it == 'ELASTIC':
            kp.amplitude = 0.0      # Blender's default 0.8 is an ABSOLUTE bounce: equal-valued keys would wobble +-0.8
        kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
    for m in list(fc.modifiers):
        fc.modifiers.remove(m)
    if cyclic and len(d) > 1:
        fc.modifiers.new('CYCLES')
    fc.update()


def write_baked(fc, frames, values):
    fc.keyframe_points.clear()
    for m in list(fc.modifiers):
        fc.modifiers.remove(m)
    fc.keyframe_points.add(len(frames))
    co = []
    for f, v in zip(frames, values):
        co += [f, v]
    fc.keyframe_points.foreach_set('co', co)
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
    fc.update()


# ---------------------------------------------------------------- spring pass
def _trs(l, q, s):
    return Matrix.Translation(l) @ q.to_matrix().to_4x4() @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))


def _strand_contact(p, q, a, b):
    """Closest approach between strand p->q and capsule axis a->b: (u along strand 0..1, point on axis, distance)."""
    best = None
    for i in range(8):                                   # strands are short: sampling is plenty
        u = 0.3 + 0.7 * i / 7.0                          # ignore the root third: a strand is attached there
        x = p + (q - p) * u
        ab = b - a
        t = 0.0 if ab.length_squared < 1e-12 else min(max((x - a).dot(ab) / ab.length_squared, 0.0), 1.0)
        c = a + ab * t
        dd = (x - c).length
        if best is None or dd < best[2]:
            best = (u, c, dd)
    return best


def _calibrate_colliders(spr):
    """Colliders must never fight the character as modelled: in the bind pose, if a strand already sits inside a
    capsule (hair styled against the head/back), that pair's radius shrinks to just under the existing clearance."""
    REST, COLL, COLLIDE = FW['REST'], FW.get('COLL', {}), FW.get('COLLIDE', {})
    bones = FW['bones']
    out = {}
    for c, names in COLLIDE.items():
        if c not in spr or c not in REST:
            continue
        cfg = spr[c]
        dv = cfg[4]
        d = V(dv) if dv is not None else dvec(c)
        piv = REST[c].translation
        tip = piv + d
        for cn in names:
            spec = COLL.get(cn)
            if spec is None:
                continue
            if spec[0] == 'bone':
                a, b, rad = bones[spec[1]].head_local, bones[spec[1]].tail_local, spec[2]
            else:
                a, b, rad = spec[1], spec[3], spec[4]
            u, cp, dist = _strand_contact(piv, tip, V(a), V(b))
            out[(c, cn)] = rad if dist >= rad else max(0.01, dist * 0.92)
    return out


def bake_springs(A, fcs, act=None, slot=None):
    """Simulate configured controls against the evaluated primary curves and bake per-frame rotations.
    Spring tuple: (freq Hz, damping ratio, weight 0-1, max deg, tip vector|None[, gravity 0-1]).
    gravity blends the target from parent-relative toward 'authored local rotation in world space' (pendulum props)."""
    CTRL, PARENT, PIV, REST = FW['CTRL'], FW['PARENT'], FW['PIV'], FW['REST']
    RROT = {c: REST[c].to_quaternion() for c in CTRL}
    spr = dict(FW['SPRING'], **{full(k): v for k, v in A.spring.items()})
    n = A.n
    sub = 8
    h = 1.0 / FW['FPS'] / sub

    def local(ctrl, f):
        ev = {}
        for chan in CH:
            ev[chan] = [fcs[(ctrl, chan, a)].evaluate(f) if (ctrl, chan, a) in fcs else DEFAULT[chan][a] for a in range(3)]
        return V(ev['l']), Euler(ev['r'], 'XYZ'), ev['s']

    FOLLOW = FW.get('FOLLOW', {})
    COLL, COLLIDE = FW.get('COLL', {}), FW.get('COLLIDE', {})
    sims = [c for c in CTRL if c in spr or c in FOLLOW]
    if not sims:
        return

    def follow_offset(c, W):
        off = [0.0, 0.0, 0.0]
        for ent in FOLLOW[c]:
            pc, tg = ent['pivot_ctrl'], ent['target']
            if pc not in W or tg not in W:
                raise RuntimeError('follow on %s needs %s and %s evaluated first (hierarchy depth)' % (c, pc, tg))
            pv = V(ent['pivot'])
            pw = W[pc] @ (REST[pc].inverted() @ pv)
            dl = W[pc].to_quaternion().inverted() @ (W[tg].translation - pw)
            sw = (RROT[pc].inverted() @ (PIV[tg] - pv)).rotation_difference(dl).to_euler('XYZ')
            w = ent.get('w', (1, 1, 1))
            cl = ent.get('clamp', ((-180, 180),) * 3)
            for a in range(3):
                off[a] += min(max(math.degrees(sw[a]) * w[a], cl[a][0]), cl[a][1])
        return off
    bone_cols = {cn for c in sims for cn in COLLIDE.get(c, ()) if COLL.get(cn, ('',))[0] == 'bone'}
    SAMPLED = {}
    if bone_cols and act is not None:                    # evaluate the IK-solved body once per frame
        arm = FW['arm']
        ad = arm.animation_data or arm.animation_data_create()
        keep = (ad.action, ad.action_slot)
        ad.action, ad.action_slot = act, slot
        scn = bpy.context.scene
        for f in range(n + 1):
            scn.frame_set(f)
            SAMPLED[f] = {cn: (arm.pose.bones[COLL[cn][1]].head.copy(), arm.pose.bones[COLL[cn][1]].tail.copy())
                          for cn in bone_cols}
        ad.action = keep[0]
        if keep[0] is not None and keep[1] is not None:
            ad.action_slot = keep[1]
    if A.loop:
        seq = [f for _ in range(3) for f in range(n)] + list(range(n + 1))
        rec_from = 3 * n
    else:
        rec_from = 20
        seq = [0] * rec_from + list(range(n + 1))
    state, prevT, out, contact = {}, {}, {c: [] for c in sims}, {}
    EFFR = _calibrate_colliders(spr)
    for i, f in enumerate(seq):
        W = {}
        for c in CTRL:
            l, e, s = local(c, f)
            if c in FOLLOW:
                fo = follow_offset(c, W)
                e = Euler((e.x + D(fo[0]), e.y + D(fo[1]), e.z + D(fo[2])), 'XYZ')
            q = e.to_quaternion()
            par = PARENT[c]
            Wp = Matrix.Identity(4) if par is None else W[par]
            off = _rel(c, par)
            Wa = Wp @ off @ _trs(l, q, s)
            if c in spr:
                cfg = spr[c]
                fr, z, wgt, mx, dv = cfg[:5]
                grav = cfg[5] if len(cfg) > 5 else 0.0
                d = RROT[c].inverted() @ (V(dv) if dv is not None else dvec(c))      # tip vector (rest world) -> local
                tgt = Wa @ d
                tgt_body = tgt.copy()                           # body-relative target: the side a collider pushes to
                if grav > 0:
                    # gravity removes the parent's pitch/roll but keeps its heading (yaw), so hanging parts turn with spins
                    fw0 = RROT[c] @ V((0, -1, 0))
                    fw1 = Wp.to_quaternion() @ (RROT[par] if par else Quaternion()).inverted() @ RROT[c] @ V((0, -1, 0))                         if par else fw0
                    a0, a1 = math.atan2(fw0.x, -fw0.y), math.atan2(fw1.x, -fw1.y)
                    yaw_q = Quaternion((0, 0, 1), a1 - a0)
                    tgt = tgt.lerp(Wa.translation + (yaw_q @ RROT[c] @ q).to_matrix() @ (d * Wa.to_scale()[0]), grav)
                st = state.get(c)
                if st is None:
                    st = state[c] = [tgt.copy(), V((0, 0, 0))]
                    prevT[c] = tgt.copy()
                wn = 2 * math.pi * fr
                k, damp = wn * wn, 2 * z * wn
                t0 = prevT[c]
                for j in range(sub):
                    tt = t0.lerp(tgt, (j + 1) / sub)
                    acc = (tt - st[0]) * k - st[1] * damp
                    st[1] += acc * h
                    st[0] += st[1] * h
                prevT[c] = tgt.copy()
                hit = False
                for cn in COLLIDE.get(c, ()):
                    spec = COLL[cn]
                    if spec[0] == 'bone':
                        if f not in SAMPLED:
                            continue
                        a, b = SAMPLED[f][cn]
                        rad = spec[2]
                    else:
                        ca, pa, cb, pb_, rad = spec
                        if ca not in W or cb not in W:
                            continue
                        a = W[ca] @ (REST[ca].inverted() @ pa)
                        b = W[cb] @ (REST[cb].inverted() @ pb_)
                    # segment-vs-capsule: the strand (pivot -> tip) against the collider axis a -> b
                    piv_ = Wa.translation
                    u, cp, dist = _strand_contact(piv_, st[0], a, b)
                    rad = EFFR.get((c, cn), rad)                     # bind-pose calibrated radius
                    hp = piv_ + (st[0] - piv_) * u                    # contact point on the strand
                    dv_ = hp - cp
                    ref = tgt_body - cp                              # the side the body-relative tip is on
                    wrong_side = (st[0] - cp).dot(ref) < 0 and (st[0] - cp).length < 2.5 * rad
                    if dist < rad or wrong_side:
                        if wrong_side or dist < 1e-6:
                            nrm = ref.normalized() if ref.length > 1e-6 else (piv_ - cp).normalized()
                        else:
                            nrm = dv_ / dist
                        if wrong_side:
                            st[0] = cp + nrm * rad                     # tunnelled: back onto the correct surface
                        else:
                            st[0] = st[0] + nrm * ((rad - dist) / max(u, 0.5))   # lever: mid-strand contact moves the tip more
                        vn = st[1].dot(nrm)
                        if vn < 0:
                            st[1] -= nrm * vn                      # kill inward velocity, keep the slide
                        hit = True
                        if FW.get('DEBUG_COLL') is not None:
                            FW['DEBUG_COLL'].setdefault((A.name, c, cn), []).append((f, round(dist, 3), round(rad, 3), round(u, 2)))
                fl_ = FW.get('FLOOR')
                if fl_ is not None and st[0].z < fl_[0] + fl_[1]:
                    st[0].z = fl_[0] + fl_[1]                        # floor: tips rest on the ground (+ strand thickness)
                    if st[1].z < 0:
                        st[1].z = 0.0
                qf = q
                lp = Wa.inverted_safe() @ st[0]
                if lp.length > 1e-6 and d.length > 1e-6:
                    oq = d.rotation_difference(lp)
                    hb = contact[c] = min(1.0, contact.get(c, 0.0) + 0.5) if hit else max(0.0, contact.get(c, 0.0) - 0.2)
                    lim, w_ = D(mx + (100 - mx) * hb), wgt + (1 - wgt) * hb  # colliders may push past the style clamp
                    if oq.angle > lim:
                        oq = Quaternion(oq.axis, lim)
                    qf = q @ Quaternion().slerp(oq, w_)
                Wa = Wp @ off @ _trs(l, qf, s)
                if i >= rec_from:
                    out[c].append((f, qf, e))
            elif c in FOLLOW and i >= rec_from:
                out[c].append((f, q, e))
            W[c] = Wa
    for c in sims:
        frames, cols = [], ([], [], [])
        prev = None
        for f, qf, e in out[c]:
            eu = qf.to_euler('XYZ', prev if prev is not None else e)
            prev = eu
            frames.append(float(f))
            for a in range(3):
                cols[a].append(eu[a])
        for a in range(3):
            write_baked(fcs[(c, 'r', a)], frames, cols[a])


def _upper_lower_sets():
    """Split controls into upper (under the branch through control, deform or space-switch parents) and lower."""
    U = FW['UPPER']
    bones, pb = FW['bones'], FW['pb']
    br = U['branch']
    br_def = FW['DEF_OF'].get(br)

    def is_upper(n):
        b = bones[n]
        seen = 0
        while b is not None and seen < 200:
            seen += 1
            if b.name in (br, br_def):
                return True
            if b.name.startswith('MCH_') and b.name in pb:
                con = next((c for c in pb[b.name].constraints if c.type == 'COPY_TRANSFORMS' and c.subtarget), None)
                if con:
                    b = bones[con.subtarget]
                    continue
            b = b.parent
        return False
    lower = [c for c in FW['CTRL'] if not is_upper(c)]
    return lower


def apply_upper_body(A, fcs):
    """Hold the lower body at the base pose; move the root's rotation (relative to base) onto the branch."""
    U = FW['UPPER']
    root, br = U['root'], U['branch']
    if FW['PARENT'].get(br) != root:
        raise RuntimeError('upper_split branch %s must be a direct child of %s' % (br, root))
    BASE = FW['BASE']

    def ev(c, chan, f):
        return [fcs[(c, chan, a)].evaluate(f) if (c, chan, a) in fcs else DEFAULT[chan][a] for a in range(3)]
    rel_root = _rel(root, FW['PARENT'].get(root)).to_quaternion()
    rel_br = _rel(br, root).to_quaternion()
    q_base = rel_root @ Euler([D(x) for x in BASE.get((root, 'r'), (0, 0, 0))], 'XYZ').to_quaternion()
    frames, cols, prev = [], ([], [], []), None
    for f in range(A.n + 1):
        q_anim = rel_root @ Euler(ev(root, 'r', f), 'XYZ').to_quaternion()
        q_sp = Euler(ev(br, 'r', f), 'XYZ').to_quaternion()
        q_new = rel_br.inverted() @ q_base.inverted() @ q_anim @ rel_br @ q_sp
        e = q_new.to_euler('XYZ', prev) if prev is not None else q_new.to_euler('XYZ')
        prev = e
        frames.append(float(f))
        for a in range(3):
            cols[a].append(e[a])
    for a in range(3):
        write_baked(fcs[(br, 'r', a)], frames, cols[a])
    for c in _upper_lower_sets():
        for chan in CH:
            b = BASE.get((c, chan), DEFAULT[chan])
            for a in range(3):
                if (c, chan, a) in fcs:
                    write_keys(fcs[(c, chan, a)], {0: (b[a], 'C')}, False, chan == 'r')


def build(A):
    act, slot, cb = new_action(A.name)
    fcs = {}
    for (ctrl, chan, a), d in A.resolve().items():
        fc = get_fc(cb, ctrl, chan, a)
        write_keys(fc, d, A.loop, chan == 'r')
        fcs[(ctrl, chan, a)] = fc
    if getattr(A, 'upper_body', False) and FW.get('UPPER'):
        apply_upper_body(A, fcs)
    bake_springs(A, fcs, act, slot)
    for name in set(FW.get('PROPS', {})) | set(A.props):       # settings props: constant default unless keyed
        d = A.props.get(name) or {0: (FW['PROPS'].get(name, 0.0), 'C')}
        fc = cb.fcurves.find('pose.bones["%s"]["%s"]' % (FW['SET'], name)) or \
            cb.fcurves.new('pose.bones["%s"]["%s"]' % (FW['SET'], name))
        fc.group = cb.groups.get(FW['SET']) or cb.groups.new(FW['SET'])
        write_keys(fc, d, False, False)
    if A.hooks:
        ad = FW['arm'].animation_data or FW['arm'].animation_data_create()
        ad.action, ad.action_slot = act, slot
        for fn in A.hooks:
            fn(act, A)
    if FW.get('INTERP'):
        for fc in cb.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = FW['INTERP']
            fc.update()
    act.use_frame_range = True
    act.frame_start, act.frame_end = 0, A.n
    act.use_cyclic = A.loop
    for name, f in A.markers.items():
        m = act.pose_markers.new(name)
        m.frame = int(f)
    act['loop'] = A.loop
    return act


def world_matrix(ctrl, f):
    """Armature-space matrix of a pose bone at frame f (evaluates the assigned action, constraints included)."""
    bpy.context.scene.frame_set(int(f))
    return FW['pb'][full(ctrl)].matrix.copy()


def key_matrix(act, ctrl, f, M, ip='B'):
    """Key ctrl's loc/rot/scale at frame f so its armature-space matrix equals M (respecting whatever its parent /
    space switch is doing at f). Use in A.after hooks for hand-offs between spaces (drop / pick up props)."""
    ctrl = full(ctrl)
    sc = bpy.context.scene
    sc.frame_set(int(f))
    p = FW['pb'][ctrl]
    p.matrix = M
    bpy.context.view_layer.update()
    vals = {'l': tuple(p.location), 'r': tuple(p.rotation_euler), 's': tuple(p.scale)}
    cb = anim_utils.action_get_channelbag_for_slot(act, act.slots[0])
    it, ease = IP[ip]
    for chan, v in vals.items():
        for a in range(3):
            fc = get_fc(cb, ctrl, chan, a)
            kp = fc.keyframe_points.insert(f, v[a])
            kp.interpolation = it
            if ease:
                kp.easing = ease
            if it == 'ELASTIC':
                kp.amplitude = 0.0
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
            fc.update()
    sc.frame_set(int(f))
    return vals


def reset_rig():
    for p in FW['pb']:
        p.location = (0, 0, 0)
        p.rotation_quaternion = (1, 0, 0, 0)
        p.rotation_euler = (0, 0, 0)
        p.scale = (1, 1, 1)


def build_all(only=None, default='Idle'):
    """Build every @clip (or the subset `only`), assign `default` and set the scene range."""
    arm = FW['arm']
    hidden = [(m, m.hide_viewport) for m in FW['meshes']]
    built = []
    try:
        reset_rig()
        for fn in CLIPS:
            if only and fn.__name__ not in only:
                continue
            built.append(build(fn()).name)
    finally:
        for m, h in hidden:
            m.hide_viewport = h
    ad = arm.animation_data or arm.animation_data_create()
    first = bpy.data.actions.get(default) or (bpy.data.actions.get(built[0]) if built else None)
    if first:
        ad.action = first
        ad.action_slot = first.slots[0]
        sc = bpy.context.scene
        sc.render.fps = FW['FPS']
        sc.frame_start, sc.frame_end = int(first.frame_range[0]), int(first.frame_range[1])
        sc.frame_set(0)
    return built


# ---------------------------------------------------------------- match an existing clip
def pose_from_action(armature, action, frame, digits=2, refine=0):
    """Control values that reproduce an existing DEFORM-bone action's pose at `frame` (e.g. the game's shipped idle),
    so new clips start/end on it. Returns a base_pose dict {short_ctrl: {'l':..., 'r':...}} (non-zero entries only):
    FK/torso controls from their deform bone, IK targets from the end bone's rotation + the lower chain bone's
    tail (works with end_mode 'rotation' or 'transforms'), poles carried with the chain's top bone; undriven controls
    stay at rest. refine=N: N coordinate-descent passes on IK target/pole locations through the real rig (use ~40 when
    a limb is nearly straight in the reference - its bend plane is ill-conditioned)."""
    arm = bpy.data.objects[armature]
    bones = arm.data.bones
    act = bpy.data.actions[action]
    cb = anim_utils.action_get_channelbag_for_slot(act, act.slots[0])
    ev = {}
    for fc in cb.fcurves:
        if not fc.data_path.startswith('pose.bones["'):
            continue
        b, ch = fc.data_path.split('"')[1], fc.data_path.rsplit('.', 1)[-1]
        ev.setdefault(b, {}).setdefault(ch, {})[fc.array_index] = fc.evaluate(frame)

    def basis(b):
        d = ev.get(b, {})
        lo = d.get('location', {})
        loc = V([lo.get(i, 0.0) for i in range(3)])
        if 'rotation_quaternion' in d:
            q = d['rotation_quaternion']
            rot = Quaternion([q.get(i, 1.0 if i == 0 else 0.0) for i in range(4)]).normalized().to_matrix().to_4x4()
        elif 'rotation_euler' in d:
            e = d['rotation_euler']
            rot = Euler([e.get(i, 0.0) for i in range(3)], arm.pose.bones[b].rotation_mode
                        if arm.pose.bones[b].rotation_mode in ('XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX') else 'XYZ').to_matrix().to_4x4()
        else:
            rot = Matrix.Identity(4)
        return Matrix.Translation(loc) @ rot
    M = {}

    def deform_world(b):
        if b not in M:
            bb = bones[b]
            rel = bb.matrix_local if bb.parent is None else bb.parent.matrix_local.inverted() @ bb.matrix_local
            M[b] = (Matrix.Identity(4) if bb.parent is None else deform_world(bb.parent.name)) @ rel @ basis(b)
        return M[b]
    deform = [b.name for b in bones if not b.name.startswith(('CTRL_', 'MCH_', 'SNAP_'))]
    for b in deform:
        deform_world(b)
    drives = {b.parent.name: b.name[5:] for b in bones if b.name.startswith('SNAP_') and b.parent}
    ik_lower, poles = {}, {}
    for p in arm.pose.bones:
        for c in p.constraints:
            if c.type == 'IK' and p.name.startswith('MCH_IK_'):
                ik_lower[c.subtarget] = p.name[7:]
                top = bones[p.name[7:]]
                for _ in range(c.chain_count - 1):
                    top = top.parent
                if c.pole_subtarget:
                    poles[c.pole_subtarget] = (top.name, p.name[7:])

    ik_end = {b.parent.name: b.name[8:] for b in bones if b.name.startswith('MCH_IKT_') and b.parent}
    W = {}
    for b in bones:                                       # desired armature-space matrices of the controls
        n, R = b.name, b.matrix_local
        if n in drives and drives[n] in M:
            d = drives[n]
            W[n] = M[d] @ bones[d].matrix_local.inverted() @ R
        elif n in ik_end and n in ik_lower:
            e, lo = ik_end[n], ik_lower[n]
            pos = M[lo] @ (bones[lo].matrix_local.inverted() @ R.translation)
            rot = (M[e].to_quaternion() @ bones[e].matrix_local.to_quaternion().inverted()) @ R.to_quaternion()
            W[n] = Matrix.Translation(pos) @ rot.to_matrix().to_4x4()
        elif n in poles:                                  # pole rides rigidly with the chain's top bone (keeps its twist)
            up, lo = poles[n]
            W[n] = Matrix.Translation(M[up] @ (bones[up].matrix_local.inverted() @ R.translation)) @                 R.to_quaternion().to_matrix().to_4x4()
    out, done = {}, {}

    def world(n):                                         # actual (posed) armature matrix of any bone
        if n in done:
            return done[n]
        b = bones[n]
        if not n.startswith(('CTRL_', 'MCH_', 'SNAP_')):
            done[n] = M[n]
            return M[n]
        pw = Matrix.Identity(4) if b.parent is None else world(b.parent.name)
        rel = b.matrix_local if b.parent is None else b.parent.matrix_local.inverted() @ b.matrix_local
        if n in W and n.startswith('CTRL_'):
            loc_m = (pw @ rel).inverted() @ W[n]
            l, q, _ = loc_m.decompose()
            e = q.to_euler('XYZ')
            vals = dict(l=tuple(round(x, 4) for x in l), r=tuple(round(math.degrees(x), digits) for x in e))
            ent = {k: v for k, v in vals.items() if max(abs(x) for x in v) > (1e-3 if k == 'l' else 0.05)}
            if ent:
                out[n[5:]] = ent
            done[n] = pw @ rel @ Matrix.Translation(l) @ q.to_matrix().to_4x4()
        else:
            done[n] = pw @ rel
        return done[n]
    for b in bones:
        if b.name.startswith('CTRL_'):
            world(b.name)
    if refine:
        _refine_ik(arm, out, M, ik_lower, poles, refine, ik_end)
    return out


def _refine_ik(arm, out, M, ik_lower, poles, iters, end_of=None):
    """Nearly straight IK limbs are ill-conditioned: coordinate-descend the IK target and pole locations (evaluated
    through the real rig) until the chain's deform bones match the reference matrices M."""
    pb, bones = arm.pose.bones, arm.data.bones
    ad = arm.animation_data
    keep_act = (ad.action, ad.action_slot) if ad else None
    keep = {p.name: (tuple(p.location), tuple(p.rotation_euler), tuple(p.rotation_quaternion), tuple(p.scale)) for p in pb}
    if ad:
        ad.action = None
    for p in pb:
        p.location = (0, 0, 0); p.rotation_quaternion = (1, 0, 0, 0); p.rotation_euler = (0, 0, 0); p.scale = (1, 1, 1)
    for k, v in out.items():
        p = pb['CTRL_' + k]
        p.location = v.get('l', (0, 0, 0))
        p.rotation_euler = [D(x) for x in v.get('r', (0, 0, 0))]
    pole_of = {v[1]: k for k, v in poles.items()}
    # the IK/FK switches are custom props: force IK while refining (otherwise the result depends on whatever value the
    # last evaluated frame left behind - FK makes the descent a no-op)
    switches = []
    if ad:
        for d in ad.drivers:
            if d.data_path.endswith('constraints["IK"].influence') and d.driver.variables:
                t = d.driver.variables[0].targets[0]
                if t.id == arm and t.data_path.startswith('pose.bones["'):
                    bn, pn = t.data_path.split('"')[1], t.data_path.split('"')[3]
                    if (bn, pn) not in [x[:2] for x in switches]:
                        switches.append((bn, pn, pb[bn][pn]))
    for bn, pn, _ in switches:
        pb[bn][pn] = 1.0
    try:
        for tgt, lo in ik_lower.items():
            chain = [lo, bones[lo].parent.name] + ([(end_of or {}).get(tgt)] if (end_of or {}).get(tgt) else [])
            pole = pole_of.get(lo)

            def err():
                bpy.context.view_layer.update()
                e = 0.0
                for d in chain:
                    a = pb[d].matrix.to_quaternion().rotation_difference(M[d].to_quaternion()).angle
                    e += math.degrees(min(a, 2 * math.pi - a)) + 100 * (pb[d].matrix.translation - M[d].translation).length
                return e
            knobs = [(tgt, 0.02)] + ([(pole, 0.08)] if pole else [])
            best = err()
            for _ in range(iters):
                improved = False
                for name, step in knobs:
                    p = pb[name]
                    for ax in range(3):
                        for sgn in (1, -1):
                            p.location[ax] += sgn * step
                            e = err()
                            if e < best - 1e-4:
                                best, improved = e, True
                                break
                            p.location[ax] -= sgn * step
                if not improved:
                    knobs = [(n, s * 0.5) for n, s in knobs]
                    if knobs[0][1] < 1e-4:
                        break
            for name, _ in knobs:
                out.setdefault(name[5:], {})['l'] = tuple(round(x, 4) for x in pb[name].location)
    finally:
        for bn, pn, v in switches:
            pb[bn][pn] = v
        for p in pb:
            l, e, q, sc = keep[p.name]
            p.location, p.rotation_euler, p.rotation_quaternion, p.scale = l, e, q, sc
        if keep_act and keep_act[0] is not None:
            ad.action = keep_act[0]
            ad.action_slot = keep_act[1]


# ---------------------------------------------------------------- QA helpers
def _seg_dist(p1, q1, p2, q2):
    """Closest distance between segments p1-q1 and p2-q2."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = d1.dot(d1), d2.dot(d2), d2.dot(r)
    if a < 1e-9 and e < 1e-9:
        return r.length
    if a < 1e-9:
        s, t = 0.0, min(max(f / e, 0.0), 1.0)
    else:
        c = d1.dot(r)
        if e < 1e-9:
            t, s = 0.0, min(max(-c / a, 0.0), 1.0)
        else:
            b = d1.dot(d2)
            den = a * e - b * b
            s = min(max((b * f - c * e) / den, 0.0), 1.0) if den > 1e-9 else 0.0
            t = (b * s + f) / e
            if t < 0:
                t, s = 0.0, min(max(-c / a, 0.0), 1.0)
            elif t > 1:
                t, s = 1.0, min(max((b - c) / a, 0.0), 1.0)
    return ((p1 + d1 * s) - (p2 + d2 * t)).length


def qa_clipping(capsules, pairs, actions=None, step=1, tolerance=0.02):
    """Self-intersection sweep. capsules: {name: (bone, radius) or (bone_a_head, bone_b_head, radius) or
    (bone, radius, (y_offset_scale...))}; pairs: [(capsule_a, capsule_b)]. A capsule spec (bone, r) uses the bone's
    head->tail; ('head:A', 'head:B', r) uses two joint positions. Returns {action: [(frame, a, b, depth_m)]} worst-first."""
    arm, sc = FW['arm'], bpy.context.scene
    pbs = arm.pose.bones

    def seg(spec):
        if callable(spec):                       # custom: fn(pose_bones) -> (p, q, radius), e.g. a weapon along its axis
            return spec(pbs)
        if isinstance(spec[0], str) and ':' in spec[0]:
            pts = []
            for s in spec[:2]:
                kind, b = s.split(':')
                pts.append(pbs[b].head.copy() if kind == 'head' else pbs[b].tail.copy())
            return pts[0], pts[1], spec[2]
        b = pbs[spec[0]]
        return b.head.copy(), b.tail.copy(), spec[1]
    ad = arm.animation_data
    keep = (ad.action, ad.action_slot, sc.frame_current)
    hidden = [(m, m.hide_viewport) for m in FW['meshes']]
    for m, _ in hidden:
        m.hide_viewport = True
    rep = {}
    try:
        acts = [a for a in bpy.data.actions if a.get(FW['TAG'])] if actions is None else [bpy.data.actions[a] for a in actions]
        for act in acts:
            ad.action, ad.action_slot = act, act.slots[0]
            hits = {}
            for f in range(int(act.frame_range[0]), int(act.frame_range[1]) + 1, step):
                sc.frame_set(f)
                S = {k: seg(v) for k, v in capsules.items()}
                for a, b in pairs:
                    pa, qa, ra = S[a]
                    pb_, qb, rb = S[b]
                    depth = ra + rb - _seg_dist(pa, qa, pb_, qb)
                    if depth > tolerance and depth > hits.get((a, b), (0, 0))[1]:
                        hits[(a, b)] = (f, depth)
            if hits:
                rep[act.name] = sorted([(f, a, b, round(dp, 3)) for (a, b), (f, dp) in hits.items()], key=lambda x: -x[3])
    finally:
        for m, h in hidden:
            m.hide_viewport = h
        ad.action, ad.action_slot = keep[0], keep[1]
        sc.frame_set(keep[2])
    return rep
def qa_report(actions=None, body_bone=None, exclude_groups=()):
    """Loop seam error (deform matrices frame 0 vs N), body height at frame 0, min mesh z at start/end."""
    arm, sc = FW['arm'], bpy.context.scene
    meshes = FW['meshes']
    skip = set()
    for m in meshes:
        for gname in exclude_groups:
            g = m.vertex_groups.get(gname)
            if g:
                skip |= {(m.name, v.index) for v in m.data.vertices if any(x.group == g.index and x.weight > 0.5 for x in v.groups)}

    def minz():
        z = 1e9
        dg = bpy.context.evaluated_depsgraph_get()
        for m in meshes:
            ev = m.evaluated_get(dg)
            me = ev.to_mesh()
            for v in me.vertices:
                if (m.name, v.index) not in skip:
                    z = min(z, (m.matrix_world @ v.co).z)
            ev.to_mesh_clear()
        return z

    def mats():
        return {b.name: arm.pose.bones[b.name].matrix.copy() for b in arm.data.bones if b.use_deform}
    rep = {}
    ad = arm.animation_data
    keep = (ad.action, ad.action_slot)
    for act in [a for a in bpy.data.actions if a.get(FW['TAG'])] if actions is None else [bpy.data.actions[a] for a in actions]:
        ad.action, ad.action_slot = act, act.slots[0]
        N = int(act.frame_range[1])
        sc.frame_set(0); m0 = mats(); z0 = minz()
        bz = arm.pose.bones[body_bone].head.z if body_bone else None
        sc.frame_set(N); mN = mats(); zN = minz()
        seam = sum((m0[k].translation - mN[k].translation).length +
                   m0[k].to_quaternion().rotation_difference(mN[k].to_quaternion()).angle for k in m0)
        rep[act.name] = dict(frames=N, loop=bool(act.get('loop')), seam=round(seam, 4), minz_start=round(z0, 3),
                             minz_end=round(zN, 3), body_z=round(bz, 3) if bz is not None else None,
                             events={m.name: m.frame for m in act.pose_markers})
    ad.action, ad.action_slot = keep
    return rep
