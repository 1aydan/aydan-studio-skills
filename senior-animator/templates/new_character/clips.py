# <CHARACTER> - clip set on top of scripts/anim_framework.py (run rig_config.py first).
#   p = r"<skill>\assets\<slug>\clips.py"; g = {'__file__': p}; exec(open(p).read(), g); g['BUILT']
# Optional globals before exec: ONLY = ['Idle', ...]
#
# Authoring API (degrees, world axes, character faces -Y):
#   A = Anim('Name', frames, loop=False)
#   A.set({...})                 clip base pose (absolute)          A.set_raw('Ctrl_R', 'r', (x,y,z)) no mirroring
#   A.pose(f, P(...), ip)        blocking key of every posed channel; ip = how the key LEAVES:
#                                B bezier | L | C | qi/qo/qio | ci/co/cio | xi/xo | bo/bi (overshoot) | eo (elastic) | si/so/sio
#   A.key(ctrl, 'l'|'r'|'s', f, value, ip)     A.keyx('Shoulder', 'r', f, (x,y,z))  mirrored pair
#   A.wave(ctrl, chan, axis, amp, period, phase, center=None)   sine keyed at extremes (loops)
#   A.spring['Ctrl'] = (...)     per-clip spring override           A.mark(f, 'Fire')  gameplay event
#   other = A.mirrored('move_right')                               base_val(ctrl, chan), add(a, b), P(*dicts)
import os
from mathutils import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__))  # this character's folder: assets/<slug>/ (outputs land here)
SKILL = os.path.dirname(os.path.dirname(HERE))     # the skill folder
exec(open(os.path.join(SKILL, 'scripts', 'anim_framework.py'), encoding='utf-8').read(), globals())

ONLY = globals().get('ONLY')
HOVER = 0.0          # TODO gameplay height on CTRL_Hover (e.g. 5.0 for a flying pet); 0 for ground characters

BASE_P = {           # TODO the idle pose every clip starts/ends in
    'Hover': dict(l=(0, 0, HOVER)),
    'COG': dict(r=(0, 0, 0)),
}

# follow-through: freq Hz, damping ratio, weight, max deg, tip vector override[, gravity 0-1]; '_L' auto-mirrors
# Typical: ears/antennae 2.5-3.5 Hz 0.25, tails 2-2.5 Hz 0.28, hanging props 1.5-2 Hz 0.3 + gravity 0.6,
#          limbs 2.2-4 Hz 0.3 weight 0.9, head/chest/pelvis 3-3.5 Hz 0.5 weight 0.3-0.5 (keeps aim)
SPRINGS = {
    # 'Tail': (2.1, 0.28, 1.0, 55, None),
    # 'Head': (3.5, 0.5, 0.35, 10, None),
}

configure(armature='TODO_armature_object', meshes=['TODO_mesh_object'], base_pose=BASE_P, springs=SPRINGS,
          action_tag='todo_anim', fps=30)          # action_tag must match rig_config panel + export.py


@clip
def Idle():
    A = Anim('Idle', 60, loop=True)
    A.wave('COG', 'l', 2, 0.03, 60, 0)              # breathe / bob
    A.wave('COG', 'r', 0, 1.5, 60, 9)               # pitch lags the bob
    A.wave('Head', 'r', 2, 3.0, 60, 5)
    return A


@clip
def Attack_01():
    A = Anim('Attack_01', 36)
    A.pose(0)
    A.pose(8, P(COG=dict(l=(0, 0.2, 0), r=(-12, 0, 0)), Head=dict(r=(-10, 0, 0))), 'qi')     # anticipation
    A.pose(12, P(COG=dict(l=(0, -0.3, 0), r=(6, 0, 0)), Head=dict(r=(0, 0, 0))), 'qo')       # fire: stay on the aim line
    A.pose(16, P(COG=dict(l=(0, 0.12, 0), r=(-5, 0, 0))), 'B')                               # recoil
    A.pose(23, P(COG=dict(l=(0, -0.04, 0), r=(3, 0, 0))), 'B')                               # overshoot
    A.pose(36)
    A.mark(12, 'Fire')
    return A


BUILT = build_all(only=ONLY, default='Idle')
print('built', BUILT)
