# Modeling kit (library) for per-asset build.py scripts. Data-level (bmesh) so it works from MCP without a viewport.
# A build.py execs this INTO ITS OWN GLOBALS, calls begin(), builds parts, and can be re-run any time (it deletes and
# rebuilds only the objects it tagged, or only the parts in ONLY):
#   lib('model_kit', into=globals())                              (lib(): SKILL.md "Running scripts")
#   begin('Lantern', style='stylized', size=0.45)                 size = the asset's largest dimension in metres
#   body = cylinder('Body', r=0.08, h=0.2, loc=(0, 0, 0.05), mat=M['Brass'])
#
# Conventions: metres, Z up, the asset faces -Y (its left is +X), base on z=0 at the origin unless the brief says
# otherwise. Rotations in degrees. Every object is named <Asset>_<Part>, tagged gm_asset/gm_part, scale 1 (sizes are
# baked into the mesh), with style-driven bevel/shading modifiers kept LIVE (non-destructive) until export.
# Primitives mark UV seams (caps + one hidden side seam) so uv_tools.unwrap() gives clean islands.
import bpy, bmesh, math
from mathutils import Vector, Matrix, Euler

V = Vector
STYLE_DEFAULTS = {   # bevel: fraction of the part's smallest dimension (capped by bevel_cap x asset size); segs: cylinder sides
    'stylized': dict(bevel=0.10, bevel_cap=0.02, bevel_segments=2, segs=(12, 32), shade='auto', angle=40, weighted=True),
    'realistic': dict(bevel=0.03, bevel_cap=0.004, bevel_segments=3, segs=(16, 64), shade='auto', angle=30, weighted=True),
    'low_poly': dict(bevel=0.0, bevel_cap=0.0, bevel_segments=1, segs=(6, 12), shade='flat', angle=0, weighted=False),
    'cartoon': dict(bevel=0.22, bevel_cap=0.05, bevel_segments=4, segs=(16, 48), shade='auto', angle=60, weighted=True),
    'anime': dict(bevel=0.06, bevel_cap=0.012, bevel_segments=2, segs=(12, 32), shade='auto', angle=45, weighted=True),
}
KIT = dict(asset=None, style='stylized', size=1.0, coll=None, only=None, D=STYLE_DEFAULTS['stylized'])


# ---------------------------------------------------------------- session
def begin(asset, style='stylized', size=1.0, collection=None, only=None, overrides=None):
    """Start (or restart) building `asset`. Deletes objects previously tagged for this asset (only the parts named in
    `only` when given). style: a key of STYLE_DEFAULTS (mixes: pass overrides=dict(bevel=..., segs=...))."""
    sc = bpy.context.scene
    if sc.name == 'GM_Review':                  # legacy separate review scene from older versions
        raise RuntimeError('active scene is the old GM_Review scene - switch back to the asset scene')
    KIT.update(asset=asset, style=style, size=size, only=set(only) if only else None)
    KIT['D'] = dict(STYLE_DEFAULTS.get(style, STYLE_DEFAULTS['stylized']), **(overrides or {}))
    cname = collection or asset
    coll = bpy.data.collections.get(cname)
    if coll is None:
        coll = bpy.data.collections.new(cname)
        sc.collection.children.link(coll)
    KIT['coll'] = coll
    for o in [o for o in bpy.data.objects if o.get('gm_asset') == asset]:
        if KIT['only'] and o.get('gm_part') not in KIT['only']:
            continue
        _remove(o)
    return KIT


def _remove(o):
    data = o.data
    bpy.data.objects.remove(o)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Curve):
            bpy.data.curves.remove(data)


def skip(name):
    """True when ONLY is set and this part is not in it (build.py: `if not skip('Lid'): ...`)."""
    return bool(KIT['only']) and name not in KIT['only']


def part(name):
    return bpy.data.objects.get('%s_%s' % (KIT['asset'], name))


def parts(asset=None, include_helpers=False):
    asset = asset or KIT['asset']
    return [o for o in bpy.data.objects if o.get('gm_asset') == asset and
            (include_helpers or not (o.get('gm_collision') or o.get('gm_cutter')))]


