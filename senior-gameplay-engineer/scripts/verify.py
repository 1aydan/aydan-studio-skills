"""Optional QA: compile and run tests headless, report only what matters (errors, failed tests, log path).

CLI:  python verify.py <project> build                       Unreal: Build.bat <Editor target>; Unity: batchmode
                                                             compile; Godot: --import (parses scripts) + dotnet build
      python verify.py <project> test [--filter X]           Unreal: Automation RunTests X; Unity: Test Runner
                                       [--platform EditMode]  (EditMode|PlayMode); Godot: GUT if installed
      python verify.py <project> test --cmd "<command>"      any other test command (output captured the same way)
      --slug <s>    logs + reports in <skill>/assets/<s>/review/ (default: the project folder name); --out <dir>
                    for any other folder

Prints JSON {ok, step, exit, errors[], tests{}, log, notes[]}. Engine paths come from inspect_project.py.
Close the Unreal editor (Live Coding) / Unity editor on that project first - both lock the build.
"""
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import inspect_project as ip  # noqa: E402

# MSVC/clang/UHT/C# "file(line[,col]): error CODE: msg" plus linker and Godot error lines.
ERR = re.compile(r'\b(?:fatal )?error\b\s*[A-Z]*\d*\s*:|^\s*(?:SCRIPT ERROR|ERROR|Parse Error):|'
                 r'Scripts have compiler errors|Unable to build while Live Coding is active', re.I | re.M)
NOT_ERR = re.compile(r'\b0 error|warning|error(s)? (?:found|count)|Error_|LogInit|-error|errors?\.txt', re.I)
NOTES = {
    'Live Coding is active': 'Unreal editor is open with Live Coding - close it, or press Ctrl+Alt+F11 in the '
                             'editor for a .cpp-only change (header/UPROPERTY changes need the editor closed).',
    'another Unity instance is running': 'The project is open in Unity - close it or verify in the open editor.',
    'Godot executable not found': 'Set "godot" in <skill>/local.json.',
}


def run(cmd, log, cwd=None, timeout=3600):
    """Run cmd, tee stdout+stderr to log, return (exit code, text, seconds)."""
    t0 = time.time()
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
                           shell=isinstance(cmd, str))
        out, code = p.stdout.decode('utf-8', errors='replace'), p.returncode
    except subprocess.TimeoutExpired as e:
        out, code = (e.stdout or b'').decode('utf-8', errors='replace') + '\n[verify] TIMEOUT', -1
    except FileNotFoundError as e:
        out, code = f'[verify] {e}', -1
    log.write_text(out, encoding='utf-8')
    return code, out, round(time.time() - t0, 1)


def errors(text, limit=40):
    seen, out = set(), []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        m = ERR.search(s)
        if m and not NOT_ERR.search(s[:m.start()]) and 'UnifiedErrorTest' not in s:
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ''
            if nxt.startswith('at:') and 'res://' in nxt:          # Godot puts the location on the next line
                s += ' @ ' + nxt[nxt.find('res://'):].rstrip(')')
            if s not in seen:
                seen.add(s)
                out.append(s[:400])
    return out[:limit]


def notes(text):
    return [msg for key, msg in NOTES.items() if key in text]


def result(step, code, text, log, secs, tests=None, extra=(), strict=False):
    """strict: any error line fails the step (Godot exits 0 even when scripts have errors)."""
    errs = [] if tests else errors(text)      # a test report already carries the failure messages
    ok = code == 0 and not (tests or {}).get('failed') and not (strict and errs)
    return dict(ok=ok, step=step, exit=code, seconds=secs, errors=errs,
                tests=tests or {}, log=str(log), notes=notes(text) + list(extra))


# ---------------------------------------------------------------- Unreal
def unreal_build(info, out):
    t = info['tools']
    cmd = [t['build'], info['editor_target'], 'Win64' if sys.platform == 'win32' else 'Linux', 'Development',
           f"-Project={info['uproject']}", '-WaitMutex', '-FromMsBuild']
    code, text, secs = run(cmd, out / 'build.log')
    return result('build', code, text, out / 'build.log', secs)


