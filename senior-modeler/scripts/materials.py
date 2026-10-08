# Material recipes (library). Every recipe keeps ONE Principled BSDF whose inputs carry the final albedo / roughness /
# metallic, so texture_bake.py can bake any recipe to PBR maps. Procedural detail that needs Cycles (AO, bevel edge
# masks) shows up fully in the bake; EEVEE previews show the base look.
#   mt = lib('materials')
#   M = mt['palette']('Lantern', {'Brass': ('#C8A040', 'pbr', dict(metallic=1, roughness=0.35)),
#                                 'Glass': ('#FFE9A0', 'glow', dict(strength=4))}, style='stylized')
#   mt['material']('Lantern', 'Wood', '#7A4A2A', recipe='stylized', roughness=0.7)
# Colours: '#RRGGBB' or (r, g, b) in sRGB 0-1 - what a colour picker or concept_match.color_regions() gives you.
# Recipes: flat | stylized (top-light gradient, cavity, edge highlight, value noise) | pbr (roughness breakup, edge wear,
#          cavity dirt) | toon (cel ramp preview, flat albedo) | glow (emissive) | glass (transmission, game-unfriendly)
# Names: M_<Asset>_<Name>. Style defaults: stylized -> 'stylized', realistic -> 'pbr', low_poly -> 'flat',
#        cartoon -> 'stylized' (soft), anime -> 'toon'.
import bpy, os

STYLE_RECIPE = {'stylized': 'stylized', 'realistic': 'pbr', 'low_poly': 'flat', 'cartoon': 'stylized', 'anime': 'toon'}


def srgb(c):
    if isinstance(c, str):
        h = c.lstrip('#')
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(c[:3])


def lin(c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in srgb(c)) + (1.0,)


def _nodes(m):
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (900, 0)
    bs = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bs.location = (600, 0)
    nt.links.new(bs.outputs[0], out.inputs['Surface'])
    return nt, bs, out


def _n(nt, kind, loc, **inputs):
    n = nt.nodes.new(kind)
    n.location = loc
    for k, v in inputs.items():
        if k in n.inputs:
            n.inputs[k].default_value = v
        else:
            setattr(n, k, v)
    return n


def _mix(nt, loc, a, b, fac, blend='MIX'):
    m = _n(nt, 'ShaderNodeMix', loc)
    m.data_type = 'RGBA'
    m.blend_type = blend
    for sock, val in (('A', a), ('B', b)):
        if isinstance(val, bpy.types.NodeSocket):
            nt.links.new(val, m.inputs[sock])
        else:
            m.inputs[sock].default_value = val
    if isinstance(fac, bpy.types.NodeSocket):
        nt.links.new(fac, m.inputs['Factor'])
    else:
        m.inputs['Factor'].default_value = fac
    return m.outputs['Result']


def _range(nt, loc, sock, a, b, c, d, clamp=True):
    r = _n(nt, 'ShaderNodeMapRange', loc)
    r.clamp = clamp
    nt.links.new(sock, r.inputs['Value'])
    r.inputs['From Min'].default_value, r.inputs['From Max'].default_value = a, b
    r.inputs['To Min'].default_value, r.inputs['To Max'].default_value = c, d
    return r.outputs['Result']


def _edge_mask(nt, x, y, radius):
    """Convex-edge mask (Cycles): 1 - dot(bevelled normal, true normal)."""
    bev = _n(nt, 'ShaderNodeBevel', (x, y), Radius=radius)
    bev.samples = 8
    geo = _n(nt, 'ShaderNodeNewGeometry', (x, y - 160))
    dot = _n(nt, 'ShaderNodeVectorMath', (x + 180, y), operation='DOT_PRODUCT')
    nt.links.new(bev.outputs['Normal'], dot.inputs[0])
    nt.links.new(geo.outputs['Normal'], dot.inputs[1])
    return _range(nt, (x + 360, y), dot.outputs['Value'], 0.995, 0.9, 0.0, 1.0)


def _ao(nt, x, y, distance):
    ao = _n(nt, 'ShaderNodeAmbientOcclusion', (x, y), Distance=distance)
    ao.samples = 16
    return ao.outputs['AO']


def _shift(c, k):
    return tuple(min(1.0, max(0.0, v * k)) for v in c[:3]) + (1.0,)


