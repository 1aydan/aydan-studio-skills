# Static-mesh export (library): Better FBX when the add-on is enabled, Blender's built-in FBX otherwise; GLB/OBJ too.
#   ex = lib('model_export')
#   ex['export']('Lantern', out_dir=os.path.join(HERE, 'export'))      -> SM_Lantern.fbx + T_ maps (HERE = assets/<slug>/)
#   ex['verify'](files)            re-import (built-in importers) in a temp scene: objects, tris, UVs, materials, size
#   ex['fbx_header'](path)         binary FBX version without importing (7400 = FBX 2014/2015, 7700 = 2018)
#
# Exports TEMPORARY copies of the evaluated parts (modifiers applied, world transforms baked), so the editable parts,
# live modifiers and recipe materials in the .blend stay untouched. join=True -> one mesh SM_<Asset> (props, weapons,
# characters); join=False -> SM_<Asset>_<Part> each (modular kits, vehicles with moving parts - pivots preserved).
# Collision parts (model_kit.collision) -> UCX_SM_<Asset>_##. Cutters are never exported. Textures (T_<Asset>_*) are
# copied next to the file; engine='unreal' writes the normal map with the green channel flipped (DirectX).
import bpy, bmesh, os, shutil, struct
import numpy as np

try:                                   # libraries are exec'd with {'__file__': path} (SKILL.md "Running scripts")
    _here = os.path.dirname(os.path.abspath(__file__))
except NameError:
    raise RuntimeError("exec this library with g = {'__file__': path_to_this_file}")


def _lib(name):
    """Load a sibling library into a fresh namespace."""
    p = os.path.join(_here, name + '.py')
    g = {'__file__': p}
    exec(open(p, encoding='utf-8').read(), g)
    return g
BETTER_FBX_OPTS = dict(
    my_file_type='.fbx', my_fbx_format='binary', my_fbx_version='FBX201800', my_fbx_axis='MayaZUp', my_fbx_unit='cm',
    my_scale=1.0, use_selection=True, use_apply_modifiers=True, use_triangulate=False, use_tangents=True,
    use_export_materials=True, use_vertex_color=True, use_optimize_for_game_engine=False, use_reset_mesh_origin=False,
    use_reset_mesh_rotation=False, my_edge_smoothing='FBXSDK', use_animation=False, use_copy_texture=False,
    use_embed_media=False, check_existing=False,
)
BUILTIN_FBX_OPTS = dict(
    use_selection=True, object_types={'MESH'}, use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=True,
    apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Z', axis_up='Y', path_mode='STRIP', bake_anim=False,
    use_custom_props=False, use_triangles=False, add_leaf_bones=False, check_existing=False,
)


def better_fbx_available():
    return hasattr(bpy.ops, 'better_export') and hasattr(bpy.ops.better_export, 'fbx')


def _parts(asset):
    return [o for o in bpy.data.objects if o.get('gm_asset') == asset and o.type == 'MESH'
            and not o.get('gm_collision') and not o.get('gm_cutter')
            and (not o.hide_render or o.get('gm_skin_hidden'))]      # hidden by the animator handoff: still the model


def _tmp_coll():
    c = bpy.data.collections.get('GM_Export_TMP')
    if c is None:
        c = bpy.data.collections.new('GM_Export_TMP')
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    return c


def _baked_copy(o, dg, coll, name):
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    me.transform(o.matrix_world)
    bm = bmesh.new()
    bm.from_mesh(me)
    if o.matrix_world.determinant() < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    ngons = [f for f in bm.faces if len(f.verts) > 4]         # n-gons block tangent export (normal maps)
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons, quad_method='BEAUTY', ngon_method='BEAUTY')
    bm.to_mesh(me)
    bm.free()
    me.name = name
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def _single_material(ob, mat):
    me = ob.data
    me.materials.clear()
    me.materials.append(mat)
    for p in me.polygons:
        p.material_index = 0