def unreal_test(info, out, flt):
    rep = out / 'ue_tests'
    cmd = [info['tools']['editor_cmd'], info['uproject'], f'-ExecCmds=Automation RunTests {flt};Quit',
           '-TestExit=Automation Test Queue Empty', f'-ReportExportPath={rep}', '-unattended', '-nopause',
           '-nosplash', '-NullRHI', '-NoSound', '-stdout', '-FullStdOutLogOutput']
    code, text, secs = run(cmd, out / 'test.log')
    tests = {}
    idx = rep / 'index.json'
    if idx.exists():
        raw = idx.read_bytes()
        d = json.loads(raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'))
        failed = [dict(test=x.get('fullTestPath'), errors=[e['event']['message'] for e in x.get('entries', [])
                                                             if e.get('event', {}).get('type') == 'Error'][:5])
                  for x in d.get('tests', []) if x.get('state') == 'Fail']
        tests = dict(passed=d.get('succeeded', 0) + d.get('succeededWithWarnings', 0), failed=len(failed),
                     not_run=d.get('notRun', 0), failures=failed)
    extra = [] if tests.get('passed') or tests.get('failed') else [f'no tests matched filter {flt!r}']
    return result('test', code, text, out / 'test.log', secs, tests, extra)


# ---------------------------------------------------------------- Unity
def unity_build(info, out):
    log = out / 'compile.log'
    cmd = [info['editor'], '-batchmode', '-nographics', '-quit', '-projectPath', info['root'], '-logFile', str(log)]
    code, _, secs = run(cmd, out / 'compile_stdout.log')
    text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
    return result('build', code, text, log, secs)


def unity_test(info, out, platform):
    log, xml = out / f'test_{platform}.log', out / f'tests_{platform}.xml'
    xml.unlink(missing_ok=True)
    cmd = [info['editor'], '-batchmode', '-nographics', '-projectPath', info['root'], '-runTests',
           '-testPlatform', platform, '-testResults', str(xml), '-logFile', str(log)]   # no -quit with -runTests
    code, _, secs = run(cmd, out / 'test_stdout.log')
    text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
    return result('test', code, text, log, secs, junit_or_nunit(xml))


# ---------------------------------------------------------------- Godot
def godot_build(info, out):
    """--import, then load every script (--import skips scripts nothing references), then dotnet build for C#."""
    g = [info['editor'], '--headless', '--path', info['root']]
    steps = [(g + ['--import'], 'import.log', True)]
    if info['counts']['gd']:
        steps.append((g + ['-s', str(HERE / 'check_scripts.gd')], 'scripts.log', True))
    if info.get('csproj'):
        steps.append((['dotnet', 'build', info['csproj'], '-nologo', '-v', 'q'], 'dotnet_build.log', False))
    parts = []
    for cmd, log, strict in steps:
        code, text, secs = run(cmd, out / log)
        parts.append(result('build', code, text, out / log, secs, strict=strict))
    return dict(ok=all(p['ok'] for p in parts), step='build', exit=next((p['exit'] for p in parts if p['exit']), 0),
                seconds=round(sum(p['seconds'] for p in parts), 1), errors=sum((p['errors'] for p in parts), []),
                tests={}, log=' | '.join(p['log'] for p in parts), notes=sum((p['notes'] for p in parts), []))


def godot_test(info, out):
    if 'gut' not in [a.lower() for a in info.get('addons', [])]:
        return dict(ok=False, step='test', exit=None, errors=[], tests={}, log=None,
                    notes=['no GUT addon found - for gdUnit4 or C# tests pass --cmd; ask before adding a test addon'])
    xml = out / 'gut.xml'
    cmd = [info['editor'], '--headless', '--path', info['root'], '-s', 'res://addons/gut/gut_cmdln.gd',
           '-gdir=res://test', '-ginclude_subdirs', '-gexit', f'-gjunit_xml_file={xml}']
    code, text, secs = run(cmd, out / 'test.log')
    return result('test', code, text, out / 'test.log', secs, junit_or_nunit(xml))


def junit_or_nunit(xml):
    """Pass/fail counts + failures from a JUnit or NUnit 3 result file."""
    if not xml.exists():
        return {}
    root = ET.parse(xml).getroot()
    fails, passed = [], 0
    for tc in root.iter():
        if tc.tag == 'test-case':                                    # NUnit 3 (Unity)
            if tc.get('result') == 'Failed':
                fails.append(dict(test=tc.get('fullname'), errors=[(tc.findtext('failure/message') or '')[:400]]))
            elif tc.get('result') == 'Passed':
                passed += 1
        elif tc.tag == 'testcase':                                   # JUnit (GUT, gdUnit4)
            f = tc.find('failure') if tc.find('failure') is not None else tc.find('error')
            if f is not None:
                fails.append(dict(test=f"{tc.get('classname')}.{tc.get('name')}",
                                  errors=[(f.get('message') or f.text or '')[:400]]))
            elif tc.find('skipped') is None:
                passed += 1
    return dict(passed=passed, failed=len(fails), failures=fails)


def verify(project, step, flt=None, platform='EditMode', cmd=None, out=None, slug=None):
    info = ip.inspect(project)
    eng = info.get('engine')
    if not eng:
        return dict(ok=False, step=step, notes=info.get('notes', []))
    out = Path(out) if out else ip.SKILL / 'assets' / (slug or info['name']) / 'review'
    out.mkdir(parents=True, exist_ok=True)
    if cmd:
        code, text, secs = run(cmd, out / f'{step}.log', cwd=info['root'])
        return result(step, code, text, out / f'{step}.log', secs)
    if eng != 'unreal' and not info.get('editor'):
        return dict(ok=False, step=step, notes=info.get('notes', []))
    if eng == 'unreal':
        if not info.get('tools'):
            return dict(ok=False, step=step, notes=info.get('notes', []))
        if step == 'build' and 'cpp' not in info['languages']:
            return dict(ok=True, step=step, notes=['Blueprint-only project: nothing to compile'])
        return unreal_build(info, out) if step == 'build' else unreal_test(info, out, flt or info['name'])
    if eng == 'unity':
        return unity_build(info, out) if step == 'build' else unity_test(info, out, platform)
    return godot_build(info, out) if step == 'build' else godot_test(info, out)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('project')
    ap.add_argument('step', choices=['build', 'test'])
    ap.add_argument('--filter', help='Unreal automation test filter (default: the project name)')
    ap.add_argument('--platform', default='EditMode', help='Unity: EditMode | PlayMode')
    ap.add_argument('--cmd', help='custom command line (run in the project root)')
    ap.add_argument('--slug', help='feature folder: logs go to <skill>/assets/<slug>/review/')
    ap.add_argument('--out', help='explicit log folder (overrides --slug)')
    a = ap.parse_args()
    res = verify(a.project, a.step, a.filter, a.platform, a.cmd, a.out, a.slug)
    print(json.dumps(res, indent=1))
    sys.exit(0 if res.get('ok') else 1)
