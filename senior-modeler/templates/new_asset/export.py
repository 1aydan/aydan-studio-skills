# <ASSET> - export (Better FBX if enabled, else Blender FBX; or glb/obj per the brief) + re-import verification.
#   p = r"<skill>\assets\<slug>\export.py"; g = {'__file__': p}; exec(open(p).read(), g); g['REPORT']
# Only after review.py STAGE='final' shows QA PASS (errors block export).
import os

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brief.py'), encoding='utf-8').read(), globals())
L = {n: lib(n) for n in ('model_kit', 'mesh_qa', 'model_export')}

B = BRIEF
E = B['export']
qa = L['mesh_qa']['qa'](L['model_kit']['parts'](B['name']), B)
if not qa['ok'] and not globals().get('FORCE'):
    raise RuntimeError('QA errors - fix or set FORCE=True with the user\'s OK:\n' + L['mesh_qa']['summary'](qa))
REPORT = L['model_export']['export'](B['name'], os.path.join(HERE, 'export'), fmt=E['fmt'],
                                     join=E['join'], collision=bool(E.get('collision')), engine=B['engine'],
                                     exporter=E.get('exporter', 'auto'), lods=E.get('lods', ()), opts=E.get('opts'),
                                     textures=B['textures'] != 'none')
REPORT['verify'] = L['model_export']['verify']([f for f in REPORT['files'] if f.endswith('.' + E['fmt'])][:1])
print(REPORT)
