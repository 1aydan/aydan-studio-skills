# UV unwrap / pack / texel density / UV QA (library). Always unwrap, even when the user wants no textures: clean UVs
# keep the asset ready for texturing, lightmaps and engine features.
#   uv = lib('uv_tools')
#   uv['unwrap'](objs, res=2048, margin_px=8)        seams -> angle-based unwrap, no seams -> smart project; then one
#                                                    shared atlas: average island scale + pack (margin in PIXELS)
#   uv['texel_density'](objs, res=2048)              px/m per object and overall (+ spread)
#   uv['uv_qa'](objs, res=512, margin_px=4)           missing UVs, out of 0-1, flipped, overlaps, padding, stretch
#   uv['uv_map'](objs, png, res=1024)                 picture: islands coloured, overlaps red, padding violations yellow
# objs: names or objects (meshes). Uses the EVALUATED mesh (modifiers applied = what gets exported) for QA.
import bpy, bmesh, math, os
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


def _objs(objs):
    return [bpy.data.objects[o] if isinstance(o, str) else o for o in objs if (bpy.data.objects[o] if isinstance(o, str) else o).type == 'MESH']


class _Edit:
    """Multi-object edit mode on objs (all faces selected, UV sync on), restored on exit."""
    def __init__(self, objs):
        self.objs = objs

    def __enter__(self):
        vl = bpy.context.view_layer
        self.keep = ([o for o in vl.objects if o.select_get()], vl.objects.active)
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for o in vl.objects:
            o.select_set(o in self.objs)
        vl.objects.active = self.objs[0]
        ts = bpy.context.scene.tool_settings
        self.sync = ts.use_uv_select_sync
        ts.use_uv_select_sync = True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='SELECT')
        return self

    def __exit__(self, *a):
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.scene.tool_settings.use_uv_select_sync = self.sync
        vl = bpy.context.view_layer
        for o in vl.objects:
            o.select_set(o in self.keep[0])
        vl.objects.active = self.keep[1]


def _ensure_layer(o, name='UVMap'):
    me = o.data
    if not me.uv_layers:
        me.uv_layers.new(name=name)
    me.uv_layers.active_index = 0
    me.uv_layers[0].active_render = True


FREEZE = ('MIRROR', 'ARRAY', 'SOLIDIFY', 'BEVEL', 'BOOLEAN', 'SCREW', 'SUBSURF', 'TRIANGULATE', 'WELD', 'DECIMATE')


def freeze(objs, types=FREEZE):
    """Apply generator modifiers (top of the stack down) so UVs are made on the real geometry. Modifiers that only
    affect shading (Weighted Normal) or deformation (Armature) stay live. Boolean cutters stay hidden in the scene."""
    out = {}
    for o in _objs(objs):
        names = [md.name for md in o.modifiers if md.type in types]      # read names BEFORE applying (RNA freed after)
        for n in names:
            with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
                bpy.ops.object.modifier_apply(modifier=n)
        if names:
            out[o.name] = names
    return out


