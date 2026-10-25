"""_build_pyz.py — package the tmaudit install into a single .pyz.

After `pip install --editable .` (which we already did), we can use
the installed `tmaudit` package as the source for a zipapp. This
produces a single `tmaudit.pyz` file that can be run on any
Python 3.9+ system without any prior install.

Usage:
    python _build_pyz.py
    python tmaudit.pyz --help
    python tmaudit.pyz verify --paper 1
"""
import os
import shutil
import subprocess
import sys
import zipapp
from pathlib import Path

# The author's development tree, which holds the same src/tmaudit/ layout as this
# repository — so this resolves here by default and can be pointed elsewhere with
# TMAUDIT_TEMPLATE_DIR, as the configs modules and _check_all_regressions.py are.
ROOT = Path(os.environ.get('TMAUDIT_TEMPLATE_DIR',
                           str(Path(__file__).resolve().parent)))
PKG = ROOT / 'src' / 'tmaudit'
BUILD = ROOT / 'build_pyz'
OUT = ROOT / 'tmaudit.pyz'


def _exclude_byproducts(_dir: str, names: list) -> list:
    """Skip interpreter and packaging byproducts.

    ``__pycache__`` appears in any tree where the tests have been run,
    so building the archive after a test run used to ship 18 stale
    ``.pyc`` files and inflate the zipapp roughly threefold
    (53 KB -> 161 KB). Bytecode does not belong in a source zipapp: it
    goes stale the moment a source file changes.
    """
    return [n for n in names
            if n == '__pycache__'
            or n.endswith('.pyc')
            or n.endswith('.egg-info')]


def main() -> int:
    if not PKG.exists():
        print(f'ERROR: {PKG} does not exist; run `pip install --editable .` first',
              file=sys.stderr)
        return 1

    # Clean build dir
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir()

    # Copy tmaudit package tree (preserve structure)
    target_pkg = BUILD / 'tmaudit'
    shutil.copytree(PKG, target_pkg, ignore=_exclude_byproducts)

    # Build the .pyz
    if OUT.exists():
        OUT.unlink()
    zipapp.create_archive(
        source=BUILD,
        target=str(OUT),
        main='tmaudit.__main__:main',
        compressed=True,
    )
    size = OUT.stat().st_size
    print(f'Built {OUT} ({size:,} bytes)')

    # Smoke test
    print()
    print('=== smoke test: tmaudit.pyz list ===')
    rc = subprocess.run(
        [sys.executable, str(OUT), 'list'],
    ).returncode
    print(f'rc = {rc}')
    return rc


if __name__ == '__main__':
    sys.exit(main())