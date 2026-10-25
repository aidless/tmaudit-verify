"""_check_pyz_fresh.py — fail if the committed tmaudit.pyz is stale.

`tmaudit.pyz` is a committed distribution artifact, and the README offers
it as a zero-install form of the tool. CI used to only rebuild it and
smoke-run `list` on the rebuilt copy, so nothing ever compared the
archive against what was committed. A v0.1.x-era archive therefore sat in
the repository while the package moved on to v0.5.1: built by Python 3.9,
carrying `.pyc`, and missing plugins.py, cache.py, report.py,
llm_fallback.py and detector_config/ entirely.

What this checks -- content, never archive bytes. `zipapp` embeds file
mtimes, so two builds of identical source are not byte-identical and a
byte diff would be flaky:

  1. every `.py` and `.yaml` file under `src/tmaudit/` is present in the
     archive, byte for byte;
  2. the archive carries no `.pyc` / `__pycache__` entries;
  3. the archive holds nothing beyond that source set plus the zipapp's
     own root `__main__.py` launcher stub.

Run it BEFORE `_build_pyz.py`, which overwrites the archive.

Usage:
    python _check_pyz_fresh.py [PATH_TO_PYZ]
"""
from __future__ import annotations
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = ROOT / 'src' / 'tmaudit'
PYZ = ROOT / 'tmaudit.pyz'

# What belongs in the archive is source (.py) and data (.yaml) under the
# package directory -- and nothing else.
WANTED_SUFFIXES = ('.py', '.yaml')

# `zipapp.create_archive(main=...)` writes this launcher at the archive
# root. It belongs to the archive format, not to src/tmaudit/.
ZIPAPP_STUB = '__main__.py'


def source_files() -> dict:
    """Map archive-relative path -> committed bytes, for the source tree."""
    out = {}
    for path in sorted(PKG.rglob('*')):
        if not path.is_file():
            continue
        if '__pycache__' in path.parts or path.suffix not in WANTED_SUFFIXES:
            continue
        rel = path.relative_to(PKG.parent).as_posix()   # 'tmaudit/...'
        out[rel] = path.read_bytes()
    return out


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    pyz = Path(args[0]) if args else PYZ

    if not pyz.exists():
        print(f'ERROR: {pyz} is missing; the committed artifact is gone',
              file=sys.stderr)
        return 1

    with zipfile.ZipFile(pyz) as z:
        archived = {i.filename: z.read(i.filename)
                    for i in z.infolist() if not i.is_dir()}

    sources = source_files()
    problems = []

    for name in sorted(archived):
        if name.endswith('.pyc') or '__pycache__' in name:
            problems.append(f'archive carries bytecode: {name}')

    for rel, blob in sources.items():
        if rel not in archived:
            problems.append(
                f'archive is MISSING {rel} -- it is in src/tmaudit/, so the '
                f'committed artifact predates it'
            )
        elif archived[rel] != blob:
            problems.append(f'archive content differs from source: {rel}')

    known = set(sources) | {ZIPAPP_STUB}
    for name in sorted(set(archived) - known):
        problems.append(f'archive holds {name}, which is not in src/tmaudit/')

    if problems:
        print(f'STALE ZIPAPP: {pyz.name} does not match src/tmaudit/',
              file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)
        print('\nRebuild it with: python _build_pyz.py', file=sys.stderr)
        return 1

    print(f'OK: {pyz.name} matches src/tmaudit/ '
          f'({len(sources)} files, no bytecode)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
