"""Tests for tmaudit_claims_plugin.

Runnable without installing the plugin package: the module is imported
from the package root.

    python -m pytest case-studies/arxiv-2502.14074/tmaudit_claims_plugin/tests
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from tmaudit_claims_plugin.checks import (  # noqa: E402
    percent_table_without_uncertainty,
    significance_without_test,
)


# ---------------------------------------------------------------------------
# claims-significance-no-test
# ---------------------------------------------------------------------------

def test_significance_without_test_fires_when_no_test_anywhere():
    tex = (
        'The method shows a significant increase over the baseline.\n'
        'It is also significantly faster.\n'
    )
    findings = significance_without_test(tex)
    assert len(findings) == 1
    f = findings[0]
    assert f.category == 'CLAIM-SIG'
    assert f.severity == 'MEDIUM'
    assert f.line == 1
    assert '2 use(s)' in f.message


def test_significance_without_test_silent_when_p_value_present():
    tex = (
        'The method shows a significant increase over the baseline '
        '(p = 0.003).\n'
    )
    assert significance_without_test(tex) == []


def test_significance_without_test_silent_when_bootstrap_present():
    tex = 'A significant effect, with a bootstrap confidence interval.\n'
    assert significance_without_test(tex) == []


def test_significance_without_test_silent_without_the_word():
    assert significance_without_test('No such wording here at all.\n') == []


def test_significance_check_needs_no_config():
    """requires_config=False: an empty/None config must not change the result."""
    tex = 'a significant difference\n'
    assert significance_without_test(tex, {}) == significance_without_test(tex, None)


# ---------------------------------------------------------------------------
# claims-headline-table-no-uncertainty
# ---------------------------------------------------------------------------

_UNCERTAIN_ELSEWHERE = (
    'text with a standard deviation reported elsewhere\n'
)


def test_percent_table_fires_on_percentage_point_estimates():
    tex = _UNCERTAIN_ELSEWHERE + (
        '\\begin{table}\n'
        '\\caption{Correlation comparison.}\n'
        '\\begin{tabular}{cc}\n'
        'Method & Spearman \\\\\n'
        'Ours & 96.4\\% \\\\\n'
        'Base & 95.0\\% \\\\\n'
        '\\end{tabular}\n'
        '\\end{table}\n'
    )
    findings = percent_table_without_uncertainty(tex)
    assert len(findings) == 1
    f = findings[0]
    assert f.category == 'CLAIM-INTERVAL'
    assert '2 percentage' in f.message
    assert 'Correlation comparison' in f.message


def test_percent_table_silent_when_table_has_pm():
    tex = _UNCERTAIN_ELSEWHERE + (
        '\\begin{table}\n'
        '\\begin{tabular}{cc}\n'
        'Ours & $96.4 \\pm 1.2$\\% \\\\\n'
        '\\end{tabular}\n'
        '\\end{table}\n'
    )
    assert percent_table_without_uncertainty(tex) == []


def test_percent_table_silent_when_document_has_no_uncertainty():
    """A paper that never reports spread is a different observation; the
    table check must not fire on it."""
    tex = (
        '\\begin{table}\n'
        '\\begin{tabular}{cc}\n'
        'Ours & 96.4\\% \\\\\n'
        '\\end{tabular}\n'
        '\\end{table}\n'
    )
    assert percent_table_without_uncertainty(tex) == []


def test_percent_table_silent_on_table_without_percentages():
    tex = _UNCERTAIN_ELSEWHERE + (
        '\\begin{table}\n'
        '\\begin{tabular}{cc}\n'
        'Ours & 12 \\\\\n'
        '\\end{tabular}\n'
        '\\end{table}\n'
    )
    assert percent_table_without_uncertainty(tex) == []


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
