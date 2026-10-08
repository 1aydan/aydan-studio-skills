# 2D concept -> 3D measurement and fidelity scoring (library). Works on any concept image: turnaround sheets
# (crop one view at a time), single orthographic views, or illustrations (measure loosely, compare by eye).
#   cm = lib('concept_match')
#   cm['measure'](IMG)                       subject bbox, aspect, per-row left/right extents (in subject-height units)
#   cm['profile'](IMG, n=40)                 [(z, half_width)] for lathe() / symmetric parts
#   cm['band'](IMG, z0, z1)                  extents of the silhouette inside a height band (e.g. the hat)
#   cm['runs'](IMG, z)                       separate segments at one height (two legs, arm vs torso)
#   cm['color_regions'](IMG, k=10)           palette clusters with hex/linear colour, share and bbox (height units)
#   cm['find_color'](IMG, '#D4A03A', blobs=True)   where a colour sits: bbox + blobs (buttons, eyes, stripes)
#   cm['place_reference'](IMG, 'front', height_m=1.8)   image empty behind the model in the viewport
#   cm['compare'](silhouette_png, IMG, out_png)          IoU + per-band width error + concept|model|overlay sheet
#
# Units: every measurement is in SUBJECT HEIGHTS (1.0 = top of subject - bottom of subject). x is relative to the
# subject's centre column (+x = image right), z is up from the subject's lowest pixel. Multiply by the brief's real
# height in metres. In a front view of a character facing -Y the image right is the character's LEFT (+X in Blender).
# crop = (x0, y0, x1, y1) in pixels, or fractions of the image when all values <= 1 (turnaround sheets).
import os
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
_CACHE = {}


def load(path, crop=None):
    key = (path, os.path.getmtime(path), tuple(crop) if crop else None)
    if key not in _CACHE:
        a = _io['read'](path)
        if crop:
            h, w = a.shape[:2]
            x0, y0, x1, y1 = crop
            if max(crop) <= 1.0:
                x0, x1, y0, y1 = x0 * w, x1 * w, y0 * h, y1 * h
            a = a[int(y0):int(y1), int(x0):int(x1)].copy()
        _CACHE.clear()
        _CACHE[key] = a
    return _CACHE[key]


