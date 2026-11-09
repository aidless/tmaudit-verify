# tmaudit-verify

[![CI](https://github.com/aidless/tmaudit-verify/actions/workflows/ci.yml/badge.svg)](https://github.com/aidless/tmaudit-verify/actions/workflows/ci.yml)

The verification-side fork of [`aidless/tmaudit`](https://github.com/aidless/tmaudit):
the same paper auditor, plus the artifact/evidence/witness tooling that never
shipped to the main repository or to PyPI.

This fork is **not published to PyPI**. Install it from a checkout.

```bash
git clone https://github.com/aidless/tmaudit-verify.git && cd tmaudit-verify
python3 -m pip install -r requirements.lock
python3 -m pip install -e . --no-deps && python3 -m pip install -e ./tmaudit_example_plugin --no-deps
python3 -m pytest -m "not slow" -q
```

Expected on Python 3.12: `511 passed, 1 skipped, 7 deselected`.

## What this repository is

`aidless/tmaudit` is the released audit CLI: it reads a LaTeX paper and reports
reviewable defects (missing code/data statement, unreferenced figures, ceremonial
citations, unpowered significance claims). This repository started as a parallel
`0.7.0` line that added `--target` and `admission`, then merged the released
`0.5.2` line, and finally grew a separate question:

> a tool that exits `0` has not necessarily produced the artifact it claims.

Everything below is in this repository only. The main repository is untouched
by this fork and remains the release channel.

### What the fork adds

| Module / command | What it does | Contract |
|---|---|---|
| `tmaudit artifacts` | Checks produced files against a spec: format, byte size, mtime, ZIP members, PDF page count, PNG dimensions, required/forbidden text, Python syntax | three verdicts (`PASS` / `FAIL` / `UNVERIFIABLE`) and graded evidence `E0..E4`; exit `1` on failure, `2` when nothing could be checked |
| `tmaudit witness` | Temporal regression ledger: records load-bearing fix markers with the surrounding commit and locates the commit that removed one | SHA-256 integrity, **unsigned by design** |
| `tmaudit.evidence` | Adds an evidence axis (`CONFIRMED` / `PARTIAL` / `UNSUBSTANTIATED`) to findings, so "how bad" is separated from "how sure" | gate semantics are explicit per tier |
| `tmaudit.metrics` | `precision@k`, `nDCG@k`, MRR with an explicit normalisation contract | both the historical and the standard nDCG are exposed |
| `--target` / `admission` | Audit an external paper with an external rule pack; statistical admission certificate | stdlib only |

All modules keep the package's `dependencies = []` contract.

## Minimal runnable checks

No install needed for these; the committed `tmaudit.pyz` is rebuilt from `src/`.

```bash
python3 tmaudit.pyz --version
python3 tmaudit.pyz artifacts README.md --format text --min-bytes 100
```

```text
PASS           E4 PARSED            5,466B  README.md
1 artifact(s): 1 pass, 0 fail, 0 unverifiable; weakest evidence PARSED
```

A missing artifact is `FAIL`, never a silent pass (exit code `1`):

```bash
python3 tmaudit.pyz artifacts --spec examples/artifact-spec.json
```

The four entries in `examples/artifact-spec.json` point at files this repository
does not ship, so this command exits `1` with four `FAIL` rows. That is the
intended demo, not a broken install.

The audit itself is unchanged from upstream:

```bash
python3 tmaudit.pyz verify --paper-dir examples/sample-paper
python3 tmaudit.pyz list
```

## What this repository can prove

- That an artifact exists, has a declared container format, a minimum size, a
  minimum modification time, the expected ZIP members, PNG dimensions, or a
  plausible PDF page count — measured from the bytes, not from the producer's
  exit code.
- That declared text is present or absent in a text artifact, and that a
  generated Python file parses.
- That `tmaudit.pyz` matches the current `src/tmaudit/` tree with no bytecode
  (`python3 _check_pyz_fresh.py`).
- That the bundled test suite passes on the Python versions CI runs
  (3.10, 3.11, 3.12).

## What it cannot prove

- **Correctness of content.** `PASS` bounds format conformance and declared
  content presence. A well-formed PDF with the wrong numbers passes.
- **That a check happened.** `UNVERIFIABLE` is a first-class verdict: "could not
  check" never equals "checked and fine". A run whose every artifact is
  unverifiable exits `2`, not `0`.
- **Authorship or release authenticity.** `witness` hashes and records git
  commits but deliberately does not sign: a signature keyed off a public commit
  proves integrity, not who produced it. The module claims no such guarantee.
- **Semantic quality of an audit finding.** Evidence tiers say how directly a
  detector re-derived a claim; they do not make a `PARTIAL` proxy finding true.
- **Network behaviour.** The tool is offline and stdlib-only; it will not fetch
  a paper, a rule pack, or an artifact.

## Repository layout

```
src/tmaudit/artifacts.py     artifact-side verification (three verdicts)
src/tmaudit/evidence.py      evidence tiers for findings
src/tmaudit/metrics.py       ranking metrics with explicit normalisation
src/tmaudit/witness.py       temporal regression ledger
examples/artifact-spec.json  runnable spec exercising each failure mode
MERGE_CEILING.md             measured merge report for the 0.6.0 line
DIVERGENCE_ANALYSIS.md       what diverged from upstream, and why
```

## Relationship and status

- Upstream release channel: <https://github.com/aidless/tmaudit> (MIT).
- This repository is a fork, not a replacement. No pull requests, tags, PyPI
  uploads, or history rewrites are made from here against the main repository.
- Version `0.7.0`; the `CHANGELOG.md` records both the `0.6.0` merge and the
  later additions.

## License

MIT, same as upstream. See [LICENSE](LICENSE).
