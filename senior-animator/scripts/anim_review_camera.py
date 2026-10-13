# Animation review camera rig + render helpers (reusable for any character).
# Run inside Blender: g = {'__file__': p := os.path.join(SKILL, 'scripts', 'anim_review_camera.py')}; exec(open(p).read(), g)
# then call g['setup'](...), g['contact_sheet'](...), g['playblast'](...) and finally g['teardown']().
#
# setup() hides other preview rigs in the scene (the Senior Modeler skill's "Preview" collection: its camera, lights,
# checker floor) so they never overlap the animation review, and remembers the scene's camera, render engine and
# their visibility. teardown() restores all of it and hides ANIM_Review - run it before saving the .blend.
#
# Builds (all in the "ANIM_Review" collection, never exported):
#   ANIM_CamPivot  empty that follows a bone of the rig horizontally (and optionally vertically)
#   ANIM_Cam       camera parented to the pivot, aimed with a Track-To at ANIM_CamAim
#   ANIM_Ground    1 m grid floor at z=0, plus ANIM_HeightRef ring at the gameplay height
#   ANIM_Key/Fill/Rim  sun lights (only matter for EEVEE/Cycles; Workbench uses studio light)
# Views are presets of camera offset relative to the pivot: front3q, front, side, back3q, top.
# look='beauty' (optional): full-colour EEVEE with the character's own materials - dark solid floor + soft area lights
# riding the camera pivot (same look at any height), the review grid/ring hidden. reel() then makes a beauty reel.
import bpy, math, os, json
import numpy as np
from mathutils import Vector

COLL = 'ANIM_Review'
OTHER_PREVIEWS = ('Preview',)     # collections from other skills' preview set-ups (Senior Modeler)
STATE_KEY = 'anim_review_restore'
BEAUTY_KEY = 'anim_review_beauty'
REVIEW_ONLY = ('ANIM_Floor', 'ANIM_HeightRef', 'ANIM_HeightPole', 'ANIM_Key', 'ANIM_Fill', 'ANIM_Rim')
BEAUTY = ('ANIM_BeautyFloor', 'ANIM_BeautyKey', 'ANIM_BeautyFill', 'ANIM_BeautyRim')
VIEWS = {   # direction from subject to camera (subject faces -Y), elevation in degrees
    'front3q': (Vector((0.65, -1.0, 0.0)), 12),
    'front': (Vector((0.0, -1.0, 0.0)), 5),
    'side': (Vector((1.0, 0.0, 0.0)), 5),
    'back3q': (Vector((-0.7, 1.0, 0.0)), 15),
    'top': (Vector((0.0, -0.15, 0.0)), 80),
}


def _coll():
    c = bpy.data.collections.get(COLL)
    if c is None:
        c = bpy.data.collections.new(COLL)
        bpy.context.scene.collection.children.link(c)
    return c


def _obj(name, data=None):
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, data)
        _coll().objects.link(ob)
    return ob


def _layer_coll(name, lc=None):
    lc = lc or bpy.context.view_layer.layer_collection
    if lc.name == name:
        return lc
    for ch in lc.children:
        r = _layer_coll(name, ch)
        if r is not None:
            return r
    return None


def _set_visible(name, visible):
    c = bpy.data.collections.get(name)
    if c is None:
        return
    c.hide_render = not visible
    lc = _layer_coll(name)
    if lc is not None:
        lc.hide_viewport = not visible


def hide_other_previews(names=OTHER_PREVIEWS):
    """Hide other skills' preview rigs (camera/lights/floor) and remember the scene state ONCE (repeated setup()
    calls keep the original snapshot). Returns the hidden collection names."""
    sc = bpy.context.scene
    if STATE_KEY not in sc:
        cam = sc.camera.name if sc.camera else None
        stale = bool(cam and cam.startswith('ANIM_'))
        if stale:                                           # snapshot taken while the review rig was already active:
            cam = next((o.name for n in names if bpy.data.collections.get(n)   # fall back to the model's own camera
                        for o in bpy.data.collections[n].objects if o.type == 'CAMERA'), None)
        state = dict(engine=sc.render.engine if sc.render.engine != 'BLENDER_WORKBENCH' else 'BLENDER_EEVEE',
                     camera=cam, collections={})
        for n in names:
            c = bpy.data.collections.get(n)
            if c is not None:
                lc = _layer_coll(n)
                state['collections'][n] = dict(render=True, viewport=True) if stale else \
                    dict(render=not c.hide_render, viewport=not (lc.hide_viewport if lc else False))
        sc[STATE_KEY] = json.dumps(state)
    hidden = []
    for n in names:
        if bpy.data.collections.get(n) is not None:
            _set_visible(n, False)
            hidden.append(n)
    _set_visible(COLL, True)
    return hidden