def crease_seams(o, angle=60):
    """Add seams on hard creases (dihedral > angle): rims of solidified shells, boolean cuts, flat caps. A hard edge
    splits the normal anyway, so the seam costs nothing extra."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    lim = math.radians(angle)
    n = 0
    for e in bm.edges:
        f = e.link_faces
        if not e.seam and len(f) == 2 and f[0].normal.angle(f[1].normal, 0) > lim:
            e.seam = True
            n += 1
    bm.to_mesh(o.data)
    bm.free()
    return n


def unwrap(objs, method='auto', angle=66, res=2048, margin_px=8, average=True, pack_now=True, rotate=True,
           keep_existing=False, freeze_first=True, crease=60):
    """method: auto | smart | angle | stretch (minimum stretch) | conformal. auto = seams marked -> angle-based,
    otherwise smart project (angle limit `angle`). keep_existing: only unwrap objects without UVs. crease: also seam
    edges sharper than this (degrees) before angle-based unwraps (0 = off).
    freeze_first: apply generator modifiers first (bevel faces made on seams by a LIVE modifier stretch across the
    atlas and pick up other islands' texels). Re-run build.py to get the live modifiers back."""
    objs = _objs(objs)
    frozen = freeze(objs) if freeze_first else {}
    done = []
    for o in objs:
        if keep_existing and o.data.uv_layers:
            continue
        _ensure_layer(o)
        m = method
        if m == 'auto':
            m = 'angle' if any(e.use_seam for e in o.data.edges) else 'smart'
        if m != 'smart' and crease:
            crease_seams(o, crease)
        with _Edit([o]):
            if m == 'smart':
                bpy.ops.uv.smart_project(angle_limit=math.radians(angle), margin_method='FRACTION', island_margin=0.0,
                                         area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
            else:
                bpy.ops.uv.unwrap(method={'angle': 'ANGLE_BASED', 'conformal': 'CONFORMAL', 'stretch': 'MINIMUM_STRETCH'}[m],
                                  fill_holes=True, correct_aspect=True, margin_method='FRACTION', margin=0.0)
        done.append((o.name, m))
    if pack_now:
        pack(objs, res=res, margin_px=margin_px, average=average, rotate=rotate)
    return dict(unwrapped=done, packed=pack_now, frozen=frozen)


def pack(objs, res=2048, margin_px=8, average=True, rotate=True):
    """One shared UV atlas for all objs (one texture set per asset). margin in pixels at `res`."""
    objs = _objs(objs)
    with _Edit(objs):
        if average:
            bpy.ops.uv.average_islands_scale()
        bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=rotate, rotate_method='ANY', scale=True,
                                merge_overlap=False, margin_method='FRACTION', margin=margin_px / float(res),
                                shape_method='CONCAVE')
    return True


# ---------------------------------------------------------------- measurement
def _tri_data(o, dg=None, evaluated=True):
    """World-space triangle positions + UVs (+ island ids) of the evaluated mesh."""
    dg = dg or bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg) if evaluated else o
    me = ev.to_mesh()
    try:
        if not me.uv_layers:
            return None
        uvl = me.uv_layers.active.data
        me.calc_loop_triangles()
        n = len(me.loop_triangles)
        loops = np.empty(n * 3, np.int64)
        me.loop_triangles.foreach_get('loops', loops)
        verts = np.empty(n * 3, np.int64)
        me.loop_triangles.foreach_get('vertices', verts)
        polys = np.empty(n, np.int64)
        me.loop_triangles.foreach_get('polygon_index', polys)
        uv = np.empty(len(uvl) * 2, np.float64)
        uvl.foreach_get('uv', uv)
        uv = uv.reshape(-1, 2)[loops].reshape(n, 3, 2)
        co = np.empty(len(me.vertices) * 3, np.float64)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        M = np.array(ev.matrix_world)
        co = co @ M[:3, :3].T + M[:3, 3]
        P = co[verts].reshape(n, 3, 3)
        islands = _islands(me, uvl)
        return dict(P=P, UV=uv, poly=polys, island=islands[polys], n_islands=int(islands.max() + 1) if len(islands) else 0)
    finally:
        ev.to_mesh_clear()


def _islands(me, uvl):
    """UV island id per polygon (faces connected through edges whose two UV endpoints match)."""
    npoly = len(me.polygons)
    parent = np.arange(npoly)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    seen = {}
    for p in me.polygons:
        ls = list(p.loop_indices)
        k = len(ls)
        for j in range(k):
            la, lb = ls[j], ls[(j + 1) % k]
            va, vb = me.loops[la].vertex_index, me.loops[lb].vertex_index
            ua, ub = uvl[la].uv, uvl[lb].uv
            ka = (va, round(ua.x, 5), round(ua.y, 5))
            kb = (vb, round(ub.x, 5), round(ub.y, 5))
            key = (ka, kb) if ka < kb else (kb, ka)
            q = seen.get(key)
            if q is None:
                seen[key] = p.index
            else:
                ra, rb = find(p.index), find(q)
                if ra != rb:
                    parent[ra] = rb
    roots = np.array([find(i) for i in range(npoly)])
    _, ids = np.unique(roots, return_inverse=True)
    return ids


