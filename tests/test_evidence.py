"""Tests for the evidence axis: tier assignment and gate semantics.

The gate rule is the point of the module — a PARTIAL finding alone
must not block a release, because a text-pattern detector is a
proxy and proxies were measured being wrong in both directions at
once (ruflo ADR-081). These tests pin that rule so a future edit
cannot quietly turn a heuristic into a release blocker.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tmaudit.evidence import (
    CONFIRMED, PARTIAL, UNSUBSTANTIATED, TIERS, annotate, gate,
    tier_of, evidence_summary,
)


class TestTierAssignment:
    def test_recomputing_detectors_are_confirmed(self):
        # C4 resolves citation keys against the .bib; C8 recomputes d and
        # power from the table's own numbers.
        assert tier_of('C4') == CONFIRMED
        assert tier_of('C8') == CONFIRMED

    def test_text_pattern_detectors_are_partial(self):
        for category in ('C1', 'C2', 'C3', 'C5', 'C6', 'C7', 'C9', 'C10'):
            assert tier_of(category) == PARTIAL, category

    def test_unknown_category_is_unsubstantiated(self):
        """An unclassified detector must not look trustworthy."""
        assert tier_of('C99') == UNSUBSTANTIATED
        assert tier_of('') == UNSUBSTANTIATED

    def test_every_tier_has_a_rationale(self):
        for category in ('C1', 'C4', 'C7', 'C8'):
            assert annotate(category).rationale

    def test_only_confirmed_blocks_alone(self):
        assert annotate('C8').blocks_alone is True
        assert annotate('C7').blocks_alone is False
        assert annotate('C99').blocks_alone is False


class TestGate:
    def test_no_findings_does_not_block(self):
        result = gate([])
        assert result['blocked'] is False

    def test_confirmed_blocks_alone(self):
        result = gate([('C8', 'power below target', 120)])
        assert result['blocked'] is True
        assert result['confirmed'] == 1

    def test_single_partial_does_not_block(self):
        """One heuristic hit is a review signal, not a gate."""
        result = gate([('C7', 'ceremonial citation', 88)])
        assert result['blocked'] is False
        assert 'uncorroborated' in result['reason']

    def test_two_partial_in_same_category_blocks(self):
        result = gate([('C7', 'ceremonial citation', 88),
                       ('C7', 'ceremonial citation', 140)])
        assert result['blocked'] is True
        assert result['partial'] == 2

    def test_two_partial_in_different_categories_do_not_block(self):
        result = gate([('C7', 'ceremonial citation', 88),
                       ('C6', 'blacklisted word', 12)])
        assert result['blocked'] is False

    def test_unsubstantiated_never_blocks(self):
        result = gate([('C99', 'suspicious', 1)])
        assert result['blocked'] is False
        assert 'never gate' in result['reason']

    def test_partial_plus_confirmed_blocks(self):
        result = gate([('C7', 'ceremonial citation', 88),
                       ('C4', 'missing bib key', 12)])
        assert result['blocked'] is True
        assert result['confirmed'] == 1 and result['partial'] == 1

    def test_summary_counts(self):
        line = evidence_summary([('C8', 'a', 1), ('C7', 'b', 2), ('C99', 'c', 3)])
        assert line == 'evidence: 1 CONFIRMED / 1 PARTIAL / 1 UNSUBSTANTIATED'