def material(asset, name, color, recipe='flat', roughness=0.55, metallic=0.0, size=1.0, **kw):
    """Create/replace M_<Asset>_<Name>. size: the asset's scale in metres (sets edge widths, AO distance, noise scale).
    kw by recipe: stylized(top_light=0.18, cavity=0.35, edge=0.25, noise=0.06), pbr(wear=0.25, wear_color, dirt=0.3,
    rough_var=0.12), toon(shadow=0.62, shadow_tint), glow(strength=5), glass(ior=1.45)."""
    full = 'M_%s_%s' % (asset, name)
    m = bpy.data.materials.get(full) or bpy.data.materials.new(full)
    nt, bs, out = _nodes(m)
    base = lin(color)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['Metallic'].default_value = metallic
    bs.inputs['Base Color'].default_value = base
    m.diffuse_color = base
    m.roughness = roughness
    m.metallic = metallic
    m['gm_recipe'] = recipe
    m['gm_color'] = '#%02X%02X%02X' % tuple(int(round(v * 255)) for v in srgb(color))
    if recipe == 'stylized':
        tl, cav, edge, noise = kw.get('top_light', 0.18), kw.get('cavity', 0.35), kw.get('edge', 0.25), kw.get('noise', 0.06)
        tc = _n(nt, 'ShaderNodeTexCoord', (-1400, 200))
        sep = _n(nt, 'ShaderNodeSeparateXYZ', (-1220, 200))
        nt.links.new(tc.outputs['Generated'], sep.inputs[0])
        grad = _mix(nt, (-1000, 200), _shift(base, 1 - tl), _shift(base, 1 + tl), sep.outputs['Z'])
        nz = _n(nt, 'ShaderNodeTexNoise', (-1220, -60), Scale=4.0 / max(size, 1e-3), Detail=3.0)
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        nzv = _range(nt, (-1000, -60), nz.outputs['Fac'], 0.3, 0.7, 1 - noise, 1 + noise)
        col = _mix(nt, (-800, 120), grad, nzv, 1.0, 'MULTIPLY')
        em = _edge_mask(nt, -1220, -320, 0.012 * size)
        col = _mix(nt, (-600, 60), col, _shift(base, 1.45), _range(nt, (-800, -320), em, 0, 1, 0, edge))
        ao = _ao(nt, -800, -520, 0.08 * size)
        col = _mix(nt, (-400, 0), col, _shift(base, 1 - cav), _range(nt, (-600, -520), ao, 0, 1, 1, 0))
        nt.links.new(col, bs.inputs['Base Color'])
    elif recipe == 'pbr':
        wear, dirt, rv = kw.get('wear', 0.25), kw.get('dirt', 0.3), kw.get('rough_var', 0.12)
        wear_c = lin(kw['wear_color']) if 'wear_color' in kw else _shift(base, 1.35)
        tc = _n(nt, 'ShaderNodeTexCoord', (-1400, 200))
        nz = _n(nt, 'ShaderNodeTexNoise', (-1220, 200), Scale=6.0 / max(size, 1e-3), Detail=6.0, Roughness=0.6)
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        em = _edge_mask(nt, -1400, -200, 0.006 * size)
        wm = _n(nt, 'ShaderNodeMath', (-860, -120), operation='MULTIPLY')
        nt.links.new(em, wm.inputs[0])
        nt.links.new(_range(nt, (-1000, 200), nz.outputs['Fac'], 0.35, 0.65, 0.3, 1.0), wm.inputs[1])
        wmask = _range(nt, (-700, -120), wm.outputs['Value'], 0, 1, 0, wear * 2)
        ao = _ao(nt, -1000, -420, 0.05 * size)
        dmask = _range(nt, (-800, -420), ao, 0.4, 1.0, dirt, 0.0)
        col = _mix(nt, (-500, 120), base, wear_c, wmask)
        col = _mix(nt, (-320, 120), col, _shift(base, 0.45), dmask)
        nt.links.new(col, bs.inputs['Base Color'])
        r = _range(nt, (-500, -200), nz.outputs['Fac'], 0.3, 0.7, roughness - rv, roughness + rv)
        rmix = _n(nt, 'ShaderNodeMath', (-320, -200), operation='ADD', use_clamp=True)
        nt.links.new(r, rmix.inputs[0])
        nt.links.new(dmask, rmix.inputs[1])
        nt.links.new(rmix.outputs['Value'], bs.inputs['Roughness'])
        if kw.get('wear_metal'):
            nt.links.new(wmask, bs.inputs['Metallic'])
    elif recipe == 'toon':
        sh, tint = kw.get('shadow', 0.62), kw.get('shadow_tint')
        dif = _n(nt, 'ShaderNodeBsdfDiffuse', (300, -260))
        dif.inputs['Color'].default_value = (1, 1, 1, 1)
        s2r = _n(nt, 'ShaderNodeShaderToRGB', (480, -260))
        nt.links.new(dif.outputs[0], s2r.inputs[0])
        ramp = _n(nt, 'ShaderNodeValToRGB', (640, -260))
        ramp.color_ramp.interpolation = 'CONSTANT'
        ramp.color_ramp.elements[1].position = 0.35
        nt.links.new(s2r.outputs['Color'], ramp.inputs['Fac'])
        dark = lin(tint) if tint else _shift(base, sh)
        mixc = _mix(nt, (900, -260), dark, base, ramp.outputs['Color'])
        emi = _n(nt, 'ShaderNodeEmission', (1080, -260))
        nt.links.new(mixc, emi.inputs['Color'])
        out.location = (1300, -260)
        nt.links.new(emi.outputs[0], out.inputs['Surface'])     # preview = cel; Principled stays the bake source
    elif recipe == 'glow':
        bs.inputs['Emission Color'].default_value = base
        bs.inputs['Emission Strength'].default_value = kw.get('strength', 5.0)
    elif recipe == 'glass':
        bs.inputs['Transmission Weight'].default_value = 1.0
        bs.inputs['IOR'].default_value = kw.get('ior', 1.45)
        bs.inputs['Roughness'].default_value = min(roughness, 0.1)
    elif recipe != 'flat':
        raise ValueError('unknown recipe ' + recipe)
    return m


def palette(asset, spec, style='stylized', size=1.0):
    """spec: {Name: color | (color, recipe) | (color, recipe, kwargs)} -> {Name: material}. recipe None = style default."""
    out = {}
    for name, v in spec.items():
        if isinstance(v, str) or all(isinstance(x, (int, float)) for x in v):
            color, recipe, kw = v, None, {}
        else:
            color, recipe, kw = v[0], (v[1] if len(v) > 1 else None), (v[2] if len(v) > 2 else {})
        out[name] = material(asset, name, color, recipe or STYLE_RECIPE.get(style, 'flat'), size=size, **(kw or {}))
    return out


def from_concept(asset, regions, names, style='stylized', size=1.0, recipes=None):
    """Materials straight from concept_match.color_regions(): names = {hex_or_index: 'Name'}."""
    spec = {}
    for key, name in names.items():
        reg = regions[key] if isinstance(key, int) else next(r for r in regions if r['hex'] == key)
        spec[name] = (reg['hex'], (recipes or {}).get(name))
    return palette(asset, spec, style, size)
