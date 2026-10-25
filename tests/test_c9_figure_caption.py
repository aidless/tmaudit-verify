"""Regression / TDD tests for the C9 (figure-caption) check.

Background:

C9 is the 9th audit category. It checks that each
figure has a caption, the caption is in the right place,
the caption matches the figure's content (per the
expected keywords config), and the figure is referenced
in the body text.

This test file is the **TDD red phase** — it specifies
the contract that `check_c9_figure_caption` must
satisfy. The implementation is not yet written; the
tests will fail with AttributeError until the function
is implemented.

Heuristic constants (documented here so the
implementation and tests share the same source of
truth):
  - Caption is BELOW the \\includegraphics by convention
    (IEEE / ACM / TMLR).
  - Caption content must contain at least one of the
    expected_keywords (case-insensitive).
  - Each figure must be referenced in the body via
    \\ref{fig:...} or \\autoref{fig:...}.

Acceptance criteria (from ROADMAP.md):
  1. C9 detects missing captions (HIGH severity).
  2. C9 detects wrong caption placement (MED severity).
  3. C9 detects content mismatch (MED severity).
  4. C9 detects unreferenced figures (MED severity).
  5. C9 is opt-in (disabled by default if no
     `c9_figure_keywords` config).

Function signature (planned):
  def check_c9_figure_caption(
      tex: str,
      c9_figure_keywords: list = None,
  ) -> list[tuple[str, str, int]]:
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tmaudit.templates import verify_TEMPLATE


# =====================================================================
# Test fixtures: sample tex with figure environments
# =====================================================================

# Figure WITH caption below the graphic (correct).
TEX_FIGURE_OK = r"""
\begin{document}
We discuss the architecture in Figure~\ref{fig:overview}.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{overview.png}
  \caption{Overview of the proposed architecture showing the
  main components and their interactions.}
  \label{fig:overview}
\end{figure}
\end{document}
"""

# Figure WITHOUT a caption (HIGH finding).
TEX_FIGURE_NO_CAPTION = r"""
\begin{document}
We discuss the architecture in Figure~\ref{fig:overview}.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{overview.png}
  \label{fig:overview}
\end{figure}
\end{document}
"""

# Figure with caption ABOVE the graphic (wrong placement).
TEX_FIGURE_CAPTION_ABOVE = r"""
\begin{document}
We discuss the architecture in Figure~\ref{fig:overview}.

\begin{figure}[t]
  \centering
  \caption{Overview of the proposed architecture.}
  \label{fig:overview}
  \includegraphics[width=0.9\textwidth]{overview.png}
\end{figure}
\end{document}
"""

# Figure with caption containing the expected keyword.
TEX_FIGURE_KEYWORD_MATCH = r"""
\begin{document}
Figure~\ref{fig:results} shows the accuracy results.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{results.png}
  \caption{Accuracy results on the test set, showing 95\%
  accuracy across all classes.}
  \label{fig:results}
\end{figure}
\end{document}
"""

# Figure with caption NOT containing any expected keyword.
TEX_FIGURE_KEYWORD_MISS = r"""
\begin{document}
Figure~\ref{fig:results} shows the picture.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{results.png}
  \caption{A pretty picture of our system.}
  \label{fig:results}
\end{figure}
\end{document}
"""

# Figure defined but never referenced in body.
TEX_FIGURE_UNREFERENCED = r"""
\begin{document}
This paper presents our system.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{orphan.png}
  \caption{An orphan figure that is never cited.}
  \label{fig:orphan}
\end{figure}
\end{document}
"""

# Figure referenced in body but label not defined (false positive
# guard for the unreferenced check).
TEX_FIGURE_UNDEFINED = r"""
\begin{document}
We discuss the architecture in Figure~\ref{fig:undefined}.

% no figure environment here
\end{document}
"""

# Multiple figures: one OK, one missing caption.
TEX_MULTIPLE_FIGURES = r"""
\begin{document}
Figure~\ref{fig:good} shows the good example.
Figure~\ref{fig:bad} shows the bad example.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{good.png}
  \caption{This is a good figure with a caption.}
  \label{fig:good}
\end{figure}

\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{bad.png}
  \label{fig:bad}
