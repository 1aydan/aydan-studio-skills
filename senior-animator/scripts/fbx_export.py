# Generic FBX exporter (library): skeletal mesh first, then one FBX per animation. Better FBX when the add-on is
# enabled, otherwise Blender's built-in FBX exporter (exporter='auto' | 'better' | 'builtin').
#   g = {'__file__': p := os.path.join(SKILL, 'scripts', 'fbx_export.py')}; exec(open(p).read(), g)
#   g['export'](armature='X_SK', meshes=['X'], char='Name', out_dir=os.path.join(HERE, 'export'), action_tag='x_anim')
#   g['verify']([...files], probe_bone='body', probe_frames=(0,))
#
# Only deform bones are written; CTRL_/MCH_/SNAP_ bones, widgets and review objects never reach the FBX
# (selection-only export). Animation files contain the armature only. Both exporters sample the evaluated pose,
# so constraint-driven deform bones bake correctly.
import bpy, os

DEFAULT_OPTS = dict(
    my_file_type='.fbx', my_fbx_format='binary', my_fbx_version='FBX201800',
    my_fbx_axis='MayaZUp', my_fbx_unit='cm', my_scale=1.0,
    use_selection=True, use_only_deform_bones=True,
    use_optimize_for_game_engine=True, use_ignore_armature_node=True,
    primary_bone_axis='Y', secondary_bone_axis='X',
    use_tangents=True, use_triangulate=False,
    check_existing=False,
)
BUILTIN_OPTS = dict(          # Blender FBX: deform bones only, no leaf bones, Y-primary bones like Better FBX
    use_selection=True, use_armature_deform_only=True, add_leaf_bones=False, primary_bone_axis='Y',
    secondary_bone_axis='X', apply_scale_options='FBX_SCALE_UNITS', mesh_smooth_type='FACE', use_tspace=True,
    use_mesh_modifiers=True, armature_nodetype='NULL', axis_forward='-Z', axis_up='Y', check_existing=False,
)


def better_fbx_available():
    return hasattr(bpy.ops, 'better_export') and hasattr(bpy.ops.better_export, 'fbx')


def _select_only(obs):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.view_layer.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[0]


def _rest(arm):
    for p in arm.pose.bones:
        p.location = (0, 0, 0)
        p.rotation_quaternion = (1, 0, 0, 0)
        p.rotation_euler = (0, 0, 0)
        p.scale = (1, 1, 1)


def export(armature, meshes, char, out_dir, action_tag=None, actions=None, only=None, skip_mesh=False,
           mesh_name='SK_{char}.fbx', anim_name='A_{char}_{action}.fbx', opts=None, exporter='auto'):
    """action_tag: export actions carrying this custom prop (set by anim_framework). actions: explicit list instead.
    exporter: 'auto' (Better FBX if enabled, else Blender FBX) | 'better' | 'builtin'. opts override the chosen
    exporter's options. Returns the list of written files (EXPORTER global = the exporter used)."""
    use_better = exporter == 'better' or (exporter == 'auto' and better_fbx_available())
    if exporter == 'better' and not better_fbx_available():
        raise RuntimeError('Better FBX add-on not enabled')
    globals()['EXPORTER'] = 'Better FBX' if use_better else 'Blender FBX'
    arm = bpy.data.objects[armature]
    mobs = [bpy.data.objects[m] for m in meshes]
    sc = bpy.context.scene
    os.makedirs(out_dir, exist_ok=True)
    O = dict(DEFAULT_OPTS if use_better else BUILTIN_OPTS, **(opts or {}))
    ad = arm.animation_data or arm.animation_data_create()
    keep = (ad.action, ad.action_slot, sc.frame_start, sc.frame_end, sc.frame_current)
    written = []
    try:
        if not skip_mesh:
            ad.action = None
            _rest(arm)
            sc.frame_set(0)
            _select_only([arm] + mobs)
            path = os.path.join(out_dir, mesh_name.format(char=char))
            if use_better:
                bpy.ops.better_export.fbx(filepath=path, use_animation=False, use_export_materials=True, **O)
            else:
                bpy.ops.export_scene.fbx(filepath=path, object_types={'ARMATURE', 'MESH'}, bake_anim=False, **O)
            written.append(path)
        if actions is not None:
            clips = [bpy.data.actions[a] for a in actions]
        else:
            clips = sorted((a for a in bpy.data.actions if action_tag and a.get(action_tag)), key=lambda a: a.name)
        for act in clips:
            if only and act.name not in only:
                continue
            ad.action = act
            if act.slots:
                ad.action_slot = act.slots[0]
            s, e = int(act.frame_range[0]), int(act.frame_range[1])
            sc.frame_start, sc.frame_end = s, e
            sc.frame_set(s)
            _select_only([arm])
            path = os.path.join(out_dir, anim_name.format(char=char, action=act.name))
            if use_better:
                bpy.ops.better_export.fbx(filepath=path, use_animation=True, my_animation_type='Active',
                                          use_timeline_range=True, use_raw_keyframe=False, my_interpolation_type='Linear',
                                          my_simplify_algorithm='0', use_export_materials=False, **O)
            else:
                bpy.ops.export_scene.fbx(filepath=path, object_types={'ARMATURE'}, bake_anim=True,
                                         bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                                         bake_anim_force_startend_keying=True, bake_anim_step=1.0,
                                         bake_anim_simplify_factor=0.0, **O)
            written.append(path)
    finally:
        ad.action = keep[0]
        if keep[0] is not None and keep[1] is not None:
            ad.action_slot = keep[1]
        sc.frame_start, sc.frame_end = keep[2], keep[3]
        sc.frame_set(keep[4])
        _select_only([arm])
    return written