def _sync():
    """Objects created/moved in this script have STALE matrix_world until the depsgraph updates."""
    bpy.context.view_layer.update()


def _rot(rot):
    return Euler([math.radians(a) for a in rot], 'XYZ')


def _finish(name, bm, loc, rot, mat, parent, bevel, shade, min_dim=None, collection=None):
    full = '%s_%s' % (KIT['asset'], name)
    old = bpy.data.objects.get(full)
    if old is not None:
        _remove(old)
    me = bpy.data.meshes.new(full)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(full, me)
    (collection or KIT['coll']).objects.link(ob)
    ob.location = V(loc)
    ob.rotation_euler = _rot(rot)
    if parent is not None:
        par = parent if isinstance(parent, bpy.types.Object) else part(parent) or bpy.data.objects[parent]
        mw = ob.matrix_world.copy()
        ob.parent = par
        ob.matrix_parent_inverse = par.matrix_world.inverted()
    ob['gm_asset'] = KIT['asset']
    ob['gm_part'] = name
    if mat is not None:
        assign(ob, mat)
    if bevel and min_dim:
        auto = bevel == 'auto'
        w = KIT['D']['bevel'] * min_dim if auto else bevel
        if auto:
            w = min(w, KIT['D']['bevel_cap'] * KIT['size'])
        if w > 0:
            add_bevel(ob, w)
    shade_obj(ob, shade)
    return ob


