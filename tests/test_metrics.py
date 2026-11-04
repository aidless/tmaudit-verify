"""Golden-value tests for tmaudit.metrics.

Every expected value is hand-computed from the DCG/IDCG definition
(1/log2(rank+1), rank from 1) rather than derived from the code
under test, so a wrong implementation cannot agree with itself.

Also pins the two behavioural differences against the ruflo ADR-081
implementation they were ported from, so the divergence is a
documented decision and not a silent drift.
"""
from __future__ import annotations
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tmaudit.metrics import (
    aggregate, is_relevant, mrr_at_k, ndcg_at_k, ndcg_at_k_standard,
    precision_at_k,
)

G2 = 1 / math.log2(3)   # rank 2 gain
G3 = 1 / math.log2(4)   # rank 3 gain


class TestNdcg:
    def test_all_relevant_is_one(self):
        assert ndcg_at_k([1, 1, 1], 3) == 1.0

    def test_relevant_at_rank1_is_one(self):
        assert ndcg_at_k([1, 0, 0], 3) == 1.0

    def test_relevant_at_rank2(self):
        assert ndcg_at_k([0, 1, 0], 3) == pytest_approx(G2)

    def test_relevant_at_rank3(self):
        assert ndcg_at_k([0, 0, 1], 3) == pytest_approx(G3)

    def test_two_relevant_packed_first_is_one(self):
        assert ndcg_at_k([1, 1, 0], 3) == 1.0

    def test_relevant_at_rank2_and_3(self):
        assert ndcg_at_k([0, 1, 1], 3) == pytest_approx((G2 + G3) / (1 + G2))

    def test_no_relevant_is_zero(self):
        assert ndcg_at_k([0, 0, 0], 3) == 0.0

    def test_k_truncates(self):
        # the rank-3 relevant item is outside k=2, so it cannot count
        assert ndcg_at_k([1, 0, 1], 2) == 1.0

    def test_standard_ideal_uses_corpus_total(self):
        # 3 relevant in corpus, one recalled at rank 1
        ideal3 = 1 + G2 + G3
        assert ndcg_at_k_standard([1, 0, 0], 3, 3) == pytest_approx(1 / ideal3)

    def test_standard_agrees_with_original_when_recall_complete(self):
        assert ndcg_at_k_standard([1, 1, 1], 3, 3) == 1.0

    def test_original_overstates_when_recall_incomplete(self):
        """The ported-from behaviour, pinned so it cannot drift unnoticed."""
        ideal3 = 1 + G2 + G3
        original = ndcg_at_k([1, 0, 0], 3)
        standard = ndcg_at_k_standard([1, 0, 0], 3, 3)
        assert original == 1.0
        assert standard < 0.5
        assert original / standard == pytest_approx(ideal3, rel=1e-9)

    def test_zero_total_relevant_is_zero(self):
        assert ndcg_at_k_standard([1, 0, 0], 3, 0) == 0.0


class TestPrecision:
    def test_two_of_three(self):
        assert precision_at_k([1, 1, 0], 3) == pytest_approx(2 / 3)

    def test_short_list_not_penalised(self):
        # two results, both relevant -> 1.0, not 2/3
        assert precision_at_k([1, 1], 3) == 1.0

    def test_divide_by_k_reproduces_original(self):
        assert precision_at_k([1, 1], 3, divide_by_k=True) == pytest_approx(2 / 3)

    def test_no_relevant_is_zero(self):
        assert precision_at_k([0, 0, 0], 3) == 0.0

    def test_empty_list_is_zero(self):
        assert precision_at_k([], 3) == 0.0


class TestMrr:
    def test_rank1(self):
        assert mrr_at_k([1, 0, 0], 3) == 1.0

    def test_rank2(self):
        assert mrr_at_k([0, 1, 0], 3) == pytest_approx(0.5)

    def test_rank3(self):
        assert mrr_at_k([0, 0, 1], 3) == pytest_approx(1 / 3)

    def test_no_relevant(self):
        assert mrr_at_k([0, 0, 0], 3) == 0.0

    def test_relevant_beyond_k_is_zero(self):
        assert mrr_at_k([0, 0, 0, 1], 3) == 0.0


class TestRelevance:
    def test_substring_match_is_case_insensitive(self):
        assert is_relevant('Fix Self-Learning wiring', ['self-learning']) is True

    def test_no_match(self):
        assert is_relevant('bump release 3.10.11', ['self-learning']) is False

    def test_empty_labels(self):
        assert is_relevant('anything', []) is False

    def test_any_of_many_labels(self):
        assert is_relevant('crypto.randomUUID hardening',
                           ['cwe-347', 'crypto.randomuuid']) is True

    def test_none_name(self):
        assert is_relevant(None, ['x']) is False


class TestAggregate:
    def test_means(self):
        agg = aggregate([[1, 0, 0], [0, 1, 0]], k=3)
        assert agg.n == 2
        assert agg.ndcg == pytest_approx((1 + G2) / 2)
        assert agg.mrr == pytest_approx(0.75)

    def test_empty(self):
        agg = aggregate([], k=3)
        assert agg.n == 0 and agg.ndcg == 0.0

    def test_standard_mode_with_totals(self):
        agg = aggregate([([1, 0, 0], 3)], k=3, standard=True)
        assert agg.ndcg == pytest_approx(1 / (1 + G2 + G3))


def pytest_approx(expected, rel=None, abs=None):
    """Local approx so this file needs no pytest import at module scope."""
    import pytest
    return pytest.approx(expected, rel=rel, abs=abs)
