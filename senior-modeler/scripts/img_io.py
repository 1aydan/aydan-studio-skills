# PNG read/write/tile helpers (library) shared by review_stage.py and concept_match.py. numpy only (no PIL in Blender).
#   io = lib('img_io')
# Arrays are float32 RGBA, TOP-DOWN (row 0 = top of the picture), values as stored in the file (sRGB for PNG/JPG).
import bpy, os, math
import numpy as np


def read(path):
    im = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = im.size
        a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1].copy()
    finally:
        bpy.data.images.remove(im)
    return a


def write(path, a):
    a = np.asarray(a, dtype=np.float32)
    if a.ndim == 2:
        a = np.dstack([a, a, a, np.ones_like(a)])
    if a.shape[2] == 3:
        a = np.dstack([a, np.ones(a.shape[:2], np.float32)])
    h, w = a.shape[:2]
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    im = bpy.data.images.new('GM_tmp_write', w, h, alpha=True)
    try:
        im.pixels = np.clip(a[::-1], 0, 1).ravel()
        im.filepath_raw = path
        im.file_format = 'PNG'
        im.save()
    finally:
        bpy.data.images.remove(im)
    return path


def resize(a, w, h):
    """Bilinear resize to (w, h)."""
    H, W = a.shape[:2]
    if (W, H) == (w, h):
        return a.copy()
    ys = np.clip((np.arange(h) + 0.5) * H / h - 0.5, 0, H - 1)
    xs = np.clip((np.arange(w) + 0.5) * W / w - 0.5, 0, W - 1)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, H - 1), np.minimum(x0 + 1, W - 1)
    fy, fx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bot = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return (top * (1 - fy) + bot * fy).astype(np.float32)


def fit_height(a, h):
    return resize(a, max(1, round(a.shape[1] * h / a.shape[0])), h)


def tile(imgs, cols=None, pad=6, bg=(0.05, 0.05, 0.06, 1.0)):
    """Tile images left->right, top->bottom; cells sized to the largest image."""
    cols = cols or len(imgs)
    rows = math.ceil(len(imgs) / cols)
    ch = max(i.shape[0] for i in imgs)
    cw = max(i.shape[1] for i in imgs)
    out = np.empty((rows * ch + (rows + 1) * pad, cols * cw + (cols + 1) * pad, 4), np.float32)
    out[:] = bg
    for k, im in enumerate(imgs):
        r, c = divmod(k, cols)
        y = pad + r * (ch + pad) + (ch - im.shape[0]) // 2
        x = pad + c * (cw + pad) + (cw - im.shape[1]) // 2
        out[y:y + im.shape[0], x:x + im.shape[1]] = im if im.shape[2] == 4 else np.dstack([im, np.ones(im.shape[:2])])
    return out


def row(imgs, pad=10, bg=(0.05, 0.05, 0.06, 1.0)):
    """Images left->right at their OWN widths (tile() gives every cell the widest width), vertically centred."""
    H = max(i.shape[0] for i in imgs)
    W = sum(i.shape[1] for i in imgs) + pad * (len(imgs) + 1)
    out = np.empty((H + 2 * pad, W, 4), np.float32)
    out[:] = bg
    x = pad
    for im in imgs:
        y = pad + (H - im.shape[0]) // 2
        out[y:y + im.shape[0], x:x + im.shape[1]] = im if im.shape[2] == 4 else np.dstack([im, np.ones(im.shape[:2])])
        x += im.shape[1] + pad
    return out


def side_by_side(paths, out_path, height=900, pad=6):
    """Before/after (or concept/render) strip from image files, all scaled to the same height."""
    return write(out_path, tile([fit_height(read(p), height) for p in paths], cols=len(paths), pad=pad))


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hex(c):
    return '#%02X%02X%02X' % tuple(int(round(max(0, min(1, x)) * 255)) for x in c[:3])