def _areas(P, UV):
    a3 = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
    e1, e2 = UV[:, 1] - UV[:, 0], UV[:, 2] - UV[:, 0]
    signed = 0.5 * (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    return a3, signed


def texel_density(objs, res=2048):
    """px per metre (at texture size res) per object and for the whole set. spread = max/min of per-island density;
    keep it under ~1.5 for one asset unless a part is intentionally favoured (faces, hero details)."""
    objs = _objs(objs)
    dg = bpy.context.evaluated_depsgraph_get()
    rep, tot3, totuv, isl = {}, 0.0, 0.0, []
    for o in objs:
        d = _tri_data(o, dg)
        if d is None:
            rep[o.name] = None
            continue
        a3, su = _areas(d['P'], d['UV'])
        au = np.abs(su)
        tot3 += a3.sum()
        totuv += au.sum()
        rep[o.name] = round(res * math.sqrt(au.sum() / max(a3.sum(), 1e-12)), 1)
        for i in range(d['n_islands']):
            s = d['island'] == i
            if a3[s].sum() > 1e-9:
                isl.append((res * math.sqrt(au[s].sum() / a3[s].sum()), a3[s].sum()))
    if isl:
        dens = np.array([x[0] for x in isl])
        w = np.array([x[1] for x in isl])
        big = dens[w > np.percentile(w, 10)] if len(w) > 5 else dens       # ignore tiny islands
        spread = float(big.max() / max(big.min(), 1e-9))
    else:
        spread = None
    return dict(per_object=rep, overall=round(res * math.sqrt(totuv / max(tot3, 1e-12)), 1),
                spread=round(spread, 2) if spread else None, res=res, uv_coverage=round(totuv, 3))


# ---------------------------------------------------------------- QA
def _raster(objs, res, dg=None):
    """owner map (global island id per pixel, -1 empty) + overlap mask. Pixel centres inside UV triangles."""
    dg = dg or bpy.context.evaluated_depsgraph_get()
    owner = np.full((res, res), -1, np.int32)
    overlap = np.zeros((res, res), bool)
    base = 0
    stats = {}
    for o in objs:
        d = _tri_data(o, dg)
        if d is None:
            continue
        UV = d['UV'] * res
        a3, su = _areas(d['P'], d['UV'])
        for t in range(len(UV)):
            tri = UV[t]
            if abs(su[t]) * res * res < 1e-4:
                continue
            x0, y0 = np.floor(tri.min(0)).astype(int)
            x1, y1 = np.ceil(tri.max(0)).astype(int)
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, res), min(y1, res)
            if x1 <= x0 or y1 <= y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            (ax, ay), (bx, by), (cx, cy) = tri
            d0 = (bx - ax) * (ys - ay) - (by - ay) * (xs - ax)
            d1 = (cx - bx) * (ys - by) - (cy - by) * (xs - bx)
            d2 = (ax - cx) * (ys - cy) - (ay - cy) * (xs - cx)
            inside = ((d0 >= 0) & (d1 >= 0) & (d2 >= 0)) | ((d0 <= 0) & (d1 <= 0) & (d2 <= 0))
            if not inside.any():
                continue
            gid = base + int(d['island'][t])
            sub = owner[y0:y1, x0:x1]
            clash = inside & (sub >= 0) & (sub != gid)
            overlap[y0:y1, x0:x1] |= clash
            sub[inside & (sub < 0)] = gid
        stats[o.name] = (base, d['n_islands'])
        base += d['n_islands']
    return owner, overlap, stats


