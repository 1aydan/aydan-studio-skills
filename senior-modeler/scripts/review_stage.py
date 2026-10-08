# Preview stage (library): camera rig, 3-point lights, floor and scale figure live IN THE MODEL SCENE, in a
# "Preview" collection - open the .blend and the asset is already framed (scene camera, hero 3/4 view), ready to
# render or show to the team. Preview objects are never tagged gm_asset, so QA and export ignore them. Every render
# restores the scene's render settings (engine, resolution, colour management, world, overrides) afterwards and
# hides non-asset objects only while it renders.
#   rs = lib('review_stage')
#   rs['setup'](['Crate_Body', 'Crate_Lid'], asset='Crate', front='-Y', scale_ref='human')
#   rs['render'](png, view='front3q', mode='clay')               one still
#   rs['sheet'](png, views=('front', 'left', 'back', 'front3q'), mode='clay')
#   rs['turntable'](png_or_mp4, frames=8)                        stills sheet, or an .mp4 when the path ends in .mp4
#   rs['review'](asset, modes=(...), views=(...), concept={...})  numbered revision pack -> <out_root>/renders/r##
#   rs['compare_revisions'](asset, 'r02', 'r03', 'clay')          before | after strip
#   rs['present'](asset, concept=img)                             team pack -> <out_root>/renders/present/
#   rs['cleanup']()                                               remove the Preview collection (asset objects untouched)
#
# Modes: clay (Workbench studio, cavity, shadows)   silhouette (black on white, for shape/concept checks)
#        wire (clay + edge overlay)   parts (one colour + number per object, legend returned - "part 4 is too thin")
#        material (EEVEE, the asset's materials)   uv (EEVEE checker override)   normals (blue front / red back faces)
# Views: front back left right top (orthographic), front3q right3q back3q hero (perspective), or (azimuth, elevation,
#        ortho). Azimuth is measured from the asset's front toward ITS left. `front` = the axis the asset faces.
import bpy, math, os, json
import numpy as np
from mathutils import Vector, Matrix, Euler

STAGE = 'Preview'                     # collection in the model scene holding the preview rig
LEGACY_SCENE = 'GM_Review'            # older versions used a separate scene; setup() removes it
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

VIEWS = {
    'front': (0, 0, True), 'back': (180, 0, True), 'left': (90, 0, True), 'right': (-90, 0, True), 'top': (0, 90, True),
    'front3q': (35, 14, False), 'right3q': (-35, 14, False), 'back3q': (145, 18, False), 'hero': (28, 4, False),
    'low3q': (35, -10, False), 'high3q': (35, 40, False),
}
FRONT_VEC = {'-Y': (0, -1, 0), '+Y': (0, 1, 0), '-X': (-1, 0, 0), '+X': (1, 0, 0)}
CLAY = (0.72, 0.71, 0.69, 1.0)
BG_DARK = (0.105, 0.11, 0.125)
OUT_ROOT = None                       # setup(out_root=...) - normally the asset folder assets/<slug>/


# ---------------------------------------------------------------- scene plumbing
def _scene():
    """The model scene (the one shown in the window)."""
    sc = bpy.context.window.scene if bpy.context.window else bpy.context.scene
    if sc.name == LEGACY_SCENE:
        sc = next(s for s in bpy.data.scenes if s.name != LEGACY_SCENE)
        bpy.context.window.scene = sc
    return sc


def _coll(name, sc=None):
    sc = sc or _scene()
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    if c.name not in sc.collection.children:
        sc.collection.children.link(c)
    return c


def _obj(name, data, coll):
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, data)
    elif data is not None and ob.data != data:
        ob.data = data
    if ob.name not in coll.objects:
        coll.objects.link(ob)
    return ob


def _mesh(name, verts, faces):
    me = bpy.data.meshes.get(name) or bpy.data.meshes.new(name)
    me.clear_geometry()
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def _mat(name, color, emission=False):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    if emission:
        sh = nt.nodes.new('ShaderNodeEmission')
        sh.inputs['Color'].default_value = color
    else:
        sh = nt.nodes.new('ShaderNodeBsdfPrincipled')
        sh.inputs['Base Color'].default_value = color
        sh.inputs['Roughness'].default_value = 0.8
    nt.links.new(sh.outputs[0], out.inputs['Surface'])
    m.diffuse_color = color
    return m


def subject():
    sc = _scene()
    if 'gm' not in sc:
        return []
    return [bpy.data.objects[n] for n in json.loads(sc['gm'])['objects'] if n in bpy.data.objects]


