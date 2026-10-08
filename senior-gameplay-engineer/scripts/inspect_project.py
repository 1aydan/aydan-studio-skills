"""Project inspector: engine, version, engine install, languages, key plugins/packages, house style, tests.

CLI:     python inspect_project.py <project_dir> [--slug <slug>]
         prints JSON; --slug also writes <skill>/assets/<slug>/project.json
Library: inspect(project_dir) -> dict

Engine installs (first hit wins): <skill>/local.json {"unreal": {"5.8": "D:/UE_5.8"}, "unity": {"6000.0.40f1":
"C:/.../Unity.exe"}, "godot": "C:/.../godot.exe"}, env UE_ROOT / UNITY_EXE / GODOT_EXE, then the standard
locations (Epic launcher manifest + registry source builds, Unity Hub folders, PATH).
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SKIP = {'.git', '.vs', '.vscode', '.idea', 'node_modules', 'Binaries', 'Intermediate', 'Saved', 'DerivedDataCache',
        'Library', 'Temp', 'Logs', 'obj', 'UserSettings', '.godot', 'addons', 'ThirdParty'}
DOCS = ['CLAUDE.md', 'AGENTS.md', 'README.md', 'CONTRIBUTING.md', '.editorconfig', '.clang-format']


def local():
    p = SKILL / 'local.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def find_root(path):
    """Walk up from path to the folder holding a .uproject, ProjectSettings/ProjectVersion.txt or project.godot."""
    p = Path(path).resolve()
    for d in [p, *p.parents]:
        if d.is_dir():
            if any(d.glob('*.uproject')):
                return d, 'unreal'
            if (d / 'ProjectSettings' / 'ProjectVersion.txt').exists():
                return d, 'unity'
            if (d / 'project.godot').exists():
                return d, 'godot'
    return None, None


def files(root, exts):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP and not d.startswith('.')]
        for f in fns:
            if os.path.splitext(f)[1].lower() in exts:
                yield Path(dp) / f


def text(p, limit=200_000):
    try:
        return p.read_text(encoding='utf-8-sig', errors='replace')[:limit]
    except OSError:
        return ''


def style(paths, lang):
    """House-style hints from existing code: indentation, brace style, C# private field prefix."""
    tabs = spaces = allman = kr = 0
    fields = {'_camelCase': 0, 'm_prefix': 0, 'camelCase': 0}
    field_re = re.compile(r'^\s*(?:\[[^\]]*\]\s*)*(?:private|protected)\s+(?:static\s+|readonly\s+)*'
                          r'[\w<>\[\],.?]+\s+(\w+)\s*(?:=|;)', re.M)
    for p in list(paths)[:400]:
        t = text(p)
        tabs += len(re.findall(r'^\t+\S', t, re.M))
        spaces += len(re.findall(r'^ {2,}\S', t, re.M))
        if lang in ('cpp', 'cs'):
            allman += len(re.findall(r'^\s*\{\s*$', t, re.M))
            kr += len(re.findall(r'\)\s*\{\s*$', t, re.M))
        if lang == 'cs':
            for n in field_re.findall(t):
                key = '_camelCase' if n.startswith('_') else 'm_prefix' if n.startswith('m_') else \
                    'camelCase' if n[:1].islower() else None
                if key:
                    fields[key] += 1
    out = {'indent': 'tabs' if tabs >= spaces else 'spaces', 'indent_counts': [tabs, spaces]}
    if lang in ('cpp', 'cs'):
        out['braces'] = 'own line (Allman)' if allman >= kr else 'same line (K&R)'
    if lang == 'cs' and any(fields.values()):
        out['private_fields'] = max(fields, key=fields.get)
        out['private_field_counts'] = fields
    return out


