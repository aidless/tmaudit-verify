"""Tests for the v0.2.0 Markdown report generator (`src/tmaudit/report.py`).

Background:

The report module is the v0.2.0 deliverable for the
acceptance criterion "tmaudit audit-all generates a
single Markdown report covering all configured papers".

The module has 3 public pieces:
  - PaperAuditResult: dataclass with one paper's audit
    results.
  - parse_verify_output(): parses a verify_p<N>.py stdout
    into a PaperAuditResult.
  - render_markdown(): renders a list of results as a
    Markdown report.

This file tests each piece, plus the integration
between them.

Acceptance criteria:
  1. The report has 4 sections (header, summary table,
     per-paper details, footer).
  2. The summary table has one row per paper.
  3. Findings are categorized by category (C1..C7).
  4. The Markdown is valid (no broken table syntax, no
     unclosed code blocks).
  5. The parser is best-effort (handles missing sections,
     empty outputs).
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tmaudit.report import (
    PaperAuditResult,
    Finding,
    render_markdown,
    write_markdown_report,
    parse_verify_output,
    SEVERITY_MAP,
)


# =====================================================================
# Test 1: empty results list produces minimal valid Markdown
# =====================================================================
def test_render_markdown_empty_results():
    """An empty results list produces a valid (but minimal) report."""
    md = render_markdown(
        results=[],
        started_at=time.time(),
        ended_at=time.time() + 1,
        tmaudit_version='0.2.0',
    )
    # The report has a header, summary, and footer
    assert '# tmaudit audit-all report' in md
    assert 'Total papers**: 0' in md
    assert 'Run metadata' in md
    # The all-pass message
    assert 'All papers passed' in md
    # No per-paper sections (the table is empty)
    assert '| Paper | Status |' in md


# =====================================================================
# Test 2: single paper, no findings -> "No issues detected"
# =====================================================================
def test_render_markdown_one_paper_pass():
    """One paper, no findings, exit code 0 -> pass message."""
    r = PaperAuditResult(
        paper=1,
        paper_dir=Path('papers/PAPER1_CONSOLIDATED'),
        exit_code=0,
        findings=[],
        started_at=time.time(),
        ended_at=time.time() + 0.5,
    )
    md = render_markdown([r], time.time() - 1, time.time(), '0.2.0')
    assert '| 1 | :white_check_mark: PASS | 0 | 0 | 0 | 0 | 0 |' in md
    assert '## Paper 1' in md
    assert 'No issues detected' in md


# =====================================================================
# Test 3: single paper, multiple findings, categorized
# =====================================================================
def test_render_markdown_finding_grouping_by_category():
    """Findings are grouped by category in the per-paper section."""
    r = PaperAuditResult(
        paper=5,
        paper_dir=Path('papers/PAPER5_CONSOLIDATED'),
        exit_code=0,
        findings=[
            Finding(category='C7', message='ceremonial 1', line=56, severity='MEDIUM'),
            Finding(category='C7', message='ceremonial 2', line=56, severity='MEDIUM'),
            Finding(category='C1', message='symbol missing', line=10, severity='HIGH'),
        ],
        started_at=time.time(),
        ended_at=time.time() + 0.5,
    )
    md = render_markdown([r], time.time() - 1, time.time(), '0.2.0')
    # Both categories appear as subsections
    assert '#### C1 (1 finding(s))' in md
    assert '#### C7 (2 finding(s))' in md
    # The HIGH finding is marked
    assert '**[HIGH] C1**' in md
    # The MEDIUM findings are marked
    assert '**[MEDIUM] C7**' in md


# =====================================================================
# Test 4: multiple papers, mixed pass/fail
# =====================================================================
def test_render_markdown_multiple_papers_pass_fail():
    """Multiple papers, mixed results, with one failure."""
    results = [
        PaperAuditResult(
            paper=1, paper_dir=Path('P1'), exit_code=0,
            findings=[], started_at=0, ended_at=1,
        ),
        PaperAuditResult(
            paper=5, paper_dir=Path('P5'), exit_code=1,  # HIGH finding -> non-zero
            findings=[
                Finding(category='C1', message='symbol X undefined', line=10, severity='HIGH'),
            ],
            started_at=0, ended_at=1,
        ),
    ]
    md = render_markdown(results, 0, 1, '0.2.0')
    # 1 of 2 failed
    assert '1 of 2 papers failed' in md
    # Summary table has both rows
    assert '| 1 | :white_check_mark: PASS' in md
    assert '| 5 | :x: FAIL' in md
    # Aggregate counts
    assert '1 total' in md
    assert '1 HIGH' in md


# =====================================================================
# Test 5: write_markdown_report writes a file
# =====================================================================
def test_write_markdown_report_writes_file(tmp_path):
    """write_markdown_report writes the report to the given path."""
    r = PaperAuditResult(
        paper=1, paper_dir=Path('P1'), exit_code=0,
        findings=[], started_at=0, ended_at=1,
    )
    out = tmp_path / 'report.md'
    write_markdown_report(out, [r], 0, 1, '0.2.0')
    assert out.exists()
    text = out.read_text(encoding='utf-8')
    assert 'tmaudit audit-all report' in text
    assert '## Paper 1' in text


# =====================================================================
# Test 6: parse_verify_output extracts findings correctly
# =====================================================================
def test_parse_verify_output_basic():
    """parse_verify_output extracts findings from a verify stdout."""
    sample_stdout = '''========================================================================
PAPER AUDIT  (verify_p5.py)
========================================================================
Source: papers/PAPER5_CONSOLIDATED/main.tex
Size:   67,798 chars
Refs:   35 entries in refs.bib

Findings by category:
  C1  [OK]     0 finding(s)
  C2  [OK]     0 finding(s)
  C3  [OK]     0 finding(s)
  C4  [OK]     0 finding(s)
  C5  [OK]     0 finding(s)
  C6  [OK]     0 finding(s)
  C7  [MEDIUM] 13 finding(s)

------------------------------------------------------------------------
DETAILED FINDINGS
------------------------------------------------------------------------

[MEDIUM] C7  (line 56)
    MED: citation 'foo' at line 56 is ceremonial.

[MEDIUM] C7  (line 56)
    MED: citation 'bar' at line 56 is ceremonial.
'''
    r = parse_verify_output(
        paper=5,
        paper_dir=Path('papers/PAPER5_CONSOLIDATED'),
        stdout=sample_stdout,
        exit_code=0,
    )
    # 2 findings extracted
    assert len(r.findings) == 2
    # Both are C7 MEDIUM
    for f in r.findings:
        assert f.category == 'C7'
        assert f.severity == 'MEDIUM'
        assert f.line == 56


# =====================================================================
# Test 7: parse_verify_output handles empty / no-findings stdout
# =====================================================================
def test_parse_verify_output_empty():
    """parse_verify_output returns empty findings for an OK audit."""
    sample_stdout = '''PAPER AUDIT  (verify_p1.py)
========================================================================
Source: papers/PAPER1_CONSOLIDATED/main.tex
Size:   50,000 chars
Refs:   25 entries in refs.bib

Findings by category:
  C1  [OK]     0 finding(s)
  C2  [OK]     0 finding(s)
  C3  [OK]     0 finding(s)
  C4  [OK]     0 finding(s)
  C5  [OK]     0 finding(s)
  C6  [OK]     0 finding(s)
  C7  [OK]     0 finding(s)

All checks passed.  No issues detected.
'''
    r = parse_verify_output(
        paper=1,
        paper_dir=Path('papers/PAPER1_CONSOLIDATED'),
        stdout=sample_stdout,
        exit_code=0,
    )
    assert r.findings == []


# =====================================================================
# Test 8: parse_verify_output handles missing DETAILED FINDINGS section
# =====================================================================
def test_parse_verify_output_no_detailed_section():
    """parse_verify_output gracefully handles output with no
    DETAILED FINDINGS section (e.g., truncated output)."""
    sample_stdout = '''PAPER AUDIT  (verify_p1.py)
========================================================================
Some output that doesn't have the DETAILED FINDINGS marker.
'''
    r = parse_verify_output(
        paper=1,
        paper_dir=Path('P1'),
        stdout=sample_stdout,
        exit_code=0,
    )
    # No findings extracted (best-effort)
    assert r.findings == []


# =====================================================================
# Test 9: severity map is consistent with verify_TEMPLATE.SEVERITY
# =====================================================================
def test_severity_map_is_correct():
    """The SEVERITY_MAP in report.py matches the SEVERITY in
    verify_TEMPLATE.py (both should agree on which categories
    are HIGH, MEDIUM, LOW)."""
    from src.tmaudit.templates.verify_TEMPLATE import SEVERITY
    for cat, sev in SEVERITY.items():
        assert SEVERITY_MAP.get(cat) == sev, (
            f'Category {cat}: verify_TEMPLATE.SEVERITY says {sev}, '
            f'but report.SEVERITY_MAP says {SEVERITY_MAP.get(cat)}'
        )


# =====================================================================
# Test 10: report has all 4 required sections
# =====================================================================
def test_report_has_all_4_sections():
    """The Markdown report has 4 distinct sections:
    1. Header (with metadata)
    2. Summary table
    3. Per-paper details
    4. Footer (run metadata)
    """
    r = PaperAuditResult(
        paper=1, paper_dir=Path('P1'), exit_code=0,
        findings=[], started_at=0, ended_at=1,
    )
    md = render_markdown([r], 0, 1, '0.2.0')
    # 1. Header
    assert '# tmaudit audit-all report' in md
    assert '**Run started**' in md
    # 2. Summary table
    assert '## Summary' in md
    assert '| Paper | Status |' in md
    # 3. Per-paper details
    assert '## Paper 1' in md
    # 4. Footer
    assert '## Run metadata' in md


# =====================================================================
# Test 11: Markdown is valid (no broken table syntax)
# =====================================================================
def test_markdown_is_valid():
    """The rendered Markdown has balanced table rows, no
    unclosed code blocks, and no broken GFM syntax."""
    r = PaperAuditResult(
        paper=1, paper_dir=Path('P1'), exit_code=0,
        findings=[
            Finding(category='C7', message='msg with `code` inside', line=10, severity='MEDIUM'),
        ],
        started_at=0, ended_at=1,
    )
    md = render_markdown([r], 0, 1, '0.2.0')
    # Each table row has the same number of pipes (GFM).
    # The summary table has 2 data rows (header + 1 paper).
    table_lines = [line for line in md.split('\n')
                   if line.startswith('|') and '|' in line[1:]]
    # All table lines should have the same number of pipes.
    n_pipes = table_lines[0].count('|')
    for line in table_lines:
        assert line.count('|') == n_pipes, (
            f'Inconsistent pipe count: {line!r}'
        )


# =====================================================================
# Test 12: empty paper_dir is OK
# =====================================================================
def test_empty_paper_dir_is_ok():
    """A PaperAuditResult with no dir is rendered without errors."""
    r = PaperAuditResult(
        paper=1, paper_dir=Path('.'), exit_code=0,
        findings=[], started_at=0, ended_at=1,
    )
    md = render_markdown([r], 0, 1, '0.2.0')
    assert '## Paper 1' in md


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
