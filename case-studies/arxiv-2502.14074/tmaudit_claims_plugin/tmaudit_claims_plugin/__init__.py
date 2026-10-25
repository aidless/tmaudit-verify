"""tmaudit_claims_plugin — two reporting-standards checks.

Registers two general checks through the ``tmaudit.plugins`` entry-point
group (declared in ``pyproject.toml``):

1. ``claims-significance-no-test`` — significance wording with no
   hypothesis-test standard anywhere in the paper.
2. ``claims-percent-table-no-uncertainty`` — a percentage-bearing
   results table with no uncertainty marker, in a paper that reports
   intervals elsewhere.

Both are ``requires_config=False`` and read only the manuscript, so they
run against any paper via ``tmaudit plugins run NAME --paper-dir DIR``.

Install with::

    pip install -e ./case-studies/arxiv-2502.14074/tmaudit_claims_plugin
"""

__version__ = "0.1.0"
