# <CHARACTER> - control rig config for scripts/rig_builder.py
# 1. Prefer: inspect_character.draft_rig_config(ARM, MESH, path, slug) writes a buildable draft for ANY skeleton.
#    Otherwise copy this folder to assets/<character_slug>/ and fill it in by hand.
# 2. FACING / SIDE_TOKENS come from inspect_character.analyze(); bone names from inspect().
# 3. Run inside Blender:
#    p = r"<skill>\assets\<slug>\rig_config.py"; g = {'__file__': p}; exec(open(p).read(), g); g['REPORT']
#    REPORT must show rest_errors == {} and pole errors ~0.
#
# Rules
#   - Every deform bone that should be animatable gets exactly one control with drives='<deform>'.
#     Unweighted / helper deform bones can stay undriven (they follow their deform parent).
#   - pivot: (x,y,z) | 'head:Bone' | 'tail:Bone' | 'mid:Bone'.  offset: (x,y,z) | 'seg:A>B' | 'half:Bone'.
#   - shapes: root, hover, cog, ring_xy (horizontal), ring_xz (around a -Y/+Y running torso), ring_yz, sphere, diamond, cube.
#   - palette: 'C' center, 'L', 'R', 'MAIN', 'IK', 'FX' or a Blender THEMExx id.
#   - CTRL_Hover only matters for flyers / hover offsets; keep it anyway (zero for ground characters).
import os

HERE = os.path.dirname(os.path.abspath(__file__))  # this character's folder: assets/<slug>/ (outputs land here)
SKILL = os.path.dirname(os.path.dirname(HERE))     # the skill folder
lib = {'__file__': os.path.join(SKILL, 'scripts', 'rig_builder.py')}
exec(open(lib['__file__'], encoding='utf-8').read(), lib)
FACING = '-Y'                        # TODO analyze()['facing']
SIDE_TOKENS = ('L_', 'R_')           # TODO analyze()['side_tokens'] (character's left first)
sides = lambda fn: lib['sides'](fn, SIDE_TOKENS)   # sides(lambda s, S, sx: [...]): s='L'/'R', S=token, sx=+1 left

ARM = 'TODO_armature_object'
ROOT_DEFORM = 'Root'                 # TODO deform root bone (or None)
COG_DEFORM = 'Pelvis'                # TODO bone the body/COG drives (hips / body)
COG_PIVOT = (0, 0, 1.0)              # TODO roughly the centre of mass

CONTROLS = [
    dict(name='CTRL_Root', pivot=(0, 0, 0), parent=None, drives=ROOT_DEFORM, shape='root', size=1.5, palette='MAIN', collection='Main', wire=2.5, length=0.3),
    dict(name='CTRL_Hover', pivot=(0, 0, 0), parent='CTRL_Root', shape='hover', size=1.2, offset=(0, 0, 0.1), palette='MAIN', collection='Main', wire=2.2),
    dict(name='CTRL_COG', pivot=COG_PIVOT, parent='CTRL_Hover', drives=COG_DEFORM, shape='cog', size=(0.8, 1.0, 1), palette='MAIN', collection='Main', wire=2.5),
    # TODO torso chain, e.g.
    dict(name='CTRL_Spine', pivot='head:Spine', parent='CTRL_COG', drives='Spine', shape='ring_xz', size=0.6, collection='Torso'),
    dict(name='CTRL_Chest', pivot='head:Chest', parent='CTRL_Spine', drives='Chest', shape='ring_xz', size=0.6, collection='Torso'),
    dict(name='CTRL_Head', pivot='head:Head', parent='CTRL_Chest', drives='Head', shape='ring_xz', size=0.5, offset='half:Head', collection='Head', wire=2.2),
    # TODO tail / ears / props (props that swing: put the pivot where they hang from)
]
CONTROLS += sides(lambda s, S, sx: [
    # TODO limb chains (FK). Front/arm and back/leg examples:
    dict(name='CTRL_Shoulder_' + s, pivot='head:%sShoulder' % S, parent='CTRL_Chest', drives=S + 'Shoulder', shape='ring_xy', size=0.2, offset='seg:%sShoulder>%sElbow' % (S, S), palette=s, collection='Limbs FK'),
    dict(name='CTRL_Elbow_' + s, pivot='head:%sElbow' % S, parent='CTRL_Shoulder_' + s, drives=S + 'Elbow', shape='ring_xy', size=0.16, offset='seg:%sElbow>%sWrist' % (S, S), palette=s, collection='Limbs FK'),
    dict(name='CTRL_Wrist_' + s, pivot='head:%sWrist' % S, parent='CTRL_Elbow_' + s, drives=S + 'Wrist', shape='ring_xy', size=0.12, offset='half:%sWrist' % S, palette=s, collection='Limbs FK'),
])

# Space switches: a control whose parent is 'MCH_<name>_Parent' follows `follow` with influence = prop.
SPACES = [
    # dict(name='Prop', pivot=(0, 0, 0), parent='CTRL_Root', follow='CTRL_Head', prop='Prop_Follow_Head', default=1.0),
]

# IK: chain = deform bones solved by IK (the last one's tail reaches the target), end = bone after the chain
# that copies the target's rotation, root_parent = SNAP_ bone of the bone above the chain.
IK = sides(lambda s, S, sx: [
    dict(key='Arm_' + s, chain=[S + 'Shoulder', S + 'Elbow'], end=S + 'Wrist', target='CTRL_IK_Hand_' + s,
         target_pivot='head:%sWrist' % S, target_parent='CTRL_Root', pole='CTRL_Pole_Arm_' + s, pole_pos=(0.5 * sx, 0.5, 1.0),
         root_parent='SNAP_Chest', prop='IK_Arm_' + s, collection='Limbs IK'),
])

CFG = dict(
    armature=ARM,
    facing=FACING,
    side_tokens=SIDE_TOKENS,
    settings_bone='CTRL_Root',
    controls=CONTROLS,
    spaces=SPACES,
    ik=IK,
    collections={'Limbs IK': False},
    panel=dict(id='TODOCHAR', label='TODO Rig', category='TODO Rig', action_tag='todo_anim'),   # action_tag must match clips.py
    widget_prefix='WGT_TODO_',
    widget_collection='WGT_TODO',
)

REPORT = lib['build_rig'](CFG)
print('rig report', REPORT)
