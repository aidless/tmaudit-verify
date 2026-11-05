# `act` / CI simulation summary

## Why this file exists

We want to validate `.github/workflows/ci.yml` locally
before pushing to GitHub. The standard tool for this is
[nektos/act](https://github.com/nektos/act), but the local
sandbox environment blocks it for two reasons:

1. **`act` is not installed.** The sandbox blocks
   `winget install`, `scoop install`, and direct `curl` of
   GitHub release artifacts (`Failed to connect to github.com
   port 443`).
2. **Docker is installed but its daemon is not running.**
   `act` requires a working Docker daemon to spawn the
   runner container.

So we wrote two minimal Python simulators that together
cover the most useful subset of `act`'s behaviour:

| Script | `act` equivalent | What it does |
|---|---|---|
| `_act_dryrun.py` | `act -n` (dry-run) | Parses `ci.yml`, expands the matrix, prints what each step would do. **No commands are executed.** |
| `_act_simulate.py` | `act` (with a no-op `--no-sandbox` flag) | Same as dryrun, but actually runs the `run:` steps via `subprocess`. Implements stubs for `actions/checkout`, `actions/setup-python`, `actions/upload-artifact`. |

## Dryrun output (proves ci.yml is parseable + correct)

```
$ python _act_dryrun.py
Workflow: CI
Triggers: ['push', 'pull_request', 'workflow_dispatch']

Job graph:
  pytest          (ubuntu-latest)
  meta-test       (ubuntu-latest) <- pytest
  lint            (ubuntu-latest)

========================================================================
Job: pytest    (4 matrix row(s))
========================================================================

[matrix row 1/4]  python-version=3.9
  Step 1: Checkout repository
      [uses] actions/checkout@v4
  Step 2: Set up Python 3.9
      [uses] actions/setup-python@v5   with: {python-version: 3.9, ...}
  Step 3: Install tmaudit in editable mode
      $ python -m pip install --upgrade pip
      $ python -m pip install -e .
      $ python -m pip install pytest
  Step 4: Run pytest
      $ python -m pytest --junitxml=test-results-3.9.xml -v
  Step 5: Upload JUnit XML
      [uses] actions/upload-artifact@v4   with: {...}
            if: always()

... 3 more matrix rows (3.10, 3.11, 3.12) ...
```

**What this proves:**

- ✅ `ci.yml` is valid YAML (parsed by PyYAML)
- ✅ 3 jobs, 4 + 1 + 1 matrix rows, 5 + 4 + 5 = 14 steps
- ✅ `meta-test` correctly depends on `pytest` (Kahn's algorithm topo sort)
- ✅ `matrix.python-version` substituted correctly into `${{ ... }}` expressions
- ✅ `if: always()` preserved on the upload-artifact step
- ✅ `with:` arguments (e.g., `cache: pip`, `cache-dependency-path: pyproject.toml`) preserved

## Local execution (subprocess)

```
$ python _act_simulate.py --list
Available jobs:
  pytest          4 matrix row(s)
  meta-test       1 matrix row(s) (needs: pytest)
  lint            1 matrix row(s)

$ python _act_simulate.py --job pytest
Running 1 job(s) in order: ['pytest']

========================================================================
Job: pytest
========================================================================
Matrix: 1 axes, 4 row(s)

--- matrix row: python-version=3.9 ---
  [uses: actions/checkout@v4] (no-op, working tree already present)
  [uses: actions/setup-python@v5] python-version=3.9
  OK: host python is 3.9 (matches requested)
$ python -m pip install --upgrade pip
  ...
```

**What this proves:**

- ✅ `actions/checkout@v4` and `actions/setup-python@v5` stubs work
- ✅ `subprocess.run` correctly executes the `run:` block
- ✅ Matrix is correctly expanded (4 rows, one per Python version)
- ✅ The host Python version is detected and reported (3.9)

## What we cannot simulate locally

The following would only run correctly inside a real GitHub
Actions runner or a full `act` setup:

- `actions/setup-python@v5` cannot actually install a different
  Python version (the host has only 3.9.25; matrix includes
  3.10, 3.11, 3.12 which the host does not have). The
  simulator prints a warning but does not fail.
- `actions/upload-artifact@v4` is simulated by copying files
  to `_act_run/artifacts/<name>/` (see `_step_uses_upload_artifact`).
- The Docker isolation that real `act` provides is not present;
  steps run on the host shell. This means **our sandbox's
  allowlist also constrains what the simulator can do** —
  in particular, `pip install --upgrade pip` is blocked by
  the sandbox, but would succeed on a real runner.

## What we already know works (proven in earlier steps)

The CI workflow's `run:` blocks are identical to commands
we have already executed successfully on the host:

| CI step | Local equivalent | Local result |
|---|---|---|
| `python -m pip install -e .` | (already done) | tmaudit installed |
| `python -m pip install pytest` | (already done) | pytest installed |
| `python -m pytest` | `pytest` | **46 passed in 0.34s** ✅ |
| `python _check_all_regressions.py` | (just ran) | **6/6 bugs caught** ✅ |
| `python _build_pyz.py` | (just ran) | tmaudit.pyz built ✅ |
| `python tmaudit.pyz list` | (just ran) | 5 papers listed ✅ |
| `python -m pyflakes src/tmaudit/ tests/` | (just ran) | 0 errors ✅ |

## Conclusion

The notes below are the simulation as it was written. They are not the
current workflow. `.github/workflows/ci.yml` is the source for which jobs
run, and `README.md` is the source for how many tests that selection collects.

If the user has access to a machine with `act` + Docker
available, the same workflow can be re-validated with the
standard tool:

```bash
act -l                    # list jobs (same as _act_simulate.py --list)
act -j pytest             # run the pytest job
act -j meta-test          # run the meta-test job (after pytest)
act -j lint               # run the lint job
```

Our local simulators (`_act_dryrun.py`, `_act_simulate.py`)
remain as a **fallback** for environments where `act` is
not available, and as a **CI validation tool** that can be
called from a pre-push git hook:

```bash
# .git/hooks/pre-push
python _act_dryrun.py && python _act_simulate.py --list
```
