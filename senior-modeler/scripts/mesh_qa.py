# Model QA (library): numbers first, then eyes (review_stage wire / normals / uv modes + uv_tools.uv_map).
#   qa = lib('mesh_qa')
#   rep = qa['qa'](objs, BRIEF)       dict(ok, errors, warnings, stats, per_object) - errors block export
#   qa['fix'](objs)                    merge doubles, delete loose, recalc outside normals, dissolve degenerate (destructive,
#                                      ask before running it on a model you did not build)
#   print(qa['summary'](rep))
# BRIEF keys used (all optional): name, style, asset_type, textures ('pbr'|'palette'|'none'), tri_budget (max) or
# (min, max), size_m (x, y, z) or height_m, origin ('base'|'center'|'world'), ground (True: rests on z=0),
# texture_res, margin_px, allow_uv_overlap, print3d (watertight + no self-intersections), deforming (character).
import bpy, bmesh, math, os, re
from mathutils import Vector
from mathutils.bvhtree import BVHTree

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
NAME_OK = re.compile(r'^[A-Za-z0-9_]+$')


def _objs(objs):
    return [bpy.data.objects[o] if isinstance(o, str) else o for o in objs]


def _eval_bm(o, dg):
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    ev.to_mesh_clear()
    return bm


def _mesh_checks(o, dg, tol):
    bm = _eval_bm(o, dg)
    try:
        bm.verts.ensure_lookup_table()
        tris = sum(len(f.verts) - 2 for f in bm.faces)
        ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
        quads = sum(1 for f in bm.faces if len(f.verts) == 4)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
        boundary = sum(1 for e in bm.edges if e.is_boundary)
        loose_v = sum(1 for v in bm.verts if not v.link_edges)
        loose_e = sum(1 for e in bm.edges if not e.link_faces)
        zero_f = sum(1 for f in bm.faces if f.calc_area() < tol * tol * 1e-2)
        zero_e = sum(1 for e in bm.edges if e.calc_length() < tol * 1e-2)
        # duplicate vertices (by distance)
        from mathutils.kdtree import KDTree
        kd = KDTree(len(bm.verts))
        for v in bm.verts:
            kd.insert(v.co, v.index)
        kd.balance()
        dup = 0
        for v in bm.verts:
            if any(i != v.index for (_, i, _) in kd.find_range(v.co, tol * 1e-3)):
                dup += 1
        # inconsistent / inside-out normals: compare with a recalculated copy
        cp = bm.copy()
        bmesh.ops.recalc_face_normals(cp, faces=cp.faces)
        cp.faces.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        flipped = sum(1 for a, b in zip(bm.faces, cp.faces) if a.normal.dot(b.normal) < 0)
        cp.free()
        nonplanar = 0
        for f in bm.faces:
            if len(f.verts) >= 4:
                n = f.normal
                c = f.calc_center_median()
                size = max((v.co - c).length for v in f.verts)
                if size > 0 and max(abs((v.co - c).dot(n)) for v in f.verts) > 0.06 * size:
                    nonplanar += 1
        return dict(tris=tris, faces=len(bm.faces), verts=len(bm.verts), quads=quads, ngons=ngons,
                    non_manifold_edges=non_manifold, boundary_edges=boundary, loose_verts=loose_v, loose_edges=loose_e,
                    zero_area_faces=zero_f, zero_length_edges=zero_e, duplicate_verts=dup, flipped_faces=flipped,
                    nonplanar_faces=nonplanar)
    finally:
        bm.free()


def _self_intersections(o, dg):
    bm = _eval_bm(o, dg)
    bm.transform(o.matrix_world)
    t = BVHTree.FromBMesh(bm)
    n = len(t.overlap(t))
    bm.free()
    return n


