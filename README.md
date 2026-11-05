# tmaudit-verify

A process can exit 0 without producing the artifact it claims.
This repository measures the artifact, the witness, and the package bytes.
It does not replace the paper auditor.

## Relationship to aidless/tmaudit

[aidless/tmaudit](https://github.com/aidless/tmaudit) is the paper-audit CLI:
it reads a LaTeX paper and reports reviewable defects. This fork is a
complement. It keeps that code so the checks below can run on a manuscript,
and it adds the verification surface that is not the release channel:
artifact verdicts (`PASS` / `FAIL` / `UNVERIFIABLE`), the witness ledger,
and the evidence axis on a finding.

Install and issues for the auditor stay on the upstream repository.
This fork is not published to PyPI. There is no download count here.

## Verify offline

These commands use the committed `tmaudit.pyz` and the standard library.
They do not install from PyPI and they do not need a network.

```bash
python3 tmaudit.pyz --version
python3 _check_pyz_fresh.py
python3 tmaudit.pyz artifacts README.md --format text --min-bytes 100
python3 tmaudit.pyz artifacts --spec examples/artifact-spec.json
python3 tmaudit.pyz verify --paper-dir examples/sample-paper
```

`_check_pyz_fresh.py` exits 0 only when `tmaudit.pyz` matches `src/tmaudit/`
and contains no bytecode. The spec command is expected to exit 1: its four
paths are not in this tree, and a missing file is `FAIL`, not a silent pass.
`verify --paper-dir` runs the upstream audit on `examples/sample-paper`.
What that audit means is documented on aidless/tmaudit. This page does not
restate it.

The test suite is a separate check. `pip install -e ".[dev]"` needs a network
the first time. After that, the CI command is the one in the next section.

## Suite

Fast suite (`python3 -m pytest -m "not slow"`): 530 selected, 5 deselected.
CI runs that selection on Python 3.10, 3.11, and 3.12.

That sentence is checked by `tests/test_claims_drift.py` against
`pytest --collect-only`. It is a collection count, not a frozen pass total.
`pyproject.toml` declares Python 3.9; this fork's CI does not run 3.9.

Deselected tests need trees this repository does not contain: the arXiv
corpus under `case-studies/arxiv-corpus/_corpus`, and the
`PAPER*_CONSOLIDATED` directories used by `TestEndToEndAudit`. The count
above assumes `_corpus` is absent. A checkout that has fetched it collects
more slow tests, and the drift guard fails rather than publishing that
private count.

`tests/test_package_data.py` opens `dist/*.whl` when a wheel is present and
skips when it is not. CI runs `python -m build` first, so the job opens the
wheel. A skip is not a pass of the packaging check.

## What exit 0 does not mean

- An artifact `PASS` is a format and declared-content check. A well-formed
  file with the wrong numbers still passes. `UNVERIFIABLE` is not a pass; a
  run whose every artifact is unverifiable exits 2.
- `witness verify` exit 0 means every marker line is present. It does not
  mean the bytes match the recorded digest, and the ledger is unsigned.
- The tool does not fetch a paper, a rule pack, or an artifact.

The holes, including ones a green suite used to miss, are in
[FAILURE_MODES.md](FAILURE_MODES.md).

## License

MIT, same as upstream. See [LICENSE](LICENSE).