def _bounds(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type not in ('MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES', 'POINTCLOUD', 'VOLUME'):
            continue
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    if not pts:
        raise ValueError('no geometry in subject')
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _nice_step(x):
    for s in (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 25, 50, 100):
        if s >= x:
            return s
    return 100


# ---------------------------------------------------------------- setup
def setup(objects, asset=None, front='-Y', floor=True, grid=True, scale_ref=None, res=(1200, 1200), lens=60,
          out_root=None, view_transform='Standard'):
    """objects: names (or objects) of the asset. scale_ref: None | 'human' (1.8 m figure) | 'cube' (1 m cube).
    Re-run after big shape changes (framing and floor are sized from the asset bbox)."""
    sc = _scene()
    _remove_legacy()
    objs = [bpy.data.objects[o] if isinstance(o, str) else o for o in objects]
    stage = _coll(STAGE, sc)
    lo, hi = _bounds(objs)
    size = hi - lo
    centre = (lo + hi) / 2
    R = max(size.length / 2, 1e-3)
    sc['gm'] = json.dumps(dict(asset=asset or objs[0].name, front=front, lo=list(lo), hi=list(hi),
                               out_root=_out_root(out_root), objects=[o.name for o in objs], res=list(res),
                               view_transform=view_transform))
    # pivot / camera / lights
    piv = _obj('GM_Pivot', None, stage)
    piv.empty_display_size = R * 0.2
    piv.location = centre
    piv.rotation_euler = (0, 0, 0)
    cd = bpy.data.cameras.get('GM_Cam') or bpy.data.cameras.new('GM_Cam')
    cd.lens = lens
    cd.sensor_fit = 'AUTO'
    cam = _obj('GM_Cam', cd, stage)
    cam.parent = piv
    sc.camera = cam
    for name, kind in (('GM_Key', 'AREA'), ('GM_Fill', 'AREA'), ('GM_Rim', 'AREA')):
        ld = bpy.data.lights.get(name) or bpy.data.lights.new(name, kind)
        ld.shape = 'DISK'
        ld.size = R * 1.6
        lo_ = _obj(name, ld, stage)
        lo_.parent = piv
    # floor: checker tiles sized to the asset (step shown in the HUD)
    for n in ('GM_FloorA', 'GM_FloorB', 'GM_ScaleRef'):
        if bpy.data.objects.get(n):
            bpy.data.objects.remove(bpy.data.objects[n])
    step = _nice_step(max(size.x, size.y, size.z) / 4)
    if floor:
        rad = max(R * 6, step * 4)
        n = int(math.ceil(rad / step))
        va, fa, vb, fb = [], [], [], []
        z = lo.z - 0.0005 * R
        for ix in range(-n, n):
            for iy in range(-n, n):
                x0, y0 = centre.x + ix * step, centre.y + iy * step
                if math.hypot(x0 + step / 2 - centre.x, y0 + step / 2 - centre.y) > rad:
                    continue
                v, f = (va, fa) if (not grid or (ix + iy) % 2 == 0) else (vb, fb)
                b = len(v)
                v += [(x0, y0, z), (x0 + step, y0, z), (x0 + step, y0 + step, z), (x0, y0 + step, z)]
                f.append((b, b + 1, b + 2, b + 3))
        for name, v, f, col in (('GM_FloorA', va, fa, (0.32, 0.33, 0.36, 1)), ('GM_FloorB', vb, fb, (0.27, 0.28, 0.31, 1))):
            if f:
                ob = _obj(name, _mesh(name, v, f), stage)
                ob.color = col
                ob.data.materials.clear()
                ob.data.materials.append(_mat(name + '_mat', col))
    if scale_ref:
        x = hi.x + max(0.25, size.x * 0.3)
        if scale_ref == 'human':      # 1.8 m blockout figure
            v, f = _human(x, centre.y, lo.z)
        else:
            s = 1.0
            v = [(x, centre.y - s / 2, lo.z), (x + s, centre.y - s / 2, lo.z), (x + s, centre.y + s / 2, lo.z), (x, centre.y + s / 2, lo.z)]
            v += [(a, b, c + s) for a, b, c in v]
            f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        ob = _obj('GM_ScaleRef', _mesh('GM_ScaleRef', v, f), stage)
        ob.color = (0.25, 0.45, 0.75, 1)
        ob.data.materials.clear()
        ob.data.materials.append(_mat('GM_ScaleRef_mat', (0.25, 0.45, 0.75, 1)))
    # HUD label, parented to the camera
    td = bpy.data.curves.get('GM_HUD') or bpy.data.curves.new('GM_HUD', 'FONT')
    hud = _obj('GM_HUD', td, stage)
    hud.parent = cam
    hud.color = (0.92, 0.92, 0.92, 1)
    hud.visible_shadow = False
    hud.hide_set(True)                                        # render-only label, keeps the viewport clean
    td.materials.clear()
    td.materials.append(_mat('GM_HUD_mat', (0.92, 0.92, 0.92, 1), emission=True))
    sc['gm_step'] = step
    if scale_ref:                                            # frame the asset AND the scale figure
        flo, fhi = _bounds(objs + [bpy.data.objects['GM_ScaleRef']])
        st = json.loads(sc['gm'])
        st.update(frame_lo=list(flo), frame_hi=list(fhi))
        sc['gm'] = json.dumps(st)
    # world + render basics
    w = bpy.data.worlds.get('GM_World') or bpy.data.worlds.new('GM_World')
    w.use_nodes = True
    bgn = next((n for n in w.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bgn:
        bgn.inputs['Color'].default_value = (0.05, 0.052, 0.058, 1)
        bgn.inputs['Strength'].default_value = 1.0
    w.color = BG_DARK
    if sc.world is None:                                     # otherwise used only while rendering
        sc.world = w
    set_view('front3q')
    return dict(scene=sc.name, collection=STAGE, centre=[round(c, 4) for c in centre], size=[round(s, 4) for s in size], floor_step=step,
                objects=[o.name for o in objs])


def _out_root(out_root):
    """Where renders go: the given folder (the asset folder), else next to the .blend, else the temp dir."""
    if out_root or OUT_ROOT:
        return out_root or OUT_ROOT
    import tempfile
    return os.path.dirname(bpy.data.filepath) if bpy.data.filepath else tempfile.gettempdir()


def _human(x, y, z0):
    """Crude 1.8 m figure (box legs/torso + head) beside the asset for scale."""
    boxes = [((x + 0.06, y, z0 + 0.43), (0.13, 0.16, 0.86)), ((x + 0.25, y, z0 + 0.43), (0.13, 0.16, 0.86)),
             ((x + 0.155, y, z0 + 1.17), (0.42, 0.22, 0.62)), ((x + 0.155, y, z0 + 1.6), (0.19, 0.22, 0.26)),
             ((x - 0.11, y, z0 + 1.12), (0.09, 0.1, 0.7)), ((x + 0.42, y, z0 + 1.12), (0.09, 0.1, 0.7))]
    v, f = [], []
    for (cx, cy, cz), (sx, sy, sz) in boxes:
        b = len(v)
        for dz in (-0.5, 0.5):
            v += [(cx - sx / 2, cy - sy / 2, cz + dz * sz), (cx + sx / 2, cy - sy / 2, cz + dz * sz),
                  (cx + sx / 2, cy + sy / 2, cz + dz * sz), (cx - sx / 2, cy + sy / 2, cz + dz * sz)]
        f += [(b, b + 3, b + 2, b + 1), (b + 4, b + 5, b + 6, b + 7), (b, b + 1, b + 5, b + 4), (b + 1, b + 2, b + 6, b + 5),
              (b + 2, b + 3, b + 7, b + 6), (b + 3, b, b + 4, b + 7)]
    return v, f


def _state():
    return json.loads(_scene()['gm'])


def _remove_legacy():
    """Older versions kept the rig in a separate 'GM_Review' scene - delete it (asset objects stay)."""
    old = bpy.data.scenes.get(LEGACY_SCENE)
    if old is None:
        return
    for cname in ('GM_Stage', 'GM_Subject'):
        c = bpy.data.collections.get(cname)
        if c:
            if cname == 'GM_Stage':
                for o in list(c.objects):
                    bpy.data.objects.remove(o)
            bpy.data.collections.remove(c)
    bpy.data.scenes.remove(old)


class _KeepRender:
    """Snapshot/restore every scene setting a preview render touches; hide non-asset objects meanwhile."""
    def __init__(self, sc, show):
        self.sc, self.show = sc, set(show)

    def __enter__(self):
        sc, r, sh = self.sc, self.sc.render, self.sc.display.shading
        self.k = dict(engine=r.engine, rx=r.resolution_x, ry=r.resolution_y, pct=r.resolution_percentage,
                      path=r.filepath, fmt=r.image_settings.file_format, cm=r.image_settings.color_mode,
                      comp=r.image_settings.compression, depth=r.image_settings.color_depth,
                      media=getattr(r.image_settings, 'media_type', None), film=r.film_transparent,
                      vt=sc.view_settings.view_transform, look=sc.view_settings.look, world=sc.world,
                      fs=sc.frame_start, fe=sc.frame_end, aa=sc.display.render_aa,
                      eevee=getattr(sc.eevee, 'taa_render_samples', None),
                      override=bpy.context.view_layer.material_override,
                      shading={a: getattr(sh, a) for a in ('light', 'color_type', 'show_cavity', 'show_shadows',
                               'show_object_outline', 'background_type', 'show_specular_highlight')},
                      bg=tuple(sh.background_color))
        self.hidden = [o for o in sc.objects if not o.hide_render and o not in self.show]
        for o in self.hidden:
            o.hide_render = True
        st = json.loads(sc['gm'])
        r.resolution_x, r.resolution_y = st.get('res', (1200, 1200))
        r.resolution_percentage = 100
        r.film_transparent = False
        sc.view_settings.view_transform = st.get('view_transform', 'Standard')
        sc.view_settings.look = 'None'
        sc.world = bpy.data.worlds.get('GM_World') or sc.world
        return self

    def __exit__(self, *a):
        sc, r, sh, k = self.sc, self.sc.render, self.sc.display.shading, self.k
        r.engine, r.filepath = k['engine'], k['path']
        r.resolution_x, r.resolution_y, r.resolution_percentage = k['rx'], k['ry'], k['pct']
        if k['media'] is not None:
            r.image_settings.media_type = k['media']
        r.image_settings.file_format, r.image_settings.color_mode = k['fmt'], k['cm']
        r.image_settings.compression, r.image_settings.color_depth = k['comp'], k['depth']
        r.film_transparent = k['film']
        sc.view_settings.view_transform, sc.view_settings.look, sc.world = k['vt'], k['look'], k['world']
        sc.frame_start, sc.frame_end, sc.display.render_aa = k['fs'], k['fe'], k['aa']
        if k['eevee'] is not None:
            sc.eevee.taa_render_samples = k['eevee']
        bpy.context.view_layer.material_override = k['override']
        for a, v in k['shading'].items():
            setattr(sh, a, v)
        sh.background_color = k['bg']
        for o in self.hidden:
            o.hide_render = False


# ---------------------------------------------------------------- views
def set_view(view='front3q', margin=1.12, target=None, zoom=1.0):
    """view: name from VIEWS or (azimuth, elevation, ortho). target: object name / list of names / (lo, hi) bbox
    to frame instead of the whole asset (close-ups). zoom > 1 frames tighter."""
    sc = _scene()
    st = _state()
    az, el, ortho = VIEWS[view] if isinstance(view, str) else view
    lo, hi = Vector(st.get('frame_lo', st['lo'])), Vector(st.get('frame_hi', st['hi']))
    if target is not None:
        if isinstance(target, (tuple, list)) and len(target) == 2 and not isinstance(target[0], str):
            lo, hi = Vector(target[0]), Vector(target[1])
        else:
            names = [target] if isinstance(target, str) else list(target)
            lo, hi = _bounds([bpy.data.objects[n] for n in names])
    centre = (lo + hi) / 2
    piv = bpy.data.objects['GM_Pivot']
    piv.location = centre
    piv.rotation_euler = (0, 0, 0)
    fwd = Vector(FRONT_VEC[st['front']])
    left = Vector((0, 0, 1)).cross(fwd)
    a, e = math.radians(az), math.radians(el)
    d = (fwd * math.cos(a) + left * math.sin(a)) * math.cos(e) + Vector((0, 0, math.sin(e)))
    d.normalize()
    upw = Vector((0, 0, 1)) if abs(d.z) < 0.99 else -fwd * (1 if d.z > 0 else -1)
    right = (-d).cross(upw).normalized()
    up = right.cross(-d).normalized()
    corners = [Vector((x, y, z)) - centre for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    cam = bpy.data.objects['GM_Cam']
    cd = cam.data
    m = margin / zoom
    xs = [abs(c.dot(right)) * m for c in corners]
    ys = [abs(c.dot(up)) * m for c in corners]
    zs = [c.dot(d) for c in corners]
    if ortho:
        cd.type = 'ORTHO'
        cd.ortho_scale = 2 * max(max(xs), max(ys) * rx / ry) if rx >= ry else 2 * max(max(ys), max(xs) * ry / rx)
        dist = max(zs) + max(cd.ortho_scale, 0.1) * 2
    else:
        cd.type = 'PERSP'
        th = (cd.sensor_width / 2) / cd.lens
        tv = th * ry / rx if rx >= ry else th
        th = th if rx >= ry else th * rx / ry
        dist = max(max(z + x / th for z, x in zip(zs, xs)), max(z + y / tv for z, y in zip(zs, ys)))
    cam.location = d * dist
    cam.rotation_euler = Matrix((right, up, d)).transposed().to_euler()      # camera looks down -Z
    rad = max((hi - lo).length / 2, 1e-3)
    cd.clip_start = max(1e-4, (dist - rad * 1.5) * 0.5) if not ortho else max(1e-4, dist * 0.01)
    cd.clip_end = dist + rad * 20
    # lights follow the camera azimuth so every view is lit the same way
    for name, (laz, lel, k) in (('GM_Key', (az + 45, max(el, 0) + 40, 7.0)), ('GM_Fill', (az - 70, 15, 2.2)),
                                ('GM_Rim', (az + 165, 35, 5.0))):
        la, le = math.radians(laz), math.radians(lel)
        ld = (fwd * math.cos(la) + left * math.sin(la)) * math.cos(le) + Vector((0, 0, math.sin(le)))
        lob = bpy.data.objects[name]
        lob.location = ld.normalized() * rad * 4
        lob.rotation_euler = (-ld).to_track_quat('-Z', 'Y').to_euler()
        lob.data.energy = k * (rad * 4) ** 2
    cam['view'] = view if isinstance(view, str) else 'az%d_el%d' % (az, el)
    _place_hud(cam, ortho, rx, ry)
    return dict(view=cam['view'], ortho=ortho, distance=round(dist, 4))


def _place_hud(cam, ortho, rx, ry):
    hud = bpy.data.objects.get('GM_HUD')
    if not hud:
        return
    cd = cam.data
    D = cd.clip_start * 1.5
    if ortho:
        hw = cd.ortho_scale / 2 if rx >= ry else cd.ortho_scale / 2 * rx / ry
        hv = hw * ry / rx
    else:
        th = (cd.sensor_width / 2) / cd.lens
        hw, hv = (th * D, th * D * ry / rx) if rx >= ry else (th * D * rx / ry, th * D)
    hud.location = (-0.96 * hw, -0.95 * hv, -D)
    hud.rotation_euler = (0, 0, 0)
    hud.data.size = hv * 0.055
    hud.data.align_x = 'LEFT'


# ---------------------------------------------------------------- render
def _engine(sc, kind):
    if kind == 'WORKBENCH':
        sc.render.engine = 'BLENDER_WORKBENCH'
    elif kind == 'CYCLES':
        sc.render.engine = 'CYCLES'
    else:
        ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
        sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in ids else 'BLENDER_EEVEE'


def _workbench(sc, light='STUDIO', cavity=True, shadow=True, outline=True, bg=BG_DARK):
    _engine(sc, 'WORKBENCH')
    sh = sc.display.shading
    sh.light = light
    sh.color_type = 'OBJECT'
    sh.show_cavity = cavity
    if cavity:
        sh.cavity_type = 'BOTH'
        sh.cavity_ridge_factor, sh.cavity_valley_factor = 1.0, 1.0
    sh.show_shadows = shadow
    sh.shadow_intensity = 0.35
    sh.show_object_outline = outline
    sh.object_outline_color = (0.02, 0.02, 0.025)
    sh.background_type = 'VIEWPORT'
    sh.background_color = bg[:3]
    sh.show_specular_highlight = True
    sc.display.render_aa = '16'


def _checker():
    img = bpy.data.images.get('GM_UVGrid') or bpy.data.images.new('GM_UVGrid', 1024, 1024)
    img.generated_type = 'COLOR_GRID'
    m = bpy.data.materials.get('GM_UVChecker') or bpy.data.materials.new('GM_UVChecker')
    m.use_nodes = True
    nt = m.node_tree
    if not any(n.type == 'TEX_IMAGE' for n in nt.nodes):
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        bs = nt.nodes.new('ShaderNodeBsdfPrincipled')
        tx = nt.nodes.new('ShaderNodeTexImage')
        tx.image = img
        tx.interpolation = 'Closest'
        bs.inputs['Roughness'].default_value = 0.7
        nt.links.new(tx.outputs['Color'], bs.inputs['Base Color'])
        nt.links.new(bs.outputs[0], out.inputs['Surface'])
    return m


def _face_orientation():
    m = bpy.data.materials.get('GM_FaceOrient') or bpy.data.materials.new('GM_FaceOrient')
    m.use_nodes = True
    m.use_backface_culling = False
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.inputs['A'].default_value = (0.1, 0.3, 0.95, 1)
    mix.inputs['B'].default_value = (0.95, 0.12, 0.1, 1)
    em = nt.nodes.new('ShaderNodeBsdfDiffuse')
    nt.links.new(geo.outputs['Backfacing'], mix.inputs['Factor'])
    nt.links.new(mix.outputs['Result'], em.inputs['Color'])
    nt.links.new(em.outputs[0], out.inputs['Surface'])
    return m


def _wire_copies(objs, thickness):
    dg = bpy.context.evaluated_depsgraph_get()
    stage = _coll(STAGE)
    made = []
    for o in objs:
        if o.type != 'MESH':
            continue
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), depsgraph=dg)
        w = bpy.data.objects.new('GM_Wire_' + o.name, me)
        w.matrix_world = o.matrix_world.copy()
        stage.objects.link(w)
        mod = w.modifiers.new('wire', 'WIREFRAME')
        mod.thickness = thickness
        mod.use_even_offset = True
        mod.use_relative_offset = False
        mod.offset = 0.0
        mod.use_replace = True
        w.color = (0.03, 0.03, 0.035, 1)
        made.append(w)
    return made


def _hue(i):
    import colorsys
    return colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.55, 0.92) + (1.0,)


def render(path, view='front3q', mode='clay', hud=True, label=None, samples=32, **view_kw):
    """Render one still of the subject. Returns dict(path, legend for mode='parts')."""
    sc = _scene()
    st = _state()
    objs = subject()
    keeper = _KeepRender(sc, objs + list(_coll(STAGE).objects))
    keeper.__enter__()                                       # review resolution first, then frame for its aspect
    vinfo = set_view(view, **view_kw)
    stage_floor = [bpy.data.objects.get(n) for n in ('GM_FloorA', 'GM_FloorB')]
    extras = [o for o in [bpy.data.objects.get('GM_ScaleRef')] if o]
    hud_ob = bpy.data.objects.get('GM_HUD')
    keep_col = {o.name: tuple(o.color) for o in objs}
    vl = bpy.context.view_layer
    temp, legend = [], None
    hide_floor = mode in ('silhouette', 'uv', 'normals') or (not isinstance(view, str) and view[1] < -2) or view == 'low3q'
    show_hud = hud and mode not in ('silhouette', 'uv', 'normals')
    for o in stage_floor:
        if o:
            o.hide_render = hide_floor
    for o in extras:
        o.hide_render = mode in ('silhouette', 'uv', 'normals')
    try:
        if mode in ('clay', 'wire', 'parts'):
            _workbench(sc)
            for i, o in enumerate(objs):
                o.color = _hue(i) if mode == 'parts' else CLAY
            if mode == 'wire':
                cd = bpy.data.objects['GM_Cam'].data
                span = cd.ortho_scale if cd.type == 'ORTHO' else vinfo['distance'] * cd.sensor_width / cd.lens
                temp += _wire_copies(objs, span * 0.0017)
            if mode == 'parts':
                legend, labels = {}, []
                cam = bpy.data.objects['GM_Cam']
                cd = cam.data
                span = cd.ortho_scale if cd.type == 'ORTHO' else vinfo['distance'] * cd.sensor_width / cd.lens
                camdir = cam.location.normalized()          # pivot is unrotated here; matrix_world may be stale
                campos = bpy.data.objects['GM_Pivot'].location + cam.location
                Dl = cd.clip_start * 2.0                    # label plane just in front of the camera
                cam_up = cam.rotation_euler.to_matrix() @ Vector((0, 1, 0))
                placed = []
                for i, o in enumerate(objs):
                    lo, hi = _bounds([o])
                    c = (lo + hi) / 2
                    depth = (c - campos).dot(-camdir)
                    if cd.type == 'ORTHO':
                        c = c + camdir * (depth - Dl)
                        size = span * 0.05
                    else:
                        c = campos + (c - campos) * (Dl / max(depth, 1e-6))
                        size = Dl * cd.sensor_width / cd.lens * 0.05
                    while any((c - p).length < size * 0.9 for p in placed):    # parts sharing a centre: stack labels
                        c = c - cam_up * size * 0.95
                    placed.append(c.copy())
                    td = bpy.data.curves.new('GM_Lbl_%d' % (i + 1), 'FONT')
                    td.body = str(i + 1)
                    td.size = size
                    td.align_x, td.align_y = 'CENTER', 'CENTER'
                    lb = bpy.data.objects.new('GM_Lbl_%d' % (i + 1), td)
                    _coll(STAGE).objects.link(lb)
                    lb.location = c
                    lb.rotation_euler = cam.rotation_euler.copy()
                    lb.color = (1.0, 0.92, 0.25, 1)
                    lb.visible_shadow = False
                    labels.append(lb)
                    legend[i + 1] = o.name
                temp += labels
        elif mode == 'silhouette':
            _workbench(sc, light='FLAT', cavity=False, shadow=False, outline=False, bg=(1, 1, 1))
            for o in objs:
                o.color = (0, 0, 0, 1)
        elif mode in ('material', 'uv', 'normals'):
            _engine(sc, 'EEVEE')
            if hasattr(sc.eevee, 'taa_render_samples'):
                sc.eevee.taa_render_samples = samples
            vl.material_override = _checker() if mode == 'uv' else _face_orientation() if mode == 'normals' else None
        else:
            raise ValueError('mode ' + mode)
        if hud_ob:
            hud_ob.hide_render = not show_hud
            hud_ob.data.body = label or '%s   %s   %s   (floor tile %s m)' % (st['asset'], vinfo['view'], mode, sc.get('gm_step'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sc.render.filepath = path
        if hasattr(sc.render.image_settings, 'media_type'):
            sc.render.image_settings.media_type = 'IMAGE'
        sc.render.image_settings.file_format = 'PNG'
        sc.render.image_settings.color_mode = 'RGBA'
        sc.render.image_settings.color_depth = '8'
        sc.render.image_settings.compression = 15             # scenes may be set to 0 = 8 MB uncompressed PNGs
        bpy.ops.render.render(write_still=True, scene=sc.name)
    finally:
        for o in objs:
            o.color = keep_col[o.name]
        keeper.__exit__(None, None, None)
        for o in stage_floor + extras:                       # leave the rig as the user expects it for F12
            if o:
                o.hide_render = False
        if hud_ob:
            hud_ob.hide_render = True                        # the label is only for review sheets
        for t in temp:
            data = t.data
            bpy.data.objects.remove(t)
            if data is not None and data.users == 0:
                (bpy.data.meshes if isinstance(data, bpy.types.Mesh) else bpy.data.curves).remove(data)
    return dict(path=path, legend=legend, **vinfo)


def sheet(path, views=('front', 'left', 'back', 'front3q'), mode='clay', cols=None, scale=0.5, label=None, **kw):
    """Render views and tile them left->right (one row unless cols). Returns dict(path, order, legend)."""
    sc = _scene()
    tmp = os.path.join(os.path.dirname(path), '_tmp')
    keep = sc.render.resolution_percentage
    sc.render.resolution_percentage = int(100 * scale)
    tiles, legend = [], None
    try:
        for v in views:
            vn = v if isinstance(v, str) else 'az%d_el%d' % (v[0], v[1])
            r = render(os.path.join(tmp, '%s_%s.png' % (mode, vn)), v, mode, label=label, **kw)
            legend = legend or r['legend']
            tiles.append(_io['read'](r['path']))
    finally:
        sc.render.resolution_percentage = keep
    _io['write'](path, _io['tile'](tiles, cols=cols or len(tiles)))
    return dict(path=path, order=[v if isinstance(v, str) else list(v) for v in views], mode=mode, legend=legend)


def turntable(path, frames=8, elevation=14, mode='material', cols=4, scale=0.5, samples=32):
    """frames stills around the asset tiled into a sheet, or an H.264 .mp4 when path ends with .mp4."""
    if not path.lower().endswith('.mp4'):
        views = [(i * 360.0 / frames, elevation, False) for i in range(frames)]
        return sheet(path, views=views, mode=mode, cols=cols, scale=scale)
    sc = _scene()
    keeper = _KeepRender(sc, subject() + list(_coll(STAGE).objects))
    keeper.__enter__()
    set_view((0, elevation, False))
    piv = bpy.data.objects['GM_Pivot']
    piv.animation_data_clear()
    piv.rotation_euler = (0, 0, 0)
    piv.keyframe_insert('rotation_euler', index=2, frame=1)
    piv.rotation_euler.z = 2 * math.pi * (frames - 1) / frames
    piv.keyframe_insert('rotation_euler', index=2, frame=frames)
    for fc in _fcurves(piv):
        for k in fc.keyframe_points:
            k.interpolation = 'LINEAR'
    try:
        sc.frame_start, sc.frame_end = 1, frames
        sc.render.resolution_percentage = int(100 * scale)
        if mode in ('clay', 'silhouette'):
            _workbench(sc)
            for o in subject():
                o['gm_keep_color'] = list(o.color)
                o.color = CLAY
        else:
            _engine(sc, 'EEVEE')
            if hasattr(sc.eevee, 'taa_render_samples'):
                sc.eevee.taa_render_samples = samples
        bpy.data.objects['GM_HUD'].hide_render = True
        sc.render.image_settings.media_type = 'VIDEO'
        sc.render.image_settings.file_format = 'FFMPEG'
        sc.render.ffmpeg.format = 'MPEG4'
        sc.render.ffmpeg.codec = 'H264'
        sc.render.ffmpeg.constant_rate_factor = 'HIGH'
        sc.render.filepath = path
        bpy.ops.render.render(animation=True, scene=sc.name)
    finally:
        for o in subject():
            if 'gm_keep_color' in o:
                o.color = o['gm_keep_color']
                del o['gm_keep_color']
        act = piv.animation_data.action if piv.animation_data else None
        piv.animation_data_clear()
        if act is not None and act.users == 0:
            bpy.data.actions.remove(act)                     # no orphan GM_PivotAction left for the animator
        piv.rotation_euler = (0, 0, 0)
        keeper.__exit__(None, None, None)
        set_view('front3q')
    return dict(path=path, frames=frames)


def _fcurves(ob):
    act = ob.animation_data.action if ob.animation_data else None
    if act is None:
        return []
    if hasattr(act, 'fcurves') and not hasattr(act, 'layers'):
        return list(act.fcurves)
    out = []
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                out += list(cb.fcurves)
    return out


# ---------------------------------------------------------------- revisions
def revision_dir(asset=None, out_root=None, new=True):
    st = _state()
    root = os.path.join(out_root or st['out_root'], 'renders')
    os.makedirs(root, exist_ok=True)
    nums = [int(d[1:]) for d in os.listdir(root) if d.startswith('r') and d[1:].isdigit()]
    n = (max(nums) + 1 if new else max(nums)) if nums else 1
    p = os.path.join(root, 'r%02d' % n)
    os.makedirs(p, exist_ok=True)
    return p


def review(asset=None, modes=('clay', 'wire', 'material'), views=('front', 'left', 'back', 'front3q'), note='',
           concept=None, closeups=None, uv=None, scale=0.5):
    """Standard revision pack in <out_root>/renders/r##/: one sheet per mode (+ uv/normals sheets if asked),
    concept comparisons, close-ups. concept: {view: image_path or (image_path, crop)}. closeups: {name: (view, target)}.
    Returns paths + concept scores; show the sheets to the user and record the revision in notes.md."""
    st = _state()
    asset = asset or st['asset']
    d = revision_dir(asset)
    rev = os.path.basename(d)
    out = dict(revision=rev, dir=d, sheets={}, concept={}, closeups={})
    for m in modes:
        r = sheet(os.path.join(d, '%s_%s.png' % (rev, m)), views=views, mode=m, scale=scale,
                  label=None)
        out['sheets'][m] = r['path']
        if r.get('legend'):
            out['legend'] = r['legend']
    if concept:
        cm = {}
        cm.update(_lib('concept_match'))
        for v, src in concept.items():
            img, crop = (src, None) if isinstance(src, str) else src
            sil = render(os.path.join(d, '_tmp', 'sil_%s.png' % v), v, 'silhouette')['path']
            out['concept'][v] = cm['compare'](sil, img, os.path.join(d, '%s_concept_%s.png' % (rev, v)), crop=crop)
    for name, (v, tgt) in (closeups or {}).items():
        out['closeups'][name] = render(os.path.join(d, '%s_close_%s.png' % (rev, name)), v, 'material' if 'material' in modes else 'clay',
                                       target=tgt, margin=1.3)['path']
    set_view(st.get('rest_view', 'front3q'))                 # leave the scene camera on the hero framing
    with open(os.path.join(d, 'review.json'), 'w', encoding='utf-8') as fh:
        json.dump(dict(out, note=note, concept={k: dict(iou=v['iou'], worst=v['worst']) for k, v in out['concept'].items()}),
                  fh, indent=1, default=str)
    return out


def auto_res(long_side=1920):
    """Frame aspect from the asset's front silhouette: tall -> 4:5 portrait, wide -> 16:9, else square."""
    st = _state()
    lo, hi = Vector(st['lo']), Vector(st['hi'])
    fwd = Vector(FRONT_VEC[st['front']])
    width = abs((hi - lo).dot(Vector((0, 0, 1)).cross(fwd)))
    a = width / max(hi.z - lo.z, 1e-6)
    if a < 0.8:
        return (int(long_side * 0.8) // 2 * 2, long_side)
    if a > 1.4:
        return (long_side, int(long_side * 9 / 16) // 2 * 2)
    return (int(long_side * 0.75), int(long_side * 0.75))


def present(asset=None, views=('hero', 'front', 'left', 'back3q'), res='auto', samples=64, concept=None,
            turntable_frames=96, turntable_samples=24, out_dir=None):
    """Team-ready presentation pack in <out_root>/renders/present/ (overwritten each run - the r## folders keep history):
    label-free full-res material stills, <Asset>_sheet.png (concept | hero + other views), <Asset>_turntable.mp4.
    concept: image path or (path, crop) shown on the sheet. turntable_frames=0 skips the video.
    A long turntable outlasts an MCP request: Blender keeps rendering - wait for the .mp4 to stop growing."""
    st = _state()
    asset = asset or st['asset']
    d = out_dir or os.path.join(st['out_root'], 'renders', 'present')
    os.makedirs(d, exist_ok=True)
    sc = _scene()
    saved = sc['gm']
    res = auto_res(1600) if res == 'auto' else res
    sc['gm'] = json.dumps(dict(st, res=list(res)))
    out = dict(dir=d, stills={})
    try:
        for v in views:
            vn = v if isinstance(v, str) else 'az%d_el%d' % (v[0], v[1])
            p = os.path.join(d, '%s_%s.png' % (asset, vn))
            render(p, v, 'material', hud=False, samples=samples)
            out['stills'][vn] = p
        imgs = [_io['read'](p) for p in out['stills'].values()]
        H = 1080                                              # sheet: [concept] | hero | column of the other views
        cells = []
        if concept:
            cm = {}
            cm.update(_lib('concept_match'))
            img, crop = (concept, None) if isinstance(concept, str) else concept
            cells.append(_io['fit_height'](cm['load'](img, crop), H))
        cells.append(_io['fit_height'](imgs[0], H))
        if len(imgs) > 1:
            n = len(imgs) - 1
            cells.append(_io['tile']([_io['fit_height'](i, (H - 6 * (n - 1)) // n) for i in imgs[1:]], cols=1, pad=3))
        out['sheet'] = _io['write'](os.path.join(d, '%s_sheet.png' % asset), _io['row'](cells, pad=10))
        out['res'] = list(res)
        if turntable_frames:
            out['turntable'] = turntable(os.path.join(d, '%s_turntable.mp4' % asset), frames=turntable_frames,
                                         elevation=10, mode='material', scale=1.0, samples=turntable_samples)['path']
    finally:
        sc['gm'] = saved
        set_view(st.get('rest_view', 'front3q'))
    return out


def compare_revisions(asset, a='r01', b=None, mode='clay', out=None):
    """before | after strip of the same sheet from two revisions (b defaults to the latest)."""
    root = os.path.join(_state()['out_root'], 'renders')
    if b is None:
        b = sorted(x for x in os.listdir(root) if x.startswith('r') and x[1:].isdigit())[-1]
    pa = os.path.join(root, a, '%s_%s.png' % (a, mode))
    pb = os.path.join(root, b, '%s_%s.png' % (b, mode))
    out = out or os.path.join(root, b, '%s_vs_%s_%s.png' % (a, b, mode))
    return _io['side_by_side']([pa, pb], out, height=600)


def cleanup():
    """Remove the Preview collection (camera, lights, floor, labels); asset objects stay. Rarely needed - the
    preview rig is meant to ship with the .blend."""
    _remove_legacy()
    sc = _scene()
    if sc.camera and sc.camera.name == 'GM_Cam':
        sc.camera = None
    stage = bpy.data.collections.get(STAGE)
    if stage:
        for o in list(stage.objects):
            data = o.data
            bpy.data.objects.remove(o)
            if data is not None and getattr(data, 'users', 1) == 0:
                for blk in (bpy.data.meshes, bpy.data.cameras, bpy.data.lights, bpy.data.curves):
                    if data.name in blk and blk[data.name] == data:
                        blk.remove(data)
                        break
        bpy.data.collections.remove(stage)
    if 'gm' in sc:
        del sc['gm']
    for blk, prefix in ((bpy.data.materials, 'GM_'), (bpy.data.worlds, 'GM_'), (bpy.data.images, 'GM_')):
        for d in [d for d in blk if d.name.startswith(prefix) and d.users == 0]:
            blk.remove(d)
    return True
