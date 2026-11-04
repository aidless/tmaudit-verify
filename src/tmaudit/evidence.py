"""tmaudit.evidence — the evidence axis of a finding.

A tmaudit finding currently carries two attributes: a category
(C1..C10) and a severity (HIGH / MEDIUM / LOW). Both answer
"how bad is it". Neither answers "how sure are we".

This module adds the third axis, **evidence tier**, ported from
the ruflo audit protocol (see ruflo's
`docs/reviews/intelligence-system-audit-2026-05-29.md`):

    CONFIRMED       the detector re-derived the fact from the
                    audited artefact, so a false positive would
                    require the recomputation itself to be wrong
    PARTIAL         the detector matched a textual or structural
                    proxy; the underlying claim may still be
                    false (over-report) or true but unmatched
                    (under-report)
    UNSUBSTANTIATED the detector names a suspicion it did not
                    reproduce

The distinction is not cosmetic. ruflo's ADR-081 measured a regex
relevance proxy that *under*-reported one configuration by 10
points and *over*-reported another by 10 points; the two errors
cancelled in aggregate and looked like agreement. A text-pattern
detector is exactly that kind of proxy, so it is labelled PARTIAL
by construction rather than by confidence.

Gate semantics (see `gate`):

    UNSUBSTANTIATED   never blocks a release decision
    PARTIAL           blocks only when corroborated by a second,
                      independent PARTIAL finding in the same
                      category, or by any CONFIRMED finding
    CONFIRMED         blocks on its own

Rationale per category is recorded in ``CHECK_EVIDENCE`` and is
deliberately reviewable: if a detector is upgraded to re-derive
its claim, its tier changes here and nowhere else.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    'CONFIRMED',
    'PARTIAL',
    'UNSUBSTANTIATED',
    'TIERS',
    'CHECK_EVIDENCE',
    'CHECK_RATIONALE',
    'tier_of',
    'annotate',
    'gate',
    'evidence_summary',
]

CONFIRMED = 'CONFIRMED'
PARTIAL = 'PARTIAL'
UNSUBSTANTIATED = 'UNSUBSTANTIATED'

TIERS = (CONFIRMED, PARTIAL, UNSUBSTANTIATED)

# What each detector actually proves. A tier belongs to the
# detector's method, not to the severity of what it found.
CHECK_EVIDENCE: dict[str, str] = {
    # Deterministic key resolution: the key is in the .bib or it
    # is not. There is no proxy step to be wrong.
    'C1': PARTIAL,     # symbol-definition scan over the abstract
    'C2': PARTIAL,     # arithmetic consistency of stated numbers
    'C3': PARTIAL,     # presence of a formal definition
    'C4': CONFIRMED,   # citation key resolution against the .bib
    'C5': PARTIAL,     # extracted n / effect size as written
    'C6': PARTIAL,     # blacklist regex over prose
    'C7': PARTIAL,     # engaged-vs-ceremonial heuristic
    'C8': CONFIRMED,   # recomputes Cohen's d and power from the table
    'C9': PARTIAL,     # caption vs figure block, not the rendered figure
    'C10': PARTIAL,    # presence / future-tense phrasing
}

CHECK_RATIONALE: dict[str, str] = {
    'C1': 'Scans the abstract for symbols used without definition; a symbol '
          'may be defined elsewhere or the scan may miss an inline definition.',
    'C2': 'Checks the stated Bonferroni arithmetic for internal consistency; '
          'it cannot re-derive the multiplicity from the design.',
    'C3': 'Detects that a concept is formalised somewhere; whether the '
          'formalisation is the right one is out of reach.',
    'C4': 'A citation key either resolves in the .bib or it does not. '
          'Deterministic, no proxy step.',
    'C5': 'Reads sample sizes and effect sizes as written; a mislabelled '
          'table column propagates silently.',
    'C6': 'Blacklisted vocabulary is a lexical proxy for the actual fault. '
          'ruflo ADR-081 measured a proxy of this shape being wrong in both '
          'directions at once.',
    'C7': 'The engaged/ceremonial classifier is a sentence-shape heuristic. '
          'A genuinely engaged citation written unusually reads as '
          'ceremonial, and a ceremonial one written unusually reads as engaged.',
    'C8': 'Recomputes Cohen\'s d and achieved power from the table\'s own '
          'numbers; a false positive requires the recomputation to be wrong.',
    'C9': 'Compares the caption against the figure block as text; the '
          'rendered axes and plotted series are not inspected.',
    'C10': 'Availability statements are detected by phrasing; a statement '
           'present in spirit but not in the expected words is missed.',
}


def tier_of(category: str) -> str:
    """Evidence tier for a finding category. Unknown categories default to
    UNSUBSTANTIATED — an unclassified detector must not look trustworthy."""
    return CHECK_EVIDENCE.get(category, UNSUBSTANTIATED)


@dataclass
class Evidence:
    """One finding's evidence tier plus the reason, for reporting."""

    tier: str
    rationale: str

    @property
    def blocks_alone(self) -> bool:
        return self.tier == CONFIRMED


def annotate(category: str) -> Evidence:
    return Evidence(tier=tier_of(category),
                    rationale=CHECK_RATIONALE.get(category, 'Unclassified detector.'))


def gate(findings: list[tuple[str, str, int]],
         severities: dict[str, str] | None = None) -> dict[str, object]:
    """Decide whether a set of findings should block a release.

    ``findings`` is a list of ``(category, message, line)`` tuples, the
    format every ``check_cN_*`` returns. ``severities`` optionally maps
    category -> severity; when omitted, report.SEVERITY_MAP is used so the
    gate and the report agree.

    Returns a dict with ``blocked``, ``reason``, and the tier breakdown.
    """
    from .report import SEVERITY_MAP

    sev = severities or SEVERITY_MAP
    tiers = [tier_of(c) for c, _m, _l in findings]

    confirmed = [f for f, t in zip(findings, tiers) if t == CONFIRMED]
    partial = [f for f, t in zip(findings, tiers) if t == PARTIAL]
    unsub = [f for f, t in zip(findings, tiers) if t == UNSUBSTANTIATED]

    # A PARTIAL finding blocks only when it is not alone: either a second
    # PARTIAL finding in the same category, or a CONFIRMED finding anywhere.
    from collections import Counter
    per_category = Counter(f[0] for f in partial)
    corroborated = [f for f in partial if per_category[f[0]] > 1] + confirmed

    blocked = bool(corroborated)
    if blocked:
        reason = 'CONFIRMED finding(s) present' if confirmed else \
                 'PARTIAL findings corroborated within one category'
    elif partial:
        reason = 'PARTIAL findings present but uncorroborated — review, do not gate'
    elif unsub:
        reason = 'UNSUBSTANTIATED findings only — label, never gate'
    else:
        reason = 'no findings'

    return {
        'blocked': blocked,
        'reason': reason,
        'confirmed': len(confirmed),
        'partial': len(partial),
        'unsubstantiated': len(unsub),
        'gate_findings': [f for f, _s in zip(findings, [sev.get(c, 'UNKNOWN') for c, _m, _l in findings])],
    }


def evidence_summary(findings: list[tuple[str, str, int]]) -> str:
    """One-line tier breakdown for a report header."""
    counts = {t: 0 for t in TIERS}
    for c, _m, _l in findings:
        counts[tier_of(c)] += 1
    return (f"evidence: {counts[CONFIRMED]} CONFIRMED / "
            f"{counts[PARTIAL]} PARTIAL / {counts[UNSUBSTANTIATED]} UNSUBSTANTIATED")
