"""Install the sa3.cpp runtime + Stable Audio 3 GGUF models for this skill (Windows x64, stdlib only).

    python setup_sa3.py --home "F:/AI Models/sa3" --variant small-sfx --variant medium [--dry-run]

- Runtime: sa3.cpp release zips from github.com/betweentwomidnights/sa3.cpp (core + cuda, or vulkan), verified
  against the release SHA256SUMS, unpacked flat into <home>/bin.
- CUDA runtime: the core+cuda package needs cudart64_12 / cublas64_12 / cublasLt64_12 beside the tools. They are
  copied from an LM Studio CUDA 12 backend when one is installed; otherwise use --backend standalone (738 MB,
  bundles the CUDA runtime) or --backend vulkan.
- Models: GGUF sets from huggingface.co/thepatch (DiT + SAME autoencoder + conditioner per variant, shared
  T5Gemma encoder + vocab). Existing files are skipped; a matching file already downloaded by LM Studio is
  copied instead of re-downloaded.
- Writes <skill>/local.json {"sa3_home": ...} so scripts/sa3.py finds the install.
Model licenses: Stability AI Community License (SA3), Gemma Terms of Use (T5Gemma encoder).
"""
import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
TAG = 'v0.1.1'
REL = f'https://github.com/betweentwomidnights/sa3.cpp/releases/download/{TAG}'
HF = 'https://huggingface.co'
VARIANTS = {   # variant: (DiT size, SAME, default DiT encoding, default SAME encoding)
    'small-sfx': ('0.5B', 'same-s', 'F16', 'F32'),
    'small-music': ('0.5B', 'same-s', 'F16', 'F32'),
    'medium': ('1.5B', 'same-l', 'F16', 'F32'),
}
CUDA_DLLS = ['cudart64_12.dll', 'cublas64_12.dll', 'cublasLt64_12.dll']


def fetch(url, dst, dry):
    dst = Path(dst)
    if dst.exists():
        print(f'[skip] {dst.name}')
        return dst
    if dry:
        print(f'[plan] {url} -> {dst}')
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_suffix(dst.suffix + '.part')
    print(f'[get]  {url}')
    with urllib.request.urlopen(url) as r, open(part, 'wb') as f:
        shutil.copyfileobj(r, f, 1 << 20)
    part.replace(dst)
    return dst


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def lmstudio_file(name):
    root = Path.home() / '.lmstudio' / 'models'
    return next(root.rglob(name), None) if root.exists() else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--home', required=True, help='install folder (holds bin/ and models/)')
    ap.add_argument('--variant', action='append', choices=list(VARIANTS), help='repeatable; default small-sfx')
    ap.add_argument('--encoding', help='DiT encoding for all variants: F16 F32 Q8_0 Q5_K_M Q4_K_M')
    ap.add_argument('--ae-encoding', help='autoencoder encoding (default F32; Q8_0 saves ~70%%)')
    ap.add_argument('--backend', default='cuda', choices=['cuda', 'vulkan', 'standalone'])
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    home = Path(a.home)
    bin_, models, dl = home / 'bin', home / 'models', home / '_downloads'
    variants = a.variant or ['small-sfx']

    # runtime
    sums = fetch(f'{REL}/SHA256SUMS', dl / 'SHA256SUMS', a.dry_run)
    zips = ['standalone'] if a.backend == 'standalone' else ['core', a.backend]
    for z in zips:
        name = f'sa3-{TAG}-windows-x64-{z}.zip'
        p = fetch(f'{REL}/{name}', dl / name, a.dry_run)
        if a.dry_run:
            continue
        want = {l.split()[1].lstrip('*'): l.split()[0] for l in sums.read_text().splitlines() if l.strip()}
        if want.get(name) != sha256(p):
            sys.exit(f'checksum mismatch for {name} - delete it and retry')
        with zipfile.ZipFile(p) as zf:
            zf.extractall(bin_)
        print(f'[ok]   {name} -> {bin_}')
    if a.backend == 'cuda' and not a.dry_run and not all((bin_ / d).exists() for d in CUDA_DLLS):
        vendor = next((Path.home() / '.lmstudio' / 'extensions' / 'backends' / 'vendor').glob('*cuda12*'), None) \
            if (Path.home() / '.lmstudio').exists() else None
        if vendor and all((vendor / d).exists() for d in CUDA_DLLS):
            for d in CUDA_DLLS:
                shutil.copy2(vendor / d, bin_ / d)
            print(f'[ok]   CUDA 12 runtime copied from {vendor}')
        else:
            print('[warn] CUDA 12 runtime DLLs not found - rerun with --backend standalone (bundles them) '
                  'or --backend vulkan')

    # models
    def model(repo, name):
        dst = models / name
        src = lmstudio_file(name) if not dst.exists() else None
        if src and not a.dry_run:
            models.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f'[copy] {name} (from LM Studio)')
            return
        fetch(f'{HF}/{repo}/resolve/main/{name}', dst, a.dry_run)

    model('thepatch/t5gemma-b-b-ul2-GGUF', 't5gemma-b-b-ul2-v1.0-vocab.gguf')
    model('thepatch/t5gemma-b-b-ul2-GGUF', 't5gemma-b-b-ul2-encoder-0.3B-v1.0-F16.gguf')
    for v in variants:
        size, same, de, ae = VARIANTS[v]
        de, ae = (a.encoding or de).upper(), (a.ae_encoding or ae).upper()
        repo = f'thepatch/stable-audio-3-{v}-GGUF'
        model(repo, f'stable-audio-3-{v}-conditioner-v1.0-F32.gguf')
        model(repo, f'stable-audio-3-{v}-dit-{size}-v1.0-{de}.gguf')
        model(repo, f'stable-audio-3-{v}-{same}-v1.0-{ae}.gguf')

    if not a.dry_run:
        (SKILL / 'local.json').write_text(json.dumps({'sa3_home': home.as_posix()}, indent=2) + '\n')
        print(f'[ok]   {SKILL / "local.json"} -> {home}')
        print('next:  python scripts/sa3.py status')


if __name__ == '__main__':
    main()