def _shift(m, dy, dx):
    out = np.zeros_like(m)
    h, w = m.shape
    out[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = m[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
    return out


def _open(m, it=1):
    for _ in range(it):
        e = m.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            e &= _shift(m, dy, dx)
        m = e
    for _ in range(it):
        d = m.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            d |= _shift(m, dy, dx)
        m = d
    return m


def background(a):
    b = np.concatenate([a[:3].reshape(-1, 4), a[-3:].reshape(-1, 4), a[:, :3].reshape(-1, 4), a[:, -3:].reshape(-1, 4)])
    return np.median(b[:, :3], axis=0)


def subject_mask(a, threshold=0.1, bg=None):
    """Foreground mask: alpha if the image has transparency, else colour distance from the border colour."""
    if a[..., 3].min() < 0.5:
        m = a[..., 3] > 0.5
    else:
        bg = background(a) if bg is None else np.asarray(bg[:3])
        m = np.abs(a[..., :3] - bg).max(axis=2) > threshold
    return _open(m, 1)


def _bbox(m, min_frac=0.002):
    rows = np.where(m.sum(1) >= max(2, min_frac * m.shape[1]))[0]
    cols = np.where(m.sum(0) >= max(2, min_frac * m.shape[0]))[0]
    if not len(rows) or not len(cols):
        raise ValueError('no subject found - pass threshold= or crop=')
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def _frame(path, crop=None, threshold=0.1):
    a = load(path, crop)
    m = subject_mask(a, threshold)
    x0, y0, x1, y1 = _bbox(m)
    H = float(y1 - y0)
    return a, m, (x0, y0, x1, y1), H, (x0 + x1) / 2.0


def measure(path, crop=None, threshold=0.1, rows=40):
    """Subject bbox and per-row silhouette extents. rows: number of sampled rows (z from 0 = bottom to 1 = top)."""
    a, m, (x0, y0, x1, y1), H, cx = _frame(path, crop, threshold)
    prof = []
    for i in range(rows + 1):
        z = i / rows
        y = min(y1 - 1, max(y0, int(round(y1 - 1 - z * (H - 1)))))
        xs = np.where(m[y])[0]
        if len(xs):
            prof.append((round(z, 3), round((xs[0] - cx) / H, 4), round((xs[-1] + 1 - cx) / H, 4)))
        else:
            prof.append((round(z, 3), None, None))
    return dict(image=a.shape[1::-1], bbox_px=(x0, y0, x1, y1), height_px=int(H), width_px=int(x1 - x0),
                aspect=round((x1 - x0) / H, 4), center_x_px=cx, rows=prof,
                note='units = subject heights; x relative to subject centre (+ = image right); z up from the bottom')


def profile(path, n=40, crop=None, threshold=0.1, z_range=(0.0, 1.0), mode='avg'):
    """[(z, half_width)] in subject heights for a symmetric/turned part (lathe). mode avg|max|left|right."""
    r = measure(path, crop, threshold, rows=n)['rows']
    out = []
    for z, l, rr in r:
        if l is None or not (z_range[0] <= z <= z_range[1]):
            continue
        hw = {'avg': (rr - l) / 2, 'max': max(-l, rr), 'left': -l, 'right': rr}[mode]
        out.append((z, round(hw, 4)))
    return out


def runs(path, z, crop=None, threshold=0.1, min_gap=0.004):
    """Separate silhouette segments at height z: [(left, right, width, centre)] in subject heights. Two legs, an arm
    and the torso, a handle and its body... gaps narrower than min_gap (subject heights) are bridged."""
    a, m, (x0, y0, x1, y1), H, cx = _frame(path, crop, threshold)
    y = min(y1 - 1, max(y0, int(round(y1 - 1 - z * (H - 1)))))
    row = m[y]
    xs = np.where(row)[0]
    if not len(xs):
        return []
    out, start, prev = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - prev > max(1, min_gap * H):
            out.append((start, prev + 1))
            start = x
        prev = x
    out.append((start, prev + 1))
    return [(round((l - cx) / H, 4), round((r - cx) / H, 4), round((r - l) / H, 4), round(((l + r) / 2 - cx) / H, 4))
            for l, r in out]


def band(path, z0, z1, crop=None, threshold=0.1):
    """Silhouette extents between heights z0..z1 (subject heights): left, right, width, centre, filled share."""
    a, m, (x0, y0, x1, y1), H, cx = _frame(path, crop, threshold)
    ya, yb = int(round(y1 - z1 * H)), int(round(y1 - z0 * H))
    sub = m[max(0, ya):max(ya + 1, yb)]
    cols = np.where(sub.any(0))[0]
    if not len(cols):
        return None
    l, r = (cols[0] - cx) / H, (cols[-1] + 1 - cx) / H
    return dict(left=round(l, 4), right=round(r, 4), width=round(r - l, 4), centre=round((l + r) / 2, 4),
                fill=round(float(sub.mean()) * (x1 - x0) / max(1, cols[-1] + 1 - cols[0]), 3))


def _kmeans(X, k, iters=25):
    lum = X @ np.array([0.2126, 0.7152, 0.0722])
    order = np.argsort(lum)
    C = X[order[np.linspace(0, len(X) - 1, k).astype(int)]].copy()
    for _ in range(iters):
        d = ((X[:, None, :] - C[None]) ** 2).sum(2)
        lab = d.argmin(1)
        newC = np.array([X[lab == i].mean(0) if np.any(lab == i) else C[i] for i in range(k)])
        if np.allclose(newC, C, atol=1e-4):
            break
        C = newC
    return C, lab


def color_regions(path, k=10, crop=None, threshold=0.1, samples=40000, merge=0.06):
    """Dominant subject colours (k-means in sRGB) with share of the silhouette and bbox in subject heights.
    Use them as the material palette and to locate parts (jacket, boots, trims). Similar clusters are merged."""
    a, m, (x0, y0, x1, y1), H, cx = _frame(path, crop, threshold)
    ys, xs = np.where(m)
    rng = np.random.default_rng(0)
    pick = rng.choice(len(ys), min(samples, len(ys)), replace=False)
    X = a[ys[pick], xs[pick], :3].astype(np.float64)
    C, lab = _kmeans(X, k)
    # merge near-duplicates
    groups = []
    for i in range(k):
        for g in groups:
            if np.abs(C[g[0]] - C[i]).max() < merge:
                g.append(i)
                break
        else:
            groups.append([i])
    out = []
    for g in groups:
        sel = np.isin(lab, g)
        if sel.sum() < 0.004 * len(lab):
            continue
        col = X[sel].mean(0)
        py, px = ys[pick][sel], xs[pick][sel]
        lo_x, hi_x = np.percentile(px, [2, 98])
        lo_y, hi_y = np.percentile(py, [2, 98])
        out.append(dict(hex=_io['rgb_to_hex'](col), srgb=[round(float(c), 4) for c in col],
                        linear=[round(float(c), 4) for c in _io['srgb_to_linear'](col)],
                        share=round(float(sel.mean()), 3),
                        x=(round((lo_x - cx) / H, 3), round((hi_x + 1 - cx) / H, 3)),
                        z=(round((y1 - hi_y - 1) / H, 3), round((y1 - lo_y) / H, 3))))
    return sorted(out, key=lambda d: -d['share'])


def palette(path, k=10, crop=None):
    return [(d['hex'], d['share']) for d in color_regions(path, k, crop)]


def _labels(m):
    """Connected components (4-neighbour) by min-label propagation with pointer jumping."""
    h, w = m.shape
    idx = np.arange(h * w).reshape(h, w)
    lab = np.where(m, idx, -1).ravel()
    big = h * w + 1
    for _ in range(4000):
        L = np.where(m, lab.reshape(h, w), big)
        nb = L.copy()
        nb[1:] = np.minimum(nb[1:], L[:-1]); nb[:-1] = np.minimum(nb[:-1], L[1:])
        nb[:, 1:] = np.minimum(nb[:, 1:], L[:, :-1]); nb[:, :-1] = np.minimum(nb[:, :-1], L[:, 1:])
        nb = np.where(m, nb, -1).ravel()
        flat = np.where(nb >= 0, nb, 0)
        for _j in range(6):
            flat = np.where(nb >= 0, np.minimum(flat, lab[flat]), 0)
        new = np.where(m.ravel(), np.minimum(flat, lab), -1)
        if np.array_equal(new, lab):
            break
        lab = new
    return lab.reshape(h, w)


def find_color(path, hex_color, tol=0.12, crop=None, threshold=0.1, blobs=False, min_px=None, max_side=420):
    """Pixels within tol (max channel diff, sRGB) of hex_color inside the subject: bbox, share, and optionally blobs
    (connected spots - buttons, eyes, studs) as centroid + size in subject heights, sorted top to bottom."""
    a, m, (x0, y0, x1, y1), H, cx = _frame(path, crop, threshold)
    c = np.array(_io['hex_to_rgb'](hex_color))
    hit = m & (np.abs(a[..., :3] - c).max(2) < tol)
    ys, xs = np.where(hit)
    if not len(ys):
        return dict(count=0)
    to_x = lambda px: round((px - cx) / H, 4)
    to_z = lambda py: round((y1 - py) / H, 4)
    lx, hx = np.percentile(xs, [1, 99])                     # robust: ignore stray anti-aliased pixels
    ly, hy = np.percentile(ys, [1, 99])
    rep = dict(count=int(len(ys)), share=round(len(ys) / max(1, m.sum()), 4),
               x=(to_x(lx), to_x(hx + 1)), z=(to_z(hy + 1), to_z(ly)),
               x_full=(to_x(xs.min()), to_x(xs.max() + 1)), z_full=(to_z(ys.max() + 1), to_z(ys.min())))
    if blobs:
        min_px = min_px or max(12, int(0.0003 * H * H))        # ignore paint speckle: ~0.03% of the subject square
        s = max(1, int(np.ceil(max(hit.shape) / max_side)))
        small = hit[::s, ::s]
        lab = _labels(small)
        out = []
        for l in np.unique(lab[lab >= 0]):
            yy, xx = np.where(lab == l)
            if len(yy) * s * s < min_px:
                continue
            out.append(dict(x=to_x((xx.mean() + 0.5) * s), z=to_z((yy.mean() + 0.5) * s),
                            w=round((np.ptp(xx) + 1) * s / H, 4), h=round((np.ptp(yy) + 1) * s / H, 4), px=int(len(yy) * s * s)))
        rep['blobs'] = sorted(out, key=lambda b: (-b['z'], b['x']))
    return rep


# ---------------------------------------------------------------- viewport reference
VIEW_ROT = {'front': (90, 0, 0), 'back': (90, 0, 180), 'left': (90, 0, 90), 'right': (90, 0, -90), 'top': (0, 0, 0)}


def place_reference(path, view='front', height_m=1.0, ground=0.0, crop=None, threshold=0.1, opacity=0.4,
                    name=None, flip=False):
    """Image empty (viewport only, drawn behind geometry, only in its axis-aligned view) scaled so the subject's
    pixel height == height_m, its bottom on `ground`, its centre column on the asset axis. Lives in GM_Reference."""
    import bpy, math
    from mathutils import Vector
    a, m, (x0, y0, x1, y1), H, cx = _frame(path, None, threshold) if not crop else (None, None, None, None, None)
    full = load(path)
    Hi, Wi = full.shape[:2]
    if crop:   # measure inside the crop, convert back to full-image pixels
        cx0, cy0, cx1, cy1 = crop
        if max(crop) <= 1.0:
            cx0, cx1, cy0, cy1 = cx0 * Wi, cx1 * Wi, cy0 * Hi, cy1 * Hi
        a, m, (x0, y0, x1, y1), H, cx = _frame(path, crop, threshold)
        x0, x1, cx, y0, y1 = x0 + cx0, x1 + cx0, cx + cx0, y0 + cy0, y1 + cy0
    s = height_m / H                                         # metres per pixel
    img = bpy.data.images.load(path, check_existing=True)
    name = name or 'REF_%s' % view
    ob = bpy.data.objects.get(name) or bpy.data.objects.new(name, None)
    coll = bpy.data.collections.get('GM_Reference')
    if coll is None:
        coll = bpy.data.collections.new('GM_Reference')
        bpy.context.scene.collection.children.link(coll)
    if ob.name not in coll.objects:
        coll.objects.link(ob)
    ob.empty_display_type = 'IMAGE'
    ob.data = img
    ob.empty_display_size = max(Wi, Hi) * s                 # Blender draws the larger image side at this size
    ob.empty_image_offset = (-0.5, -0.5)
    ob.empty_image_depth = 'BACK'
    ob.show_empty_image_only_axis_aligned = True
    ob.use_empty_image_alpha = True
    ob.color[3] = opacity
    ob.hide_render = True
    ob.hide_select = True
    ob.rotation_euler = [math.radians(v) for v in VIEW_ROT[view]]
    ob.scale = (-1 if flip else 1, 1, 1)
    # image centre relative to the subject's bottom-centre, in image-plane metres (right, up)
    right = (Wi / 2.0 - cx) * s * (-1 if flip else 1)
    up = (y1 - Hi / 2.0) * s
    R = ob.rotation_euler.to_matrix()
    ob.location = R @ Vector((right, up, 0)) * 1.0 + Vector((0, 0, 0))
    ob.location.z = ground + up
    ob['gm_reference'] = path
    return dict(object=ob.name, metres_per_px=round(s, 6), width_m=round((x1 - x0) * s, 4), height_m=height_m)


# ---------------------------------------------------------------- fidelity check
def _subject_crop(a, m):
    x0, y0, x1, y1 = _bbox(m)
    return a[y0:y1, x0:x1], m[y0:y1, x0:x1]


def compare(model_png, concept_path, out_png=None, crop=None, threshold=0.1, model_threshold=0.1, bands=10, height=700):
    """Silhouette fidelity of a render (review_stage mode='silhouette', same view, orthographic) against the concept.
    Both subjects are scaled to the same height and aligned on their bbox centre. Returns IoU, aspect of each and
    per-band widths (model vs concept, in subject heights) worst first; writes concept | model | overlay
    (grey = both, red = concept only -> model missing/too narrow, cyan = model only -> too wide/extra)."""
    ca = load(concept_path, crop)
    cm_ = subject_mask(ca, threshold)
    ma = _io['read'](model_png)
    mm = subject_mask(ma, model_threshold)
    cimg, cmask = _subject_crop(ca, cm_)
    mimg, mmask = _subject_crop(ma, mm)
    def scale(img, mask):
        w = max(1, round(img.shape[1] * height / img.shape[0]))
        im = _io['resize'](img, w, height)
        mk = _io['resize'](np.dstack([mask.astype(np.float32)] * 4), w, height)[..., 0] > 0.5
        return im, mk
    cimg, cmask = scale(cimg, cmask)
    mimg, mmask = scale(mimg, mmask)
    W = max(cimg.shape[1], mimg.shape[1])
    def pad(mk):
        out = np.zeros((height, W), bool)
        o = (W - mk.shape[1]) // 2
        out[:, o:o + mk.shape[1]] = mk
        return out
    C, M = pad(cmask), pad(mmask)
    inter, union = (C & M).sum(), (C | M).sum()
    iou = float(inter) / max(1, union)
    rep_b = []
    for i in range(bands):
        ya, yb = int(height * (1 - (i + 1) / bands)), int(height * (1 - i / bands))
        cw = C[ya:yb].any(0).sum() / height
        mw = M[ya:yb].any(0).sum() / height
        ca_ = C[ya:yb].sum() / height ** 2 * bands
        ma_ = M[ya:yb].sum() / height ** 2 * bands
        rep_b.append(dict(z=(round(i / bands, 2), round((i + 1) / bands, 2)), concept_w=round(cw, 3), model_w=round(mw, 3),
                          width_err=round(mw - cw, 3), area_err=round(ma_ - ca_, 3)))
    worst = sorted(rep_b, key=lambda b: -abs(b['width_err']) - abs(b['area_err']))
    if out_png:
        ov = np.zeros((height, W, 4), np.float32)
        ov[..., 3] = 1
        ov[...] = (0.08, 0.08, 0.09, 1)
        ov[C & M] = (0.62, 0.62, 0.64, 1)
        ov[C & ~M] = (0.95, 0.2, 0.2, 1)
        ov[M & ~C] = (0.1, 0.85, 0.95, 1)
        for i in range(1, bands):                            # band guides
            ov[int(height * i / bands), ::4] = (0.35, 0.35, 0.4, 1)
        _io['write'](out_png, _io['tile']([cimg, mimg, ov], cols=3, pad=8))
    return dict(iou=round(iou, 4), concept_aspect=round(cmask.shape[1] / height, 4), model_aspect=round(mmask.shape[1] / height, 4),
                bands=rep_b, worst=worst[:4], sheet=out_png,
                read='width_err > 0: model wider than concept in that band; < 0: narrower. z from bottom (0) to top (1).')
