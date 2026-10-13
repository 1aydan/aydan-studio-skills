# Texture baking (library): any material recipe -> one PBR texture set per asset, sharing the packed UV atlas.
#   tb = lib('texture_bake')
#   rep = tb['bake'](objs, 'Lantern', out_dir, res=2048)        T_<Asset>_BaseColor / _ORM / _Normal (/ _Emissive)
#   tb['swap'](objs, 'Lantern', 'baked')     every slot -> M_<Asset> (image textures); 'source' restores the recipes
#   tb['palette_texture'](objs, 'Lantern', out_dir)   low-poly: one swatch image, UV0 -> swatches, UV1 keeps the unwrap
#
# How: Cycles bake. Base colour / roughness / metallic / emission are read from each material's Principled BSDF
# input (whatever drives it) through a temporary Emission shader -> EMIT bake (no lighting baked in). Normal = NORMAL
# bake (tangent space, OpenGL/+Y like Blender, Unity, Godot; flip green for Unreal - see reference/texturing.md),
# from a high-poly when `high` is given (selected-to-active with cage extrusion) else from the material's bump/normal.
# AO = Cycles AO bake. ORM = R AO, G Roughness, B Metallic (Unreal/glTF packing). Restores the render engine.
import bpy, os, math
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
_io = {}
_io.update(_lib('img_io'))
COLOR_MAPS = ('BaseColor', 'Emissive')
SOCKET = {'BaseColor': 'Base Color', 'Roughness': 'Roughness', 'Metallic': 'Metallic', 'Emissive': 'Emission Color'}


def _objs(objs):
    return [bpy.data.objects[o] if isinstance(o, str) else o for o in objs]


def _mats(objs):
    seen = []
    for o in objs:
        for s in o.material_slots:
            if s.material and s.material not in seen:
                seen.append(s.material)
    return seen


def _principled(m):
    return next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if m.use_nodes else None


def _output(m):
    outs = [n for n in m.node_tree.nodes if n.type == 'OUTPUT_MATERIAL']
    return next((n for n in outs if n.is_active_output), outs[0] if outs else None)


class _Selected:
    def __init__(self, objs):
        self.objs = objs

    def __enter__(self):
        vl = bpy.context.view_layer
        self.keep = ([o for o in vl.objects if o.select_get()], vl.objects.active)
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for o in vl.objects:
            o.select_set(o in self.objs)
        vl.objects.active = self.objs[-1]

    def __exit__(self, *a):
        vl = bpy.context.view_layer
        for o in vl.objects:
            o.select_set(o in self.keep[0])
        vl.objects.active = self.keep[1]


def _image(name, res, color):
    img = bpy.data.images.get(name)
    if img is None or tuple(img.size) != (res, res):
        if img is not None:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name, res, res, alpha=True, float_buffer=False)
    img.colorspace_settings.name = 'sRGB' if color else 'Non-Color'
    return img