# ---------------------------------------------------------------- Unreal
def _ue_roots(assoc):
    """Candidate engine roots for an EngineAssociation ('5.8', a source-build GUID, or '' = engine tree)."""
    cfg = local().get('unreal', {})
    if assoc in cfg:
        yield Path(cfg[assoc])
    if os.environ.get('UE_ROOT'):
        yield Path(os.environ['UE_ROOT'])
    dat = Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')) / 'Epic/UnrealEngineLauncher/LauncherInstalled.dat'
    if dat.exists():
        for it in json.loads(text(dat)).get('InstallationList', []):
            if it.get('AppName') == f'UE_{assoc}':
                yield Path(it['InstallLocation'])
    if sys.platform == 'win32' and assoc.startswith('{'):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Epic Games\Unreal Engine\Builds') as k:
                yield Path(winreg.QueryValueEx(k, assoc)[0])
        except OSError:
            pass
    for base in ('C:/Program Files/Epic Games', '/Users/Shared/Epic Games'):
        yield Path(base) / f'UE_{assoc}'


def unreal(root):
    up = next(root.glob('*.uproject'))
    data = json.loads(text(up))
    assoc = data.get('EngineAssociation', '')
    # no association = project inside a source engine tree
    cands = _ue_roots(assoc) if assoc else root.parents
    engine = next((d for d in cands if (d / 'Engine/Build/Build.version').exists()), None)
    version = assoc
    tools = {}
    if engine:
        bv = json.loads(text(engine / 'Engine/Build/Build.version'))
        version = f"{bv['MajorVersion']}.{bv['MinorVersion']}.{bv['PatchVersion']}"
        win = sys.platform == 'win32'
        b = engine / 'Engine'
        tools = {'build': str(b / ('Build/BatchFiles/Build.bat' if win else
                                   f"Build/BatchFiles/{'Mac' if sys.platform == 'darwin' else 'Linux'}/Build.sh")),
                 'editor_cmd': str(b / ('Binaries/Win64/UnrealEditor-Cmd.exe' if win else
                                        'Binaries/Linux/UnrealEditor-Cmd')),
                 'uat': str(b / ('Build/BatchFiles/RunUAT.bat' if win else 'Build/BatchFiles/RunUAT.sh'))}
    src = root / 'Source'
    code = list(files(src, {'.h', '.cpp'})) if src.exists() else []
    targets = {}
    for t in (src.glob('*.Target.cs') if src.exists() else []):
        m = re.search(r'Type\s*=\s*TargetType\.(\w+)', text(t))
        targets[t.name[:-len('.Target.cs')]] = m.group(1) if m else 'inherited'
    plugins = [p['Name'] for p in data.get('Plugins', []) if p.get('Enabled')]
    project_plugins = [p.parent.name for p in (root / 'Plugins').glob('**/*.uplugin')] \
        if (root / 'Plugins').exists() else []
    tests = [str(p.relative_to(root)) for p in code if re.search(
        r'IMPLEMENT_(SIMPLE|COMPLEX)_AUTOMATION_TEST|BEGIN_DEFINE_SPEC|TEST_CASE_NAMED|\bTEST_CASE\(', text(p))]
    game_ini = text(root / 'Config/DefaultGame.ini')
    copyright_ = re.search(r'^CopyrightNotice=(.*)$', game_ini, re.M)
    return dict(
        engine='unreal', version=version, engine_root=str(engine) if engine else None, tools=tools,
        languages=(['cpp'] if code else []) + ['blueprint'],
        modules=[f"{m['Name']} ({m.get('Type', '?')})" for m in data.get('Modules', [])],
        targets=targets, editor_target=next((n for n, t in targets.items() if t == 'Editor'), f'{up.stem}Editor'),
        uproject=str(up), plugins_enabled=plugins, project_plugins=project_plugins,
        counts={'h': sum(p.suffix == '.h' for p in code), 'cpp': sum(p.suffix == '.cpp' for p in code)},
        copyright_notice=copyright_.group(1).strip() if copyright_ else None,
        house_style=style(code, 'cpp') if code else {}, tests=tests[:30],
        notes=[] if engine else [f'engine for EngineAssociation {assoc!r} not found - set it in local.json'])


