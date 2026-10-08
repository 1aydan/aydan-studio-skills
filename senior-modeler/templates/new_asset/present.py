# <ASSET> - team presentation pack -> assets/<slug>/renders/present/: label-free 1080p material stills, one-page sheet
# (concept | hero + views), turntable .mp4. Run after the final review (and in the bind pose you want shown).
#   p = r"<skill>\assets\<slug>\present.py"; g = {'__file__': p}; exec(open(p).read(), g); g['REPORT']
# Optional globals: VIEWS, FRAMES (turntable length, 0 = no video), POSES ({group: rot} before rendering).
# The turntable usually outlasts one MCP request - Blender keeps rendering; wait for the .mp4 to finish growing.
import os

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brief.py'), encoding='utf-8').read(), globals())
L = {n: lib(n) for n in ('model_kit', 'review_stage')}

B = BRIEF
import bpy
skin = bpy.data.objects.get(B['name'])                  # after handoff.py the skinned mesh IS the asset
objs = [skin] if skin is not None and skin.get('gm_skin_of') == B['name'] else L['model_kit']['parts'](B['name'])
for grp, rot in (globals().get('POSES') or {}).items():
    L['model_kit']['pose_group'](grp, rot, asset=B['name'])
L['review_stage']['setup']([o.name for o in objs], asset=B['name'], out_root=B['out_root'])
concept = next(iter((B.get('concept') or {}).values()), None)
REPORT = L['review_stage']['present'](B['name'], views=globals().get('VIEWS') or ('hero', 'front', 'left', 'back3q'),
                                      concept=concept, turntable_frames=globals().get('FRAMES', 96))
print(REPORT)