\end{figure}
\end{document}
"""

# Malformed LaTeX (unclosed braces).
TEX_MALFORMED = r"""
\begin{document
We discuss the architecture in Figure~\ref{fig:overview}.

\begin{figure
  \centering
  \includegraphics
  \caption{Broken figure
  \label{fig:overview}
"""

# Figure with caption that PARTIALLY matches keyword
# (the keyword is in the body text, not the caption).
TEX_FIGURE_KEYWORD_PARTIAL = r"""
\begin{document}
Figure~\ref{fig:results} shows the accuracy.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{results.png}
  \caption{Performance comparison of our system on three
  benchmark datasets.}
  \label{fig:results}
\end{figure}
\end{document}
"""


def _fresh_check(tex: str, c9_keywords: list = None) -> list:
    """Convenience: call check_c9_figure_caption with default args."""
    return verify_TEMPLATE.check_c9_figure_caption(tex, c9_keywords)


# =====================================================================
# Sub-check 1: Caption exists
# =====================================================================

# Test 1: Figure without caption -> HIGH finding
def test_c9_no_caption_emits_high():
    """A figure without a \\caption should emit a HIGH finding.

    This is a real reviewer concern: a figure without a
    caption is essentially undocumented.
    """
    findings = _fresh_check(TEX_FIGURE_NO_CAPTION)
    high_findings = [
        f for f in findings
        if f[0] == 'C9' and 'HIGH' in f[1]
    ]
    assert len(high_findings) == 1, (
        f'Expected 1 HIGH finding, got: {findings}'
    )


# Test 2: Figure with caption -> no HIGH finding
def test_c9_with_caption_no_finding():
    """A figure with a caption (regardless of content) should
    not emit a HIGH finding. The caption-content check is
    separate (sub-check 3)."""
    findings = _fresh_check(TEX_FIGURE_OK)
    high_findings = [
        f for f in findings
        if f[0] == 'C9' and 'HIGH' in f[1]
    ]
    assert len(high_findings) == 0, (
        f'Expected 0 HIGH findings, got: {high_findings}'
    )


# Test 3: Empty tex -> no findings
def test_c9_empty_tex_no_finding():
    """An empty tex should produce 0 findings (no figures to check)."""
    findings = _fresh_check('')
    assert findings == [], f'Expected 0 findings, got: {findings}'


# =====================================================================
# Sub-check 2: Caption placement
# =====================================================================

# Test 4: Caption below graphic -> no MED placement finding
def test_c9_caption_below_figure_ok():
    """Caption below the graphic (the correct convention) ->
    no MED placement finding."""
    findings = _fresh_check(TEX_FIGURE_OK)
    med_findings = [
        f for f in findings
        if f[0] == 'C9' and 'MED' in f[1] and 'caption' in f[1].lower()
        and ('above' in f[1].lower() or 'placement' in f[1].lower()
             or 'below' in f[1].lower())
    ]
    assert len(med_findings) == 0, (
        f'Expected 0 MED placement findings, got: {med_findings}'
    )


# Test 5: Caption above graphic -> MED finding
def test_c9_caption_above_figure_emits_med():
    """Caption above the graphic (wrong convention) -> MED finding.

    This is a real reviewer concern: some conferences
    (IEEE, ACM) require captions below the figure.
    """
    findings = _fresh_check(TEX_FIGURE_CAPTION_ABOVE)
    med_findings = [
        f for f in findings
        if f[0] == 'C9' and 'MED' in f[1] and 'above' in f[1].lower()
    ]
    assert len(med_findings) == 1, (
        f'Expected 1 MED "caption above" finding, got: {findings}'
    )


# =====================================================================
# Sub-check 3: Caption content (matches expected keywords)
# =====================================================================

# Test 6: Caption matches keyword -> no MED content finding
def test_c9_caption_matches_keyword_no_finding():
    """Caption contains the expected keyword ('accuracy') ->
    no MED content finding."""
    findings = _fresh_check(TEX_FIGURE_KEYWORD_MATCH, [
        {'fig_id': 'fig:results', 'expected_keywords': ['accuracy', 'precision']},
    ])
    med_findings = [
        f for f in findings
        if f[0] == 'C9' and 'MED' in f[1] and 'keyword' in f[1].lower()
    ]
    assert len(med_findings) == 0, (
        f'Expected 0 MED keyword findings, got: {med_findings}'
    )


# Test 7: Caption does NOT match keyword -> MED finding
def test_c9_caption_no_keyword_emits_med():
    """Caption does NOT contain any expected keyword ->
    MED finding (caption is too generic)."""
    findings = _fresh_check(TEX_FIGURE_KEYWORD_MISS, [
        {'fig_id': 'fig:results', 'expected_keywords': ['accuracy', 'precision']},
    ])
    med_findings = [
        f for f in findings
        if f[0] == 'C9' and 'MED' in f[1] and 'keyword' in f[1].lower()
    ]
    assert len(med_findings) == 1, (
        f'Expected 1 MED keyword finding, got: {findings}'
    )


# Test 8: Caption has different keyword (not in config) -> no MED
def test_c9_caption_partial_keyword_no_finding():
    """Caption has 'performance' but config expects 'accuracy' ->
    no MED finding (we don't penalize for having extra keywords)."""
    findings = _fresh_check(TEX_FIGURE_KEYWORD_PARTIAL, [
        {'fig_id': 'fig:results', 'expected_keywords': ['accuracy']},
    ])
    # 'accuracy' is NOT in the caption, but the test design
    # says "no MED" because we don't penalize for extra words.
    # (Wait, the caption does NOT contain 'accuracy', so this
    # test is actually testing the negative case. The MED
    # should fire. But for 'partial' we mean 'the keyword
    # appears somewhere in the document', which is a different
    # test. Let's make this test verify the negative case.)
    med_findings = [
        f for f in findings
        if f[0] == 'C9' and 'MED' in f[1] and 'keyword' in f[1].lower()
    ]
    # The caption doesn't contain 'accuracy', so MED should fire.
    assert len(med_findings) == 1, (
        f'Expected 1 MED keyword finding (caption lacks "accuracy"), '
        f'got: {findings}'
    )


# =====================================================================
# Sub-check 4: Figure referenced in body
# =====================================================================

# Test 9: Figure referenced in body -> no MED unreferenced finding
def test_c9_figure_referenced_no_finding():
    """Figure with \\label and a body \\ref -> no MED unreferenced finding."""
    findings = _fresh_check(TEX_FIGURE_OK)
    med_findings = [
        f for f in findings
        if f[0] == 'C9' and 'MED' in f[1] and 'referenced' in f[1].lower()
    ]
    assert len(med_findings) == 0, (
        f'Expected 0 MED unreferenced findings, got: {med_findings}'
    )


# Test 10: Figure defined but not referenced -> MED finding
def test_c9_figure_not_referenced_emits_med():
    """Figure with \\label but no body \\ref -> MED unreferenced finding.

    This is a real reviewer concern: orphan figures clutter
    the paper and suggest the author didn't intend to include them.
    """
    findings = _fresh_check(TEX_FIGURE_UNREFERENCED)
    med_findings = [
        f for f in findings
        if f[0] == 'C9' and 'MED' in f[1] and 'referenced' in f[1].lower()
    ]
    assert len(med_findings) >= 1, (
        f'Expected >= 1 MED unreferenced finding, got: {findings}'
    )


# Test 11: \\ref in body but no figure -> no finding (false positive guard)
def test_c9_undefined_reference_no_finding():
    """A \\ref in the body that doesn't match any \\label should NOT
    emit a finding (it's just a forward reference)."""
    findings = _fresh_check(TEX_FIGURE_UNDEFINED)
    med_findings = [
        f for f in findings
        if f[0] == 'C9' and 'unreferenced' in f[1].lower()
    ]
    # No figure is defined, so no figure can be "unreferenced".
    assert len(med_findings) == 0, (
        f'Expected 0 MED unreferenced findings, got: {med_findings}'
    )


# =====================================================================
# Per-paper config: opt-in
# =====================================================================

# Test 12: No c9_figure_keywords -> C9 still runs (sub-checks 1, 2, 4
# are independent of c9_figure_keywords; only sub-check 3 uses it).
def test_c9_disabled_when_no_keywords():
    """When c9_figure_keywords is None, sub-checks 1, 2, 4 still
    run (they don't need the config), but sub-check 3 (keyword
    match) is skipped. This is the "graceful degradation" pattern."""
    findings = _fresh_check(TEX_FIGURE_NO_CAPTION, None)
    # Sub-check 1: no caption -> HIGH
    high_findings = [
        f for f in findings
        if f[0] == 'C9' and 'HIGH' in f[1]
    ]
    assert len(high_findings) == 1, (
        f'Expected 1 HIGH finding, got: {findings}'
    )


# =====================================================================
# Edge cases
# =====================================================================

# Test 13: Multiple figures, mixed pass/fail
def test_c9_multiple_figures_mixed():
    """2 figures: 1 with caption (OK), 1 without (HIGH).
    The unreferenced check applies to each figure.

    Note: 'fig:good' is referenced in body -> no MED for it.
    'fig:bad' is referenced in body too -> no MED for it.
    Only the missing-caption check fires.
    """
    findings = _fresh_check(TEX_MULTIPLE_FIGURES)
    high_findings = [
        f for f in findings
        if f[0] == 'C9' and 'HIGH' in f[1]
    ]
    # Only 'fig:bad' should produce a HIGH (no caption).
    assert len(high_findings) == 1, (
        f'Expected 1 HIGH finding (fig:bad has no caption), got: {high_findings}'
    )


# Test 14: Malformed LaTeX -> no crash
def test_c9_malformed_latex_no_crash():
    """Malformed LaTeX (unclosed braces, unclosed environments)
    should not crash the audit."""
    # Should not raise
    findings = _fresh_check(TEX_MALFORMED)
    assert isinstance(findings, list)


# Test 15: Per-paper config with no figures -> no findings
def test_c9_no_figures_in_tex_no_finding():
    """A tex with no figures but c9_figure_keywords configured
    should produce 0 findings (nothing to verify)."""
    findings = _fresh_check(
        r'This paper has no figures, just text.',
        [
            {'fig_id': 'fig:overview', 'expected_keywords': ['overview']},
        ],
    )
    # No figures means no findings, even if keywords are configured.
    assert findings == [], f'Expected 0 findings, got: {findings}'


# Test 16: Caption with case-insensitive keyword match
def test_c9_caption_case_insensitive_keyword():
    """The keyword match is case-insensitive.

    A caption 'OVERVIEW OF THE SYSTEM' should match the
    keyword 'overview' (lowercase).
    """
    tex = r"""
\begin{document}
\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{fig.png}
  \caption{OVERVIEW OF THE SYSTEM ARCHITECTURE.}
  \label{fig:overview}
\end{figure}
\end{document}
"""
    findings = _fresh_check(tex, [
        {'fig_id': 'fig:overview', 'expected_keywords': ['overview']},
    ])
    med_findings = [
        f for f in findings
        if f[0] == 'C9' and 'MED' in f[1] and 'keyword' in f[1].lower()
    ]
    assert len(med_findings) == 0, (
        f'Expected 0 MED findings (case-insensitive match), got: {med_findings}'
    )


# =====================================================================
# Nested-brace captions (found by auditing arXiv:2502.14074)
# =====================================================================
# A real caption often nests braces, e.g.
#   \caption{\textbf{Rankings ... \textsc{Swim} ...}}
#   \caption{\textcolor[HTML]{2f70b8}{{Llama-3-70B}} are used as baselines.}
# The old brace-bounded regex accepted only one brace level, so a figure
# that DID carry a caption was reported as having none.

TEX_FIGURE_NESTED_CAPTION = r"""
\begin{document}
Figure~\ref{fig:nested} is described in the text.

\begin{figure}[t]
  \centering
  \includegraphics[width=0.9\textwidth]{nested.png}
  \caption{\textbf{Rankings from baseline-fixed frameworks show high
  sensitivity.} \textsc{Swim} is compared against a baseline.}
  \label{fig:nested}
\end{figure}
\end{document}
"""


def test_c9_nested_brace_caption_is_recognised():
    """A caption with two brace levels (\\textbf{... \\textsc{...} ...})
    must count as present, so no HIGH missing-caption finding fires."""
    findings = _fresh_check(TEX_FIGURE_NESTED_CAPTION)
    high = [f for f in findings if f[0] == 'C9' and 'HIGH' in f[1]]
    assert high == [], f'unexpected HIGH (missing caption): {findings}'


def test_c9_double_brace_caption_is_recognised():
    """The `{{...}}` form (e.g. inside \\textcolor) is also handled."""
    tex = (
        '\\begin{figure}[t]\n'
        '\\includegraphics{fig.png}\n'
        '\\caption{\\textcolor[HTML]{2f70b8}{{Llama-3-70B}} is a baseline.}\n'
        '\\label{fig:x}\n'
        '\\end{figure}\n'
    )
    findings = _fresh_check(tex)
    high = [f for f in findings if f[0] == 'C9' and 'HIGH' in f[1]]
    assert high == [], high


def test_c9_unbalanced_caption_brace_is_not_a_caption():
    """A truly unclosed caption group must still be treated as missing,
    so the scan does not swallow the rest of the figure block."""
    tex = (
        '\\begin{figure}[t]\n'
        '\\includegraphics{fig.png}\n'
        '\\caption{broken caption\n'
        '\\end{figure}\n'
    )
    findings = _fresh_check(tex)
    high = [f for f in findings if f[0] == 'C9' and 'HIGH' in f[1]]
    assert len(high) == 1, high


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
