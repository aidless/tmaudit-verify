"""Two reporting-standards checks for a manuscript that reports
quantitative comparisons.

These are general checks, not a rulepack written for one paper. They
flag two shapes that make a quantitative claim hard to read about:

  * ``claims-significance-no-test`` — the word "significant/significantly"
    is used to describe a difference or an effect, but the document
    reports no p-value, bootstrap, permutation test, or significance test
    anywhere, so a reader cannot map the word onto an inferential
    standard.
  * ``claims-percent-table-no-uncertainty`` — a results table reports
    percentage values with no uncertainty marker, while the document
    reports intervals or standard deviations elsewhere, so the numbers
    carry less information than the paper is capable of giving.

Both are MEDIUM and both are ``requires_config=False``: they read only
the manuscript. Neither asserts that a result is wrong — only that a
reporting convention is missing.

Registered through the ``tmaudit.plugins`` entry-point group in
``pyproject.toml``; installed with::

    pip install -e ./case-studies/arxiv-2502.14074/tmaudit_claims_plugin

and run with::

    tmaudit plugins run claims-significance-no-test --paper-dir DIR
    tmaudit plugins run claims-percent-table-no-uncertainty --paper-dir DIR
"""
from __future__ import annotations
import re
from typing import List, Optional

from tmaudit import Finding, check


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# A hypothesis-test standard. A confidence interval or a standard
# deviation is an uncertainty measure, but it does not by itself license
# the word "significant": only a test statistic, a resampling standard,
# or a stated p-value does. So the patterns below are deliberately the
# test-based standards, not every uncertainty marker.
_TEST_STANDARD_RE = re.compile(
    r'p[\s\-]*value'                       # "p-value" / "p value"
    r'|p\s*[<=]\s*0?\.\d+'                 # "p < 0.05", "p = .03"
    r'|\bbootstrap'                        # bootstrap CI on a statistic
    r'|\bpermutation\s+(?:test|based)'
    r'|\bsignificance\s+test'
    r'|\bhypothesis\s+test'
    r'|\bt[\s\-]*test'                     # t-test / t test
    r'|\bWilcoxon'
    r'|\bMann[\s\-]Whitney',
    re.IGNORECASE,
)

# The word whose use implies an inferential claim.
_SIGNIFICANCE_RE = re.compile(r'\bsignificant(?:ly)?\b', re.IGNORECASE)

# An uncertainty marker anywhere in the document (used by the table
# check to decide whether the paper is *capable* of reporting spread).
_UNCERTAINTY_RE = re.compile(
    r'\\pm|±|confidence\s+interval|standard\s+deviation|\bstd\b',
    re.IGNORECASE,
)

# A results table reporting percentages as point estimates.
_TABLE_RE = re.compile(r'\\begin\{table\*?\}.*?\\end\{table\*?\}', re.DOTALL)
_CAPTION_RE = re.compile(r'\\caption\{((?:[^{}]|\{[^{}]*\})*)\}', re.DOTALL)
_PERCENT_RE = re.compile(r'\d+(?:\.\d+)?\s*\\?%')
# Uncertainty *inside the table*: a ±, a std/CI column, or a bracketed or
# parenthesised numeric interval.
_TABLE_UNCERTAINTY_RE = re.compile(
    r'\\pm|±|\bstd\b|\bCI\b|confidence|standard\s+deviation'
    r'|\[\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\]'
    r'|\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)',
    re.IGNORECASE,
)


def _line_of(text: str, pos: int) -> int:
    return text.count('\n', 0, pos) + 1


# ---------------------------------------------------------------------------
# Check 1: significance wording with no test standard
# ---------------------------------------------------------------------------

@check(
    name='claims-significance-no-test',
    severity='MEDIUM',
    requires_config=False,
    help_text=(
        'Uses "significant/significantly" but reports no p-value, '
        'bootstrap, permutation test, or significance test anywhere'
    ),
    version='0.1.0',
)
def significance_without_test(
    tex: str,
    config: Optional[dict] = None,
) -> List[Finding]:
    """Flag significance wording in a document that reports no test.

    If the document reports a hypothesis-test standard anywhere (a
    p-value, bootstrap, permutation test, t-test, ...), the check stays
    silent: whether an individual sentence cites it is a judgement call.
    If it reports none, every occurrence of the significance word is
    reported as a single finding that lists where the word appears.
    """
    hits = list(_SIGNIFICANCE_RE.finditer(tex))
    if not hits:
        return []
    if _TEST_STANDARD_RE.search(tex):
        return []

    lines = sorted({_line_of(tex, m.start()) for m in hits})
    shown = lines[:8]
    more = f' (+{len(lines) - len(shown)} more)' if len(lines) > len(shown) else ''
    return [Finding(
        category='CLAIM-SIG',
        severity='MEDIUM',
        message=(
            f'{len(hits)} use(s) of "significant/significantly" on '
            f'{len(lines)} line(s) {shown}{more}, but the document reports '
            f'no p-value, bootstrap, permutation test, or significance test '
            f'anywhere. A significance word reads as an inferential claim; '
            f'with no test standard in the paper, the reader cannot tell '
            f'which uses are statistical. Reporting-standards observation, '
            f'not a claim that the results are wrong.'
        ),
        line=lines[0],
    )]


# ---------------------------------------------------------------------------
# Check 2: a percentage table with no uncertainty
# ---------------------------------------------------------------------------

@check(
    name='claims-percent-table-no-uncertainty',
    severity='MEDIUM',
    requires_config=False,
    help_text=(
        'A results table reports percentage values with no uncertainty, '
        'while the document reports intervals elsewhere'
    ),
    version='0.1.0',
)
def percent_table_without_uncertainty(
    tex: str,
    config: Optional[dict] = None,
) -> List[Finding]:
    """Flag percentage-bearing tables that carry no uncertainty.

    Only runs when the document reports uncertainty somewhere (a ``±``,
    a confidence interval, or a standard deviation): a paper that never
    reports spread is a different — and noisier — observation. When it
    does, every table that reports percentages as bare point estimates
    is reported, because those numbers invite a significance reading and
    a point estimate cannot distinguish signal from resampling noise.
    """
    if not _UNCERTAINTY_RE.search(tex):
        return []

    findings: List[Finding] = []
    for m in _TABLE_RE.finditer(tex):
        block = m.group(0)
        percents = _PERCENT_RE.findall(block)
        if not percents:
            continue
        if _TABLE_UNCERTAINTY_RE.search(block):
            continue
        cap = _CAPTION_RE.search(block)
        cap_text = ' '.join(cap.group(1).split())[:120] if cap else '(no caption)'
        line = _line_of(tex, m.start())
        findings.append(Finding(
            category='CLAIM-INTERVAL',
            severity='MEDIUM',
            message=(
                f'Table at line {line} reports {len(percents)} percentage '
                f'value(s) with no uncertainty marker, though the document '
                f'reports intervals elsewhere. Caption: '
                f'"{cap_text}". A point estimate cannot distinguish signal '
                f'from resampling noise. Reporting-standards observation, '
                f'not a claim that the numbers are wrong.'
            ),
            line=line,
        ))
    return findings
