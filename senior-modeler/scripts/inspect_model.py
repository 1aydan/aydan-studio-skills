# Scene / model inspection (library) - step 1 when the user hands you an existing model or scene. Never assume.
#   im = lib('inspect_model')
#   im['inspect']()                   file, units, add-ons, every object (type, transforms, collections, modifiers...)
#   im['analyze'](['Chair'])          size, ground, tri/quad/ngon mix, shading, UVs, materials, X-symmetry, scale sanity
#   im['snapshot'](['Chair'], out_dir)   quick clay sheet via review_stage (LOOK before editing)
import bpy, os, math
from mathutils import Vector
from mathutils.kdtree import KDTree

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
r3 = lambda v: [round(x, 4) for x in v]


def inspect():
    sc = bpy.context.scene
    objs = []
    for o in sc.objects:
        d = dict(name=o.name, type=o.type, parent=o.parent.name if o.parent else None,
                 collections=[c.name for c in o.users_collection], loc=r3(o.location), rot_deg=r3([math.degrees(a) for a in o.rotation_euler]),
                 scale=r3(o.scale), dims=r3(o.dimensions), hidden=o.hide_get() if o.name in bpy.context.view_layer.objects else None,
                 hide_render=o.hide_render)
        if o.type == 'MESH':
            me = o.data
            d.update(verts=len(me.vertices), faces=len(me.polygons), modifiers=[(m.name, m.type) for m in o.modifiers],
                     materials=[m.name if m else None for m in me.materials], uv_layers=[u.name for u in me.uv_layers],
                     shape_keys=[k.name for k in me.shape_keys.key_blocks] if me.shape_keys else None,
                     color_attrs=[a.name for a in me.color_attributes], skinned=any(m.type == 'ARMATURE' for m in o.modifiers),
                     gm_asset=o.get('gm_asset'))
        objs.append(d)
    return dict(blend=bpy.data.filepath or '(unsaved)', dirty=bpy.data.is_dirty, blender=bpy.app.version_string,
                scene=sc.name, units=(sc.unit_settings.system, sc.unit_settings.scale_length, sc.unit_settings.length_unit),
                render_engine=sc.render.engine, better_fbx=hasattr(bpy.ops, 'better_export') and hasattr(bpy.ops.better_export, 'fbx'),
                gltf=hasattr(bpy.ops.export_scene, 'gltf'), objects=objs,
                images=[(i.name, bpy.path.abspath(i.filepath_raw) if i.filepath_raw else None, tuple(i.size)) for i in bpy.data.images],
                preview_rig='Preview' in bpy.data.collections)


def analyze(objects):
    """Read an existing model before touching it."""
    objs = [bpy.data.objects[o] if isinstance(o, str) else o for o in objects]
    meshes = [o for o in objs if o.type == 'MESH']
    dg = bpy.context.evaluated_depsgraph_get()
    pts, tris, quads, ngons, faces, smooth, flat = [], 0, 0, 0, 0, 0, 0
    sharp = seams = 0
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        pts += [ev.matrix_world @ v.co for v in me.vertices]
        for p in me.polygons:
            n = len(p.vertices)
            tris += n - 2
            faces += 1
            quads += n == 4
            ngons += n > 4
            smooth += p.use_smooth
        sharp += sum(1 for e in me.edges if e.use_edge_sharp)
        seams += sum(1 for e in me.edges if e.use_seam)
        ev.to_mesh_clear()
    if not pts:
        return dict(error='no mesh geometry')
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    size = hi - lo
    centre = (lo + hi) / 2
    # X-mirror symmetry about the bbox centre (share of vertices with a mirrored partner)
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    tol = max(size) * 0.004
    step = max(1, len(pts) // 4000)
    sample = pts[::step]
    sym = sum(1 for p in sample if kd.find(Vector((2 * centre.x - p.x, p.y, p.z)))[2] < tol) / max(1, len(sample))
    longest = 'XYZ'[max(range(3), key=lambda i: size[i])]
    notes = []
    if max(size) > 200 or max(size) < 0.005:
        notes.append('size %.4f m - probably a unit/scale problem (cm import or mm CAD?)' % max(size))
    if any(abs(s - 1) > 1e-4 for o in objs for s in o.scale):
        notes.append('unapplied object scale on %s' % [o.name for o in objs if any(abs(s - 1) > 1e-4 for s in o.scale)])
    if abs(lo.z) > 0.01 * size.z:
        notes.append('not resting on z=0 (lowest z %.4f)' % lo.z)
    if sym > 0.9:
        notes.append('X-symmetric (%.0f%%): model one half + Mirror, check centre-line verts' % (100 * sym))
    return dict(size_m=r3(size), lowest_z=round(lo.z, 4), centre=r3(centre), longest_axis=longest,
                tris=tris, faces=faces, quad_share=round(quads / max(1, faces), 3), ngons=ngons,
                smooth_share=round(smooth / max(1, faces), 3), sharp_edges=sharp, seams=seams,
                uv=[(o.name, [u.name for u in o.data.uv_layers]) for o in meshes],
                materials=sorted({m.name for o in meshes for m in o.data.materials if m}),
                x_symmetry=round(sym, 3), notes=notes)


def snapshot(objects, out_dir, views=('front', 'left', 'back', 'front3q'), mode='clay', asset=None):
    """Clay sheet of existing objects (uses review_stage; nothing in the user's scene changes)."""
    rs = {}
    rs.update(_lib('review_stage'))
    rs['setup'](objects, asset=asset or 'inspect')
    return rs['sheet'](os.path.join(out_dir, 'inspect_%s.png' % mode), views=views, mode=mode)