# ---------------------------------------------------------------- Unity
def _unity_exe(version):
    cfg = local().get('unity', {})
    if version in cfg:
        return Path(cfg[version])
    if os.environ.get('UNITY_EXE'):
        return Path(os.environ['UNITY_EXE'])
    bases = [Path('C:/Program Files/Unity/Hub/Editor'), Path('/Applications/Unity/Hub/Editor'),
             Path.home() / 'Unity/Hub/Editor']
    sec = Path(os.environ.get('APPDATA', '')) / 'UnityHub/secondaryInstallPath.json'
    if sec.exists():
        bases.insert(0, Path(json.loads(text(sec)) or '.'))
    for b in bases:
        for exe in ('Editor/Unity.exe', 'Unity.app/Contents/MacOS/Unity', 'Editor/Unity'):
            if (b / version / exe).exists():
                return b / version / exe
    return None


def _unity_installed():
    out = []
    for b in (Path('C:/Program Files/Unity/Hub/Editor'), Path('/Applications/Unity/Hub/Editor'),
              Path.home() / 'Unity/Hub/Editor'):
        out += [d.name for d in b.iterdir()] if b.exists() else []
    return out


def unity(root):
    pv = text(root / 'ProjectSettings/ProjectVersion.txt')
    version = re.search(r'm_EditorVersion:\s*(\S+)', pv).group(1)
    manifest = json.loads(text(root / 'Packages/manifest.json') or '{}').get('dependencies', {})
    notable = {k: v for k, v in manifest.items() if not k.startswith('com.unity.modules.')}
    ps = text(root / 'ProjectSettings/ProjectSettings.asset', 2_000_000)
    handler = re.search(r'activeInputHandler:\s*(\d)', ps)
    es = text(root / 'ProjectSettings/EditorSettings.asset')
    epm = re.search(r'm_EnterPlayModeOptionsEnabled:\s*(\d)', es)
    epm_opts = re.search(r'm_EnterPlayModeOptions:\s*(\d)', es)
    code = list(files(root / 'Assets', {'.cs'}))
    asmdefs = []
    for a in (root / 'Assets').rglob('*.asmdef'):
        try:
            d = json.loads(text(a))
        except ValueError:
            continue
        refs = ' '.join(d.get('references', []) + d.get('precompiledReferences', []) +
                        d.get('optionalUnityReferences', []))
        asmdefs.append(dict(name=d.get('name'), path=str(a.relative_to(root)),
                            editor_only=d.get('includePlatforms') == ['Editor'],
                            test='TestRunner' in refs or 'nunit' in refs or 'TestAssemblies' in refs))
    exe = _unity_exe(version)
    return dict(
        engine='unity', version=version, editor=str(exe) if exe else None,
        installed_editors=_unity_installed(), languages=['cs'], packages=notable,
        input_handling={'0': 'Input Manager (old)', '1': 'Input System package', '2': 'both'}.get(
            handler.group(1) if handler else '', 'unknown'),
        enter_play_mode_options=(None if not epm else
                                 {'enabled': epm.group(1) == '1', 'flags': epm_opts.group(1) if epm_opts else '0'}),
        asmdefs=asmdefs, counts={'cs': len(code)}, house_style=style(code, 'cs') if code else {},
        tests=[a['name'] for a in asmdefs if a['test']],
        notes=[] if exe else [f'Unity {version} not found - install it via Unity Hub or set local.json; never open '
                              f'the project with another version without asking (it upgrades the project)'])


# ---------------------------------------------------------------- Godot
def godot_config(p):
    """project.godot -> {section: {key: raw value}} (multi-line values joined)."""
    out, sec, key, buf, depth = {}, '', None, [], 0
    for line in text(p).splitlines():
        if key is not None:
            buf.append(line)
            depth += sum(line.count(c) for c in '([{') - sum(line.count(c) for c in ')]}')
            if depth <= 0:
                out[sec][key], key = '\n'.join(buf), None
            continue
        s = line.strip()
        if not s or s.startswith(';'):
            continue
        if s.startswith('[') and s.endswith(']'):
            sec = s[1:-1]
            out.setdefault(sec, {})
            continue
        if '=' in s:
            k, v = s.split('=', 1)
            out.setdefault(sec, {})
            depth = sum(v.count(c) for c in '([{') - sum(v.count(c) for c in ')]}')
            if depth > 0:
                key, buf = k, [v]
            else:
                out[sec][k] = v
    return out