def _bounds(objs, dg):
    pts = []
    for o in objs:
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def qa(objs, brief=None, uv_res=512, uv=True):
    """Full model QA against the brief. errors = must fix before export; warnings = judge per style/asset type.
    uv=False skips UV/texture checks (blockout and modelling passes, before surface.py)."""
    B = dict(brief or {})
    objs = [o for o in _objs(objs) if o.type == 'MESH' and not o.get('gm_collision') and not o.get('gm_cutter')]
    dg = bpy.context.evaluated_depsgraph_get()
    errors, warnings, per = [], [], {}
    lo, hi = _bounds(objs, dg)
    size = hi - lo
    tol = max(size) * 1e-3
    asset = B.get('name')
    tot = dict(tris=0, ngons=0, quads=0, faces=0)
    for o in objs:
        m = _mesh_checks(o, dg, tol)
        per[o.name] = m
        for k in tot:
            tot[k] += m[k]
        tag = o.name + ': '
        # transforms
        s = o.matrix_world.to_scale()
        if any(abs(x - 1) > 1e-4 for x in o.scale):
            (errors if any(x < 0 for x in o.scale) else warnings).append(tag + 'unapplied scale %s' % [round(x, 3) for x in o.scale])
        if any(x < 0 for x in s):
            errors.append(tag + 'negative world scale (normals flip in engines)')
        if o.parent and o.parent.type == 'MESH' and any(abs(x - 1) > 1e-4 for x in o.parent.scale):
            warnings.append(tag + 'parent has unapplied scale')
        # geometry
        if m['flipped_faces']:      # on open meshes (cards, planes) "outside" is ambiguous: warn, check the normals render
            (warnings if m['boundary_edges'] else errors).append(tag + '%d faces with inconsistent/inside-out normals' % m['flipped_faces'])
        if m['loose_verts'] or m['loose_edges']:
            errors.append(tag + 'loose geometry (%d verts, %d edges)' % (m['loose_verts'], m['loose_edges']))
        if m['zero_area_faces'] or m['zero_length_edges']:
            errors.append(tag + 'degenerate geometry (%d zero-area faces, %d zero-length edges)' % (m['zero_area_faces'], m['zero_length_edges']))
        if m['duplicate_verts']:
            warnings.append(tag + '%d overlapping vertices (merge by distance unless intentional splits)' % m['duplicate_verts'])
        if m['non_manifold_edges']:
            (errors if B.get('print3d') else warnings).append(tag + '%d non-manifold edges' % m['non_manifold_edges'])
        if m['boundary_edges'] and B.get('print3d'):
            errors.append(tag + 'open boundary (%d edges) - not watertight' % m['boundary_edges'])
        if m['ngons'] and B.get('deforming', B.get('asset_type') == 'character'):
            warnings.append(tag + '%d n-gons on a deforming mesh (quads deform predictably)' % m['ngons'])
        if m['nonplanar_faces'] > 0.1 * max(1, m['faces']):
            warnings.append(tag + '%d non-planar faces (shading artefacts after triangulation)' % m['nonplanar_faces'])
        if B.get('print3d') and _self_intersections(o, dg):
            errors.append(tag + 'self-intersections (print)')
        # shading vs style
        me = o.data
        smooth = sum(p.use_smooth for p in me.polygons) / max(1, len(me.polygons))
        if B.get('style') == 'low_poly' and smooth > 0.5:
            warnings.append(tag + 'smooth shading on a low-poly style asset (expected flat facets)')
        if B.get('style') in ('stylized', 'realistic', 'cartoon', 'anime') and smooth < 0.2 and m['faces'] > 50:
            warnings.append(tag + 'flat shaded - use auto smooth (shade by angle) + weighted normals')
        # materials
        if not me.materials or all(mm is None for mm in me.materials):
            errors.append(tag + 'no material')
        else:
            used = {p.material_index for p in me.polygons}
            empty = [i for i, mm in enumerate(me.materials) if mm is None]
            if empty:
                errors.append(tag + 'empty material slots %s' % empty)
            unused = [me.materials[i].name for i in range(len(me.materials)) if i not in used and me.materials[i]]
            if unused:
                warnings.append(tag + 'unused material slots %s' % unused)
        # naming
        if not NAME_OK.match(o.name) or re.search(r'\.\d{3}$', o.name):
            warnings.append(tag + 'name has spaces/dots/.001 suffix (engine names)')
        if asset and not o.name.startswith(asset):
            warnings.append(tag + 'name does not start with the asset name %s' % asset)
    # whole-asset checks
    budget = B.get('tri_budget')
    if budget:
        bmin, bmax = (0, budget) if isinstance(budget, (int, float)) else budget
        if tot['tris'] > bmax * 1.1:
            errors.append('triangles %d over budget %d (+10%% tolerance)' % (tot['tris'], bmax))
        elif tot['tris'] > bmax:
            warnings.append('triangles %d slightly over budget %d' % (tot['tris'], bmax))
        elif tot['tris'] < bmin:
            warnings.append('triangles %d under the expected %d - silhouette may read too low-res' % (tot['tris'], bmin))
    tgt = B.get('size_m')
    if tgt:
        for ax, want, got in zip('XYZ', tgt, size):
            if want and abs(got - want) > 0.05 * want:
                warnings.append('size %s %.3f m vs brief %.3f m (%+.0f%%)' % (ax, got, want, 100 * (got - want) / want))
    elif B.get('height_m'):
        if abs(size.z - B['height_m']) > 0.03 * B['height_m']:
            warnings.append('height %.3f m vs brief %.3f m' % (size.z, B['height_m']))
    if B.get('ground', True) and abs(lo.z) > max(0.002, 0.005 * size.z):
        warnings.append('lowest point z=%.4f (asset should rest on the ground plane z=0)' % lo.z)
    origin = B.get('origin', 'base')
    centre = (lo + hi) / 2
    if origin == 'base' and (abs(centre.x) > 0.02 * max(size) or abs(centre.y) > 0.02 * max(size)):
        warnings.append('asset not centred on the world origin in XY (pivot/placement in engine)')
    if max(size) > 200 or max(size) < 0.005:
        warnings.append('size %.3f m looks like a unit mistake (cm/m?)' % max(size))
    # UVs
    res = B.get('texture_res', 2048)
    if not uv:
        stats = dict(objects=len(objs), size_m=[round(x, 4) for x in size], lowest_z=round(lo.z, 4), **tot,
                     quad_share=round(tot['quads'] / max(1, tot['faces']), 3), uv=None, texel_density_px_m=None,
                     texel_spread=None, texture_res=res)
        return dict(ok=not errors, errors=errors, warnings=warnings, stats=stats, per_object=per)
    uv = {}
    uv.update(_lib('uv_tools'))
    margin = B.get('margin_px', 8) * uv_res / float(res)
    u = uv['uv_qa'](objs, res=uv_res, margin_px=max(1, int(round(margin))), allow_overlap=B.get('allow_uv_overlap', False))
    errors += ['UV: ' + e for e in u['errors']]
    warnings += ['UV: ' + w for w in u['warnings']]
    td = uv['texel_density'](objs, res)
    want = B.get('texel_px_m')
    if want and td['overall'] and td['overall'] < 0.8 * want:
        warnings.append('texel density %.0f px/m < target %d at %d px: raise texture_res, pack tighter or accept'
                        % (td['overall'], want, res))
    if B.get('textures', 'pbr') != 'none':
        maps = {n for o in objs for s in o.material_slots if s.material and s.material.use_nodes
                for n in s.material.node_tree.nodes if n.type == 'TEX_IMAGE'}
        for n in maps:
            im = n.image
            if im is None:
                errors.append('image node without an image in %s' % n.id_data.name)
                continue
            p = bpy.path.abspath(im.filepath_raw or '')
            if not im.packed_file and p and not os.path.exists(p) and not im.is_dirty:
                errors.append('missing texture file %s' % p)
            w, h = im.size
            if w and (w & (w - 1) or h & (h - 1)):
                warnings.append('texture %s is %dx%d (not power of two)' % (im.name, w, h))
    stats = dict(objects=len(objs), size_m=[round(x, 4) for x in size], lowest_z=round(lo.z, 4), **tot,
                 quad_share=round(tot['quads'] / max(1, tot['faces']), 3), uv=u['stats'], texel_density_px_m=td['overall'],
                 texel_spread=td['spread'], texture_res=res)
    return dict(ok=not errors, errors=errors, warnings=warnings, stats=stats, per_object=per)


