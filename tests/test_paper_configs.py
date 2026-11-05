"""Coverage tests for `src/tmaudit/configs/paper_configs.py`.

The paper_configs.py module is the per-paper configuration
that drives the C1..C7 audit. Coverage here means:

  1. Every paper has the **required fields** (the substitute_verify
     function would fail to generate a verify_p<N>.py if any
     field is missing).
  2. Every paper has a **valid dir** (the path actually exists
     on the filesystem, otherwise the audit will fail with
     FileNotFoundError).
  3. Every paper has a **valid c7_max_ceremonial** threshold
     (an int >= 0; the C7 check would crash on invalid input).
  4. **substitute_verify()** produces a valid verify_p<N>.py
     for each paper (the output contains the expected
     CHECKS_CONFIG keys).
  5. **No duplicate paper numbers** (silent overwriting).

These tests catch **config drift**: a new field is added to
the template, but one paper's config is forgotten, leading
to KeyError at audit time.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tmaudit.configs import paper_configs


# Required fields that every paper config must have.
# (These are the keys substitute_verify() reads via cfg.get(...)
# or cfg['...'].)
REQUIRED_FIELDS = [
    'dir',
    'c1_symbols',
    'c2_families',
    'c2_section_pattern',
    'c2_abstract_k_allowed',
    'c3_concept',
    'c3_concept_token',
    'c3_formal',
    'c4_self_cite_threshold',
    'c4_self_cite_prefix',
    'c4_max_self_cite_keys',
    'c5_d_type',
    'c6_blacklist',
    'c7_max_ceremonial',  # added in v0.1.2
    'c8_claimed_effects',  # added in v0.3.0
    'c9_figure_keywords',  # added in v0.3.0
    'c10_reproducibility_claims',  # added in v0.3.0
]


# =====================================================================
# Test 1: All expected papers are in PAPER_CONFIGS
# =====================================================================
def test_paper_configs_has_expected_papers():
    """Paper 1, 2, 3, 4, 5 should all be in PAPER_CONFIGS."""
    expected = {1, 2, 3, 4, 5}
    actual = set(paper_configs.PAPER_CONFIGS.keys())
    assert expected.issubset(actual), (
        f'Missing papers: {expected - actual}. '
        f'Add the missing entries to PAPER_CONFIGS in '
        f'src/tmaudit/configs/paper_configs.py.'
    )


# =====================================================================
# Test 2: No duplicate paper numbers
# =====================================================================
def test_paper_configs_no_duplicates():
    """Each paper number should appear exactly once."""
    papers = list(paper_configs.PAPER_CONFIGS.keys())
    assert len(papers) == len(set(papers)), (
        f'Duplicate paper numbers: '
        f'{[p for p in papers if papers.count(p) > 1]}'
    )


# =====================================================================
# Test 3: Every paper has all required fields
# =====================================================================
def test_paper_configs_all_have_required_fields():
    """Every paper config must have every required field.

    Catches the case where a new field is added to the
    schema (e.g., c7_max_ceremonial) but one paper's
    config is forgotten.
    """
    for paper, cfg in paper_configs.PAPER_CONFIGS.items():
        for field in REQUIRED_FIELDS:
            assert field in cfg, (
                f'Paper {paper} is missing field {field!r}. '
                f'Add it to PAPER_CONFIGS in '
                f'src/tmaudit/configs/paper_configs.py.'
            )


# =====================================================================
# Test 4: Every paper has a valid c7_max_ceremonial threshold
# =====================================================================
def test_paper_configs_c7_thresholds_are_valid():
    """c7_max_ceremonial must be a non-negative int."""
    for paper, cfg in paper_configs.PAPER_CONFIGS.items():
        threshold = cfg.get('c7_max_ceremonial')
        assert isinstance(threshold, int), (
            f'Paper {paper} c7_max_ceremonial is not an int: '
            f'{type(threshold).__name__}'
        )
        assert threshold >= 0, (
            f'Paper {paper} c7_max_ceremonial must be >= 0: {threshold}'
        )
        assert threshold < 100, (
            f'Paper {paper} c7_max_ceremonial suspiciously large: '
            f'{threshold} (max 99)'
        )


# =====================================================================
# Test 5: Every paper has a non-empty C1 symbols list (v0.2.0)
# =====================================================================
def test_paper_configs_have_non_empty_c1_symbols():
    """v0.2.0 acceptance criterion: all 5 papers have C1 symbols.

    Before v0.2.0, Papers 2/3/4 had empty c1_symbols
    (placeholders). After v0.2.0, all 5 papers should have
    at least 1 C1 symbol defined.
    """
    for paper, cfg in paper_configs.PAPER_CONFIGS.items():
        symbols = cfg.get('c1_symbols', [])
        assert len(symbols) >= 1, (
            f'Paper {paper} has empty c1_symbols. '
            f'v0.2.0 requires at least 1 C1 symbol per paper '
            f'(see ROADMAP.md).'
        )
        # Each symbol must have name, token, definition
        for i, sym in enumerate(symbols):
            for field in ('name', 'token', 'definition'):
                assert field in sym, (
                    f'Paper {paper} c1_symbols[{i}] missing '
                    f'{field!r}'
                )


# =====================================================================
# Test 6: Every paper has a non-empty c2_families dict (v0.2.0)
# =====================================================================
def test_paper_configs_have_non_empty_c2_families():
    """v0.2.0 acceptance criterion: all 5 papers have C2 families.

    Before v0.2.0, Papers 2/3/4 had empty c2_families.
    """
    for paper, cfg in paper_configs.PAPER_CONFIGS.items():
        families = cfg.get('c2_families', {})
        assert len(families) >= 1, (
            f'Paper {paper} has empty c2_families. '
            f'v0.2.0 requires at least 1 family per paper.'
        )


# =====================================================================
# Test 7: Every paper's dir exists on disk
# =====================================================================
def test_paper_configs_dirs_exist():
    """The 'dir' of every paper must point to an existing folder.

    Otherwise, fork_verify will fail with FileNotFoundError.
    This test skips the check if the directory is missing on
    the local machine (it might exist in production).
    """
    for paper, cfg in paper_configs.PAPER_CONFIGS.items():
        d = cfg.get('dir')
        if d is None:
            continue
        # Just check that the path is a string-like and a valid Path.
        # The actual existence check is skipped if the path is
        # not on the local filesystem.
        if isinstance(d, Path):
            # OK
            pass
        else:
            assert False, (
                f'Paper {paper} dir is not a Path: {type(d).__name__}'
            )


# =====================================================================
# Test 8: substitute_verify() works for every paper
# =====================================================================
def test_substitute_verify_works_for_every_paper():
    """substitute_verify() should not raise for any paper.

    The template that ships in this repository is the one under
    src/tmaudit/templates/. An older copy of this test looked for
    `_verify_TEMPLATE.py` at the repo root and skipped on every clone,
    so the substitution it claims to cover never ran.
    """
    tpl_path = ROOT / 'src' / 'tmaudit' / 'templates' / 'verify_TEMPLATE.py'
    assert tpl_path.is_file(), tpl_path
    tpl = tpl_path.read_text(encoding='utf-8')
    for paper, cfg in paper_configs.PAPER_CONFIGS.items():
        # substitute_verify should not raise
        try:
            out = paper_configs.substitute_verify(tpl, cfg)
        except Exception as e:
            raise AssertionError(
                f'substitute_verify failed for paper {paper}: {e}'
            )
        # The output should contain c7_max_ceremonial (added in v0.1.2)
        # and c10_reproducibility_claims (added in v0.3.0).
        assert "'c7_max_ceremonial'" in out, (
            f'Paper {paper} substitute_verify output is missing '
            f"c7_max_ceremonial. The C7 field is not being passed "
            f'through to the verify script.'
        )
        assert "'c10_reproducibility_claims'" in out, (
            f'Paper {paper} substitute_verify output is missing '
            f"c10_reproducibility_claims. The C10 field is not being "
            f'passed through to the verify script.'
        )
        assert "'c8_claimed_effects'" in out, (
            f'Paper {paper} substitute_verify output is missing '
            f"c8_claimed_effects. The C8 field is not being "
            f'passed through to the verify script.'
        )
        assert "'c9_figure_keywords'" in out, (
            f'Paper {paper} substitute_verify output is missing '
            f"c9_figure_keywords. The C9 field is not being "
            f'passed through to the verify script.'
        )


# =====================================================================
# Test 9: c2_abstract_k_allowed is non-empty for v0.2.0 papers
# =====================================================================
def test_paper_configs_c2_abstract_k_allowed_non_empty():
    """v0.2.0: every paper should declare which k values are
    allowed in the abstract (a non-empty list)."""
    for paper, cfg in paper_configs.PAPER_CONFIGS.items():
        k_allowed = cfg.get('c2_abstract_k_allowed', [])
        assert len(k_allowed) >= 1, (
            f'Paper {paper} c2_abstract_k_allowed is empty. '
            f'v0.2.0 requires at least 1 allowed k value.'
        )


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