def segments(r, minimum=None):
    """Cylinder side count for radius r under the current style (multiple of 4, keeps symmetry)."""
    lo, hi = KIT['D']['segs']
    if r < 0.006 * KIT['size']:                 # buttons, studs, fringe, cords: silhouette-irrelevant
        lo = max(6, lo // 2)
    t = min(1.0, math.sqrt(max(r, 1e-6) / (0.25 * KIT['size'])))
    n = lo + (hi - lo) * t
    return max(minimum or lo, int(4 * round(n / 4)))


# ---------------------------------------------------------------- primitives
def box(name, size, loc=(0, 0, 0), rot=(0, 0, 0), base=False, top_scale=None, mat=None, parent=None, bevel='auto',
        shade='style'):
    """size (x, y, z). base=True: origin at the bottom face centre. top_scale=(sx, sy): taper the top face."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, calc_uvs=False)
    sx, sy, sz = size
    for v in bm.verts:
        v.co = V((v.co.x * sx, v.co.y * sy, v.co.z * sz + (sz / 2 if base else 0)))
    if top_scale:
        top = max(v.co.z for v in bm.verts)
        for v in bm.verts:
            if abs(v.co.z - top) < 1e-6:
                v.co.x *= top_scale[0]
                v.co.y *= top_scale[1]
    _box_seams(bm)
    return _finish(name, bm, loc, rot, mat, parent, bevel, shade, min(size))


def _box_seams(bm):
    """Cross-shaped unfold: seams on the top/bottom rims except one edge each, plus the four verticals but one."""
    zs = sorted({round(v.co.z, 6) for v in bm.verts})
    bot, top = zs[0], zs[-1]
    vert_edges = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1e-6]
    rims = [e for e in bm.edges if e not in vert_edges]
    back = max(vert_edges, key=lambda e: (e.verts[0].co.y, e.verts[0].co.x))
    for e in vert_edges:
        e.seam = e is not back
    for z in (bot, top):
        ring = [e for e in rims if abs(e.verts[0].co.z - z) < 1e-6]
        keep = min(ring, key=lambda e: (e.verts[0].co.y + e.verts[1].co.y))       # front edge stays attached
        for e in ring:
            e.seam = e is not keep


def cylinder(name, r, h, n=None, loc=(0, 0, 0), rot=(0, 0, 0), base=True, r_top=None, caps=True, mat=None, parent=None,
             bevel='auto', shade='style'):
    """Along local +Z. base=True: origin at the bottom cap (limbs: rot=(0, 90, 0) points it along +X).
    r_top: taper / cone (0 = point). caps=False: open tube."""
    n = n or segments(max(r, r_top or 0))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=n, radius1=r,
                          radius2=r if r_top is None else max(r_top, 0.0), depth=h)
    if r_top == 0:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    if base:
        for v in bm.verts:
            v.co.z += h / 2
    _ring_seams(bm)
    return _finish(name, bm, loc, rot, mat, parent, bevel, shade, min(2 * r, h))


def _ring_seams(bm, axis=2):
    """Seams around every cap / hard ring and down one side line (the side that faces +Y = back of the asset)."""
    bm.edges.ensure_lookup_table()
    for e in bm.edges:
        f = e.link_faces
        if len(f) == 2 and f[0].normal.angle(f[1].normal, 0) > math.radians(60):
            e.seam = True
    side = [e for e in bm.edges if abs((e.verts[0].co - e.verts[1].co).normalized()[axis]) > 0.3
            and not any(len(f.verts) > 4 for f in e.link_faces)]
    if side:
        key = lambda e: (round(-(e.verts[0].co.y + e.verts[1].co.y), 4), abs(e.verts[0].co.x + e.verts[1].co.x))
        best = min(side, key=key)
        line = [e for e in side if abs(e.verts[0].co.x + e.verts[1].co.x - best.verts[0].co.x - best.verts[1].co.x) < 1e-5
                and abs(e.verts[0].co.y + e.verts[1].co.y - best.verts[0].co.y - best.verts[1].co.y) < 1e-5]
        for e in line:
            e.seam = True


def sphere(name, r, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), n=None, rings=None, mat=None, parent=None,
           shade='smooth'):
    """UV sphere (radius r, then scaled per axis into the mesh). Seam down the back meridian."""
    n = n or segments(r * max(scale))
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=n, v_segments=rings or max(4, n // 2), radius=r)
    for v in bm.verts:
        v.co = V((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
    _meridian_seam(bm)
    return _finish(name, bm, loc, rot, mat, parent, None, shade)


def _meridian_seam(bm):
    for e in bm.edges:
        a, b = e.verts[0].co, e.verts[1].co
        if abs(a.x) < 1e-6 and abs(b.x) < 1e-6 and a.y >= -1e-6 and b.y >= -1e-6:
            e.seam = True


def lathe(name, profile, n=None, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, cap=True, shade='style',
          bevel=None, scale=(1, 1)):
    """Revolve [(radius, z), ...] (bottom -> top) around local Z. radius 0 = pole. cap=True closes open ends with
    an n-gon. scale=(sx, sy) makes it elliptical (torsos, flattened bottles). The profile can come straight from
    concept_match.profile() x the real height. Seam on the back."""
    n = n or segments(max(p[0] for p in profile))
    bm = bmesh.new()
    rings = []
    sx, sy = scale
    for r, z in profile:
        if r < 1e-6:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((sx * r * math.sin(2 * math.pi * i / n), -sy * r * math.cos(2 * math.pi * i / n), z))
                          for i in range(n)])
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        for i in range(n):
            j = (i + 1) % n
            if len(a) == 1:
                bm.faces.new((a[0], b[i], b[j]))
            elif len(b) == 1:
                bm.faces.new((a[i], a[j], b[0]))
            else:
                bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap:
        if len(rings[0]) > 1:
            bm.faces.new(list(reversed(rings[0])))
        if len(rings[-1]) > 1:
            bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for e in bm.edges:
        a, b = e.verts[0].co, e.verts[1].co
        if abs(a.x) < 1e-6 and abs(b.x) < 1e-6 and a.y >= -1e-9 and b.y >= -1e-9 and (a - b).length > 0:
            e.seam = True
        elif len(e.link_faces) == 2 and any(len(f.verts) > 4 for f in e.link_faces):
            e.seam = True
    # pole caps (domes, flat tops ending in r=0): seam ring where the cap starts, so the cap unwraps as a disc
    # instead of stretching around the single meridian seam
    for ends in (range(len(profile)), range(len(profile) - 1, -1, -1)):
        idx = list(ends)
        if profile[idx[0]][0] > 1e-6:
            continue
        k = 1
        while k < len(idx) - 1:
            (r0, z0), (r1, z1) = profile[idx[k - 1]], profile[idx[k]]
            (r2, z2) = profile[idx[k + 1]]
            if abs(z2 - z1) > abs(r2 - r1):          # next segment is steep: the cap ends at ring k
                break
            k += 1
        ring = rings[idx[k]]
        if len(ring) > 1:
            for i in range(len(ring)):
                e = bm.edges.get((ring[i], ring[(i + 1) % len(ring)]))
                if e:
                    e.seam = True
    md = min(2 * max(p[0] for p in profile), abs(profile[-1][1] - profile[0][1]))
    return _finish(name, bm, loc, rot, mat, parent, bevel, shade, md)


def extrude(name, pts, depth, plane='XZ', loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, bevel='auto',
            shade='style'):
    """Closed 2D outline extruded symmetrically: plane 'XZ' (front view, depth along Y), 'YZ' (side), 'XY' (top).
    Good for shields, blades, signs, badges - or a silhouette traced from concept_match.measure() rows."""
    bm = bmesh.new()
    ax = {'XZ': (0, 2, 1), 'YZ': (1, 2, 0), 'XY': (0, 1, 2)}[plane]
    def P(u, v, w):
        c = [0.0, 0.0, 0.0]
        c[ax[0]], c[ax[1]], c[ax[2]] = u, v, w
        return c
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if area < 0:
        pts = list(reversed(pts))
    f0 = [bm.verts.new(P(u, v, -depth / 2)) for u, v in pts]
    f1 = [bm.verts.new(P(u, v, depth / 2)) for u, v in pts]
    bm.faces.new(f0)
    bm.faces.new(list(reversed(f1)))
    k = len(pts)
    for i in range(k):
        j = (i + 1) % k
        bm.faces.new((f0[i], f0[j], f1[j], f1[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for e in bm.edges:
        if any(len(f.verts) > 4 for f in e.link_faces):
            e.seam = True
    us = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    return _finish(name, bm, loc, rot, mat, parent, bevel, shade, min(max(us) - min(us), max(vs) - min(vs), depth))


def torus(name, R, r, n=None, m=None, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, shade='smooth'):
    """Ring in the local XY plane (major radius R, tube radius r). Rims, belts, handles, coils."""
    n = n or segments(R)
    m = m or max(6, min(16, segments(r) // 2) // 2 * 2)      # tube cross-section: half the main density
    bm = bmesh.new()
    grid = []
    for i in range(n):
        a = 2 * math.pi * i / n
        row = []
        for j in range(m):
            b = 2 * math.pi * j / m
            rr = R + r * math.cos(b)
            row.append(bm.verts.new((rr * math.sin(a), -rr * math.cos(a), r * math.sin(b))))
        grid.append(row)
    for i in range(n):
        for j in range(m):
            a, b, c, d = grid[i][j], grid[(i + 1) % n][j], grid[(i + 1) % n][(j + 1) % m], grid[i][(j + 1) % m]
            bm.faces.new((a, b, c, d))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    for e in bm.edges:
        (a, b) = e.verts
        ia, ja = divmod(a.index, m)
        ib, jb = divmod(b.index, m)
        if (ia == ib == n // 2) or (ja == jb == m // 2):       # one ring across the back + one around the inside
            e.seam = True
    return _finish(name, bm, loc, rot, mat, parent, None, shade)


def tube(name, pts, r, n=None, smooth=True, caps=True, loc=(0, 0, 0), mat=None, parent=None, resolution=3,
         taper=None):
    """Sweep a circle of radius r along a polyline (smooth=True: Bezier through the points). Cables, cords, rope
    trims, pipes, handles, horns (taper=(r_start, r_end) scales the radius along the path)."""
    cu = bpy.data.curves.new('GM_tmp_tube', 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_mode = 'ROUND'
    cu.bevel_depth = r
    cu.bevel_resolution = max(1, (n or segments(r)) // 4 - 1)
    cu.use_fill_caps = caps
    cu.resolution_u = resolution
    if smooth:
        sp = cu.splines.new('BEZIER')
        sp.bezier_points.add(len(pts) - 1)
        for bp, p in zip(sp.bezier_points, pts):
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = 'AUTO'
        pts_ = sp.bezier_points
    else:
        sp = cu.splines.new('POLY')
        sp.points.add(len(pts) - 1)
        for pp, p in zip(sp.points, pts):
            pp.co = (p[0], p[1], p[2], 1)
        pts_ = sp.points
    if taper:
        for i, p in enumerate(pts_):
            t = i / max(1, len(pts_) - 1)
            p.radius = (taper[0] + (taper[1] - taper[0]) * t) / r
    tmp = bpy.data.objects.new('GM_tmp_tube', cu)
    bpy.context.scene.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg), depsgraph=dg)
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=r * 1e-4)
    return _finish(name, bm, loc, (0, 0, 0), mat, parent, None, shade='smooth')


def from_bmesh(name, bm, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, bevel=None, shade='style'):
    """Wrap custom bmesh geometry as a tagged part (for anything the primitives do not cover)."""
    return _finish(name, bm, loc, rot, mat, parent, bevel, shade, None)


# ---------------------------------------------------------------- copies / mirrors
def mirror_copy(ob, name, axis='X'):
    """Separate mirrored part (right boot from the left one). Transforms are baked; modifiers and materials copied."""
    _sync()
    ob = ob if isinstance(ob, bpy.types.Object) else part(ob)
    i = 'XYZ'.index(axis)
    S = Matrix.Identity(4)
    S[i][i] = -1
    full = '%s_%s' % (KIT['asset'], name)
    if bpy.data.objects.get(full) is not None and bpy.data.objects[full] != ob:
        _remove(bpy.data.objects[full])
    me = ob.data.copy()
    me.name = full
    mw = ob.matrix_world.copy()
    me.transform(mw)
    me.transform(S)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    origin = S @ mw.translation
    for v in bm.verts:
        v.co -= origin
    bm.to_mesh(me)
    bm.free()
    new = bpy.data.objects.new(me.name, me)
    KIT['coll'].objects.link(new)
    new.location = origin
    for k in ('gm_asset',):
        new[k] = ob[k]
    new['gm_part'] = name
    for md in ob.modifiers:
        nm = new.modifiers.new(md.name, md.type)
        for p in md.bl_rna.properties:
            if not p.is_readonly and p.identifier not in ('name', 'type'):
                try:
                    setattr(nm, p.identifier, getattr(md, p.identifier))
                except Exception:
                    pass
    return new


def duplicate(ob, name, loc=None, rot=None, linked=False):
    """Copy of a part (buttons, studs, rivets). linked=True shares mesh data (instances)."""
    ob = ob if isinstance(ob, bpy.types.Object) else part(ob)
    full = '%s_%s' % (KIT['asset'], name)
    if bpy.data.objects.get(full):
        _remove(bpy.data.objects[full])
    new = ob.copy()
    if not linked:
        new.data = ob.data.copy()
        new.data.name = full
    new.name = full
    KIT['coll'].objects.link(new)
    new['gm_part'] = name
    if loc is not None:
        new.location = V(loc)
    if rot is not None:
        new.rotation_euler = _rot(rot)
    return new


# ---------------------------------------------------------------- modifiers / shading
def add_bevel(ob, width, segments=None, angle=30, limit='ANGLE'):
    md = ob.modifiers.get('GM_Bevel') or ob.modifiers.new('GM_Bevel', 'BEVEL')
    md.width = width
    md.segments = segments or KIT['D']['bevel_segments']
    md.limit_method = limit
    md.angle_limit = math.radians(angle)
    md.use_clamp_overlap = True
    md.mark_seam = True               # bevel strips on seam edges stay seams when frozen before unwrap
    md.miter_outer = 'MITER_ARC' if KIT['style'] in ('stylized', 'cartoon') else 'MITER_SHARP'
    _wn_last(ob)
    return md


def _wn_last(ob):
    if not KIT['D'].get('weighted'):
        return
    wn = ob.modifiers.get('GM_WeightedNormal') or ob.modifiers.new('GM_WeightedNormal', 'WEIGHTED_NORMAL')
    wn.keep_sharp = True
    wn.mode = 'FACE_AREA'
    while ob.modifiers[-1] != wn:
        bpy.context.view_layer.update()
        idx = list(ob.modifiers).index(wn)
        ob.modifiers.move(idx, len(ob.modifiers) - 1)


def mirror(ob, axis='X', bisect=False, mirror_u=False, merge=True):
    md = ob.modifiers.new('GM_Mirror', 'MIRROR')
    md.use_axis = [a == axis for a in 'XYZ']
    md.use_bisect_axis = [bisect and a == axis for a in 'XYZ']
    md.use_clip = True
    md.use_mirror_merge = merge
    md.use_mirror_u = mirror_u        # offset mirrored UVs? (False = stacked: saves space, no unique bake)
    _first(ob, md)
    return md


def subsurf(ob, levels=1, render=None):
    md = ob.modifiers.new('GM_Subsurf', 'SUBSURF')
    md.levels = levels
    md.render_levels = render or levels
    _wn_last(ob)
    return md


def solidify(ob, thickness, offset=-1.0):
    md = ob.modifiers.new('GM_Solidify', 'SOLIDIFY')
    md.thickness = thickness
    md.offset = offset
    md.use_even_offset = True
    _first(ob, md)
    return md


def array(ob, count, offset=(1, 0, 0), relative=True):
    md = ob.modifiers.new('GM_Array', 'ARRAY')
    md.count = count
    md.use_relative_offset = relative
    md.use_constant_offset = not relative
    if relative:
        md.relative_offset_displace = offset
    else:
        md.constant_offset_displace = offset
    _first(ob, md)
    return md


def boolean(ob, cutter, op='DIFFERENCE', apply_now=False):
    """cutter: a part (or object) used as a cutter; it is tagged gm_cutter (never exported) and hidden."""
    cutter = cutter if isinstance(cutter, bpy.types.Object) else part(cutter)
    cutter['gm_cutter'] = True
    cutter.display_type = 'WIRE'
    cutter.hide_render = True
    md = ob.modifiers.new('GM_Bool_' + cutter.name, 'BOOLEAN')
    md.operation = op
    md.object = cutter
    md.solver = 'EXACT'
    _first(ob, md)
    if apply_now:
        apply(ob, md.name)
    return md


def _first(ob, md):
    """Generators/deformers go before bevel + weighted normal."""
    idx = list(ob.modifiers).index(md)
    firsts = [i for i, m in enumerate(ob.modifiers) if m.name in ('GM_Bevel', 'GM_WeightedNormal', 'GM_Subsurf')]
    if firsts and idx > min(firsts):
        ob.modifiers.move(idx, min(firsts))


def shade_obj(ob, mode='style', angle=None):
    """'flat' | 'smooth' | 'auto' (smooth + sharp edges above angle) | 'style' (from the style defaults)."""
    me = ob.data
    if mode == 'style':
        mode = KIT['D']['shade']
    if mode == 'flat':
        me.shade_flat()
    elif mode == 'smooth':
        me.shade_smooth()
    else:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(angle or KIT['D']['angle'] or 30))


def apply(ob, modifier='all'):
    """Apply one modifier (name) or 'all' - destructive, prefer keeping them live until export."""
    names = [m.name for m in ob.modifiers] if modifier == 'all' else [modifier]
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        for n in names:
            bpy.ops.object.modifier_apply(modifier=n)


# ---------------------------------------------------------------- materials / faces
def assign(ob, mat, faces=None):
    """Add mat to ob (once) and assign it to faces (indices or fn(centre, normal) -> bool, local space), or all."""
    me = ob.data
    if mat.name not in [m.name for m in me.materials if m]:
        me.materials.append(mat)
    idx = [m.name if m else None for m in me.materials].index(mat.name)
    if faces is None:
        if len(me.materials) == 1:
            for p in me.polygons:
                p.material_index = idx
        return idx
    sel = faces if not callable(faces) else [p.index for p in me.polygons if faces(V(p.center), V(p.normal))]
    for i in sel:
        me.polygons[i].material_index = idx
    return idx


def faces_where(ob, fn):
    return [p.index for p in ob.data.polygons if fn(V(p.center), V(p.normal))]


# ---------------------------------------------------------------- transforms / origins
def apply_transforms(ob):
    """Bake loc/rot/scale into the mesh (data-level; bpy.ops.object.transform_apply can no-op from MCP)."""
    if ob.parent:
        raise ValueError('unparent first')
    ob.data.transform(ob.matrix_basis)
    ob.matrix_basis = Matrix.Identity(4)


def set_origin(ob, where='base'):
    """'base' (bottom centre), 'center' (bbox centre), 'world' (0,0,0) or a world point. Mesh stays in place."""
    _sync()
    mw = ob.matrix_world
    pts = [mw @ v.co for v in ob.data.vertices]
    lo = V((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = V((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    target = {'base': V(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)), 'center': (lo + hi) / 2,
              'world': V((0, 0, 0))}.get(where) if isinstance(where, str) else V(where)
    local = mw.inverted() @ target
    ob.data.transform(Matrix.Translation(-local))
    ob.matrix_world = mw @ Matrix.Translation(local)


def join(objs, name):
    """Join parts into one object named <Asset>_<name> (destructive; export can join temporary copies instead)."""
    objs = [o if isinstance(o, bpy.types.Object) else part(o) for o in objs]
    with bpy.context.temp_override(active_object=objs[0], object=objs[0], selected_objects=objs, selected_editable_objects=objs):
        bpy.ops.object.join()
    ob = objs[0]
    ob.name = ob.data.name = '%s_%s' % (KIT['asset'], name)
    ob['gm_part'] = name
    return ob


def set_pose(objs, pivot, rot=(0, 0, 0)):
    """Pose rigid parts as a group about a world pivot (degrees, XYZ), ABSOLUTE from their built rest transform
    (stored in gm_rest on first use). Arm angle T<->A, lid open, door swing, turret yaw. Only object transforms
    change, so UVs, bakes and modifiers survive; export bakes the posed world transforms."""
    _sync()
    P = Matrix.Translation(V(pivot))
    R = _rot(rot).to_matrix().to_4x4()
    for o in objs:
        o = o if isinstance(o, bpy.types.Object) else part(o)
        if 'gm_rest' not in o:
            o['gm_rest'] = [x for row in o.matrix_world for x in row]
        rest = Matrix([o['gm_rest'][i * 4:i * 4 + 4] for i in range(4)])
        o.matrix_world = P @ R @ P.inverted() @ rest
    return len(objs)


def group(objs, name, pivot):
    """Tag rigid parts as a pose group with its pivot (world, metres): arms, lids, doors, wheels."""
    for o in objs:
        o = o if isinstance(o, bpy.types.Object) else part(o)
        o['gm_group'] = name
        o['gm_pivot'] = list(pivot)
    return name


def pose_group(name, rot=(0, 0, 0), asset=None):
    """Pose a group by name (absolute rotation from the built rest). review.py POSES / export use this."""
    objs = [o for o in parts(asset, include_helpers=True) if o.get('gm_group') == name]
    if not objs:
        raise ValueError('no group %s' % name)
    return set_pose(objs, objs[0]['gm_pivot'], rot)


def groups(asset=None):
    return sorted({o['gm_group'] for o in parts(asset, include_helpers=True) if o.get('gm_group')})


def bounds(objs=None):
    _sync()
    objs = objs or parts()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ V(c) for c in ev.bound_box]
    lo = V((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = V((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


# ---------------------------------------------------------------- game helpers
def collision(objs, kind='convex', name='Collision'):
    """UCX_ collision hull for game engines (box or convex hull of the parts). Tagged gm_collision; exported as
    UCX_SM_<Asset>_## next to the mesh."""
    _sync()
    objs = [o if isinstance(o, bpy.types.Object) else part(o) for o in (objs if isinstance(objs, (list, tuple)) else [objs])]
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        pts += [ev.matrix_world @ v.co for v in me.vertices]
        ev.to_mesh_clear()
    bm = bmesh.new()
    if kind == 'box':
        lo = V((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = V((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co = V(((lo.x + hi.x) / 2 + v.co.x * (hi.x - lo.x), (lo.y + hi.y) / 2 + v.co.y * (hi.y - lo.y),
                      (lo.z + hi.z) / 2 + v.co.z * (hi.z - lo.z)))
    else:
        vs = [bm.verts.new(p) for p in pts]
        bmesh.ops.convex_hull(bm, input=vs)
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _finish(name, bm, (0, 0, 0), (0, 0, 0), None, None, None, 'flat')
    ob['gm_collision'] = True
    ob.display_type = 'WIRE'
    ob.hide_render = True
    return ob
