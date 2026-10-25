"""Tests for `tmaudit list` — the entry point that shows the built-in rulepacks.

Why this file exists: `tmaudit list` had no test coverage at all until 0.6.0,
and that is exactly why a rough edge survived in it. The five built-in
configurations describe the author's own manuscripts, so their `dir` values are
Windows paths from the machine they were written on. On a fresh install
anywhere else, `tmaudit list` printed five paths that resolve to nothing and
said nothing about it — a new user reasonably concludes the install is broken.

The fix under test is a labelling fix, not a hiding fix: missing paths are
still shown (hiding them would misrepresent what ships in the package) but they
are marked, and the output names the environment variable that repoints them
plus the flag that audits an arbitrary paper instead.

Both branches are covered: what happens when paths are missing, and what
happens when they exist (the author's own machine, and any machine where
TMAUDIT_RESEARCH_DIR has been pointed at a real tree).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tmaudit import cli
from tmaudit.configs.paper_configs import PAPER_CONFIGS as VERIFY_CONFIGS


def _run_list(capsys) -> str:
    """Call cmd_list and return everything it printed."""
    rc = cli.cmd_list(argparse.Namespace())
    captured = capsys.readouterr()
    assert rc == 0, 'cmd_list must exit 0 — it is a read-only listing'
    return captured.out


def test_list_names_every_built_in_paper(capsys):
    out = _run_list(capsys)
    for n in sorted(VERIFY_CONFIGS):
        assert f'  {n}' in out, f'paper {n} missing from list output'
    assert 'Known paper configurations:' in out


def test_all_missing_explains_the_override(monkeypatch, capsys):
    """Every configured path is missing -> every row is marked, plus setup advice.

    This is the fresh-install case, and the one the 0.6.0 fix was written for.
    """

    class _Missing:
        def is_dir(self):
            return False

    monkeypatch.setattr(cli, 'Path', lambda _p: _Missing())
    out = _run_list(capsys)

    assert f'{len(VERIFY_CONFIGS)} of {len(VERIFY_CONFIGS)}' in out, (
        'a summary count of missing paths should be printed'
    )
    assert out.count('(missing)') == len(VERIFY_CONFIGS), (
        'every row whose directory is absent must carry the (missing) mark'
    )
    assert 'TMAUDIT_RESEARCH_DIR' in out, (
        'when nothing resolves, output must name the environment variable that '
        'repoints the paths; otherwise the mark says something is wrong but '
        'not how to fix it'
    )
    assert '--paper-dir' in out, (
        'output must point at the flag that audits an arbitrary paper, which '
        'is the path a new user actually wants'
    )
    assert "author's own manuscripts" in out, (
        'output must say where these paths came from, so a missing directory '
        'reads as "not mine" rather than "download incomplete"'
    )


def test_partially_missing_drops_repeated_setup_advice(monkeypatch, capsys):
    """One path resolves, the rest do not -> marks stay, setup advice goes.

    Repeating "these are the author's manuscripts" when one of them is in fact
    pointing at a tree on this machine would be false, and repeating the export
    line to someone who already exported it is noise.
    """
    resolved = sorted(VERIFY_CONFIGS)[0]

    class _Path:
        def __init__(self, p):
            self._p = str(p)

        def is_dir(self):
            return self._p == str(VERIFY_CONFIGS[resolved]['dir'])

    monkeypatch.setattr(cli, 'Path', _Path)
    out = _run_list(capsys)

    assert out.count('(missing)') == len(VERIFY_CONFIGS) - 1, (
        'only the unresolved paths should be marked'
    )
    assert 'TMAUDIT_RESEARCH_DIR' not in out, (
        'do not repeat the export hint to a user who is already using it'
    )
    assert "author's own manuscripts" not in out, (
        'this claim is false once one path resolves locally'
    )
    assert 'did not resolve' in out, (
        'the partial case still needs a line explaining the remaining marks'
    )


def test_list_is_quiet_when_paths_exist(monkeypatch, capsys):
    """No missing path -> no warning block, no per-row marks."""

    class _Present:
        def is_dir(self):
            return True

    monkeypatch.setattr(cli, 'Path', lambda _p: _Present())
    out = _run_list(capsys)

    assert '(missing)' not in out, (
        'paths that exist must not be marked; a false alarm makes the mark '
        'meaningless'
    )
    assert 'TMAUDIT_RESEARCH_DIR' not in out, (
        'the override hint is only relevant when something is actually missing'
    )
    for n in sorted(VERIFY_CONFIGS):
        assert f'  {n}' in out, 'rows must still be printed when paths exist'


def test_list_never_hides_a_configured_paper(monkeypatch, capsys):
    """Missing paths are labelled, never dropped.

    Dropping them would misrepresent the package: the rulepacks really are
    bundled, and the row is the only place a user can learn a rulepack for
    paper N exists at all.
    """

    class _Missing:
        def is_dir(self):
            return False

    monkeypatch.setattr(cli, 'Path', lambda _p: _Missing())
    out = _run_list(capsys)

    for n, cfg in sorted(VERIFY_CONFIGS.items()):
        row = [ln for ln in out.splitlines() if ln.startswith(f'  {n}')]
        assert row, f'paper {n} was dropped from the listing'
        assert str(cfg['dir']) in row[0], (
            f'paper {n} row must still show the configured path'
        )


def test_list_reflects_real_filesystem_for_built_ins(capsys):
    """Against the real filesystem, the marks must agree with what is there.

    This is the assertion that would have caught the original rough edge on a
    non-Windows machine: it does not hardcode "missing" or "present", it
    derives the expectation from the filesystem and requires the output to
    match.
    """
    out = _run_list(capsys)
    expected_missing = sum(
        1 for cfg in VERIFY_CONFIGS.values() if not Path(cfg['dir']).is_dir()
    )
    assert out.count('(missing)') == expected_missing, (
        f'{expected_missing} configured path(s) do not exist here, but the '
        f'output marks a different number'
    )


def test_missing_mark_does_not_shadow_the_path(capsys):
    """The mark is a suffix on the path, so the path stays greppable."""
    out = _run_list(capsys)
    for line in out.splitlines():
        if line.endswith('(missing)'):
            assert '  (missing)' in line, (
                'mark should be separated from the path by whitespace, not '
                'glued onto it — users copy these paths'
            )