def _dedupe_materials(ob):
    me = ob.data
    names = [m.name if m else None for m in me.materials]
    uniq = list(dict.fromkeys(names))
    if len(uniq) == len(names):
        return
    remap = [uniq.index(n) for n in names]
    idx = [remap[p.material_index] if p.material_index < len(remap) else 0 for p in me.polygons]
    mats = [bpy.data.materials.get(n) if n else None for n in uniq]
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    for p, i in zip(me.polygons, idx):
        p.material_index = i


def _select(obs):
    vl = bpy.context.view_layer
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in vl.objects:
        o.select_set(o in obs)
    vl.objects.active = obs[0]


def _write(path, fmt, exporter, opts):
    if fmt == 'fbx':
        if exporter in ('auto', 'better') and better_fbx_available():
            bpy.ops.better_export.fbx(filepath=path, **dict(BETTER_FBX_OPTS, **(opts or {})))
            return 'Better FBX'
        if exporter == 'better':
            raise RuntimeError('Better FBX add-on not enabled')
        bpy.ops.export_scene.fbx(filepath=path, **dict(BUILTIN_FBX_OPTS, **(opts or {})))
        return 'Blender FBX'
    if fmt in ('glb', 'gltf'):
        bpy.ops.export_scene.gltf(filepath=path, export_format='GLB' if fmt == 'glb' else 'GLTF_SEPARATE',
                                  use_selection=True, export_apply=True, export_texcoords=True, export_normals=True,
                                  export_tangents=True, export_materials='EXPORT', export_image_format='AUTO', **(opts or {}))
        return 'glTF'
    if fmt == 'obj':
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True, apply_modifiers=True, export_materials=True,
                              path_mode='COPY', forward_axis='NEGATIVE_Z', up_axis='Y', **(opts or {}))
        return 'OBJ'
    raise ValueError(fmt)


def _textures(mats):
    out = []
    for m in mats:
        if m and m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and n.image and n.image.filepath_raw:
                    p = bpy.path.abspath(n.image.filepath_raw)
                    if os.path.exists(p) and p not in out:
                        out.append(p)
    return out


def export(asset, out_dir, fmt='fbx', objects=None, join=True, collision=True, textures=True, engine='unreal',
           exporter='auto', lods=(), opts=None, use_baked=True):
    """Write SM_<Asset>.<fmt> (+ UCX collision, LOD files SM_<Asset>_LOD1.., textures). exporter: auto (Better FBX if
    enabled, else Blender FBX) | better | builtin. use_baked: export with M_<Asset> (the baked texture material) when
    it exists. opts: exporter option overrides (e.g. my_fbx_version='FBX201400' for Better FBX). Returns a report."""
    os.makedirs(out_dir, exist_ok=True)
    parts = [bpy.data.objects[o] if isinstance(o, str) else o for o in objects] if objects else _parts(asset)
    if not parts:
        raise ValueError('no parts tagged gm_asset=%s' % asset)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    coll = _tmp_coll()
    baked = bpy.data.materials.get('M_%s' % asset) if use_baked else None
    temp, written, rep = [], [], dict(files=[], notes=[])
    try:
        for o in parts:
            temp.append(_baked_copy(o, dg, coll, 'SM_%s_%s' % (asset, o.get('gm_part', o.name))))
        if join and len(temp) > 1:
            with bpy.context.temp_override(active_object=temp[0], object=temp[0], selected_objects=temp,
                                           selected_editable_objects=temp):
                bpy.ops.object.join()
            temp = [temp[0]]
        if join:
            temp[0].name = temp[0].data.name = 'SM_%s' % asset
        for t in temp:
            if baked is not None:
                _single_material(t, baked)
            else:
                _dedupe_materials(t)
        cols = []
        if collision:
            for i, c in enumerate(o for o in bpy.data.objects if o.get('gm_asset') == asset and o.get('gm_collision')):
                cc = _baked_copy(c, dg, coll, 'UCX_%s_%02d' % (temp[0].name, i))
                cc.data.materials.clear()
                cols.append(cc)
        main = os.path.join(out_dir, 'SM_%s.%s' % (asset, fmt))
        _select(temp + cols)
        rep['exporter'] = _write(main, fmt, exporter, opts)
        written.append(main)
        for i, ratio in enumerate(lods, 1):
            src = temp[0]
            lod = bpy.data.objects.new('SM_%s_LOD%d' % (asset, i), src.data.copy())
            coll.objects.link(lod)
            md = lod.modifiers.new('dec', 'DECIMATE')
            md.ratio = ratio
            md.use_collapse_triangulate = True
            temp.append(lod)
            p = os.path.join(out_dir, 'SM_%s_LOD%d.%s' % (asset, i, fmt))
            _select([lod])
            _write(p, fmt, exporter, opts)
            written.append(p)
        rep['tris'] = sum(sum(len(p.vertices) - 2 for p in t.data.polygons) for t in temp[:1])
        if textures:
            mats = [m for t in temp[:1] for m in t.data.materials]
            for p in _textures(mats):
                dst = os.path.join(out_dir, os.path.basename(p))
                if engine == 'unreal' and p.lower().endswith('_normal.png'):
                    io = {}
                    io.update(_lib('img_io'))
                    a = io['read'](p)
                    a[..., 1] = 1.0 - a[..., 1]
                    io['write'](dst, a)
                    rep['notes'].append('normal map green flipped for Unreal (DirectX): ' + os.path.basename(dst))
                elif os.path.normcase(p) != os.path.normcase(dst):
                    shutil.copy2(p, dst)
                written.append(dst)
    finally:
        for t in temp + (cols if collision else []):
            me = t.data
            bpy.data.objects.remove(t)
            if me and me.users == 0:
                bpy.data.meshes.remove(me)
        if not coll.objects:
            bpy.data.collections.remove(coll)
    rep['files'] = written
    rep['collision'] = len(cols) if collision else 0
    return rep