def teardown(remove=False):
    """Undo setup(): restore the scene camera, render engine and the other preview rigs' visibility; hide (or with
    remove=True delete) ANIM_Review. Run before saving the .blend or handing it back to the model process."""
    sc = bpy.context.scene
    _beauty(sc, None, False)
    state = json.loads(sc[STATE_KEY]) if STATE_KEY in sc else None
    if state:
        sc.render.engine = state['engine']
        cam = bpy.data.objects.get(state['camera']) if state['camera'] else None
        sc.camera = cam
        for n, vis in state['collections'].items():
            c = bpy.data.collections.get(n)
            if c is not None:
                c.hide_render = not vis['render']
                lc = _layer_coll(n)
                if lc is not None:
                    lc.hide_viewport = not vis['viewport']
        del sc[STATE_KEY]
    c = bpy.data.collections.get(COLL)
    if c is not None:
        if remove:
            for o in list(c.objects):
                bpy.data.objects.remove(o)
            bpy.data.collections.remove(c)
        else:
            _set_visible(COLL, False)
    return state


def setup(arm_name, follow_bone, aim_height=0.0, distance=9.0, lens=50, height_ref=None,
          follow_z=True, res=(960, 960), engine='BLENDER_WORKBENCH', hide_previews=OTHER_PREVIEWS, look='review'):
    """follow_bone: rig bone the camera tracks (use the COG for gameplay framing, Root for root-motion review).
    follow_z=False keeps the camera at aim_height (shows height changes like falls/jumps against the grid).
    hide_previews: other skills' preview collections to hide while reviewing (restored by teardown()).
    look: 'review' (Workbench clay, grid, height ring) | 'beauty' (full-colour EEVEE, see _beauty())."""
    sc = bpy.context.scene
    hide_other_previews(hide_previews or ())
    arm = bpy.data.objects[arm_name]
    piv = _obj('ANIM_CamPivot')
    piv.empty_display_type = 'PLAIN_AXES'
    for c in list(piv.constraints):
        piv.constraints.remove(c)
    cl = piv.constraints.new('COPY_LOCATION')
    cl.target, cl.subtarget = arm, follow_bone
    cl.use_z = follow_z
    piv.location = (0, 0, aim_height)
    cl.use_offset = False
    if not follow_z:
        piv.location.z = aim_height
    aim = _obj('ANIM_CamAim')
    aim.empty_display_type = 'SPHERE'
    aim.empty_display_size = 0.1
    aim.parent = piv
    aim.location = (0, 0, 0)
    cd = bpy.data.cameras.get('ANIM_Cam') or bpy.data.cameras.new('ANIM_Cam')
    cd.lens = lens
    cd.clip_end = 500
    cd.sensor_fit, cd.sensor_height = 'VERTICAL', 36.0     # same vertical framing at any aspect (16:9 beauty)
    cam = _obj('ANIM_Cam', cd)
    cam.parent = piv
    for c in list(cam.constraints):
        cam.constraints.remove(c)
    tt = cam.constraints.new('TRACK_TO')
    tt.target = aim
    tt.track_axis, tt.up_axis = 'TRACK_NEGATIVE_Z', 'UP_Y'
    cam['distance'] = distance
    sc.camera = cam
    # floor grid
    gname = 'ANIM_Ground'
    me = bpy.data.meshes.get(gname) or bpy.data.meshes.new(gname)
    me.clear_geometry()
    n, s = 20, 1.0
    verts, edges = [], []
    for i in range(-n, n + 1):
        a = len(verts)
        verts += [(i * s, -n * s, 0), (i * s, n * s, 0), (-n * s, i * s, 0), (n * s, i * s, 0)]
        edges += [(a, a + 1), (a + 2, a + 3)]
    me.from_pydata(verts, edges, [])
    g = _obj(gname, me)
    g.data = me
    # Workbench doesn't render loose edges, so the visible floor is a checkerboard of 1 m quads
    pl = bpy.data.meshes.get('ANIM_Floor') or bpy.data.meshes.new('ANIM_Floor')
    pl.clear_geometry()
    quads, pv = [], []
    for ix in range(-n, n):
        for iy in range(-n, n):
            if (ix + iy) % 2 == 0:
                b = len(pv)
                pv += [(ix, iy, -0.002), (ix + 1, iy, -0.002), (ix + 1, iy + 1, -0.002), (ix, iy + 1, -0.002)]
                quads.append((b, b + 1, b + 2, b + 3))
    pl.from_pydata(pv, [], quads)
    fl = _obj('ANIM_Floor', pl)
    fl.data = pl
    fl.color = (0.32, 0.34, 0.38, 1)
    g.hide_render = True
    if height_ref is not None:
        rname = 'ANIM_HeightRef'
        rm = bpy.data.meshes.get(rname) or bpy.data.meshes.new(rname)
        rm.clear_geometry()
        k = 64
        rv = []
        for i in range(k):
            a = 2 * math.pi * i / k
            for r in (2.4, 2.5):
                rv.append((r * math.cos(a), r * math.sin(a), height_ref))
        rf = [(2 * i, 2 * ((i + 1) % k), 2 * ((i + 1) % k) + 1, 2 * i + 1) for i in range(k)]
        rm.from_pydata(rv, [], rf)
        ro = _obj(rname, rm)
        ro.data = rm
        ro.color = (1.0, 0.75, 0.1, 1)
        # vertical pole from ground to the reference height
        pm = bpy.data.meshes.get('ANIM_HeightPole') or bpy.data.meshes.new('ANIM_HeightPole')
        pm.clear_geometry()
        w = 0.03
        x0 = 2.45
        pm.from_pydata([(x0 - w, -w, 0), (x0 + w, -w, 0), (x0 + w, w, 0), (x0 - w, w, 0),
                        (x0 - w, -w, height_ref), (x0 + w, -w, height_ref), (x0 + w, w, height_ref), (x0 - w, w, height_ref)], [],
                       [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
        po = _obj('ANIM_HeightPole', pm)
        po.data = pm
        po.color = (1.0, 0.75, 0.1, 1)
    # lights for EEVEE/Cycles
    for name, rot, e in (('ANIM_Key', (50, 0, -35), 3.5), ('ANIM_Fill', (65, 0, 140), 1.2), ('ANIM_Rim', (30, 0, 170), 2.5)):
        ld = bpy.data.lights.get(name) or bpy.data.lights.new(name, 'SUN')
        ld.energy = e
        lo = _obj(name, ld)
        lo.rotation_euler = [math.radians(a) for a in rot]
    # render settings
    sc.render.engine = engine
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    if engine == 'BLENDER_WORKBENCH':
        sh = sc.display.shading
        sh.light = 'STUDIO'
        sh.show_shadows = True
        sh.show_cavity = True
        sh.cavity_type = 'BOTH'
        sh.show_object_outline = True
        sh.background_type = 'VIEWPORT'
        sc.display.shading.background_color = (0.08, 0.09, 0.11)
        sh.color_type = 'MATERIAL'
    for name, col in (('ANIM_Floor', (0.30, 0.32, 0.36, 1)), ('ANIM_HeightRef', (1.0, 0.7, 0.05, 1)),
                      ('ANIM_HeightPole', (1.0, 0.7, 0.05, 1))):
        ob = bpy.data.objects.get(name)
        if ob:
            mat = bpy.data.materials.get(name + '_mat') or bpy.data.materials.new(name + '_mat')
            mat.diffuse_color = col
            ob.data.materials.clear()
            ob.data.materials.append(mat)
    _beauty(sc, piv, look == 'beauty', distance)
    set_view('front3q')
    return cam


def _beauty(sc, piv, on, distance=2.0):
    """look='beauty': EEVEE with the meshes' own materials, a dark solid floor and soft area lights parented to the camera
    pivot (lights scale with the camera distance, so any character size works). off: remove them and restore the
    world / colour management / samples snapshot."""
    for n in REVIEW_ONLY:
        ob = bpy.data.objects.get(n)
        if ob is not None:
            ob.hide_render = on
    if not on:
        for n in BEAUTY:
            ob = bpy.data.objects.get(n)
            if ob is not None:
                data, kind = ob.data, ob.type
                bpy.data.objects.remove(ob)
                if data is not None and data.users == 0:
                    (bpy.data.lights if kind == 'LIGHT' else bpy.data.meshes).remove(data)
        if BEAUTY_KEY in sc:
            k = json.loads(sc[BEAUTY_KEY])
            sc.view_settings.view_transform, sc.view_settings.look = k['vt'], k['look']
            sc.world = bpy.data.worlds.get(k['world']) if k['world'] else None
            if k['samples'] is not None:
                sc.eevee.taa_render_samples = k['samples']
            del sc[BEAUTY_KEY]
        return
    if BEAUTY_KEY not in sc:
        sc[BEAUTY_KEY] = json.dumps(dict(vt=sc.view_settings.view_transform, look=sc.view_settings.look,
                                         world=sc.world.name if sc.world else None,
                                         samples=getattr(sc.eevee, 'taa_render_samples', None)))
    ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in ids else 'BLENDER_EEVEE'
    sc.eevee.taa_render_samples = 64
    sc.view_settings.view_transform, sc.view_settings.look = 'Standard', 'None'
    w = bpy.data.worlds.get('ANIM_BeautyWorld') or bpy.data.worlds.new('ANIM_BeautyWorld')
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.055, 0.06, 0.07, 1)
    sc.world = w
    d = distance
    me = bpy.data.meshes.get('ANIM_BeautyFloor') or bpy.data.meshes.new('ANIM_BeautyFloor')
    me.clear_geometry()
    s = 20 * d
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    mat = bpy.data.materials.get('ANIM_BeautyFloor_mat') or bpy.data.materials.new('ANIM_BeautyFloor_mat')
    mat.use_nodes = True
    bs = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bs.inputs['Base Color'].default_value = (0.07, 0.075, 0.085, 1)
    bs.inputs['Roughness'].default_value = 0.55
    me.materials.clear()
    me.materials.append(mat)
    _obj('ANIM_BeautyFloor', me)
    for name, off, k, size, col in (('Key', (0.72, -0.78, 0.83), 37, 0.66, (1.0, 0.95, 0.88)),   # power = k * d^2
                                    ('Fill', (-0.9, -0.55, 0.22), 12, 1.0, (0.8, 0.88, 1.0)),
                                    ('Rim', (-0.33, 1.0, 0.72), 55, 0.45, (0.85, 0.95, 1.0))):
        ld = bpy.data.lights.get('ANIM_Beauty' + name) or bpy.data.lights.new('ANIM_Beauty' + name, 'AREA')
        ld.energy, ld.size, ld.color = k * d * d, size * d, col
        lo = _obj('ANIM_Beauty' + name, ld)
        lo.parent = piv
        lo.location = Vector(off) * d
        for c in list(lo.constraints):
            lo.constraints.remove(c)
        t = lo.constraints.new('TRACK_TO')
        t.target, t.track_axis, t.up_axis = piv, 'TRACK_NEGATIVE_Z', 'UP_Y'


def set_view(view='front3q', distance=None):
    cam = bpy.data.objects['ANIM_Cam']
    d = distance or cam.get('distance', 9.0)
    direction, elev = VIEWS[view]
    h = direction.normalized()
    e = math.radians(elev)
    off = Vector((h.x * math.cos(e), h.y * math.cos(e), math.sin(e))) * d
    cam.location = off
    cam['view'] = view


def _render_to(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    sc.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True)


def contact_sheet(out_path, frames, views=('front3q',), cols=None, scale=0.5, tmp_dir=None):
    """Render each frame x view and tile them into one PNG (rows = views, cols = frames by default)."""
    sc = bpy.context.scene
    tmp_dir = tmp_dir or os.path.join(os.path.dirname(out_path), '_cs_tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    keep = sc.render.resolution_percentage
    sc.render.resolution_percentage = int(100 * scale)
    tiles = []
    for v in views:
        set_view(v)
        for f in frames:
            sc.frame_set(f)
            p = os.path.join(tmp_dir, '%s_%04d.png' % (v, f))
            _render_to(p)
            tiles.append(p)
    sc.render.resolution_percentage = keep
    imgs = []
    for p in tiles:
        im = bpy.data.images.load(p, check_existing=False)
        w, h = im.size
        a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
        imgs.append(a)
        bpy.data.images.remove(im)
    cols = cols or len(frames)
    rows = math.ceil(len(imgs) / cols)
    h, w = imgs[0].shape[:2]
    sheet = np.zeros((rows * h, cols * w, 4), dtype=np.float32)
    sheet[..., 3] = 1
    for i, a in enumerate(imgs):
        r, c = divmod(i, cols)
        sheet[(rows - 1 - r) * h:(rows - r) * h, c * w:(c + 1) * w] = a   # Blender images are bottom-up
    out = bpy.data.images.new('ANIM_contact', cols * w, rows * h, alpha=True)
    out.pixels = sheet.ravel()
    out.filepath_raw = out_path
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    return out_path


def playblast(out_path, view='front3q', fmt='FFMPEG', scale=0.5):
    """Render the scene frame range to an mp4 (H.264) for review."""
    sc = bpy.context.scene
    set_view(view)
    keep = (sc.render.resolution_percentage, sc.render.filepath, sc.render.image_settings.media_type
            if hasattr(sc.render.image_settings, 'media_type') else None)
    sc.render.resolution_percentage = int(100 * scale)
    if hasattr(sc.render.image_settings, 'media_type'):
        sc.render.image_settings.media_type = 'VIDEO'
    sc.render.image_settings.file_format = 'FFMPEG'
    sc.render.ffmpeg.format = 'MPEG4'
    sc.render.ffmpeg.codec = 'H264'
    sc.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    sc.render.filepath = out_path
    bpy.ops.render.render(animation=True)
    sc.render.resolution_percentage = keep[0]
    sc.render.filepath = keep[1]
    if keep[2] is not None:
        sc.render.image_settings.media_type = keep[2]
    sc.render.image_settings.file_format = 'PNG'
    return out_path


def reel(out_path, actions=None, action_tag=None, view='front3q', scale=0.75, loop_repeats=2, hold=10, label=True,
         font_size=None, keep_frames=False):
    """ONE video of all clips back to back (call setup() first; teardown() afterwards).
    actions: names in order, or None = every action tagged `action_tag` (the clips.py tag), else every action that
    animates the armature. Each clip is rendered once as PNG frames, loops are repeated `loop_repeats` times, the
    last frame is held `hold` frames, and the clip name (+ frame count, LOOP / root-motion hints) is burnt in with a
    sequencer text strip. Assembled in a temporary scene and encoded to H.264. Returns dict(path, clips, frames)."""
    import shutil
    sc = bpy.context.scene
    piv = bpy.data.objects['ANIM_CamPivot']
    arm = piv.constraints[0].target if piv.constraints else None
    if arm is None:
        raise RuntimeError('run setup() first')
    ad = arm.animation_data or arm.animation_data_create()
    if actions is None:
        acts = [a for a in bpy.data.actions if (a.get(action_tag) if action_tag else
                any(fc.data_path.startswith('pose.bones') for fc in _action_fcurves(a)))]
        acts.sort(key=lambda a: a.name)
    else:
        acts = [bpy.data.actions[n] for n in actions]
    tmp = os.path.join(os.path.dirname(out_path), '_reel_tmp')
    keep = (ad.action, ad.action_slot, sc.frame_start, sc.frame_end, sc.frame_current, sc.render.filepath,
            sc.render.resolution_percentage, sc.render.image_settings.file_format,
            getattr(sc.render.image_settings, 'media_type', None))
    set_view(view)
    rendered = []
    try:
        sc.render.resolution_percentage = int(100 * scale)
        if hasattr(sc.render.image_settings, 'media_type'):
            sc.render.image_settings.media_type = 'IMAGE'
        sc.render.image_settings.file_format = 'PNG'
        for act in acts:
            ad.action = act
            if act.slots:
                ad.action_slot = act.slots[0]
            s, e = int(act.frame_range[0]), int(act.frame_range[1])
            loop = bool(act.get('loop')) or act.use_cyclic
            if loop:
                e -= 1                                  # frame N == frame 0 on loops: drop it so repeats are seamless
            d = os.path.join(tmp, act.name)
            os.makedirs(d, exist_ok=True)
            sc.frame_start, sc.frame_end = s, e
            sc.render.filepath = os.path.join(d, 'f_')
            bpy.ops.render.render(animation=True)
            files = sorted(f for f in os.listdir(d) if f.startswith('f_') and f.endswith('.png'))
            rendered.append((act, d, files, loop))
        # assemble in a temporary sequencer scene
        rs = bpy.data.scenes.new('ANIM_Reel')
        rs.render.fps = sc.render.fps
        rs.render.resolution_x = int(sc.render.resolution_x * scale)
        rs.render.resolution_y = int(sc.render.resolution_y * scale)
        rs.render.resolution_percentage = 100
        se = rs.sequence_editor_create()
        strips = se.strips if hasattr(se, 'strips') else se.sequences
        f = 1
        fs = font_size or max(18, rs.render.resolution_y // 22)
        for act, d, files, loop in rendered:
            start = f
            for rep in range(loop_repeats if loop else 1):
                st = strips.new_image(act.name, os.path.join(d, files[0]), 1, f)
                for fn in files[1:]:
                    st.elements.append(fn)
                f += len(files)
            if hold:
                st = strips.new_image(act.name + '_hold', os.path.join(d, files[-1]), 1, f)
                st.frame_final_duration = hold
                f += hold
            if label:
                hints = ['LOOP x%d' % loop_repeats] if loop else []
                root = arm.data.bones[0].name
                moving = lambda fc: len({round(k.co.y, 4) for k in fc.keyframe_points}) > 1   # keyed AND changing
                if any((fc.data_path == 'pose.bones["CTRL_Root"].location' or
                        fc.data_path == 'pose.bones["%s"].location' % root) and moving(fc) for fc in _action_fcurves(act)):
                    hints.append('root motion')
                markers = ', '.join('%s %d' % (m.name, m.frame) for m in act.pose_markers)
                txt = '%s   (%d f%s)%s' % (act.name, int(act.frame_range[1] - act.frame_range[0]),
                                           ', ' + ', '.join(hints) if hints else '', ('   ' + markers) if markers else '')
                t = strips.new_effect(act.name + '_label', 'TEXT', 2, frame_start=start, length=f - start)
                t.text = txt
                t.font_size = fs
                t.location = (0.03, 0.04)
                t.anchor_x, t.anchor_y = 'LEFT', 'BOTTOM'
                t.color = (1, 1, 1, 1)
                t.use_shadow = True
        rs.frame_start, rs.frame_end = 1, f - 1
        if hasattr(rs.render.image_settings, 'media_type'):
            rs.render.image_settings.media_type = 'VIDEO'
        rs.render.image_settings.file_format = 'FFMPEG'
        rs.render.ffmpeg.format = 'MPEG4'
        rs.render.ffmpeg.codec = 'H264'
        rs.render.ffmpeg.constant_rate_factor = 'MEDIUM'
        rs.render.filepath = out_path
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        bpy.ops.render.render(animation=True, scene=rs.name)
        bpy.data.scenes.remove(rs)
    finally:
        ad.action = keep[0]
        if keep[0] is not None and keep[1] is not None:
            ad.action_slot = keep[1]
        sc.frame_start, sc.frame_end = keep[2], keep[3]
        sc.frame_set(keep[4])
        sc.render.filepath, sc.render.resolution_percentage = keep[5], keep[6]
        if keep[8] is not None:
            sc.render.image_settings.media_type = keep[8]
        sc.render.image_settings.file_format = keep[7]
        if not keep_frames and os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        rs_left = bpy.data.scenes.get('ANIM_Reel')
        if rs_left:
            bpy.data.scenes.remove(rs_left)
    return dict(path=out_path, clips=[a.name for a, *_ in rendered], frames=f - 1)


def _action_fcurves(act):
    if hasattr(act, 'layers') and act.layers:
        out = []
        for layer in act.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    out += list(cb.fcurves)
        return out
    return list(getattr(act, 'fcurves', []))
