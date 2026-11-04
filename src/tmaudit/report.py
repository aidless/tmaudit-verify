"""tmaudit.report — Markdown report generator for `audit-all`.

When `tmaudit audit-all --output report.md` is run, this
module takes the list of per-paper audit results and renders
them as a single Markdown report. The report has:

  1. A header with metadata (run timestamp, total papers,
     pass/fail counts).
  2. An aggregate table summarising each paper's status
     (PASS / FAIL, total findings, HIGH/MED/LOW counts).
  3. A per-paper section with:
     - Paper title and path
     - Findings by category (C1, C2, ..., C7)
     - Detailed findings (severity, location, message)
     - Exit code and timestamp
  4. A footer with run metadata (elapsed time, tmaudit
     version, etc.).

The Markdown is **GitHub-flavored** (uses tables, fenced
code blocks, and is parseable by standard Markdown
renderers).

Public API:
  - PaperAuditResult: dataclass with one paper's audit
    results.
  - render_markdown(results, ...): returns the Markdown
    string.
  - parse_verify_output(stdout): parses a verify_p<N>.py
    stdout into a PaperAuditResult.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .evidence import tier_of as evidence_tier_of


@dataclass
class Finding:
    """One finding from a paper audit.

    Mirrors the (category, message, line) tuple format
    used in verify_TEMPLATE.py.
    """
    category: str  # 'C1', 'C2', ..., 'C7'
    message: str
    line: int
    severity: str = 'UNKNOWN'  # 'HIGH', 'MEDIUM', 'LOW'


@dataclass
class PaperAuditResult:
    """Result of auditing one paper."""
    paper: int
    paper_dir: Path
    exit_code: int
    findings: list[Finding] = field(default_factory=list)
    raw_stdout: str = ''
    raw_stderr: str = ''
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def duration_seconds(self) -> float:
        if self.ended_at and self.started_at:
            return self.ended_at - self.started_at
        return 0.0

    @property
    def passed(self) -> bool:
        """A paper is "passed" if exit_code == 0 (no HIGH findings)."""
        return self.exit_code == 0

    @property
    def n_findings(self) -> int:
        return len(self.findings)

    @property
    def n_high(self) -> int:
        return sum(1 for f in self.findings if f.severity == 'HIGH')

    @property
    def n_medium(self) -> int:
        return sum(1 for f in self.findings if f.severity == 'MEDIUM')

    @property
    def n_low(self) -> int:
        return sum(1 for f in self.findings if f.severity == 'LOW')


# Severity mapping (from verify_TEMPLATE.SEVERITY).
# C10 is variable: HIGH for missing availability, MED for
# consistency / future-tense, LOW for missing metadata.
# We default to LOW here; the per-finding severity is
# embedded in the message itself.
SEVERITY_MAP = {
    'C1': 'HIGH',
    'C2': 'HIGH',
    'C3': 'MEDIUM',
    'C4': 'MEDIUM',
    'C5': 'MEDIUM',
    'C6': 'LOW',
    'C7': 'MEDIUM',
    'C8': 'MEDIUM',
    'C9': 'MEDIUM',
    'C10': 'LOW',
}


# Regex to parse a verify_p<N>.py stdout. The script's
# output is human-readable with sections separated by
# '===' markers. We extract:
#   - The "Findings by category:" section
#   - The "DETAILED FINDINGS" section (lines like
#     [MEDIUM] C7  (line 56)
#         MED: citation ...)
_CATEGORY_SECTION_RE = re.compile(
    r'Findings by category:\n'
    r'((?:.*\n)*?)'
    r'(?:-{5,}|\Z)',
    re.MULTILINE,
)
_CATEGORY_LINE_RE = re.compile(r'\s+([C]\d+)\s+\[(\w+)\]\s+(\d+) finding\(s\)')
_FINDING_HEADER_RE = re.compile(r'\[(\w+)\]\s+([C]\d+)\s+\(line\s+(\d+|-?\d+|global)\)')
_FINDING_BODY_RE = re.compile(r'^\s{4}(\S.*)$')
_PAPER_HEADER_RE = re.compile(
    r'PAPER AUDIT\s+\((?P<file>verify_p\d+\.py)\)\n'
    r'={5,}\n'
    r'Source:\s*(?P<source>.+)\n'
    r'Size:\s*(?P<size>[\d,]+)\s+chars\n'
    r'Refs:\s*(?P<refs>\d+)\s+entries in refs\.bib',
)


def parse_verify_output(
    paper: int,
    paper_dir: Path,
    stdout: str,
    stderr: str = '',
    exit_code: int = 0,
    started_at: float = 0.0,
    ended_at: float = 0.0,
) -> PaperAuditResult:
    """Parse a verify_p<N>.py stdout into a PaperAuditResult.

    The parser is **best-effort**: if the output format
    changes, we still return a result with whatever
    information we could extract.
    """
    findings = _parse_findings(stdout)
    return PaperAuditResult(
        paper=paper,
        paper_dir=paper_dir,
        exit_code=exit_code,
        findings=findings,
        raw_stdout=stdout,
        raw_stderr=stderr,
        started_at=started_at,
        ended_at=ended_at,
    )


def _parse_findings(stdout: str) -> list[Finding]:
    """Parse the 'DETAILED FINDINGS' section of a verify output."""
    findings = []
    # Find the 'DETAILED FINDINGS' section.
    marker = 'DETAILED FINDINGS'
    idx = stdout.find(marker)
    if idx < 0:
        return findings
    body = stdout[idx + len(marker):]
    # Each finding is:
    #   [SEVERITY] Cn  (line N)
    #       message
    #       (possibly more indented lines)
    #   [SEVERITY] C(m+1)  ...
    # We split on the [..] headers.
    lines = body.split('\n')
    i = 0
    current_severity = None
    current_category = None
    current_line = -1
    current_message_lines = []
    while i < len(lines):
        line = lines[i]
        m = _FINDING_HEADER_RE.match(line)
        if m:
            # Flush the previous finding
            if current_category is not None:
                findings.append(Finding(
                    category=current_category,
                    message='\n'.join(current_message_lines).strip(),
                    line=current_line,
                    severity=current_severity,
                ))
            current_severity = m.group(1)
            current_category = m.group(2)
            current_line = int(m.group(3)) if m.group(3) != 'global' else -1
            current_message_lines = []
        elif line.startswith('    ') and current_category is not None:
            # Indented body line
            current_message_lines.append(line.strip())
        i += 1
    # Flush the last finding
    if current_category is not None:
        findings.append(Finding(
            category=current_category,
            message='\n'.join(current_message_lines).strip(),
            line=current_line,
            severity=current_severity,
        ))
    return findings


def _format_timestamp(ts: float) -> str:
    """Format a unix timestamp as an ISO 8601 string."""
    if ts <= 0:
        return 'N/A'
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def render_markdown(
    results: list[PaperAuditResult],
    started_at: float,
    ended_at: float,
    tmaudit_version: str = 'dev',
    cache_used: bool = False,
) -> str:
    """Render a list of PaperAuditResults as a Markdown report.

    The report has 4 sections:
      1. Header (run metadata, aggregate counts)
      2. Summary table (one row per paper)
      3. Per-paper details (findings, exit code, etc.)
      4. Footer (timing, version, cache state)
    """
    lines = []
    # ----- Header -----
    lines.append('# tmaudit audit-all report')
    lines.append('')
    n_total = len(results)
    n_pass = sum(1 for r in results if r.passed)
    n_fail = n_total - n_pass
    n_high = sum(r.n_high for r in results)
    n_medium = sum(r.n_medium for r in results)
    n_low = sum(r.n_low for r in results)
    n_findings = sum(r.n_findings for r in results)

    lines.append(f'- **Run started**: {_format_timestamp(started_at)}')
    lines.append(f'- **Run ended**:   {_format_timestamp(ended_at)}')
    lines.append(f'- **Duration**:    {ended_at - started_at:.2f}s')
    lines.append(f'- **tmaudit version**: {tmaudit_version}')
    lines.append(f'- **Cache used**: {"yes" if cache_used else "no"}')
    lines.append(f'- **Total papers**: {n_total}')
    lines.append('')
    if n_fail == 0:
        lines.append('## :white_check_mark: All papers passed')
    else:
        lines.append(f'## :x: {n_fail} of {n_total} papers failed')
    lines.append('')
    lines.append(
        f'**Aggregate findings**: {n_findings} total '
        f'({n_high} HIGH, {n_medium} MEDIUM, {n_low} LOW)'
    )
    lines.append('')
    # Evidence axis: how sure we are, independent of how bad it is. See
    # tmaudit.evidence for why a PARTIAL finding alone must not gate.
    if n_findings:
        tiers = {'CONFIRMED': 0, 'PARTIAL': 0, 'UNSUBSTANTIATED': 0}
        for r in results:
            for f in r.findings:
                tiers[evidence_tier_of(f.category)] = \
                    tiers.get(evidence_tier_of(f.category), 0) + 1
        lines.append(
            f'**Aggregate evidence**: {tiers["CONFIRMED"]} CONFIRMED, '
            f'{tiers["PARTIAL"]} PARTIAL (proxy-based — review, do not gate alone), '
            f'{tiers["UNSUBSTANTIATED"]} UNSUBSTANTIATED'
        )
        lines.append('')
    # ----- Summary table -----
    lines.append('## Summary')
    lines.append('')
    lines.append('| Paper | Status | Exit | Findings | HIGH | MEDIUM | LOW | Duration |')
    lines.append('|------:|:------:|:----:|:--------:|:----:|:------:|:---:|:---------|')
    for r in results:
        status = ':white_check_mark: PASS' if r.passed else ':x: FAIL'
        lines.append(
            f'| {r.paper} | {status} | {r.exit_code} | '
            f'{r.n_findings} | {r.n_high} | {r.n_medium} | {r.n_low} | '
            f'{r.duration_seconds:.2f}s |'
        )
    lines.append('')
    # ----- Per-paper details -----
    for r in results:
        lines.append('---')
        lines.append('')
        lines.append(f'## Paper {r.paper}')
        lines.append('')
        lines.append(f'- **Directory**: `{r.paper_dir}`')
        lines.append(f'- **Exit code**: {r.exit_code}')
        lines.append(f'- **Findings**: {r.n_findings} '
                     f'({r.n_high} HIGH, {r.n_medium} MEDIUM, {r.n_low} LOW)')
        lines.append(f'- **Started**: {_format_timestamp(r.started_at)}')
        lines.append(f'- **Ended**:   {_format_timestamp(r.ended_at)}')
        lines.append(f'- **Duration**: {r.duration_seconds:.2f}s')
        lines.append('')
        if not r.findings:
            lines.append(':white_check_mark: **No issues detected.**')
            lines.append('')
        else:
            # Group by category
            by_category: dict[str, list[Finding]] = {}
            for f in r.findings:
                by_category.setdefault(f.category, []).append(f)
            lines.append('### Findings')
            lines.append('')
            for cat in sorted(by_category.keys()):
                cat_findings = by_category[cat]
                tier = evidence_tier_of(cat)
                lines.append(f'#### {cat} ({len(cat_findings)} finding(s)) '
                             f'— evidence: {tier}')
                lines.append('')
                for f in cat_findings:
                    loc = f'line {f.line}' if f.line > 0 else 'global'
                    lines.append(f'- **[{f.severity}] {f.category}** ({loc}) '
                                 f'— evidence: {evidence_tier_of(f.category)}')
                    # Indent the message
                    msg_lines = f.message.split('\n')
                    for ml in msg_lines:
                        lines.append(f'  {ml}')
                lines.append('')
    # ----- Footer -----
    lines.append('---')
    lines.append('')
    lines.append('## Run metadata')
    lines.append('')
    lines.append('- Generated by: `tmaudit audit-all`')
    lines.append(f'- tmaudit version: {tmaudit_version}')
    lines.append(f'- Timestamp: {_format_timestamp(ended_at)}')
    lines.append(f'- Duration: {ended_at - started_at:.2f}s')
    lines.append(f'- Total papers: {n_total} ({n_pass} pass, {n_fail} fail)')
    lines.append(f'- Total findings: {n_findings} '
                 f'({n_high} HIGH, {n_medium} MEDIUM, {n_low} LOW)')
    lines.append('')
    return '\n'.join(lines)


def write_markdown_report(
    path: Path,
    results: list[PaperAuditResult],
    started_at: float,
    ended_at: float,
    tmaudit_version: str = 'dev',
    cache_used: bool = False,
) -> None:
    """Render and write the Markdown report to `path`.

    Convenience function: combines `render_markdown()` and
    `path.write_text()`.
    """
    md = render_markdown(
        results,
        started_at=started_at,
        ended_at=ended_at,
        tmaudit_version=tmaudit_version,
        cache_used=cache_used,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding='utf-8')
