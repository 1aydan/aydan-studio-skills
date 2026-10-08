# <ASSET> - UVs (always) + textures per BRIEF['textures']. Run after build.py (it freezes generator modifiers;
# re-run build.py + surface.py together for geometry changes).
#   p = r"<skill>\assets\<slug>\surface.py"; g = {'__file__': p}; exec(open(p).read(), g); g['REPORT']
import os

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brief.py'), encoding='utf-8').read(), globals())
L = {n: lib(n) for n in ('model_kit', 'uv_tools', 'texture_bake', 'mesh_qa')}

B = BRIEF
objs = L['model_kit']['parts'](B['name'])
REPORT = dict(unwrap=L['uv_tools']['unwrap'](objs, res=B['texture_res'], margin_px=B['margin_px']))
REPORT['uv_qa'] = L['uv_tools']['uv_qa'](objs, res=512, margin_px=max(1, B['margin_px'] * 512 // B['texture_res']),
                                         allow_overlap=B['allow_uv_overlap'])
REPORT['texel'] = L['uv_tools']['texel_density'](objs, B['texture_res'])
tex_dir = os.path.join(HERE, 'textures')
if B['textures'] == 'pbr':
    REPORT['bake'] = L['texture_bake']['bake'](
        objs, B['name'], tex_dir, res=B['texture_res'],
        ao_in_albedo={'stylized': 0.3, 'cartoon': 0.2}.get(B['style'], 0.0),
        maps=('BaseColor',) if B['style'] == 'anime' else ('BaseColor', 'Roughness', 'Metallic', 'Normal', 'AO'))
    L['texture_bake']['swap'](objs, B['name'], 'baked')
elif B['textures'] == 'palette':
    REPORT['palette'] = L['texture_bake']['palette_texture'](objs, B['name'], tex_dir)
L['uv_tools']['uv_map'](objs, os.path.join(tex_dir, 'UV_%s.png' % B['name']), res=1024,
                        margin_px=B['margin_px'] * 1024 // B['texture_res'])
print({k: v for k, v in REPORT.items() if k != 'unwrap'})
