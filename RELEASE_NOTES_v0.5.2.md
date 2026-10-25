# Release Notes — v0.5.2

> **TLDR.** Packaging and documentation only. The wheel now includes
> `detector_config/detector.yaml`, so a plain `pip install tmaudit` gets the
> shipped detector thresholds instead of silently using defaults. The README
> now starts with a runnable quick start and the real output it produces.

## Fixed

- `detector.yaml` was missing from the sdist/wheel: `[tool.setuptools.package-data]`
  listed `templates/*` and `configs/*` but not `detector_config/*.yaml`.
  Non-editable installs fell back to defaults; `tests/test_detector_config.py`
  failed against the installed package. Editable installs masked it.

## Fixed

- **A relative `--paper-dir` was resolved twice.** `fork_*` wrote the script to
  `paper/verify_generic.py` and then launched it with `cwd=paper`, so a relative
  path became `paper/paper/verify_generic.py` and the quick start failed. The
  fork helpers now resolve the directory to an absolute path first; a regression
  test runs the CLI from a parent directory with `--paper-dir paper`.

## Added

- `examples/sample-paper/` — a deliberately flawed manuscript plus `refs.bib`,
  used by the README quick start. It produces one MEDIUM (unreferenced figure
  label) and five LOW (reproducibility) findings.

## Documentation

- README first screen rewritten: what it checks, one-command install, real
  output, and the honest scope boundary (C1–C3/C6 are per-paper; C4–C10 run on
  any manuscript).

## Verification

- `263 passed, 3 skipped` against a non-editable install of this version.
- `_check_pyz_fresh.py` accepts the rebuilt `tmaudit.pyz`.
