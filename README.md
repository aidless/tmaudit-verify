# tmaudit

**Catch the reporting defects reviewers catch — before you submit.**

`tmaudit` audits the LaTeX source of a machine-learning paper for the things
that get flagged in review but are cheap to fix: a missing code/data statement,
unreported seeds and hyperparameters, a figure whose label is never referenced,
ceremonial citations, and significance claims with no power analysis. No API
key, no network, and no required dependencies.

[![CI](https://github.com/aidless/tmaudit/actions/workflows/ci.yml/badge.svg)](https://github.com/aidless/tmaudit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tmaudit)](https://pypi.org/project/tmaudit/)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Tests](https://img.shields.io/badge/tests-391%20passing-brightgreen)
![Meta--tests](https://img.shields.io/badge/meta--tests-14%2F14%20caught-success)
![Categories](https://img.shields.io/badge/audit%20categories-C1..C10-blue)
![PR%20Checks](https://img.shields.io/badge/PR%20checks-44%20checkboxes-blueviolet)
![Issues](https://img.shields.io/badge/issues-4%20templates-blueviolet)
![Security](https://img.shields.io/badge/security-policy%20in%20place-green)
![Version](https://img.shields.io/badge/version-0.6.0-blue)
![Roadmap](https://img.shields.io/badge/roadmap-through%20v0.5.0-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

```bash
pipx install tmaudit
tmaudit verify --paper-dir path/to/your/paper
```

Excerpt of real output from a deliberately flawed sample manuscript
([`examples/sample-paper/`](examples/sample-paper/)):

```text
Findings by category:
  C9  [MEDIUM]  1 finding(s)
  C10  [LOW]    5 finding(s)

[MEDIUM] C9  (global)
    MED: figure fig:unused is defined but never referenced in the body text
    (no \ref{fig:unused} or \autoref{fig:unused}). Reviewer §5 #9.

[LOW] C10  (global)
    HIGH: paper has no code/data availability statement (no
    \section{...Availability...}, no GitHub/GitLab/Zenodo URL, and no
    "code is available" phrase). Reviewer §5 #10.
```

## Four ways to use it

### (0) Audit a paper you do not own (`--target`, v0.6.0)

`--paper N` only works on this author's five directories. To audit any
other paper, drop a config next to it and use the same command:

```toml
# paper.toml, next to main.tex
schema = "tmaudit-target/1"

[paper]
name = "my-paper"          # optional: names the generated verify_my-paper.py
tex_basename = "main"      # optional
# bib = "references.bib"   # optional: auto-detected (.bib or compiled .bbl)

[checks]
c4_self_cite_prefix = "smith2025"

[[checks.c1_symbols]]
name = 'CAF'
token = '\\bCAF\\b'
definition = 'CAF.{0,80}='
```

```bash
tmaudit verify --target paper.toml          # forks verify_my-paper.py and runs it
tmaudit verify --target paper.toml --dry-run
```

Unknown keys are errors with a suggestion, not silent no-ops. `.json`
works too, for Python 3.9/3.10 without `tmaudit[toml]`.

Exit codes: `0` clean, `1` HIGH finding, `2` did not complete (missing
input or a crashed check), `3` ran but at least one category could not be
observed (e.g. C1 on a paper with no abstract).

### (A) Run the single-file `tmaudit.pyz` (zero install)

```bash
# on any machine with Python 3.9+
python tmaudit.pyz list
python tmaudit.pyz verify --paper 1
python tmaudit.pyz compile --paper 5
python tmaudit.pyz fix-unicode --paper 1
python tmaudit.pyz audit-all
```

The `.pyz` is a self-extracting Python zip archive; the user does not
need to `pip install` anything. The file is `~87 KB` and contains all
five `PAPER_CONFIGS` and all three templates.

This is the **recommended distribution form** for handing the tool
to a co-author or to the TMLR reviewers.

### (B) `pip install --editable .` (development)

```bash
git clone https://github.com/aidless/tmaudit
cd tmaudit
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pip install -e ./tmaudit_example_plugin   # the test suite expects this plugin
python -m pytest -q
```

Edits to `src/tmaudit/templates/*.py` or
`src/tmaudit/configs/*.py` are picked up immediately on the next
`tmaudit` invocation. This is the **recommended form for ongoing
development** of the templates themselves.

### (C) `pip install .` (deployment to a venv)

```bash
python -m venv .venv
source .venv/bin/activate           # or .venv\Scripts\activate on Windows
pip install .
tmaudit list
```

This produces a `tmaudit` console-script entry in the venv. The
template and config files are inside the wheel.

### (D) `pip install tmaudit` (from PyPI)

```bash
pip install tmaudit          # or: pipx install tmaudit
tmaudit list
```

Published on PyPI via trusted publishing (OIDC) from
`.github/workflows/publish-pypi.yml`; new versions are cut from GitHub
Releases. This is the quickest form for someone who just wants the CLI.

## What it checks

| Category | What it catches |
|---|---|
| **C4** | citations that do not resolve to a `.bib`/`.bbl` entry |
| **C5** | sample size and effect-size omissions |
| **C7** | ceremonial citations (cited, never engaged with) |
| **C8** | significance claims without a reported effect size or power analysis |
| **C9** | figures without a caption below the graphic; `fig:` labels never referenced |
| **C10** | no availability statement; missing seeds, hyperparameters, hardware, library versions |
| **C1–C3, C6** | per-paper rulepack for five specific manuscripts: symbol definition, Bonferroni consistency, formalization, hype vocabulary |

C4–C10 run on any LaTeX manuscript. C1–C3 and C6 are configuration-driven and
report **not applicable** on a paper the rulepack was not written for — that is
stated in the output, not silently reported as a pass.

## Scope, stated plainly

This is not a reviewer and does not judge novelty. It checks reporting
completeness against a fixed rulepack, and it tells you when a category did not
run. For checks the generic categories do not cover, write a plugin
([`docs/PLUGINS.md`](docs/PLUGINS.md)) — the contract is a function that
receives the paper root and returns `Finding` objects.

## Try it on the sample, no paper needed

```bash
git clone https://github.com/aidless/tmaudit
cd tmaudit
pipx install tmaudit          # or: pip install -e .
tmaudit verify --paper-dir examples/sample-paper
```

`verify` forks a `verify_generic.py` script into the target directory and runs
it. That file is the entire audit, in the open: read it, edit the thresholds, or
delete it after the run. It is generated, not a hidden binary.

## Extend it: your own checks

A plugin is a package exposing a function decorated with `@check` under the
`tmaudit.plugins` entry-point group. It receives the paper's root `.tex` and
returns `Finding` objects.

```bash
tmaudit plugins list
tmaudit plugins run my-check --paper-dir /path/to/your/paper
```

The full contract and a three-check example ship in
[`tmaudit_example_plugin/`](tmaudit_example_plugin/) and
[`docs/PLUGINS.md`](docs/PLUGINS.md).

## `tmaudit admission`: is a reported gain certifiable? (v0.6.0)

Paper audits ask whether a claim is *internally consistent*. A self-evolving
harness claim needs a different question: the revision was **selected against
the same evidence that is later reported as the result**, so a positive delta is
not by itself evidence of generalization.

`admission` implements the sufficient condition of arXiv:2610.18813 §4.2
(preprint; read, not re-derived):

```
Δ_k(H') ≤ Δ̂_k(H') + sqrt( 2 ln(KT/δ) / m )          eq. 8, "accept only candidates with negative upper bounds"
Δ̂_k(H') + sqrt( 2 ln(KT/δ) / m ) + 2η < 0           eq. 9, evaluator-vs-target gap bounded by η
```

```bash
# one claim: +7.3pp observed on 89 fresh tasks, K=5 candidates, T=10 rounds, δ=.05
tmaudit admission --gain 7.3 --tasks 89
# [NOT CERTIFIED] gain=+7.30pp  upper=+32.10pp  m=89  K=5  T=10  delta=0.05  eta=0.00pp
# note: certifying this gain would need tasks m >= 2,593

tmaudit admission --required-tasks 2.0        # invert eq. 8 → tasks m >= 34,539
tmaudit admission --grid                       # table of (m, minimum certifiable gain)
tmaudit admission --audit claims.json          # batch; exit 1 if any claim fails
```

Exit codes: `0` every claim certified, `1` at least one uncertified (so it
gates CI), `2` bad input.

**Two rules that decide most verdicts**, both from the source paper:

1. **`m` counts fresh independent *tasks*, not rollouts.** Extra rollouts on
   the same task raise precision without raising the sample size, so `--tasks`
   is not "number of runs". At K=5, T=10, δ=.05 and m=89 tasks, the smallest
   gain the rule can certify at all is **39.4 pp**; at m=500 it is 16.6 pp, and
   at m=2,000 it is 8.3 pp (`--grid` prints the whole table).
2. **η is not free.** The term enters eq. 9 as `2η` and sits on the *same* side
   as the confidence width, so an η of 2 pp adds 4 pp to the margin: a 7.3 pp
   gain moves from "needs 2,593 tasks" to "needs 12,687 tasks", and once
   `2η ≥ gain` no sample size certifies at all (`--eta-pp` then reports
   "no m suffices").

Also included: `retention_ledger()` for eq. (6) —
`E R_s(H_k) ≤ E R̂_s(H_s) + β_{s,s} + Σ ε_{s,u}` — where the per-round `ε`
terms are *separate assumptions* that accumulate, so once their sum reaches the
gain being defended the bound is vacuous by construction.

What the tool does **not** do: it certifies a *gain*, never a *cause*. A
certified delta still says nothing about which harness component produced it,
and the bound covers the historical task mixture, not an arbitrary future
distribution.

## Self-audit: the audit core on 25 real papers

The rulepack is per-paper by design, so the sharpest question a reader can
ask is: *what does this tool do on a paper its config was not written for?*
We ran all ten categories over **25 real arXiv `cs.CL` LaTeX sources**,
exactly as `main()` runs them.

It found four defects in the tool itself:

- the factory `CHECKS_CONFIG` was one specific paper's config, so a generic
  run fired that paper's checks against any document;
- "clean" could mean "did not run" — a category with no configuration
  reported zero findings, indistinguishable from a pass;
- one missing config key aborted the whole audit with a `KeyError`;
- the BibTeX key pattern fabricated "missing citation" findings for keys
  that were present in `refs.bib`, whenever a key sat on its own line.

**All four are fixed in v0.5.1**, with regression tests; the two smaller
findings (a `SyntaxWarning` on import, and an observation failure filed as a
HIGH finding) are fixed as well. The v0.5.0 findings are kept verbatim as
evidence, and the harness restores the v0.5.0 config so the config-driven
defects replay: [`case-studies/arxiv-corpus/`](case-studies/arxiv-corpus/README.md)
has the coverage matrix, the method, and what the numbers do **not**
establish.

### Round two (v0.6.0): the same corpus through `--target`

The v0.5.0 round ran through `PAPER_CONFIGS`, i.e. with configs the author
had written. The honest follow-up is to run the *external* path — the one a
stranger uses — over the same 25 sources, with a six-line config generated
per paper and nothing else tuned:

| Metric | v0.5.1 | v0.6.0 via `--target` |
|---|---|---|
| Papers completing the audit | 21 / 25 | **25 / 25** |
| Papers aborting (exit 2) | 4 | **0** |
| Papers with a category `[not observed]` | — | **0** |
| Papers whose bibliography resolved | 21 | **25** |
| Bibliography filenames handled | `refs.bib` | `main.bbl`, `bib.bib`, `references.bib` |

The three defects this round found are the ones v0.6.0 fixed: C4 did not
read `.bbl` (what an arXiv tarball actually ships), C1 crashed the entire
audit when a document had no `\begin{abstract}`, and the bibliography
filename was assumed rather than detected. Each aborted a *different*
paper, which is why one hand-chosen paper would not have found any of them.

Run install-free, from the built wheel, in an environment with no
third-party packages.

### Auditing a paper the rulepack was not written for

[`case-studies/arxiv-2502.14074/`](case-studies/arxiv-2502.14074/README.md)
runs the two public extension paths — `verify --paper-dir` and two plugin
checks — against one real paper (*Investigating Non-Transitivity in
LLM-as-a-Judge*, arXiv:2502.14074, ICML 2025). It reports two
reporting-standards observations, records three candidate weaknesses that
were checked and **withdrawn**, and surfaced a caption-parsing defect in
the tool (nested braces), fixed in this commit. Every input is pinned by
SHA-256; the results, and what the audit does **not** establish, are in its
README.

## v0.3.0 highlights

**Released: 2026-07-10.** This release adds 3 new audit categories
(C8, C9, C10) and brings the project to **10 categories, 176 unit
tests, 12/12 meta-test bugs caught, 5/5 papers auditable**.

| Category | What it checks | Severity | Always runs? |
|---|---|---|---|
| **C1** (v0.1.0) | Symbol inline definition | HIGH | Yes |
| **C2** (v0.1.0) | Bonferroni consistency | HIGH | Yes |
| **C3** (v0.1.0) | Formalization of key concept | MEDIUM | Yes |
| **C4** (v0.1.0) | Self-citation threshold | MEDIUM | Yes |
| **C5** (v0.1.0) | Test-name d | MEDIUM | Yes |
| **C6** (v0.1.1) | Blacklist word frequency | LOW | Yes |
| **C7** (v0.1.2) | Ceremonial citation detection | MEDIUM | Yes |
| **C8** (v0.3.0) | **Statistical power** (d-mismatch, post-hoc power) | HIGH/MED | No (opt-in) |
| **C9** (v0.3.0) | **Figure-caption consistency** (4 sub-checks) | HIGH/MED | Yes (sub-check 3 opt-in) |
| **C10** (v0.3.0) | **Reproducibility** (availability, metadata, consistency) | HIGH/MED/LOW | Yes (sub-check 2 opt-in) |
| **C7-LLM** (v0.2.0) | LLM fallback for C7 borderline cases (opt-in via `TMAUDIT_LLM_*` env) | MEDIUM | No |

**v0.2.0 added** (still shipping): `audit-all --output report.md`
generates a single Markdown report covering all papers; the report
is uploaded as a CI artefact.

**v0.2.0 added** (still shipping): per-paper config for Paper 2,
Paper 3, Paper 4 (was placeholder in v0.1.1). All 5 papers
(P1..P5) are now auditable.

**Per-paper config** for v0.3.0: `c8_claimed_effects` (statistical),
`c9_figure_keywords` (figure-caption), `c10_reproducibility_claims`
(reproducibility). Empty list = opt-out (with graceful degradation
in C9 and C10).

See [`RELEASE_NOTES_v0.3.0.md`](./RELEASE_NOTES_v0.3.0.md) for the
full release notes and [`engineering_notes_verify_template.md`](./engineering_notes_verify_template.md)
§12 (C8+C10) and §13 (C9) for the design rationale.

## CLI reference

```text
tmaudit list                              # show all known paper configs
tmaudit verify --paper N [--dry-run]      # fork verify_pN.py + run audit
tmaudit compile --paper N [--dry-run]     # fork _compile_check.py + 4-pass build
tmaudit fix-unicode --paper N [--dry-run] # fork _fix_abstract_unicode.py
tmaudit audit-all [--start 1] [--end 5]   # verify all papers in a range
tmaudit verify --target paper.toml        # audit a paper you do not own (v0.6.0)
tmaudit admission --gain PP --tasks M     # certify a reported gain (v0.6.0)
```

Every paper subcommand also accepts `--paper-dir PATH` to override the
default paper directory.

## The standard 3-step protocol for any new paper

```powershell
cd F:\Research\PAPER<N>_CONSOLIDATED

# 1. audit
tmaudit verify --paper N

# 2. fix abstract Unicode (if any finding)
tmaudit fix-unicode --paper N
tmaudit verify --paper N

# 3. compile
tmaudit compile --paper N
```

## Package layout

```
TEMPLATE/
├── pyproject.toml                            # build config
├── tmaudit.pyz                               # single-file distribution (64 KB)
├── README.md                                 # this file
├── engineering_notes_verify_template.md      # 6-bug engineering diary
├── _setup_pkg.py                             # one-time: copy templates into src/
├── _build_pyz.py                             # rebuild tmaudit.pyz after any src/ change
├── _compile_appendix.py                      # LaTeX compile for the appendix
├── _regen_appendix.py                        # regenerate appendix_engineering.tex
├── _status.py                                # TEMPLATE/ state summary
└── src/
    └── tmaudit/                              # the actual package
        ├── __init__.py
        ├── __main__.py                       # `python -m tmaudit`
        ├── cli.py                            # argparse CLI
        ├── forge.py                          # template-substitution engine
        ├── templates/
        │   ├── __init__.py
        │   ├── verify_TEMPLATE.py            # ≈ 22 KB, ~400 lines
        │   ├── compile_check_TEMPLATE.py     # ≈ 4.5 KB
        │   └── fix_abstract_unicode_TEMPLATE.py  # ≈ 5 KB
        └── configs/
            ├── __init__.py                   # re-exports
            ├── paper_configs.py              # VERIFY_CONFIGS for paper 1..5
            └── compile_configs.py            # COMPILE_CONFIGS for paper 1..5
```

## Adding a new paper (e.g., Paper 6)

Edit **two** files:

1. `src/tmaudit/configs/paper_configs.py` — add a new entry to
   `PAPER_CONFIGS` (or `VERIFY_CONFIGS` after re-export). The fields
   are documented in the docstring at the top of that file.
2. `src/tmaudit/configs/compile_configs.py` — add a matching entry
   to `COMPILE_CONFIGS`. The fields are documented in the docstring
   there.

Then:

```powershell
python -m pip install --editable . --break-system-packages
python _build_pyz.py
tmaudit list               # confirm Paper 6 shows up
tmaudit verify --paper 6   # fork + run; will report any HIGH-severity
                           # issues caused by your config choices
```

## Verifying the .pyz is portable

```bash
# On the source machine:
python _build_pyz.py
# -> tmaudit.pyz (64 KB)

# Copy tmaudit.pyz to a fresh machine with no Python packages installed
# (only a base Python 3.9+ interpreter):
scp tmaudit.pyz other-host:/tmp/
ssh other-host 'python /tmp/tmaudit.pyz list'
# -> should print the same 5-paper table
```

The `.pyz` has **no external dependencies** (only the Python standard
library). It works on Linux, macOS, and Windows alike.

## Bug history

The **twelve historical bugs** encountered while building this
package are documented in
[`engineering_notes_verify_template.md`](./engineering_notes_verify_template.md).
Each bug has a dedicated regression test in
`tests/test_forge_happy.py`, `tests/test_bug5_unit.py`,
`tests/test_c6_threshold.py`, `tests/test_c7_citation_context.py`,
`tests/test_cache.py`, `tests/test_c10_reproducibility.py`,
`tests/test_c8_statistical_power.py`, and
`tests/test_c9_figure_caption.py`. The meta-test
(`_check_all_regressions.py`) injects each bug in turn, asserts the
regression test catches it, and restores the source. **14/14 bugs
are caught.**

The fix patterns (raw-string regex literals, brace-counting state
machines, non-letter-class regex, second/third-pass audit logic,
sentinel-character sub-string extraction, etc.) are all implemented
in `src/tmaudit/forge.py` and
`src/tmaudit/templates/verify_TEMPLATE.py`.

## Continuous integration

### Workflow

`.github/workflows/ci.yml` runs on every push and pull request.
It consists of **seven** jobs:

1. **pytest** (matrix: Python 3.9, 3.10, 3.11, 3.12, 3.13 on
   `ubuntu-latest` — every version `requires-python >=3.9` claims)
   — runs the **246-test** suite and uploads JUnit XML artifacts.
2. **meta-test** (Python 3.11) — runs `_check_all_regressions.py`
   to verify that each of the **14 regression tests** actually catches
   its target bug, then runs `_check_pyz_fresh.py` to confirm the
   committed `tmaudit.pyz` still matches `src/tmaudit/`, and finally
   builds the archive and runs it as a smoke test.
3. **validate-community-files** (Python 3.11) — runs
   `_check_github_templates.py` to verify the `.github/`
   directory structure (4 issue templates, PR template, CODEOWNERS,
   dependabot.yml, CODE_OF_CONDUCT, SUPPORT, workflows).
4. **audit-all** (Python 3.11) — runs
   `tmaudit audit-all --start 1 --end 5 --output audit-report.md
   --no-cache` and uploads the Markdown report as a CI artefact.
5. **lint** (Python 3.11) — runs `pyflakes` on `src/tmaudit/`
   and `tests/`.
6. **mutation-control** (Python 3.11) — proves the pytest and lint
   gates can actually fail: injects a known mutation, asserts both
   gates go red, then asserts a deliberately neutralised gate (wrapped
   in `|| true`) is rejected as a negative control.
7. **secret-scan** (Python 3.11) — scans the full history with
   `gitleaks`, so a committed credential fails the build.

### Local validation (before pushing)

To run the same checks locally before pushing:

```bash
pip install -e . pytest pyflakes
pip install -e ./tmaudit_example_plugin
pytest
python _check_all_regressions.py
python _check_pyz_fresh.py
python _build_pyz.py
python tmaudit.pyz list
python -m pyflakes src/tmaudit/ tests/
```

`pytest` runs the full suite: **246 passed, 3 skipped** on a machine
without the research tree — the two `@pytest.mark.slow` end-to-end audit
tests require the real `PAPER<N>_CONSOLIDATED` papers and auto-skip when
the directory is absent (point `TMAUDIT_RESEARCH_DIR` at the tree to run
them). **Scope note:** CI runs `pytest -m "not slow"`, which deselects
those two and reports **246 passed, 1 skipped, 2 deselected** — both
lines above are the same 249 collected tests, differing only in the two
deselected slow tests.

### Local CI simulation (`act` / `_act_*`)

The preferred tool for local CI simulation is
[nektos/act](https://github.com/nektos/act):

```bash
act -l                    # list jobs
act -j pytest             # run the pytest job
act -j meta-test          # run the meta-test job (after pytest)
act -j lint               # run the lint job
```

`act` requires `act` installed **and** a working Docker daemon.
If either is unavailable (e.g., on a restricted sandbox machine),
this repo ships two **fallback** simulators:

| Script | `act` equivalent | What it does |
|---|---|---|
| `_act_dryrun.py` | `act -n` (dry-run) | Parses `ci.yml`, expands the matrix, prints what each step would do. **No commands are executed.** |
| `_act_simulate.py` | `act` (real run) | Same as dryrun, but actually runs the `run:` steps via `subprocess`. Implements stubs for `actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v4`. |

```bash
python _act_dryrun.py            # show what would be executed
python _act_dryrun.py --list     # show jobs only
python _act_simulate.py --list   # list jobs (act -l equivalent)
python _act_simulate.py --job pytest    # run pytest job
```

### CI simulation results

`_act_dryrun.py` was used to validate the workflow before
pushing. Results:

- ✅ `ci.yml` is valid YAML (parsed by PyYAML)
- ✅ **7 jobs** (a 5-version pytest matrix plus 6 single-run jobs)
- ✅ `meta-test` correctly depends on `pytest` (Kahn's algorithm topo sort)
- ✅ `matrix.python-version` substituted correctly into `${{ ... }}` expressions
- ✅ `if: always()` preserved on the upload-artifact step
- ✅ `with:` arguments (e.g., `cache: pip`, `cache-dependency-path: pyproject.toml`) preserved

The CI workflow's `run:` blocks are identical to commands
we have already executed successfully on the host:

| CI step | Local result |
|---|---|
| `python -m pip install -e .` | tmaudit installed ✅ |
| `python -m pip install pytest scipy` | deps installed ✅ |
| `python -m pytest -m "not slow"` | **246 passed, 1 skipped in ~5s** ✅ |
| `python _check_all_regressions.py` | **14/14 bugs caught** ✅ |
| `python _check_github_templates.py` | **44/44 OK** ✅ |
| `python -m src.tmaudit audit-all ...` | audit-report.md generated ✅ |
| `python -m src.tmaudit audit-all ...` | report uploaded as artefact ✅ |
| `python _build_pyz.py` | tmaudit.pyz built ✅ |
| `python tmaudit.pyz list` | 5 papers listed ✅ |
| `python -m pyflakes src/tmaudit/ tests/` | 0 errors ✅ |

### What `_act_*` cannot simulate

- `actions/setup-python@v5` cannot actually install a different
  Python version (the host has only one Python; the matrix
  includes 3.9–3.13). The simulator prints a
  warning but does not fail.
- `actions/upload-artifact@v4` is simulated by copying files
  to `_act_run/artifacts/<name>/`.
- The Docker isolation that real `act` provides is not present;
  steps run on the host shell.

### Pre-push hook recommendation

To enforce CI validation before every push:

```bash
# .git/hooks/pre-push
python _check_yaml.py && python _act_dryrun.py
```

The `_check_yaml.py` script validates `ci.yml` is parseable
and has the expected structure (catches YAML syntax errors
before pushing).

### Full evidence

For the full simulation transcript (including the 5 sandbox
issues encountered and how they were worked around), see
[`act_summary.md`](./act_summary.md).
