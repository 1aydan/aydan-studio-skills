# <CHARACTER> - FBX export (Better FBX if enabled, else Blender FBX): SK first, then one file per clip + re-import check.
#   p = r"<skill>\assets\<slug>\export.py"; g = {'__file__': p}; exec(open(p).read(), g); g['REPORT']
# Optional globals: ONLY = ['Idle', ...], SKIP_MESH = True.
import os

HERE = os.path.dirname(os.path.abspath(__file__))  # this character's folder: assets/<slug>/ (outputs land here)
SKILL = os.path.dirname(os.path.dirname(HERE))     # the skill folder
lib = {'__file__': os.path.join(SKILL, 'scripts', 'fbx_export.py')}
exec(open(lib['__file__'], encoding='utf-8').read(), lib)

CHAR = 'TODOCharacter'
FILES = lib['export'](
    armature='TODO_armature_object',
    meshes=['TODO_mesh_object'],
    char=CHAR,                                               # -> SK_<CHAR>.fbx, A_<CHAR>_<Clip>.fbx
    out_dir=os.path.join(HERE, 'export'),
    action_tag='todo_anim',
    only=globals().get('ONLY'),
    skip_mesh=globals().get('SKIP_MESH', False),
    # opts=dict(my_fbx_version='FBX201400'),                 # exporter overrides if the project needs them
)
REPORT = lib['verify']([f for f in FILES if os.path.basename(f).startswith('SK_') or f.endswith('_Idle.fbx')],
                       probe_bone='TODO_body_bone', probe_frames=(0,))
REPORT['written'] = [os.path.basename(f) for f in FILES]
print(REPORT)