def _godot_exe():
    cfg = local().get('godot')
    if cfg:
        return Path(cfg)
    if os.environ.get('GODOT_EXE'):
        return Path(os.environ['GODOT_EXE'])
    for n in ('godot', 'godot4', 'Godot'):
        w = shutil.which(n)
        if w:
            return Path(w)
    return None


def godot(root):
    cfg = godot_config(root / 'project.godot')
    app = cfg.get('application', {})
    feats = re.findall(r'"([^"]+)"', app.get('config/features', ''))
    version = next((f for f in feats if re.match(r'\d+\.\d+', f)), None)
    if not version:
        version = '4.x' if cfg.get('', {}).get('config_version') == '5' else '3.x'
    gd = list(files(root, {'.gd'}))
    cs = list(files(root, {'.cs'}))
    scenes = list(files(root, {'.tscn'}))
    csproj = next(root.glob('*.csproj'), None)
    sdk = re.search(r'Godot\.NET\.Sdk/([\w.\-]+)', text(csproj)) if csproj else None
    addons = sorted(d.name for d in (root / 'addons').iterdir() if d.is_dir()) if (root / 'addons').exists() else []
    autoload = {k: v.strip('"').lstrip('*') for k, v in cfg.get('autoload', {}).items()}
    hs = {}
    if gd or scenes:
        snake = sum(bool(re.fullmatch(r'[a-z0-9_]+', p.stem)) for p in gd + scenes)
        hs['file_names'] = 'snake_case' if snake * 2 >= len(gd) + len(scenes) else 'PascalCase/mixed'
    if gd:
        typed = sum(len(re.findall(r'^func\s+\w+\(.*\)\s*->', text(p), re.M)) for p in gd)
        funcs = sum(len(re.findall(r'^func\s', text(p), re.M)) for p in gd)
        hs['gdscript'] = dict(style(gd, 'gd'), typed_func_returns=f'{typed}/{funcs}')
    if cs:
        hs['csharp'] = style(cs, 'cs')
    exe = _godot_exe()
    return dict(
        engine='godot', version=version, editor=str(exe) if exe else None,
        languages=(['gdscript'] if gd else []) + (['cs'] if cs or 'C#' in feats else []),
        main_scene=app.get('run/main_scene', '').strip('"'), features=feats, autoloads=autoload,
        addons=addons, input_actions=list(cfg.get('input', {}).keys()),
        physics_3d=cfg.get('physics', {}).get('3d/physics_engine', 'default').strip('"'),
        csproj=str(csproj) if csproj else None, dotnet_sdk=sdk.group(1) if sdk else None,
        counts={'gd': len(gd), 'cs': len(cs), 'tscn': len(scenes)}, house_style=hs,
        tests=[a for a in addons if a.lower() in ('gut', 'gdunit4')] +
              [str(d.relative_to(root)) for d in (root / 'test', root / 'tests') if d.exists()],
        notes=[] if exe else ['Godot executable not found - set "godot" in local.json or GODOT_EXE'])


def inspect(project):
    root, kind = find_root(project)
    if not root:
        return {'engine': None, 'notes': [f'no Unreal/Unity/Godot project found at or above {project}']}
    info = {'unreal': unreal, 'unity': unity, 'godot': godot}[kind](root)
    info['root'] = str(root)
    info['name'] = root.name
    info['project_docs'] = [d for d in DOCS if (root / d).exists()]
    info['git'] = (root / '.git').exists() or any((p / '.git').exists() for p in root.parents)
    return info


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('project')
    ap.add_argument('--slug')
    a = ap.parse_args()
    res = inspect(a.project)
    out = json.dumps(res, indent=1)
    if a.slug:
        dst = SKILL / 'assets' / a.slug / 'project.json'
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(out, encoding='utf-8')
    print(out)