def _dilate(img, px):
    """Bake margin done right: grow every island into texels NO object baked (alpha 0) only. Blender bakes objects
    one at a time and each object's own margin overwrites neighbouring objects' baked texels when islands are closer
    than the margin (pack gaps are smaller): foreign colour bands along island edges."""
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    done = a[..., 3] > 0.5
    col = a[..., :3] * done[..., None]
    for _ in range(px):
        if done.all():
            break
        acc = np.zeros_like(col)
        cnt = np.zeros(done.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            m = np.roll(np.roll(done, dy, 0), dx, 1)
            acc += np.roll(np.roll(col, dy, 0), dx, 1) * m[..., None]
            cnt += m
        grow = ~done & (cnt > 0)
        col[grow] = acc[grow] / cnt[grow][:, None]
        done = done | grow
    a[..., :3] = np.where(done[..., None], col, a[..., :3])
    a[..., 3] = 1.0
    img.pixels.foreach_set(a.ravel())


def _target_nodes(mats, img):
    made = []
    for m in mats:
        nt = m.node_tree
        n = nt.nodes.new('ShaderNodeTexImage')
        n.name = n.label = 'GM_BakeTarget'
        n.image = img
        n.location = (-200, 600)
        for x in nt.nodes:
            x.select = False
        n.select = True
        nt.nodes.active = n
        made.append((m, n))
    return made


def _route_socket(mats, socket):
    """Temporarily drive each material output with Emission(<Principled socket>)."""
    undo = []
    for m in mats:
        nt = m.node_tree
        bs, out = _principled(m), _output(m)
        if out is None:
            continue
        old = [l.from_socket for l in out.inputs['Surface'].links]
        em = nt.nodes.new('ShaderNodeEmission')
        em.name = 'GM_BakeEmit'
        em.inputs['Strength'].default_value = 1.0
        if bs is None:
            em.inputs['Color'].default_value = tuple(m.diffuse_color) if socket == 'Base Color' else (0, 0, 0, 1)
        else:
            src = bs.inputs[socket]
            if src.is_linked:
                nt.links.new(src.links[0].from_socket, em.inputs['Color'])
            else:
                v = src.default_value
                em.inputs['Color'].default_value = tuple(v) if hasattr(v, '__len__') else (v, v, v, 1)
            if socket == 'Emission Color':     # bake emission colour x strength (clamped to 1 in an 8-bit image)
                k = bs.inputs['Emission Strength'].default_value
                if not src.is_linked:
                    c = em.inputs['Color'].default_value
                    em.inputs['Color'].default_value = (c[0] * k, c[1] * k, c[2] * k, 1)
        nt.links.new(em.outputs[0], out.inputs['Surface'])
        undo.append((m, em, out, old))
    return undo


def _unroute(undo):
    for m, em, out, old in undo:
        nt = m.node_tree
        nt.nodes.remove(em)
        for s in old:
            nt.links.new(s, out.inputs['Surface'])


def _has_normal_detail(mats):
    for m in mats:
        bs = _principled(m)
        if bs is not None and bs.inputs['Normal'].is_linked:
            return True
    return False


def bake(objs, asset, out_dir, res=2048, maps=('BaseColor', 'Roughness', 'Metallic', 'Normal', 'AO'), high=None,
         cage=0.02, margin_px=16, ao_samples=64, ao_in_albedo=0.0, pack_orm=True, emissive='auto', device=None,
         emit_samples='auto'):
    """Bake the texture set. objs must share one non-overlapping UV atlas (uv_tools.unwrap). high: names of high-poly
    objects for Normal/AO (selected-to-active, cage extrusion in metres). ao_in_albedo 0..0.6 multiplies AO into the
    base colour (hand-painted look; keep 0 for realistic). emit_samples: Cycles samples for the colour/roughness/
    metallic maps - 'auto' = 32 when a material uses ray-traced nodes (Bevel edge masks, AO: one sample bakes them as
    speckle that averages to flat bars at a distance), else 1. Returns {map: path} + notes."""
    objs = [o for o in _objs(objs) if o.type == 'MESH']
    missing = [o.name for o in objs if not o.data.uv_layers]
    if missing:
        raise ValueError('unwrap first: %s' % missing)
    mats = _mats(objs)
    sc = bpy.context.scene
    keep = (sc.render.engine, sc.cycles.samples, sc.render.bake.margin, sc.render.bake.margin_type,
            sc.render.bake.use_selected_to_active, sc.render.bake.cage_extrusion, getattr(sc.cycles, 'device', None))
    os.makedirs(out_dir, exist_ok=True)
    if emissive == 'auto':
        emissive = any(_principled(m) is not None and (_principled(m).inputs['Emission Strength'].default_value > 0 and
                       tuple(_principled(m).inputs['Emission Color'].default_value)[:3] != (0, 0, 0)) for m in mats)
    todo = list(maps) + (['Emissive'] if emissive and 'Emissive' not in maps else [])
    if emit_samples == 'auto':
        traced = any(n.type in ('BEVEL', 'AMBIENT_OCCLUSION') for m in mats if m.node_tree for n in m.node_tree.nodes)
        emit_samples = 32 if traced else 1
    rep, notes = {}, []
    hi = [bpy.data.objects[h] if isinstance(h, str) else h for h in (high or [])]
    try:
        sc.render.engine = 'CYCLES'
        if device:
            sc.cycles.device = device
        sc.render.bake.margin = 0                       # margin: _dilate() after each map (see there)
        sc.render.bake.margin_type = 'EXTEND'
        sc.render.bake.use_clear = True
        for mp in todo:
            if mp == 'Normal' and not hi and not _has_normal_detail(mats):
                notes.append('Normal skipped: no high-poly and no bump/normal in the materials (would be flat)')
                continue
            img = _image('T_%s_%s' % (asset, mp), res, mp in COLOR_MAPS)
            targets = _target_nodes(mats, img)
            undo = []
            try:
                s2a = bool(hi) and mp in ('Normal', 'AO')
                sc.render.bake.use_selected_to_active = s2a
                sc.render.bake.cage_extrusion = cage
                sc.render.bake.normal_space = 'TANGENT'
                kind = 'EMIT' if mp in SOCKET else {'Normal': 'NORMAL', 'AO': 'AO'}.get(mp)
                if kind is None:
                    raise ValueError('map ' + mp)
                sc.cycles.samples = ao_samples if mp == 'AO' else (1 if mp == 'Normal' else emit_samples)
                if mp in SOCKET:
                    undo = _route_socket(mats, SOCKET[mp])
                # selected-to-active writes only into the active object: one pass per low-poly object
                for i, batch in enumerate([[o] for o in objs] if s2a else [objs]):
                    sc.render.bake.use_clear = i == 0
                    with _Selected(hi + batch if s2a else batch):
                        bpy.ops.object.bake(type=kind)
            finally:
                _unroute(undo)
                for m, n in targets:
                    m.node_tree.nodes.remove(n)
            _dilate(img, margin_px)
            path = os.path.join(out_dir, 'T_%s_%s.png' % (asset, mp))
            img.filepath_raw = path
            img.file_format = 'PNG'
            img.save()
            rep[mp] = path
    finally:
        sc.render.engine, sc.cycles.samples, sc.render.bake.margin, sc.render.bake.margin_type = keep[:4]
        sc.render.bake.use_selected_to_active, sc.render.bake.cage_extrusion = keep[4:6]
        if keep[6] is not None:
            sc.cycles.device = keep[6]
    if ao_in_albedo and 'AO' in rep and 'BaseColor' in rep:
        bc, ao = _io['read'](rep['BaseColor']), _io['read'](rep['AO'])
        bc[..., :3] *= (1 - ao_in_albedo) + ao_in_albedo * ao[..., :1]
        _io['write'](rep['BaseColor'], bc)
        _reload(rep['BaseColor'])
        notes.append('AO multiplied into BaseColor x%.2f' % ao_in_albedo)
    if pack_orm and ('Roughness' in rep or 'Metallic' in rep):
        ref = _io['read'](rep.get('Roughness') or rep['Metallic'])
        h, w = ref.shape[:2]
        ch = lambda k, d: _io['read'](rep[k])[..., 0] if k in rep else np.full((h, w), d, np.float32)
        orm = np.dstack([ch('AO', 1.0), ch('Roughness', 0.5), ch('Metallic', 0.0), np.ones((h, w), np.float32)])
        rep['ORM'] = os.path.join(out_dir, 'T_%s_ORM.png' % asset)
        _io['write'](rep['ORM'], orm)                      # loose maps stay on disk for inspection; ORM is the one used
    build_baked_material(asset, rep)
    return dict(maps=rep, notes=notes, res=res, material='M_%s' % asset)


def _reload(path):
    for im in bpy.data.images:
        if im.filepath_raw and os.path.normcase(bpy.path.abspath(im.filepath_raw)) == os.path.normcase(path):
            im.reload()


def _load(path, color):
    im = bpy.data.images.load(path, check_existing=True)
    im.reload()
    im.colorspace_settings.name = 'sRGB' if color else 'Non-Color'
    return im


def build_baked_material(asset, maps):
    """M_<Asset>: BaseColor + ORM (+ Normal, Emissive) image textures into a Principled BSDF. This is the engine material."""
    name = 'M_%s' % asset
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (500, 0)
    bs = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bs.location = (200, 0)
    nt.links.new(bs.outputs[0], out.inputs['Surface'])
    y = 300
    if 'BaseColor' in maps:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image, t.location = _load(maps['BaseColor'], True), (-400, y)
        nt.links.new(t.outputs['Color'], bs.inputs['Base Color'])
    if 'ORM' in maps:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image, t.location = _load(maps['ORM'], False), (-400, y - 300)
        sp = nt.nodes.new('ShaderNodeSeparateColor')
        sp.location = (-120, y - 300)
        nt.links.new(t.outputs['Color'], sp.inputs['Color'])
        nt.links.new(sp.outputs['Green'], bs.inputs['Roughness'])
        nt.links.new(sp.outputs['Blue'], bs.inputs['Metallic'])
    else:
        for k, sock in (('Roughness', 'Roughness'), ('Metallic', 'Metallic')):
            if k in maps:
                t = nt.nodes.new('ShaderNodeTexImage')
                t.image = _load(maps[k], False)
                nt.links.new(t.outputs['Color'], bs.inputs[sock])
    if 'Normal' in maps:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image, t.location = _load(maps['Normal'], False), (-400, y - 600)
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.location = (-120, y - 600)
        nt.links.new(t.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], bs.inputs['Normal'])
    if 'Emissive' in maps:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image, t.location = _load(maps['Emissive'], True), (-400, y - 900)
        nt.links.new(t.outputs['Color'], bs.inputs['Emission Color'])
        bs.inputs['Emission Strength'].default_value = 1.0
    m['gm_baked'] = True
    return m