def verify(files, probe_bone=None, probe_frames=(0,)):
    """Re-import each FBX into a temporary scene and report objects, bone count, leaked rig bones, anim range and
    the probe bone's world head position (in Blender units after import). Cleans up afterwards."""
    main = bpy.context.window.scene
    kinds = (bpy.data.meshes, bpy.data.armatures, bpy.data.actions, bpy.data.materials, bpy.data.images)
    existing = [set(blk) for blk in kinds]                 # only clean up what the re-import creates
    tmp = bpy.data.scenes.new('TMP_fbx_verify')
    bpy.context.window.scene = tmp
    rep = {}
    try:
        for fp in files:
            before = set(bpy.data.objects)
            bpy.ops.import_scene.fbx(filepath=fp)
            new = [o for o in bpy.data.objects if o not in before]
            info = {'objects': [(o.name, o.type) for o in new]}
            a = next((o for o in new if o.type == 'ARMATURE'), None)
            if a:
                info['bones'] = len(a.data.bones)
                info['leaked_rig_bones'] = [b.name for b in a.data.bones if b.name.startswith(('CTRL_', 'MCH_', 'SNAP_'))]
                act = a.animation_data.action if a.animation_data else None
                if act:
                    info['range'] = [int(x) for x in act.frame_range]
                    if probe_bone and probe_bone in a.pose.bones:
                        for f in probe_frames:
                            tmp.frame_set(f)
                            info['%s@%d' % (probe_bone, f)] = [round(x, 3) for x in a.matrix_world @ a.pose.bones[probe_bone].head]
            rep[os.path.basename(fp)] = info
            for o in new:
                bpy.data.objects.remove(o)
    finally:
        bpy.context.window.scene = main
        bpy.data.scenes.remove(tmp)
        for blk, had in zip(kinds, existing):
            for d in [d for d in blk if d not in had]:
                blk.remove(d)
    return rep


def export_objects(objects, path, animation=False, frame_range=None, opts=None):
    """Export non-skinned objects (props: static meshes, or object-animated meshes like a thrown item) with Better FBX.
    objects: names; animation=True exports each object's active action over frame_range (start, end)."""
    obs = [bpy.data.objects[n] for n in objects]
    sc = bpy.context.scene
    keep = (sc.frame_start, sc.frame_end, sc.frame_current)
    # props keep their world placement / object motion: Better FBX's game-engine optimisation resets object origins
    O = dict(DEFAULT_OPTS, use_optimize_for_game_engine=False, use_reset_mesh_origin=False, use_reset_mesh_rotation=False)
    O.update(opts or {})
    O.pop('use_only_deform_bones', None)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if frame_range:
            sc.frame_start, sc.frame_end = frame_range
        sc.frame_set(sc.frame_start)
        _select_only(obs)
        kw = dict(use_animation=animation, use_export_materials=True)
        if animation:
            kw.update(my_animation_type='Active', use_timeline_range=True, use_raw_keyframe=False,
                      my_interpolation_type='Linear', my_simplify_algorithm='0')
        bpy.ops.better_export.fbx(filepath=path, **kw, **O)
    finally:
        sc.frame_start, sc.frame_end = keep[0], keep[1]
        sc.frame_set(keep[2])
    return path

