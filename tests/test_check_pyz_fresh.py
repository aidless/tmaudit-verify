"""Counter-proof for _check_pyz_fresh.py.

This repository requires that a gate be able to fail -- mutation-control
and the 14-bug meta-test exist for exactly that reason -- and the gate
guarding the committed zipapp is no exception. These tests prove it
rejects archives that drift from src/tmaudit/, and accepts the one that
is actually committed.
"""
from __future__ import annotations
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import _check_pyz_fresh as guard  # noqa: E402


def _write_archive(path: Path, entries: dict) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for name, blob in entries.items():
            z.writestr(name, blob)


def _archive_from_source(path: Path, drop: str = "") -> None:
    entries = {k: v for k, v in guard.source_files().items() if k != drop}
    entries[guard.ZIPAPP_STUB] = b"# launcher\n"
    _write_archive(path, entries)


def test_accepts_the_committed_archive(capsys):
    rc = guard.main([str(ROOT / "tmaudit.pyz")])
    out, err = capsys.readouterr()
    assert rc == 0, err
    assert "OK:" in out


def test_rejects_an_archive_that_predates_a_module(tmp_path, capsys):
    """Drop one module the source tree has: the guard must fail.

    This is the v0.1.x failure mode it was written for -- the committed
    archive was missing plugins.py, cache.py, report.py and
    llm_fallback.py while the package had moved on.
    """
    stale = tmp_path / "predates.pyz"
    _archive_from_source(stale, drop="tmaudit/plugins.py")

    rc = guard.main([str(stale)])
    _, err = capsys.readouterr()
    assert rc == 1, "an archive missing a source module must be rejected"
    assert "tmaudit/plugins.py" in err
    assert "MISSING" in err


def test_rejects_an_archive_carrying_bytecode(tmp_path, capsys):
    """A source zipapp must not ship .pyc; the guard must fail if it does."""
    dirty = tmp_path / "bytecode.pyz"
    _archive_from_source(dirty)
    with zipfile.ZipFile(dirty, "a") as z:
        z.writestr("tmaudit/__pycache__/cli.cpython-39.pyc", b"\x00\x00")

    rc = guard.main([str(dirty)])
    _, err = capsys.readouterr()
    assert rc == 1, "bytecode in the archive must be rejected"
    assert "bytecode" in err


def test_rejects_content_that_differs_from_source(tmp_path, capsys):
    """Same file names, different bytes: still stale."""
    drifted = tmp_path / "drifted.pyz"
    _archive_from_source(drifted)
    entries = {k: v for k, v in guard.source_files().items()}
    entries["tmaudit/cli.py"] = entries["tmaudit/cli.py"] + b"\n# edited\n"
    entries[guard.ZIPAPP_STUB] = b"# launcher\n"
    _write_archive(drifted, entries)

    rc = guard.main([str(drifted)])
    _, err = capsys.readouterr()
    assert rc == 1, "content drift must be rejected, not just missing files"
    assert "differs from source" in err
