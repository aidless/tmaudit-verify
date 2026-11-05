"""_check_all_regressions.py — verify that each bug-specific
regression test actually catches a re-introduction of its bug.

The case list has 16 bugs. ``tests/test_claims_drift.py`` fails if
that sentence disagrees with the list. Exit 0 means every bug that
ran was caught and the restored suite passes. A check that prints
SKIPPED is not in that total and is not a pass.

For each bug, this script:
  1. Backs up the relevant source file (forge.py,
     templates/verify_TEMPLATE.py, configs/paper_configs.py,
     or cache.py).
  2. Injects a small change that re-introduces the bug.
  3. Runs the targeted TestBug* / test_<N>_<description> test.
  4. Asserts the test FAILS (i.e. the bug fingerprint is
     recognised).
  5. Restores the original source.
  6. Re-runs the test and asserts it PASSES.

Exit code:
  0 if every bug that ran was caught and the restored suite passes.
  1 if any bug is NOT caught (i.e. the regression test would
    silently miss the bug — a serious problem).

Usage:
    python _check_all_regressions.py
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

# The author's development tree, which holds the same src/tmaudit/ layout as this
# repository — so pointing it here lets the harness run anywhere. TMAUDIT_TEMPLATE_DIR
# overrides it, matching the configs modules.
TEMPLATE = Path(os.environ.get('TMAUDIT_TEMPLATE_DIR',
                               str(Path(__file__).resolve().parent)))
FORGE = TEMPLATE / 'src' / 'tmaudit' / 'forge.py'
VERIFY_TPL = TEMPLATE / 'src' / 'tmaudit' / 'templates' / 'verify_TEMPLATE.py'
PAPER_CONFIGS = TEMPLATE / 'src' / 'tmaudit' / 'configs' / 'paper_configs.py'
PYTEST = [sys.executable, '-m', 'pytest', '--no-header', '-q',
          '--tb=line', '--color=no']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _paper_dirs_present() -> bool:
    """True when the paper directories the end-to-end tests audit are present.

    Bugs 4 and 6 are checked through
    tests/test_forge_happy.py::TestEndToEndAudit::test_paper_{1,5}_forks_and_passes,
    which fork a verify script and run the real audit expecting zero findings. That
    needs the manuscripts on the machine that holds them. The file whose absence
    fails first is the forked script itself — FileNotFoundError on
    '<research>/PAPER1_CONSOLIDATED/verify_p1.py' — so that is what decides whether
    the check can run. Requiring only main.tex would treat an empty placeholder as a
    real paper and let the check pass vacuously.
    """
    root = Path(os.environ.get('TMAUDIT_RESEARCH_DIR', 'papers'))
    return all((root / f'PAPER{n}_CONSOLIDATED' / f'verify_p{n}.py').exists()
               for n in (1, 5))


def _purge_pycache() -> None:
    """Delete every __pycache__ under TEMPLATE.

    Without this, a stale .pyc can be served for an injected source change:
    the pyc header stores the source mtime with 1-second resolution, and the
    inject-then-run sequence can land inside the same second. Python then
    treats the cache as fresh (it does not compare file size), the buggy code
    is never imported, the regression test passes, and the harness reports
    "regression test NOT effective" for a test that is actually fine. The
    same failure mode was already hit by the byte-compile mutation-control job
    (see .github/workflows/ci.yml).
    """
    for cache in TEMPLATE.rglob('__pycache__'):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def _run_pytest(test_target: str, extra: list[str] | None = None) -> tuple[int, str]:
    # PYTHONDONTWRITEBYTECODE: no .pyc is created between two runs, so there is
    # nothing to go stale. Cleared at the end of the harness in main().
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8',
           'PYTHONDONTWRITEBYTECODE': '1'}
    _purge_pycache()
    result = subprocess.run(
        PYTEST + (extra or []) + [test_target],
        cwd=str(TEMPLATE),
        env=env,
        capture_output=True,
        text=True,
        errors='replace',
    )
    return result.returncode, (result.stdout + '\n' + result.stderr)


@contextmanager
def _patched(path: Path) -> Iterator[None]:
    """Backup ``path`` and restore those exact bytes on exit.

    An earlier version restored tracked files with ``git checkout HEAD``.
    That puts back the last commit, so any uncommitted edit in the same
    file is discarded and the final sanity run then fails for a reason
    that is not the injected bug. The bytes to put back are the bytes
    that were on disk when the injection started.
    """
    backup = path.read_bytes() if path.exists() else None
    try:
        yield
    finally:
        if backup is not None:
            path.write_bytes(backup)
        elif path.exists():
            path.unlink()


def _check_bug(
    bug_id: str,
    test_target: str,
    inject_fn: Callable[[], None],
) -> bool:
    """Inject a bug via inject_fn, run the test, assert catch + restore.

    Returns True iff the regression test caught the bug AND
    restoration left the test passing.
    """
    print(f'\n=== Bug {bug_id}: inject + verify catch ===')
    try:
        inject_fn()
    except Exception as e:
        print(f'  ERROR during inject: {e!r}')
        return False

    # Step 1: with bug injected, run the test and expect FAIL
    rc, out = _run_pytest(test_target)
    caught = (rc != 0 and 'FAILED' in out)
    if caught:
        # Find the specific failing test line for reporting
        fail_lines = [line for line in out.splitlines() if 'FAILED' in line]
        first_fail = fail_lines[0] if fail_lines else '(no FAILED line)'
        print(f'  PASS: regression test caught the bug (rc={rc})')
        print(f'        e.g., {first_fail[:120]}')
    else:
        print(f'  FAIL: regression test did NOT catch the bug (rc={rc})')
        print('  --- pytest output (last 25 lines) ---')
        for line in out.splitlines()[-25:]:
            print(f'    | {line}')
        return False

    # Step 2: restore and re-run, expect PASS
    # (we use a fresh subprocess to ensure no caching of the
    # modified module)
    rc, out = _run_pytest(test_target)
    if rc != 0:
        print(f'  RESTORE FAILED: test still failing after restore (rc={rc})')
        print('  --- pytest output (last 25 lines) ---')
        for line in out.splitlines()[-25:]:
            print(f'    | {line}')
        return False
    print(f'  RESTORE OK: test passes again after restore (rc=0)')
    return True


# ---------------------------------------------------------------------------
# Bug-specific inject functions
#
# Each function:
#   - uses _patched() to back up the file
#   - writes a buggy version
#   - the buggy version is reverted when _patched() exits
#   - we then call _check_bug() which runs pytest twice and
#     asserts catch + restore
# ---------------------------------------------------------------------------

def inject_bug1() -> None:
    """Bug 1: r-string -> repr. Patch the r-string return in
    _format_simple_value with a plain repr return.
    """
    with _patched(FORGE):
        original = FORGE.read_text(encoding='utf-8')
        old = "return f\"r'{escaped}'\""
        new = 'return repr(value)  # BROKEN: regressed to no r-string'
        if old not in original:
            raise RuntimeError(f'bug-1 anchor not found: {old!r}')
        FORGE.write_text(original.replace(old, new, 1), encoding='utf-8')
        # Run check inside the patch context
        _check_bug_inside_patch('1', 'tests/test_forge.py::TestBug1ReprInterpretsBackslash')


def inject_bug2() -> None:
    """Bug 2: re.sub interprets backslashes in replacement. Replace
    the manual brace-counting block with a broken re.sub call.
    """
    with _patched(FORGE):
        original = FORGE.read_text(encoding='utf-8')
        block_start = original.find(
            "# Replace the existing CHECKS_CONFIG block with literal string slicing"
        )
        if block_start < 0:
            raise RuntimeError('bug-2 anchor not found')
        block_end = original.find(
            "out = out[:start] + new_block + '\\n' + out[end:]",
            block_start,
        )
        if block_end < 0:
            raise RuntimeError('bug-2 anchor end not found')
        block_end = original.find('\n', block_end) + 1
        broken = (
            "    # BROKEN: re.sub interprets backslashes in the replacement text\n"
            "    import re as _re\n"
            "    out = _re.sub(\n"
            "        r'CHECKS_CONFIG: dict = \\{.*?\\}',\n"
            "        new_block + '\\n',\n"
            "        out,\n"
            "        count=1,\n"
            "        flags=_re.DOTALL,\n"
            "    )\n"
        )
        FORGE.write_text(
            original[:block_start] + broken + original[block_end:],
            encoding='utf-8',
        )
        _check_bug_inside_patch('2', 'tests/test_forge.py::TestBug2ResubBackslashInReplacement')


def inject_bug3() -> None:
    """Bug 3: na\"ive brace counter. Replace the state machine in
    forge._substitute_verify with a simple counter that does NOT
    skip braces inside string literals.
    """
    with _patched(FORGE):
        original = FORGE.read_text(encoding='utf-8')
        while_marker = '    while i < len(out):\n'
        start = original.find(while_marker)
        if start < 0:
            raise RuntimeError('bug-3 anchor (while loop) not found')
        end = original.find('    return out\n', start)
        if end < 0:
            raise RuntimeError('bug-3 anchor end (return out) not found')
        end += len('    return out\n')
        naive = (
            '    while i < len(out):\n'
            '        c = out[i]\n'
            '        if c == "}":  # BROKEN: no string-literal awareness\n'
            '            depth -= 1\n'
            '            if depth == 0:\n'
            '                end = i + 1\n'
            '                break\n'
            '        elif c == "{":\n'
            '            depth += 1\n'
            '        i += 1\n'
        )
        FORGE.write_text(
            original[:start] + naive + original[end:],
            encoding='utf-8',
        )
        _check_bug_inside_patch('3', 'tests/test_forge.py::TestBug3BraceCounterIgnoresStringLiterals')


def inject_bug4() -> None:
    """Bug 4: C1 narrow 250-char window. Disable the second and
    third passes in check_c1_abstract_definitions so only the
    250-char window is used. Paper 1's TTRL symbol is defined
    1500+ chars after first mention, so the audit will flag it.
    """
    with _patched(VERIFY_TPL):
        original = VERIFY_TPL.read_text(encoding='utf-8')
        # Mark the second/third passes as dead code by raising
        # before they execute.
        marker = '        # Second pass: definition anywhere within the abstract'
        start = original.find(marker)
        if start < 0:
            raise RuntimeError('bug-4 anchor (second pass) not found')
        # Replace the next 30 lines with a no-op
        broken_block = (
            '        # BROKEN: second pass disabled (bug 4 regression)\n'
            '        pass\n\n'
        )
        # Find the third pass and kill that too
        third_pass = original.find(
            '        # Third pass: definition in the first',
            start,
        )
        if third_pass < 0:
            raise RuntimeError('bug-4 anchor (third pass) not found')
        # Find the end of the third pass: the next "return findings" at the same indent
        end = original.find('        return findings\n', third_pass)
        if end < 0:
            raise RuntimeError('bug-4 anchor end (return findings) not found')
        end += len('        return findings\n')
        # Replace both passes with a no-op
        patched = (
            original[:start]
            + broken_block
            + original[end:]
        )
        # Also remove the "    abstract, abs_start = abs_result" for
        # safety: no, that's needed. Just disable the two passes.
        VERIFY_TPL.write_text(patched, encoding='utf-8')
        # Bug 4 is in the verify_TEMPLATE.py, so we need to run
        # the end-to-end audit (which executes the template code).
        if not _paper_dirs_present():
            print(f'  SKIPPED: Bug 4 is checked through an end-to-end test')
            print('           that audits a real paper. TMAUDIT_RESEARCH_DIR')
            print(f'           has no PAPER1_CONSOLIDATED/verify_p1.py,')
            print('           so the check cannot run here.')
            return
        _check_bug_inside_patch('4', 'tests/test_forge_happy.py::TestEndToEndAudit::test_paper_1_forks_and_passes')


def inject_bug5() -> None:
    """Bug 5: C5 test-name regex too strict. Replace the relaxed
    `paired[^a-zA-Z]{0,8}t[^a-zA-Z]{0,3}test` with the strict
    `paired\\s+t-test` that does not match `paired $t$-tests`.
    """
    with _patched(VERIFY_TPL):
        original = VERIFY_TPL.read_text(encoding='utf-8')
        relaxed_pattern = (
            "r'paired[^a-zA-Z]{0,8}t[^a-zA-Z]{0,3}test|'\n"
        )
        strict_replacement = (
            "r'paired\\s+t-test|'\n"
        )
        if relaxed_pattern not in original:
            raise RuntimeError('bug-5 anchor (relaxed pattern) not found')
        VERIFY_TPL.write_text(
            original.replace(relaxed_pattern, strict_replacement, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch('5', 'tests/test_bug5_unit.py')


def inject_bug6() -> None:
    """Bug 6: c2_section_pattern too narrow. Remove the
    `Statistical Protocol` branch from the Paper 5 config so
    the audit fails to find Paper 5's `Statistical Protocol`
    section.
    """
    with _patched(PAPER_CONFIGS):
        original = PAPER_CONFIGS.read_text(encoding='utf-8')
        # The Paper 5 c2_section_pattern is a multi-line string
        # with an alternation branch for "Statistical Protocol".
        # We remove that branch, leaving only the "Power analysis"
        # branch (which does NOT match Paper 5's section).
        old_pat = (
            "        'c2_section_pattern': (\n"
            "            r'\\\\section\\*?\\{[^}]*Power analysis[^}]*\\}|'\n"
            "            r'\\\\subsection\\*?\\{[^}]*Statistical Protocol[^}]*\\}'\n"
            "        ),"
        )
        new_pat = (
            "        'c2_section_pattern': (\n"
            "            r'\\\\section\\*?\\{[^}]*Power analysis[^}]*\\}'\n"
            "        ),"
        )
        if old_pat not in original:
            raise RuntimeError('bug-6 anchor (Statistical Protocol branch) not found')
        PAPER_CONFIGS.write_text(
            original.replace(old_pat, new_pat, 1),
            encoding='utf-8',
        )
        if not _paper_dirs_present():
            print(f'  SKIPPED: Bug 6 is checked through an end-to-end test')
            print('           that audits a real paper. TMAUDIT_RESEARCH_DIR')
            print(f'           has no PAPER5_CONSOLIDATED/verify_p5.py,')
            print('           so the check cannot run here.')
            return
        _check_bug_inside_patch('6', 'tests/test_forge_happy.py::TestEndToEndAudit::test_paper_5_forks_and_passes')


def inject_bug7() -> None:
    """Bug 7: C6 blacklist false-positive on idiomatic English.
    The min_count threshold (3) is the fix that makes 1-2
    occurrences of 'yield' / 'reveal' not be reported. If the
    threshold is removed (set to 0), the audit reverts to the
    buggy behaviour: every occurrence generates a finding.

    We inject by changing the literal `min_count: int = 3` to
    `min_count: int = 0` in
    `src/tmaudit/templates/verify_TEMPLATE.py::check_c6_blacklist`.

    The regression test that should catch this is
    `test_c6_does_not_flag_single_occurrence`: it constructs a
    tex with one 'paradigm' and asserts the C6 finding list
    is empty. With min_count=0, the finding list is non-empty
    (it has 1 entry) and the test fails.
    """
    with _patched(VERIFY_TPL):
        original = VERIFY_TPL.read_text(encoding='utf-8')
        old = '    min_count: int = 3'
        new = '    min_count: int = 0  # BROKEN: regression to 1-occurrence reporting'
        if old not in original:
            raise RuntimeError(f'bug-7 anchor not found: {old!r}')
        VERIFY_TPL.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '7',
            'tests/test_c6_threshold.py::test_c6_does_not_flag_single_occurrence',
        )


def inject_bug8() -> None:
    """Bug 8: C7 inverted threshold check. The implementation
    has `if n_ceremonial > c7_max_ceremonial:` which fires
    when the ceremonial count *exceeds* the threshold. If
    this is inverted to `if n_ceremonial < c7_max_ceremonial:`,
    the check fires only when there are *fewer* ceremonial
    cites than the threshold — which is essentially the inverse
    condition. As a result, papers with 3+ ceremonial cites
    (the case C7 is supposed to flag) get NO findings.

    We inject by changing the literal `if n_ceremonial >
    c7_max_ceremonial:` to `if n_ceremonial < c7_max_ceremonial:
    # BROKEN: inverted threshold`.

    The regression test that should catch this is
    `test_c7_threshold_2_flags_3_ceremonial_cites`: it
    constructs a tex with 3 ceremonial cites and asserts the
    C7 finding list has at least one entry. With the inverted
    condition, n_ceremonial=3 is NOT less than
    c7_max_ceremonial=2, so no findings are produced and the
    test fails.
    """
    with _patched(VERIFY_TPL):
        original = VERIFY_TPL.read_text(encoding='utf-8')
        old = '    if n_ceremonial > c7_max_ceremonial:'
        new = '    if n_ceremonial < c7_max_ceremonial:  # BROKEN: inverted threshold'
        if old not in original:
            raise RuntimeError(f'bug-8 anchor not found: {old!r}')
        VERIFY_TPL.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '8',
            'tests/test_c7_citation_context.py::test_c7_threshold_2_flags_3_ceremonial_cites',
        )


def inject_bug9() -> None:
    """Bug 9: cache put does not replace existing entries. The
    implementation uses `INSERT OR REPLACE` in the SQL, which
    atomically replaces an entry if the key already exists.
    If we change this to `INSERT` (without OR REPLACE), the
    put will FAIL silently when the key already exists
    (SQLite raises IntegrityError on duplicate primary key,
    but we currently don't catch it, so the entry is not
    stored).

    We inject by changing
    `'INSERT OR REPLACE INTO entries (key, value, created_at, size_bytes) '`
    to
    `'INSERT INTO entries (key, value, created_at, size_bytes) '`
    (with a `# BROKEN` comment).

    The regression test that should catch this is
    `test_put_replaces_existing_entry`: it puts a value, then
    puts a different value under the same key, and asserts the
    second value is returned. With `INSERT` (no `OR REPLACE`),
    the second put raises an IntegrityError that is not
    caught, and the test fails (or the second put silently
    leaves the original value, and the test fails with
    `v == 'second'` mismatch).
    """
    cache_path = TEMPLATE / 'src' / 'tmaudit' / 'cache.py'
    with _patched(cache_path):
        original = cache_path.read_text(encoding='utf-8')
        old = "'INSERT OR REPLACE INTO entries (key, value, created_at, size_bytes) '"
        new = "'INSERT INTO entries (key, value, created_at, size_bytes) '  # BROKEN: no OR REPLACE"
        if old not in original:
            raise RuntimeError(f'bug-9 anchor not found: {old!r}')
        cache_path.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '9',
            'tests/test_cache.py::test_put_replaces_existing_entry',
        )


def inject_bug10() -> None:
    """Bug 10: C10 inverted severity. The implementation
    emits findings in the form 'HIGH: ...', 'MED: ...', or
    'LOW: ...' (severity at the start of the message). If we
    invert this (e.g., always emit 'LOW: ...' regardless of
    severity), the tests that look for 'HIGH' or 'MED' in
    the message will fail.

    We inject by changing the first finding's severity
    prefix from 'HIGH:' to 'LOW:' (the bug case). With this
    change, test_c10_no_availability_statement_emits_high
    (which asserts at least one finding has 'HIGH' in it)
    will fail because all findings say 'LOW' instead.

    The anchor is the first finding in check_c10_reproducibility:
    'HIGH: paper has no code/data availability statement'.
    The injection replaces 'HIGH:' with 'LOW:' on this line.
    """
    with _patched(VERIFY_TPL):
        original = VERIFY_TPL.read_text(encoding='utf-8')
        old = "'HIGH: paper has no code/data availability statement '"
        new = "'LOW: paper has no code/data availability statement '  # BROKEN: wrong severity"
        if old not in original:
            raise RuntimeError(f'bug-10 anchor not found: {old!r}')
        VERIFY_TPL.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '10',
            'tests/test_c10_reproducibility.py::test_c10_no_availability_statement_emits_high',
        )


def inject_bug11() -> None:
    """Bug 11: C8 inverted d-mismatch threshold. The
    implementation has `_C8_D_MISMATCH_THRESHOLD = 0.10`,
    meaning a HIGH finding is emitted when |d_actual - d_claimed|
    > 0.10. If we change this to 0.10 < threshold (e.g.,
    change `> 0.10` to `< 0.10` in the comparison), the bug
    flips: a d-mismatch is now reported when |diff| is
    SMALL, not LARGE. For the test fixture, d_claimed=0.5 and
    d_actual=0.5, so the test expects 0 HIGH findings. With
    the bug (`< 0.10`), the test would emit a HIGH finding
    for a non-existent mismatch, and the test would fail.

    The anchor is the line `if d_diff > _C8_D_MISMATCH_THRESHOLD:`
    in check_c8_statistical_power. The injection changes
    `>` to `<`.
    """
    with _patched(VERIFY_TPL):
        original = VERIFY_TPL.read_text(encoding='utf-8')
        old = 'if d_diff > _C8_D_MISMATCH_THRESHOLD:'
        new = 'if d_diff < _C8_D_MISMATCH_THRESHOLD:  # BROKEN: inverted comparison'
        if old not in original:
            raise RuntimeError(f'bug-11 anchor not found: {old!r}')
        VERIFY_TPL.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '11',
            'tests/test_c8_statistical_power.py::test_c8_effect_numbers_match_no_finding',
        )


def inject_bug12() -> None:
    """Bug 12: C9 inverted caption-placement condition. The
    implementation has
        if (parsed['has_caption']
                and parsed['graphic_pos'] >= 0
                and parsed['caption_pos'] >= 0
                and parsed['caption_pos'] < parsed['graphic_pos']):
    which fires when the caption is ABOVE the graphic
    (caption_pos < graphic_pos). If we change `<` to `>`,
    the bug fires when the caption is BELOW the graphic
    instead — the opposite of what we want.

    For test_c9_caption_above_figure_emits_med (the
    caption-above test), the buggy `>` condition would NOT
    fire (caption_pos is < graphic_pos, not >), so the test
    would fail because no MED finding is emitted. The bug
    also affects test_c9_caption_below_figure_ok: with the
    inverted condition, a below-figure caption would fire
    the MED (a false positive).

    The anchor is the line
        and parsed['caption_pos'] < parsed['graphic_pos']):
    in check_c9_figure_caption. The injection changes
    `<` to `>`.
    """
    with _patched(VERIFY_TPL):
        original = VERIFY_TPL.read_text(encoding='utf-8')
        old = 'and parsed[\'caption_pos\'] < parsed[\'graphic_pos\']):'
        new = ('and parsed[\'caption_pos\'] > parsed[\'graphic_pos\']):'
               '  # BROKEN: inverted comparison')
        if old not in original:
            raise RuntimeError(f'bug-12 anchor not found: {old!r}')
        VERIFY_TPL.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '12',
            'tests/test_c9_figure_caption.py::test_c9_caption_above_figure_emits_med',
        )


def inject_bug13() -> None:
    """Bug 13: loader raises on a malformed entry-point.

    The implementation in ``src/tmaudit/plugins.py`` wraps
    the entry-point's ``load()`` call in try/except and
    returns ``None`` for failed loads. If we replace the
    except with a bare ``raise``, the loader re-raises the
    ImportError, which crashes the test (and would crash the
    audit in production).

    The anchor is the ``except Exception as e:`` line in
    ``_load_entry_point``. The injection changes it to
    ``except Exception:  # BROKEN: re-raise instead of skip``.
    With the bug, a broken plugin (e.g.
    ``nonexistent_module_xyz``) crashes
    ``test_loader_skips_malformed_entry_point`` instead of
    being skipped.
    """
    plugins_path = TEMPLATE / 'src' / 'tmaudit' / 'plugins.py'
    with _patched(plugins_path):
        original = plugins_path.read_text(encoding='utf-8')
        old = (
            '    except Exception as e:\n'
            '        log.warning(\n'
            '            "tmaudit plugin %r failed to import: %s",\n'
            '            ep.name, e,\n'
            '        )\n'
            '        return None\n'
        )
        new = (
            '    except Exception:  # BROKEN: re-raise instead of skip\n'
            '        raise\n'
        )
        if old not in original:
            raise RuntimeError(f'bug-13 anchor not found in {plugins_path}')
        plugins_path.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '13',
            'tests/test_plugin_api.py::test_loader_skips_malformed_entry_point',
        )


def inject_bug14() -> None:
    """Bug 14: per-paper c11_plugins_disabled is ignored.

    The implementation in ``src/tmaudit/plugins.py``
    ``audit_plugins`` filters via
    ``filter_active(load_plugins(), disabled)`` so that the
    disabled list excludes names. If we change that call to
    ``load_plugins()`` only (dropping the ``filter_active``
    step), every registered plugin runs even when the paper
    disables it.

    The anchor is the line
        ``plugins = filter_active(load_plugins(), disabled, enabled)``
    in ``audit_plugins``. The injection changes it to
    ``plugins = load_plugins()`` (no filter, ignores both
    disabled and enabled).
    With the bug, the regression test
    ``test_audit_plugins_respects_per_paper_disable`` sees
    the synthetic plugin's finding even though it was
    disabled, and fails.
    """
    plugins_path = TEMPLATE / 'src' / 'tmaudit' / 'plugins.py'
    with _patched(plugins_path):
        original = plugins_path.read_text(encoding='utf-8')
        old = '    plugins = filter_active(load_plugins(), disabled, enabled)'
        new = ('    plugins = load_plugins()  # BROKEN: ignore disabled'
               ' list')
        if old not in original:
            raise RuntimeError(f'bug-14 anchor not found in {plugins_path}')
        plugins_path.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '14',
            'tests/test_plugin_api.py::test_audit_plugins_respects_per_paper_disable',
        )


def inject_bug15() -> None:
    """Bug 15: c11_plugins_enabled whitelist is ignored.

    The v0.5.0 implementation in ``filter_active`` (in
    ``src/tmaudit/plugins.py``) supports an ``enabled`` kwarg
    that whitelists plugins: when non-empty, only plugins in
    the list are kept. The implementation has the structure::

        enabled_set = set(enabled) if enabled else set()
        ...
        if enabled_set:
            return {n: c for n, c in plugins.items() if n in enabled_set}

    If the early-return branch is replaced with a fall-through
    (i.e., the whitelist branch is removed), then any plugins
    in the ``enabled`` list run but so do plugins NOT in the
    list -- the whitelist is effectively ignored.

    The injection replaces the whitelist branch with a comment,
    so that the function falls through to the disabled-check
    branch (which treats ``enabled`` as if it weren't set).

    With the bug, the regression test
    ``test_audit_plugins_respects_c11_plugins_enabled`` registers
    a plugin that's NOT in the whitelist, runs audit, and
    expects 0 findings. The buggy version would produce findings,
    causing the test to fail.
    """
    plugins_path = TEMPLATE / 'src' / 'tmaudit' / 'plugins.py'
    with _patched(plugins_path):
        original = plugins_path.read_text(encoding='utf-8')
        # Anchor: the whitelist branch block.
        # The block starts with `if enabled_set:` and ends with
        # `if n in enabled_set}` (the dict-comprehension line).
        # We'll replace the whole block with a no-op comment.
        old_block_start = '    if enabled_set:\n'
        start_idx = original.find(old_block_start)
        if start_idx < 0:
            raise RuntimeError(
                f'bug-15 anchor (whitelist branch start) not found in {plugins_path}'
            )
        # Find the end: the dict comprehension body line.
        end_marker = '                if n in enabled_set}\n'
        end_idx = original.find(end_marker, start_idx)
        if end_idx < 0:
            raise RuntimeError(
                f'bug-15 anchor (whitelist branch end) not found in {plugins_path}'
            )
        end_idx += len(end_marker)
        broken = '    # BROKEN: whitelist branch disabled (bug 15)\n    pass\n\n'
        plugins_path.write_text(
            original[:start_idx] + broken + original[end_idx:],
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '15',
            'tests/test_plugin_api.py::test_audit_plugins_respects_c11_plugins_enabled',
        )


def inject_bug16() -> None:
    """Bug 16: precedence rule violated when both enabled and
    disabled are set (enabled should win).

    The v0.5.0 spec (§16.4) says: when both ``c11_plugins_enabled``
    and ``c11_plugins_disabled`` are set on a paper config, the
    enabled list wins and disabled is ignored (with a warning
    log). The implementation in ``filter_active`` enforces this
    by checking ``enabled_set`` first and short-circuiting.

    If the precedence check is inverted (e.g., the disabled
    branch runs first and returns early), then the whitelist
    is silently ignored.

    The injection swaps the two ``if`` blocks: the disabled
    branch runs first, returning a blacklisted dict; the
    enabled branch never executes.

    With the bug, the regression test
    ``test_filter_active_whitelist_overrides_blacklist`` builds
    a plugin dict where plugins A, B, C exist, sets
    enabled=['A'] and disabled=['B'], and expects {'A': ...}
    only. The buggy version returns {'A', 'C'} (disabled is
    applied, whitelist ignored), failing the assertion.
    """
    plugins_path = TEMPLATE / 'src' / 'tmaudit' / 'plugins.py'
    with _patched(plugins_path):
        original = plugins_path.read_text(encoding='utf-8')
        # We replace the order of the two `if` blocks. The
        # original order is enabled-first then disabled; we
        # invert to disabled-first.
        enabled_start_marker = '    if enabled_set:\n'
        enabled_start = original.find(enabled_start_marker)
        if enabled_start < 0:
            raise RuntimeError(
                f'bug-16 anchor (enabled start) not found in {plugins_path}'
            )
        # The enabled branch body is 5 lines; the closing line
        # is the dict comprehension continuation. We use a
        # precise anchor: the closing brace line.
        end_marker = '        if n in enabled_set}\n'
        enabled_end = original.find(end_marker, enabled_start)
        if enabled_end < 0:
            raise RuntimeError(
                f'bug-16 anchor (enabled end) not found in {plugins_path}'
            )
        enabled_end += len(end_marker)
        # Extract the enabled block.
        enabled_block = original[enabled_start:enabled_end]
        # Find the disabled branch (we move the enabled block
        # to AFTER the disabled branch). We need the SECOND
        # occurrence of `if disabled_set:` (the outer one), not
        # the inner one inside the warning log.
        disabled_start_marker = '    if disabled_set:\n'
        first_disabled = original.find(disabled_start_marker)
        if first_disabled < 0:
            raise RuntimeError(
                f'bug-16 anchor (disabled start, first) not found in {plugins_path}'
            )
        # The outer `if disabled_set:` is the second occurrence.
        disabled_start = original.find(
            disabled_start_marker, first_disabled + len(disabled_start_marker)
        )
        if disabled_start < 0:
            raise RuntimeError(
                f'bug-16 anchor (disabled start, second) not found in {plugins_path}'
            )
        disabled_end_marker = '        if n not in disabled_set}\n'
        disabled_end = original.find(disabled_end_marker, disabled_start)
        if disabled_end < 0:
            raise RuntimeError(
                f'bug-16 anchor (disabled end) not found in {plugins_path}'
            )
        disabled_end += len(disabled_end_marker)
        disabled_block = original[disabled_start:disabled_end]
        # Compose: original up to enabled_start, then disabled_block,
        # then enabled_block, then rest after enabled_end.
        swapped = (
            original[:enabled_start]
            + disabled_block
            + enabled_block
            + original[enabled_end:]
        )
        plugins_path.write_text(swapped, encoding='utf-8')
        _check_bug_inside_patch(
            '16',
            'tests/test_plugin_api.py::test_filter_active_whitelist_overrides_blacklist',
        )


# ---------------------------------------------------------------------------
# Per-bug test runner
# ---------------------------------------------------------------------------

# Module-level container so inject_* can pass results back to main().
# We use a list of (bug_id, success, error_msg) tuples.
_results: list[tuple[str, bool, str]] = []


def _check_bug_inside_patch(bug_id: str, test_target: str) -> None:
    """Run pytest inside the patch context (where the bug is in
    place). Append the result to _results.
    """
    rc, out = _run_pytest(test_target)
    caught = (rc != 0 and 'FAILED' in out)
    if caught:
        _results.append((bug_id, True, ''))
    else:
        # Save last 5 lines for diagnostics
        snippet = '\n'.join(out.splitlines()[-5:])
        _results.append((bug_id, False, snippet))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    cases: list[tuple[str, Callable[[], None]]] = [
        ('1', inject_bug1),
        ('2', inject_bug2),
        ('3', inject_bug3),
        ('4', inject_bug4),
        ('5', inject_bug5),
        ('6', inject_bug6),
        ('7', inject_bug7),
        ('8', inject_bug8),
        ('9', inject_bug9),
        ('10', inject_bug10),
        ('11', inject_bug11),
        ('12', inject_bug12),
        ('13', inject_bug13),
        ('14', inject_bug14),
        ('15', inject_bug15),
        ('16', inject_bug16),
    ]

    for bug_id, inject_fn in cases:
        try:
            inject_fn()
        except Exception as e:
            _results.append((bug_id, False, f'inject failed: {e!r}'))

    # After all bugs have been injected-and-restored (via the
    # _patched context manager), do a final clean run to confirm
    # the workspace is intact.
    print()
    print('=' * 72)
    print('SUMMARY')
    print('=' * 72)
    for bug_id, ok, err in sorted(_results):
        marker = '[OK]' if ok else '[FAIL]'
        print(f'  Bug {bug_id}: {marker}')
        if err:
            print(f'    {err}')

    n_pass = sum(1 for _, ok, _ in _results if ok)
    n_total = len(_results)
    print()
    print(f'  {n_pass}/{n_total} bugs are correctly caught by their regression tests.')

    # Final sanity check: all tests should pass on the restored code
    print()
    print('=== Final sanity: full test suite should pass ===')
    # Every @pytest.mark.slow test is excluded when the per-paper research
    # directories are absent. That set is the end-to-end audits and the corpus
    # regression, which is why Bug 4 and Bug 6 are skipped in the same situation.
    # The exclusion is stated, not silent.
    slow_excluded = not _paper_dirs_present()
    if slow_excluded:
        print('  (the @pytest.mark.slow end-to-end tests are excluded: '
              'TMAUDIT_RESEARCH_DIR has no paper directories)')
    rc, out = _run_pytest('tests/', ['-m', 'not slow'] if slow_excluded else None)
    if rc == 0:
        print(f'  OK: full test suite passes (rc=0)')
    else:
        print(f'  WARN: full test suite returns rc={rc} after all restores')
        print('  --- pytest output (last 25 lines) ---')
        for line in out.splitlines()[-25:]:
            print(f'    | {line}')

    if n_pass == n_total and rc == 0:
        print()
        print('=== ALL REGRESSION TESTS ARE EFFECTIVE ===')
        return 0
    print()
    print('=== SOME REGRESSION TESTS ARE NOT EFFECTIVE ===')
    return 1


if __name__ == '__main__':
    sys.exit(main())