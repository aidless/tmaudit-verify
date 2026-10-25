"""Tests for the generic ``verify --paper-dir`` path (no ``--paper``).

`tmaudit verify --paper-dir DIR` audits a manuscript the built-in
rulepack was not written for. Two properties the pre-2026-10 template
did not have:

  * the manuscript's root file need not be named ``main.tex``;
  * the bibliography may be a compiled ``.bbl`` only (no ``refs.bib``),
    and when neither is present C4 reports "not applicable" instead of
    aborting the whole audit.

The reverse is also tested: a directory with no manuscript ``.tex`` at
all is still an operational error (exit 2), so "not applicable" is not
allowed to swallow a genuinely missing input.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tmaudit import cli, forge
from src.tmaudit.templates import verify_TEMPLATE


# A manuscript that is clean under every generic check (availability
# statement + all four metadata categories, engagement-verb cites, no
# p/d values, no figures) so a passing run is exit 0.
CLEAN_TEX = (
    '\\documentclass{article}\n'
    '\\begin{document}\n'
    '\\begin{abstract}\n'
    'We study the method and find it is available and reproducible.\n'
    '\\end{abstract}\n'
    'We adopt \\cite{keyA} and extend \\cite{keyB}.\n'
    '\\section{Code availability}\n'
    'Code is available at https://github.com/example/repo. '
    'Hyperparameters (learning rate, batch size, optimizer), the random '
    'seed, the hardware (GPU), and the library version (PyTorch 2) are '
    'listed in the appendix.\n'
    '\\end{document}\n'
)

# A compiled .bbl defining both cited keys -- the form a submission
# ships when the .bib is withheld.
CLEAN_BBL = (
    '\\begin{thebibliography}{2}\n'
    '\\bibitem[Author(2024)]{keyA} A. Author. A paper, 2024.\n'
    '\\bibitem{keyB} B. Author. Another paper, 2024.\n'
    '\\end{thebibliography}\n'
)


def _run_script(script: Path, paper_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=str(paper_dir),
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# _bib_keys: both .bib and .bbl sources
# ---------------------------------------------------------------------------

def test_bib_keys_parses_bbl_bibitems():
    keys = verify_TEMPLATE._bib_keys(CLEAN_BBL)
    assert keys == {'keyA', 'keyB'}, keys


def test_bib_keys_parses_bib_entries():
    bib = '@article{keyA,\n  author = {A},\n}\n@inproceedings{keyB, x = 1}\n'
    assert verify_TEMPLATE._bib_keys(bib) == {'keyA', 'keyB'}


def test_bib_keys_unions_both_sources():
    mixed = '@article{keyA, author = {A}}\n\\bibitem{keyB} B.\n'
    assert verify_TEMPLATE._bib_keys(mixed) == {'keyA', 'keyB'}


# ---------------------------------------------------------------------------
# find_main_tex
# ---------------------------------------------------------------------------

def test_find_main_tex_prefers_main(tmp_path):
    (tmp_path / 'main.tex').write_text('\\begin{document}x\\end{document}',
                                       encoding='utf-8')
    (tmp_path / 'other.tex').write_text('\\begin{document}y\\end{document}',
                                        encoding='utf-8')
    assert forge.find_main_tex(tmp_path).name == 'main.tex'


def test_find_main_tex_falls_back_to_sole_root(tmp_path):
    """No main.tex: the sole .tex declaring \\begin{document} is chosen."""
    (tmp_path / 'paper.tex').write_text('\\begin{document}x\\end{document}',
                                        encoding='utf-8')
    (tmp_path / 'macros.tex').write_text('% no document env\n',
                                         encoding='utf-8')
    assert forge.find_main_tex(tmp_path).name == 'paper.tex'


def test_find_main_tex_returns_none_when_absent(tmp_path):
    (tmp_path / 'notes.txt').write_text('nothing', encoding='utf-8')
    assert forge.find_main_tex(tmp_path) is None


# ---------------------------------------------------------------------------
# fork_verify_generic: neutral script, non-main.tex + .bbl-only paper
# ---------------------------------------------------------------------------

def test_fork_verify_generic_emits_empty_config_and_dir_root(tmp_path):
    script = forge.fork_verify_generic(tmp_path)
    text = script.read_text(encoding='utf-8')
    assert script.name == 'verify_generic.py'
    assert 'CHECKS_CONFIG: dict = {}' in text
    assert f"ROOT = Path({tmp_path.as_posix()!r})" in text


def test_generic_run_on_paper_tex_with_bbl_is_not_an_error(tmp_path):
    """Rename the root away from main.tex and ship only a .bbl: the audit
    must run (C4 applicable via the .bbl) rather than exit 2."""
    (tmp_path / 'paper.tex').write_text(CLEAN_TEX, encoding='utf-8')
    (tmp_path / 'paper.bbl').write_text(CLEAN_BBL, encoding='utf-8')
    script = forge.fork_verify_generic(tmp_path)
    proc = _run_script(script, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'Source: ' in proc.stdout and 'paper.tex' in proc.stdout
    # C4 ran against the .bbl, so it must NOT be reported not applicable.
    c4_lines = [ln for ln in proc.stdout.splitlines()
                if ln.strip().startswith('C4')]
    assert len(c4_lines) == 1, proc.stdout
    assert 'not applicable' not in c4_lines[0], c4_lines[0]


def test_generic_run_without_bib_reports_c4_not_applicable(tmp_path):
    """No .bib and no .bbl: C4 is not applicable, and the run is still an
    audit (exit 0) -- the reverse of the old `return 2` on missing refs.bib."""
    (tmp_path / 'paper.tex').write_text(CLEAN_TEX, encoding='utf-8')
    script = forge.fork_verify_generic(tmp_path)
    proc = _run_script(script, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    c4_lines = [ln for ln in proc.stdout.splitlines()
                if ln.strip().startswith('C4')]
    assert len(c4_lines) == 1, proc.stdout
    assert 'not applicable' in c4_lines[0], c4_lines[0]
    assert 'no .bib or .bbl' in c4_lines[0], c4_lines[0]


def test_generic_run_without_any_tex_is_exit_2(tmp_path):
    """A directory with no manuscript .tex is a genuine operational error,
    so "not applicable" cannot be used to hide a missing input."""
    script = forge.fork_verify_generic(tmp_path)
    proc = _run_script(script, tmp_path)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert 'no manuscript .tex found' in proc.stderr


# ---------------------------------------------------------------------------
# CLI wiring: --paper-dir without --paper
# ---------------------------------------------------------------------------

def test_cli_verify_needs_paper_or_paper_dir():
    assert cli.main(['verify']) == 2


def test_cli_verify_paper_dir_runs_generic(tmp_path):
    (tmp_path / 'paper.tex').write_text(CLEAN_TEX, encoding='utf-8')
    (tmp_path / 'paper.bbl').write_text(CLEAN_BBL, encoding='utf-8')
    rc = cli.main(['verify', '--paper-dir', str(tmp_path)])
    assert rc == 0, rc
    assert (tmp_path / 'verify_generic.py').exists()


def test_cli_verify_relative_paper_dir_is_not_resolved_twice(tmp_path, monkeypatch):
    """Regression: a relative --paper-dir was joined twice.

    The forked script is launched with cwd=target.parent, so passing the
    still-relative target made Python look for
    paper/paper/verify_generic.py. fork_* now resolves the directory first.
    """
    paper = tmp_path / 'paper'
    paper.mkdir()
    (paper / 'paper.tex').write_text(CLEAN_TEX, encoding='utf-8')
    (paper / 'paper.bbl').write_text(CLEAN_BBL, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    rc = cli.main(['verify', '--paper-dir', 'paper'])
    assert rc == 0, rc
    assert (paper / 'verify_generic.py').exists()


def test_cli_verify_paper_dir_dry_run_writes_nothing(tmp_path):
    rc = cli.main(['verify', '--paper-dir', str(tmp_path), '--dry-run'])
    assert rc == 0
    assert not (tmp_path / 'verify_generic.py').exists()


if __name__ == '__main__':
    sys.exit(__import__('pytest').main([__file__, '-v']))