def summary(rep):
    s = rep['stats']
    lines = ['QA %s - %d objects, %d tris (%d%% quads), size %s m, texel %s px/m @%d' % (
        'PASS' if rep['ok'] else 'FAIL', s['objects'], s['tris'], 100 * s['quad_share'], s['size_m'],
        s['texel_density_px_m'], s['texture_res'])]
    lines += ['  ERROR ' + e for e in rep['errors']]
    lines += ['  warn  ' + w for w in rep['warnings']]
    return '\n'.join(lines)


def fix(objs, merge=True, loose=True, normals=True, degenerate=True, dist=None):
    """Destructive cleanup on the base meshes (not the modifier results). Returns what changed per object."""
    out = {}
    for o in _objs(objs):
        if o.type != 'MESH':
            continue
        me = o.data
        bm = bmesh.new()
        bm.from_mesh(me)
        d = dist or max(o.dimensions) * 1e-5 or 1e-6
        r = {}
        if degenerate:
            n = len(bm.edges)
            bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=d)
            r['degenerate'] = n - len(bm.edges)
        if merge:
            n = len(bm.verts)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=d)
            r['merged'] = n - len(bm.verts)
        if loose:
            lv = [v for v in bm.verts if not v.link_edges]
            le = [e for e in bm.edges if not e.link_faces]
            bmesh.ops.delete(bm, geom=le, context='EDGES')
            bmesh.ops.delete(bm, geom=[v for v in lv if v.is_valid], context='VERTS')
            r['loose'] = len(lv) + len(le)
        if normals:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.update()
        out[o.name] = r
    return out