def fbx_header(path):
    """(is_binary, version) from the FBX header, e.g. (True, 7400)."""
    with open(path, 'rb') as fh:
        head = fh.read(27)
    if head[:18] == b'Kaydara FBX Binary':
        return True, struct.unpack('<I', head[23:27])[0]
    return False, None


def verify(files, expect_tris=None):
    """Re-import each file with Blender's built-in importer into a temp scene (never Better FBX over MCP) and report
    objects, triangles, UV layers, materials, images and size in metres. Cleans up afterwards."""
    main = bpy.context.window.scene
    kinds = (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.objects)
    existing = [set(k) for k in kinds]
    tmp = bpy.data.scenes.new('TMP_verify')
    bpy.context.window.scene = tmp
    rep = {}
    try:
        for fp in files:
            ext = os.path.splitext(fp)[1].lower()
            if ext not in ('.fbx', '.glb', '.gltf', '.obj'):
                continue
            before = set(bpy.data.objects)
            if ext == '.fbx':
                bpy.ops.import_scene.fbx(filepath=fp)
            elif ext in ('.glb', '.gltf'):
                bpy.ops.import_scene.gltf(filepath=fp)
            else:
                bpy.ops.wm.obj_import(filepath=fp)
            new = [o for o in bpy.data.objects if o not in before]
            meshes = [o for o in new if o.type == 'MESH' and not o.name.startswith('UCX_')]
            pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
            size = [round(max(p[i] for p in pts) - min(p[i] for p in pts), 4) for i in range(3)] if pts else None
            info = dict(objects=[(o.name, o.type) for o in new],
                        tris=sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes),
                        uv_layers={o.name: [u.name for u in o.data.uv_layers] for o in meshes},
                        materials=sorted({m.name for o in meshes for m in o.data.materials if m}),
                        size_m=size, scale=[list(map(lambda x: round(x, 4), o.scale)) for o in meshes][:3])
            if ext == '.fbx':
                info['fbx_header'] = fbx_header(fp)
            if expect_tris and abs(info['tris'] - expect_tris) > 0:
                info['tri_mismatch'] = (info['tris'], expect_tris)
            rep[os.path.basename(fp)] = info
            for o in new:
                bpy.data.objects.remove(o)
    finally:
        bpy.context.window.scene = main
        bpy.data.scenes.remove(tmp)
        for blk, had in zip(kinds, existing):
            for d in [d for d in blk if d not in had]:
                try:
                    blk.remove(d)
                except Exception:
                    pass
    return rep
