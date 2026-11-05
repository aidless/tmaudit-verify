# Contributing to tmaudit

Welcome! This document explains how to set up a development
environment, run the test suite, and install the pre-commit
hook that enforces our quality bar.

The whole workflow takes **~5 minutes** on a fresh clone.

## Table of contents

- [Quick start](#quick-start)
- [The test suite](#the-test-suite)
- [Pre-commit hook](#pre-commit-hook)
- [Adding a new paper](#adding-a-new-paper)
- [Pull request checklist](#pull-request-checklist)
- [Troubleshooting](#troubleshooting)

## Quick start

### 1. Clone and install

```bash
git clone <repo-url> tmaudit
cd tmaudit
python -m pip install -e . pytest pyflakes pyyaml
```

The `pip install -e .` (editable mode) registers the `tmaudit`
CLI and makes the package source importable from any test.
You only need to re-run this when `pyproject.toml` changes.

### 2. Verify the install

```bash
tmaudit list
# Should print: 1 OK ... 5 OK with paths to PAPER<N>_CONSOLIDATED
```

If you see a `ModuleNotFoundError`, your Python is not finding
the `tmaudit` package — make sure you used `pip install -e .`
(where the `.` is the repo root) and not `pip install tmaudit`.

### 3. Run the test suite

```bash
python -m pytest -m "not slow"
# The selected and deselected counts are the sentence in README.md.
```

### 4. Run the meta-test (optional but recommended)

```bash
python _check_all_regressions.py
# Prints "<caught>/<recorded>". Checks that need PAPER*_CONSOLIDATED
# print SKIPPED and are not in that fraction. A skip is not a pass.
# The case-list length is checked by tests/test_claims_drift.py.
```

### 5. Install the pre-commit hook

This is **strongly recommended**:

```bash
# Linux / macOS / WSL
./hooks/install-precommit.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File hooks\install-precommit.ps1
```

After installation, every `git commit` will automatically run
the four CI steps below and abort the commit if any fails.

## The test suite

The test suite lives in `tests/`:

| File | Tests | Purpose |
|---|---|---|
| `tests/test_forge.py` | 26 | Unit tests for `tmaudit.forge`. **One test class per documented bug** (bugs 1–6 from `engineering_notes_verify_template.md`). |
| `tests/test_forge_happy.py` | 13 | Integration tests — fork + run `verify_p<N>.py` on Paper 1 and Paper 5, expect 0 findings. |
| `tests/test_bug5_unit.py` | 7 | Direct unit test of the C5 test-name regex in `verify_TEMPLATE.py`. Bypasses the need for a paper containing `paired $t$-tests`. |
| `tests/conftest.py` | — | Shared fixtures (paper 1/5 configs, real templates). |
| `tests/__init__.py` | — | Package marker. |

### Running subsets

```bash
# Run only the bug-1 regression test
pytest tests/test_forge.py::TestBug1ReprInterpretsBackslash -v

# Run only the end-to-end tests
pytest tests/test_forge_happy.py::TestEndToEndAudit -v

# Run with coverage
pip install coverage
coverage run -m pytest
coverage report
```

### The meta-test: regression-injection validation

`tests/test_forge.py` contains tests that **claim** to catch
each of the 6 historical bugs. But what if a future change
breaks the test such that it silently passes even when the
bug is reintroduced? That's a **silent false negative**, and
it's worse than no test at all.

To prevent that, `_check_all_regressions.py` is a **meta-test**:
it temporarily injects a small change that re-introduces each
bug, runs the corresponding regression test, asserts the test
**fails**, then restores the source and asserts the test
**passes** again. A regression test that always passes — even
with the bug injected — is the worst possible failure mode,
and this script catches it.

```bash
python _check_all_regressions.py
# Prints "<caught>/<recorded>". Checks that need PAPER*_CONSOLIDATED
# print SKIPPED and are not in that fraction. A skip is not a pass.
# The case-list length is checked by tests/test_claims_drift.py.
```

## Pre-commit hook

The pre-commit hook runs four checks on every `git commit`:

| Step | Script | What it checks |
|---|---|---|
| 1 | `_check_yaml.py` | `.github/workflows/ci.yml` is parseable YAML with expected structure. |
| 2 | `pytest -m "not slow"` | The fast suite. The selected and deselected counts are the sentence in `README.md`, not a number frozen here. |
| 3 | `_check_all_regressions.py` | Each injected bug that can run here is caught. Checks that need `PAPER*_CONSOLIDATED` are skipped, and a skip is not a pass. |
| 4 | `_build_pyz.py` | `tmaudit.pyz` builds without error. |

The hook is implemented in `hooks/pre-commit` as a **cross-platform
Python script** (not bash) so it works identically on Windows,
macOS, and Linux.

### Installing the hook

```bash
# Linux / macOS / WSL
./hooks/install-precommit.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File hooks\install-precommit.ps1
```

The installer copies `hooks/pre-commit` to `.git/hooks/pre-commit`.
Git will then invoke it automatically on every `git commit`.

### Verifying the hook

```bash
git commit --allow-empty -m "test pre-commit hook"
```

You should see all four steps run and a "All pre-commit checks
passed." message.

### Skipping the hook (use sparingly)

```bash
git commit --no-verify -m "WIP: fix typo"
```

This is **not** recommended. The hook exists to catch
regressions before they reach the remote. Use `--no-verify`
only for WIP commits that you intend to amend or squash.

### Uninstalling the hook

```bash
# Linux / macOS / WSL
./hooks/install-precommit.sh --uninstall

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File hooks\install-precommit.ps1 -Uninstall
```

### Using the pre-commit framework (optional, advanced)

If you prefer the [pre-commit framework](https://pre-commit.com/)
(installed via `pip install pre-commit` and configured via
`.pre-commit-config.yaml`), this repo does not yet ship a
config. The `hooks/pre-commit` script is a standalone
alternative that does not require the framework.

## Adding a new paper

To add audit support for a new paper (e.g., Paper 6):

### 1. Create the paper directory

```bash
mkdir PAPER6_CONSOLIDATED
# Copy your LaTeX source as main.tex and your bibliography as refs.bib
```

### 2. Edit the per-paper config

Edit `src/tmaudit/configs/paper_configs.py` and add a new
entry to `PAPER_CONFIGS`:

```python
6: {
    'dir': Path('papers/PAPER6_CONSOLIDATED'),
    'c1_symbols': [
        {
            'name': '$M (memory size)$',
            'token': r'\bM\b',
            'definition': r'\bM\b.{0,80}=|memory.{0,30}size',
        },
    ],
    'c2_families': {'main': 3},
    'c2_section_pattern': (
        r'\\section\*?\{[^}]*Power analysis[^}]*\}'
    ),
    'c2_abstract_k_allowed': [3],
    'c3_concept': 'crossover',
    'c3_concept_token': r'\\textbf\{crossover\}|\bcrossover\b',
    'c3_formal': r'crossover.{0,80}\arg\?min',
    'c3_formal_secondary': None,
    'c4_self_cite_threshold': 0.30,
    'c4_self_cite_prefix': 'liu2026',
    'c4_max_self_cite_keys': 3,
    'c5_d_type': "Cohen's d",
    'c6_blacklist': ['paradigm', 'yield', 'reveal'],
},
```

The fields are documented in the docstring at the top of
`src/tmaudit/configs/paper_configs.py`. Run
`python _check_all_regressions.py` to make sure your config
does not break the existing 6 regression tests.

### 3. Test the new paper

```bash
tmaudit verify --paper 6
# Should report 0 findings if your paper passes the audit.
# If it reports findings, they are real issues to fix in the paper.
```

### 4. (Optional) Add a regression test

If the new paper exercises a code path that the existing
tests do not (e.g., a unique c3_formal pattern), add a
test to `tests/test_forge_happy.py::TestEndToEndAudit`:

```python
def test_paper_6_forks_and_passes(self):
    target = forge.fork_verify(6)
    result = subprocess.run(
        [sys.executable, str(target)],
        cwd=target.parent,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert 'All checks passed' in result.stdout
```

## Pull request checklist

Before opening a pull request, make sure:

- [ ] `python -m pytest -m "not slow"` passes (count is in `README.md`)
- [ ] `python _check_all_regressions.py` reports every injected bug caught
- [ ] `python _build_pyz.py` produces a working `tmaudit.pyz`
- [ ] `python tmaudit.pyz list` lists the correct papers
- [ ] `python _check_yaml.py` reports `ci.yml` is valid
- [ ] If you added a paper, you added a `TestEndToEndAudit` case for it
- [ ] If you added a fix for a bug, you added a regression test for it
      AND verified it actually catches the bug (using `_check_all_regressions.py`)

When you open a pull request, GitHub will automatically
populate the PR body with the template at
[`.github/PULL_REQUEST_TEMPLATE.md`](./.github/PULL_REQUEST_TEMPLATE.md).
That template contains 40 checkboxes (10 H2 sections + 3
pre-merge sub-categories) — most of which mirror the items
above. The template also includes sections for **What** /
**Why** / **Type of change** / **Affected components** /
**Test plan** / **Breaking changes** / **Reviewer notes** that
GitHub's PR UI exposes to the reviewer.

Quick rule: **if you cannot fill in the "Test plan" section
with command output, the PR is not ready for review.**

## Troubleshooting

### `tmaudit: command not found` after `pip install -e .`

Your `pip` and `python` are pointing to different Python
installations. Run:

```bash
which python
which pip
python -m pip install -e .
# This forces pip to use the same Python that `python` invokes.
```

### `ModuleNotFoundError: No module named 'tmaudit'` in tests

You are running `pytest` from a different Python than the one
you used for `pip install -e .`. Always invoke `pytest` as
`python -m pytest` (which uses the current `python`).

### `pytest` reports `ModuleNotFoundError: No module named 'yaml'`

`pyyaml` is a test-time dependency. Install it:

```bash
python -m pip install pyyaml
```

### Pre-commit hook fails on Windows with `'python' is not recognized`

The hook uses `sys.executable` (the actual Python interpreter)
so it should always find Python. If you see this error, the
hook is being invoked by a shell that has a different PATH.
Try `git commit` from PowerShell (not Git Bash) so the
`sys.executable` is consistent.

### Meta-test fails with "anchor (X) not found"

This means the inject function's anchor string (a literal
chunk of source code) does not match the current state of
the source file. Either the source was edited and the anchor
needs updating, or the file is already in a broken state
from a previous incomplete run. To recover:

```bash
# Check the file is in its expected state
git diff src/tmaudit/

# Restore from git
git checkout src/tmaudit/

# Re-run
python _check_all_regressions.py
```

### Pre-commit hook is slow

The full pre-commit run takes ~10 seconds (dominated by the
meta-test's 12 pytest invocations). To skip the meta-test
for a quick commit:

```bash
git commit --no-verify -m "wip: incremental progress"
```

Then run the meta-test manually before pushing.

## Continuous integration

This repo uses GitHub Actions (see `.github/workflows/ci.yml`).
The CI runs the same four checks as the pre-commit hook,
plus a `pyflakes` lint, on Python 3.9, 3.10, 3.11, 3.12.

For local CI simulation, see the "Local CI simulation
(`act` / `_act_*`)" section in [README.md](./README.md#local-ci-simulation-act--_act_).

## Where to get help

- **Bug reports**: open a GitHub issue using the
  [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
  The issue chooser will pre-fill the body and apply the
  `bug` + `needs-triage` labels.
- **Feature requests**: open a GitHub issue using the
  [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).
  Use this for a **new** audit category, **new** CLI
  subcommand, or **new** paper config. The chooser will
  apply the `enhancement` + `needs-triage` labels.
- **Enhancements**: open a GitHub issue using the
  [enhancement template](.github/ISSUE_TEMPLATE/enhancement.md).
  Use this for **improving an existing check** (e.g., C6
  threshold), making the CLI more ergonomic, performance
  improvements (e.g., the cache), or better error messages.
  This template asks for a "before vs after" example, a
  risk assessment, and a migration path. The chooser will
  apply the `enhancement` + `needs-triage` labels.
- **Documentation**: open a GitHub issue using the
  [documentation template](.github/ISSUE_TEMPLATE/docs.md).
  Use this for **docs-only changes**: typos, clarifications,
  new sections, restructures, and translations. No code
  change. This is the fastest template to fill and the
  easiest to merge. The chooser will apply the
  `documentation` + `needs-triage` labels.
- **Security vulnerabilities**: do **not** open a public
  issue. See [SECURITY.md](./SECURITY.md) for the private
  disclosure process.
- **Q&A / how-to questions**: use
  [GitHub Discussions](https://github.com/aidless/tmaudit/discussions).
- **Architecture / design questions**: see
  [`engineering_notes_verify_template.md`](./engineering_notes_verify_template.md)
  for the engineering diary of the original 6 bugs.
- **CI / pre-commit questions**: see
  [README.md "Continuous integration"](./README.md#continuous-integration)
  and [`act_summary.md`](./act_summary.md).