def uv_qa(objs, res=512, margin_px=4, allow_overlap=False, stretch_limit=2.0):
    """Returns dict(errors, warnings, stats). Overlaps are errors unless allow_overlap (mirrored/stacked UVs on purpose;
    then nothing unique can be baked there). margin_px is checked at `res` (scale it from the real texture size)."""
    objs = _objs(objs)
    dg = bpy.context.evaluated_depsgraph_get()
    errors, warnings, st = [], [], {}
    for o in objs:
        if not o.data.uv_layers:
            errors.append('%s: no UV map' % o.name)
    have = [o for o in objs if o.data.uv_layers]
    flipped, outside, tris, zero = 0, 0, 0, 0
    ratios, weights, slivers = [], [], []
    for o in have:
        d = _tri_data(o, dg)
        a3, su = _areas(d['P'], d['UV'])
        tris += len(su)
        flipped += int((su < 0).sum()) if (su > 0).sum() >= (su < 0).sum() else int((su > 0).sum())
        outside += int(((d['UV'] < -1e-4) | (d['UV'] > 1 + 1e-4)).any(axis=(1, 2)).sum())
        zero += int((np.abs(su) < 1e-12).sum())
        ok = (a3 > 1e-12) & (np.abs(su) > 1e-12)
        ratios.append(np.abs(su[ok]) / a3[ok])
        weights.append(a3[ok])
        span = np.ptp(d['UV'], axis=1).max(1)                              # UV extent of each triangle
        edge3 = np.linalg.norm(d['P'] - np.roll(d['P'], 1, axis=1), axis=2).max(1)
        slivers.append((span, edge3))
    if have:
        r = np.concatenate(ratios)
        w = np.concatenate(weights)
        med = float(np.median(r)) if len(r) else 1.0
        lr = np.abs(np.log2(np.sqrt(r / med)))                     # 1.0 = twice / half the median texel density
        bad = float(w[lr > math.log2(stretch_limit)].sum() / max(w.sum(), 1e-12))
        st.update(tris=tris, flipped_tris=flipped, tris_outside_0_1=outside, zero_area_uv_tris=zero)
        st['area_density_off_x%s' % stretch_limit] = round(bad, 3)
        span = np.concatenate([x[0] for x in slivers])
        e3 = np.concatenate([x[1] for x in slivers])
        uv_per_m = math.sqrt(med)                                              # median UV units per metre
        n_sliver = int((span > np.maximum(e3 * uv_per_m * 6, 0.02)).sum())      # triangles stretched across the atlas
        st['atlas_spanning_tris'] = n_sliver
        if n_sliver:
            errors.append('%d triangles stretch across the atlas (live bevel/mirror on seams? freeze before unwrap)' % n_sliver)
        owner, overlap, isl = _raster(have, res, dg)
        cov = float((owner >= 0).mean())
        ov = float(overlap.sum()) / max(1.0, float((owner >= 0).sum()))
        pad = _padding(owner, margin_px)
        st.update(uv_fill=round(cov, 3), overlap_share=round(ov, 4), padding_violation_px=int(pad.sum()),
                  islands=sum(v[1] for v in isl.values()))
        if flipped:
            errors.append('%d flipped UV triangles (mirrored islands)' % flipped)
        if outside:
            (warnings if allow_overlap else errors).append('%d triangles outside 0-1 UV space' % outside)
        if ov > 0.002:
            (warnings if allow_overlap else errors).append('UV overlap %.1f%% of used area' % (100 * ov))
        if pad.sum() > 0:
            warnings.append('%d px closer than %d px to another island at %d px (bleeding on mips)' % (pad.sum(), margin_px, res))
        if bad > 0.05:
            warnings.append('%.0f%% of surface has texel density off by >x%s from the median (stretch / scale)' % (100 * bad, stretch_limit))
        if cov < 0.45:
            warnings.append('UV space only %.0f%% used - pack tighter or lower the texture size' % (100 * cov))
    return dict(ok=not errors, errors=errors, warnings=warnings, stats=st)


def _padding(owner, m):
    if m <= 0:
        return np.zeros_like(owner, bool)
    bad = np.zeros_like(owner, bool)
    H, W = owner.shape
    for dy in range(-m, m + 1):
        for dx in range(-m, m + 1):
            if (dx == 0 and dy == 0) or dx * dx + dy * dy > m * m:
                continue
            sh = np.full_like(owner, -1)
            sh[max(0, dy):H + min(0, dy), max(0, dx):W + min(0, dx)] = owner[max(0, -dy):H - max(0, dy), max(0, -dx):W - max(0, dx)]
            bad |= (owner >= 0) & (sh >= 0) & (sh != owner)
    return bad


def uv_map(objs, path, res=1024, margin_px=None):
    """UV layout picture: each island a colour, overlaps red, padding violations yellow (margin_px at res)."""
    import colorsys
    io = {}
    io.update(_lib('img_io'))
    objs = [o for o in _objs(objs) if o.data.uv_layers]
    owner, overlap, _ = _raster(objs, res)
    img = np.zeros((res, res, 4), np.float32)
    img[...] = (0.09, 0.09, 0.1, 1)
    ids = np.unique(owner[owner >= 0])
    for i in ids:
        img[owner == i] = colorsys.hsv_to_rgb((i * 0.618034) % 1, 0.45, 0.85) + (1.0,)
    if margin_px:
        img[_padding(owner, margin_px)] = (1, 0.85, 0.1, 1)
    img[overlap] = (1, 0.1, 0.1, 1)
    img[::max(1, res // 8), :] = img[::max(1, res // 8), :] * 0.6
    img[:, ::max(1, res // 8)] = img[:, ::max(1, res // 8)] * 0.6
    io['write'](path, img[::-1])               # UV v=0 is the bottom of the texture
    return path


def add_layer(objs, name='UV_Lightmap', from_active=True):
    """Second UV channel (lightmaps / palette workflows keep the real unwrap in channel 1)."""
    for o in _objs(objs):
        if name not in o.data.uv_layers:
            lay = o.data.uv_layers.new(name=name, do_init=from_active)
    return True
