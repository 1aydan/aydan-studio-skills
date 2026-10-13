# <CHARACTER> - one video of every clip back to back (review / sharing): assets/<slug>/renders/<Char>_reel.mp4
#   p = r"<skill>\assets\<slug>\reel.py"; g = {'__file__': p}; exec(open(p).read(), g); g['REEL']
# Optional globals: ORDER = ['Idle', ...] (default: CLIPS below), VIEW = 'front3q', LOOPS = 2, HOLD = 10, SCALE = 0.75
#   LOOK = 'beauty': full-colour EEVEE 1920x1080 (own materials, floor + soft lights) -> <Char>_beauty.mp4
# Clip names are burnt in (name, length, LOOP xN / root motion, event markers). The camera follows FOLLOW; root-motion
# clips travel out of a fixed frame, so the follow camera keeps them centred. Restores the scene afterwards.
import os, bpy

HERE = os.path.dirname(os.path.abspath(__file__))  # this character's folder: assets/<slug>/ (outputs land here)
SKILL = os.path.dirname(os.path.dirname(HERE))     # the skill folder
cam = {'__file__': os.path.join(SKILL, 'scripts', 'anim_review_camera.py')}
exec(open(cam['__file__'], encoding='utf-8').read(), cam)

CHAR = 'TODOCharacter'
ARM = 'TODO_armature_object'
FOLLOW = 'CTRL_COG'
CLIPS = ['Idle']                     # TODO presentation order (idle, locomotion, attacks, reactions, death last)
HEIGHT = 1.8                         # TODO character height (camera distance / aim)

LOOK = globals().get('LOOK', 'review')
RES = (1920, 1080) if LOOK == 'beauty' else (960, 960)

try:
    cam['setup'](ARM, FOLLOW, distance=2.3 * HEIGHT, follow_z=False, res=RES, look=LOOK)
    bpy.data.objects['ANIM_CamPivot'].location.z = 0.5 * HEIGHT
    REEL = cam['reel'](os.path.join(HERE, 'renders', '%s_%s.mp4' % (CHAR, 'beauty' if LOOK == 'beauty' else 'reel')),
                       actions=globals().get('ORDER') or CLIPS, view=globals().get('VIEW', 'front3q'),
                       loop_repeats=globals().get('LOOPS', 2), hold=globals().get('HOLD', 10),
                       scale=globals().get('SCALE', 1.0 if LOOK == 'beauty' else 0.75))
finally:
    cam['teardown']()                # scene camera, engine and the model's Preview rig back as they were
print(REEL)
