"""tmaudit.metrics — ranking metrics with an explicit normalisation contract.

Ported from the metrics extracted out of ruflo's ADR-081 benchmark
(``scripts/benchmark-pretrained-retrieval.mjs``) after measuring that
implementation against hand-computed values.

Two corrections are carried over, both of which change reported numbers:

1. **``precision_at_k`` normalisation.** The original divides the
   relevant count by ``k`` unconditionally, so a query that returns
   two results, both relevant, scores 0.667 rather than 1.0 — the
   metric silently penalises short result lists. ``divide_by_k``
   reproduces the original behaviour for comparability; the default
   normalises by ``min(k, len(returned))``.

2. **``ndcg_at_k`` ideal-DCG source.** The original builds IDCG from
   the number of relevant items *found in the top-k*. The standard
   builds it from the number of relevant items *in the corpus*. When
   the corpus holds relevant items the top-k missed, the original
   reports a higher score: measured 1.000 vs 0.469 for the same
   ranking with three relevant items in the corpus and one recalled
   at rank 1 — a 2.13x overstatement exactly where recall is worst.
   ``ndcg_at_k`` keeps the original semantics so historical numbers
   stay reproducible; ``ndcg_at_k_standard`` is the standard form.
   Both are exposed so a report can state which one it used.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ['is_relevant', 'ndcg_at_k', 'ndcg_at_k_standard',
           'precision_at_k', 'mrr_at_k', 'aggregate', 'Metrics']


def is_relevant(name: str | None, expected_substrings) -> bool:
    """Binary relevance: ``name`` contains any labelled substring."""
    if not name or not expected_substrings:
        return False
    lower = str(name).lower()
    return any(s.lower() in lower for s in expected_substrings)


def _dcg(ranked, k: int) -> float:
    return sum(1.0 / math.log2(i + 2) for i, rel in enumerate(ranked[:k]) if rel)


def ndcg_at_k(ranked_relevance, k: int) -> float:
    """nDCG@k with IDCG from the relevant count *inside the top-k*.

    Reproduces the ruflo ADR-081 implementation. Use
    :func:`ndcg_at_k_standard` unless you need comparability with
    numbers produced by that benchmark.
    """
    arr = list(ranked_relevance)[:k]
    dcg = _dcg(arr, k)
    n_rel = sum(1 for r in arr if r)
    if n_rel == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
    return dcg / idcg if idcg > 0 else 0.0


def ndcg_at_k_standard(ranked_relevance, k: int, total_relevant: int) -> float:
    """nDCG@k with IDCG from ``total_relevant`` items in the corpus.

    Requires the labelled total. Returns 0.0 when the corpus holds no
    relevant items for the query.
    """
    arr = list(ranked_relevance)[:k]
    dcg = _dcg(arr, k)
    ideal_n = min(k, total_relevant)
    if ideal_n == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_n))
    return dcg / idcg if idcg > 0 else 0.0


def precision_at_k(ranked_relevance, k: int, *, divide_by_k: bool = False) -> float:
    """Precision@k. Normalises by ``min(k, len(returned))`` by default."""
    arr = list(ranked_relevance)
    if not arr:
        return 0.0
    denom = k if divide_by_k else min(k, len(arr))
    return sum(1 for r in arr[:k] if r) / denom


def mrr_at_k(ranked_relevance, k: int) -> float:
    """Reciprocal rank of the first relevant item within the top-k."""
    arr = list(ranked_relevance)[:k]
    for i, rel in enumerate(arr):
        if rel:
            return 1.0 / (i + 1)
    return 0.0


@dataclass(frozen=True)
class Metrics:
    n: int
    ndcg: float
    precision: float
    mrr: float


def aggregate(per_query, k: int = 3, *, standard: bool = False) -> Metrics:
    """Mean of each metric across queries.

    ``per_query`` is a list of boolean rankings. When ``standard`` is set,
    each entry may be a ``(ranking, total_relevant)`` pair so nDCG uses the
    corpus-normalised ideal.
    """
    n = len(per_query)
    if n == 0:
        return Metrics(0, 0.0, 0.0, 0.0)

    def ndcg_of(entry) -> float:
        if standard and isinstance(entry, tuple):
            ranking, total = entry
            return ndcg_at_k_standard(ranking, k, total)
        return ndcg_at_k(entry, k)

    return Metrics(
        n=n,
        ndcg=sum(ndcg_of(e) for e in per_query) / n,
        precision=sum(precision_at_k(e[0] if isinstance(e, tuple) else e, k)
                      for e in per_query) / n,
        mrr=sum(mrr_at_k(e[0] if isinstance(e, tuple) else e, k)
                for e in per_query) / n,
    )
