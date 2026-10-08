# <ASSET> - review pack + QA -> assets/<slug>/renders/r##/ (numbered revision). Show the sheets to the user.
#   p = r"<skill>\assets\<slug>\review.py"; g = {'__file__': p, 'STAGE': 'blockout', 'NOTE': 'r01 blockout'}; exec(open(p).read(), g); g['REPORT']
# STAGE: blockout (clay + silhouette vs concept) | model (+ wire, parts legend) | final (+ material, uv, normals, QA)
# POSES: {group: (rx, ry, rz)} applied before rendering (model_kit.pose_group); pose stays as set afterwards.
import os

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brief.py'), encoding='utf-8').read(), globals())
L = {n: lib(n) for n in ('model_kit', 'review_stage', 'mesh_qa')}

B = BRIEF
STAGE = globals().get('STAGE', 'model')
import bpy
skin = bpy.data.objects.get(B['name'])                  # after handoff.py the skinned mesh IS the asset
objs = [skin] if skin is not None and skin.get('gm_skin_of') == B['name'] else L['model_kit']['parts'](B['name'])
for grp, rot in (globals().get('POSES') or {}).items():  # e.g. {'Arm_L': (0, 0, 0)} = concept pose for the overlay
    L['model_kit']['pose_group'](grp, rot, asset=B['name'])
L['review_stage']['setup']([o.name for o in objs], asset=B['name'], out_root=B['out_root'],
                           scale_ref='human' if B['asset_type'] != 'character' else None)
modes = {'blockout': ('clay',), 'model': ('clay', 'wire', 'parts'),
         'final': ('clay', 'wire', 'material', 'uv', 'normals')}[STAGE]
views = globals().get('VIEWS') or (('front', 'left', 'back', 'front3q') if B['asset_type'] != 'environment'
                                   else ('front3q', 'back3q', 'top', 'hero'))
REPORT = L['review_stage']['review'](B['name'], modes=modes, views=views, note=globals().get('NOTE', ''),
                                     concept=B.get('concept'), closeups=globals().get('CLOSEUPS'))
if STAGE != 'blockout':                  # blockouts have no UVs/materials yet - judge shapes only
    REPORT['qa'] = L['mesh_qa']['qa'](objs, B, uv=STAGE == 'final')
    REPORT['qa_summary'] = L['mesh_qa']['summary'](REPORT['qa'])
    print(REPORT['qa_summary'])
for v, c in REPORT['concept'].items():
    print('concept %s IoU %.3f worst bands %s' % (v, c['iou'], [(b['z'], b['width_err']) for b in c['worst']]))
