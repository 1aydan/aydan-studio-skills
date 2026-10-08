# <ASSET> - handoff to the Senior Animator skill (characters / creatures / anything that will be animated with bones).
#   p = r"<skill>\assets\<slug>\handoff.py"; g = {'__file__': p}; exec(open(p).read(), g); g['REPORT']
# Builds <Name>_SK (deform skeleton fitted to the model, rest = bind pose) + <Name> (joined skinned mesh, source parts
# hidden but kept), checks the weights, renders a pose test, writes handoff.md here and
# <senior-animator>/assets/<slug>/handoff_from_modeler.md. Re-run after model changes (re-skins; refuses to replace a skeleton the animator rigged).
import os

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brief.py'), encoding='utf-8').read(), globals())
L = {n: lib(n) for n in ('model_kit', 'handoff')}
ho = L['handoff']

B = BRIEF
H = B['height_m']
N = B['name']
u = lambda x, y, z: (x * H, y * H, z * H)
# pa = lambda p, part: tuple(ho['posed'](u(*p), '%s_%s' % (N, part)))   # landmarks on posed groups (T -> A arms)

# TODO landmarks in subject heights (from the concept measurements / build.py), character's LEFT side + centre
LM = dict(
    pelvis=u(0, 0, 0.50), spine=u(0, 0, 0.58), chest=u(0, 0, 0.68), neck=u(0, 0, 0.82), head=u(0, 0, 0.86),
    head_top=u(0, 0, 1.0),
    clavicle=u(0.02, 0, 0.80), shoulder=u(0.10, 0, 0.80), elbow=u(0.25, 0.01, 0.80), wrist=u(0.38, 0, 0.80),
    hand_tip=u(0.46, 0, 0.80),
    hip=u(0.06, 0, 0.50), knee=u(0.06, -0.01, 0.27), ankle=u(0.06, 0, 0.05), ball=u(0.06, -0.07, 0.01),
    toe=u(0.06, -0.12, 0.01),
)
EXTRA = []        # e.g. dict(name='jaw', head=..., tail=..., parent='head'), dict(name='L_ear', ...) (L_ mirrors)
bones = ho['biped'](LM, arm_segments=2, leg_segments=2, extra=EXTRA)     # 1 segment = rigid one-piece limbs
ho['build_skeleton'](N, bones, force=globals().get('FORCE', False))   # FORCE only with the user's OK

if B.get('deforming'):
    skin = ho['skin_auto'](N)                                            # one soft mesh, heat weights
else:
    RULES = {}    # TODO {'Hat*': 'head', 'Sleeve_L': 'L_upperarm', ...}; unmatched parts -> nearest bone
    skin = ho['skin_rigid'](N, RULES)
QA = ho['check'](N, rigid=not B.get('deforming'))
TEST = ho['pose_test'](N, {'L_upperarm': (0, 0, -50), 'R_upperarm': (0, 0, 30), 'L_thigh': (-35, 0, 0),
                          'L_calf': (40, 0, 0), 'head': (0, 25, 0)},
                       os.path.join(HERE, 'renders', 'handoff_pose_test.png'))
NOTES = ho['write_handoff'](N, SLUG, dict(mesh=skin['mesh'], height=H, pose=B.get('pose'), style=B['style'],
                                          skin='auto weights' if B.get('deforming') else 'rigid parts',
                                          springs={}, notes=[]))
REPORT = dict(bones=len(bones), qa=QA, pose_test=TEST['path'], notes=NOTES)
print(REPORT)