def swap(objs, asset, to='baked'):
    """Point every material slot at M_<Asset> ('baked') or back at the recipe materials ('source'). Slot indices
    are preserved, so the swap is lossless and repeatable."""
    baked = bpy.data.materials.get('M_%s' % asset)
    for o in _objs(objs):
        me = o.data
        if to == 'baked':
            if baked is None:
                raise ValueError('bake first')
            if 'gm_src_mats' not in o:
                o['gm_src_mats'] = [s.material.name if s.material else '' for s in o.material_slots]
            if not me.materials:
                me.materials.append(baked)
            for i in range(len(me.materials)):
                me.materials[i] = baked
        else:
            src = o.get('gm_src_mats')
            if src:
                for i, n in enumerate(src):
                    if i < len(me.materials):
                        me.materials[i] = bpy.data.materials.get(n) if n else None
                del o['gm_src_mats']
    return to


# ---------------------------------------------------------------- low-poly palette texture
def palette_texture(objs, asset, out_dir, swatch=16, colors=None):
    """One small swatch image T_<Asset>_Palette.png from the materials' colours; every face's UVs collapse into its
    material's swatch (UV0), the real unwrap is kept in UV1 'UV_Unwrap'; slots -> M_<Asset>_Palette (Closest)."""
    objs = [o for o in _objs(objs) if o.type == 'MESH']
    mats = _mats(objs)
    cols = []
    for m in mats:
        bs = _principled(m)
        c = tuple(bs.inputs['Base Color'].default_value)[:3] if bs else tuple(m.diffuse_color)[:3]
        cols.append(c)
    n = len(cols)
    g = max(1, math.ceil(math.sqrt(n)))
    size = g * swatch
    img = np.zeros((size, size, 4), np.float32)
    img[..., 3] = 1
    centre = {}
    for i, (m, c) in enumerate(zip(mats, cols)):
        r, k = divmod(i, g)
        srgb = _io['linear_to_srgb'](np.array(c))
        img[r * swatch:(r + 1) * swatch, k * swatch:(k + 1) * swatch, :3] = srgb
        centre[m.name] = ((k + 0.5) / g, 1 - (r + 0.5) / g)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'T_%s_Palette.png' % asset)
    _io['write'](path, img)
    pm = bpy.data.materials.get('M_%s_Palette' % asset) or bpy.data.materials.new('M_%s_Palette' % asset)
    pm.use_nodes = True
    nt = pm.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bs = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bs.inputs['Roughness'].default_value = 0.8
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = _load(path, True)
    t.interpolation = 'Closest'
    nt.links.new(t.outputs['Color'], bs.inputs['Base Color'])
    nt.links.new(bs.outputs[0], out.inputs['Surface'])
    for o in objs:
        me = o.data
        if 'UV_Unwrap' not in me.uv_layers:
            me.uv_layers.active_index = 0
            me.uv_layers.new(name='UV_Unwrap', do_init=True)
        uv0 = me.uv_layers[0].data
        slot_c = [centre.get(s.material.name) if s.material else (0.5, 0.5) for s in o.material_slots]
        for p in me.polygons:
            c = slot_c[p.material_index] if p.material_index < len(slot_c) else (0.5, 0.5)
            for li in p.loop_indices:
                uv0[li].uv = c
        o['gm_src_mats'] = [s.material.name if s.material else '' for s in o.material_slots]
        for i in range(len(me.materials)):
            me.materials[i] = pm
        me.uv_layers.active_index = 0
        me.uv_layers[0].active_render = True
    return dict(path=path, swatches={m.name: centre[m.name] for m in mats}, material=pm.name)
