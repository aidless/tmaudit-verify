# Writing a tmaudit plugin

This document is the user-facing path for adding your own checks to
`tmaudit` — including for a manuscript the built-in rulepack was not
written for.

## When you need a plugin

The ten built-in categories (C1..C10) are **configured per paper** in
`src/tmaudit/configs/paper_configs.py`, and the shipped configs cover
the five papers of this project only. Concretely:

- `tmaudit verify --paper N` accepts `N` in 1..5. It forks that paper's
  C1..C10 rules and runs them.
- `tmaudit verify --paper-dir DIR` (no `--paper`) forks the shipped
  **factory template** into `DIR`: the per-paper categories (C1/C2/C3/C6)
  report **not applicable** and the generic categories run. That is the
  config-free baseline for a manuscript the rulepack was not written for.
- Neither covers checks the generic categories do not have. For those,
  write a plugin — the supported path for your own checks.

Everything below is the whole contract. A plugin needs no
dependencies beyond `tmaudit` itself.

## The contract

A plugin is a function that takes the paper's `main.tex` source and an
optional config dict, and returns a list of `Finding` objects:

```python
def my_check(tex: str, config: dict | None = None) -> list[Finding]: ...
```

It is decorated with `@check` and registered under the entry-point
group `tmaudit.plugins`.

### `@check` keyword arguments

| Argument | Required | Meaning |
|---|---|---|
| `name` | yes | Unique plugin name; what `plugins list` / `plugins run` take |
| `severity` | no | One of `HIGH`, `MEDIUM`, `LOW`, `MED`; default `MEDIUM` |
| `help_text` | no | One-line description shown by `plugins info` |
| `version` | no | Default `0.1.0`; bump it to invalidate cached results |
| `requires_config` | no | Advisory metadata only — see the note below |

### `Finding` fields

| Field | Default | Notes |
|---|---|---|
| `category` | — | Non-empty `str` |
| `severity` | — | Must be one of the four values; anything else raises `ValueError` |
| `message` | — | The text shown to the reader |
| `line` | `-1` | 1-based line number in `main.tex` |
| `paper_id` | `None` | Filled in by the runner; leave unset |

## A minimal plugin, copy-paste ready

Two files plus a packaging stanza:

```
my-paper-checks/
├── pyproject.toml
└── my_paper_checks/
    └── __init__.py
```

`my_paper_checks/__init__.py`:

```python
"""Checks for my own manuscript."""
from __future__ import annotations

from typing import List, Optional

from tmaudit import Finding, check


@check(
    name="my-symbol-defined",
    severity="HIGH",
    help_text="Every use of my metric abbreviation must define it inline",
    version="0.1.0",
)
def my_symbol_defined(
    tex: str,
    config: Optional[dict] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    # Your parameters live in your own code — the built-in config
    # for this paper does not exist, so put them here.
    token = r"\bMMR\b"
    must_define = r"MMR.{0,80}=|mean.{0,20}rank"
    ...
    return findings
```

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "my-paper-checks"
version = "0.1.0"
description = "Audit checks for my manuscript"
requires-python = ">=3.9"
dependencies = []          # tmaudit is required at runtime, not at install

[project.entry-points."tmaudit.plugins"]
my-symbol-defined = "my_paper_checks:my_symbol_defined"
```

A complete working example with three finished checks — TODO markers,
`XXX` debug markers, and abstract word count — ships in
[`tmaudit_example_plugin/`](../tmaudit_example_plugin/). Copy it as a
starting point.

## Install, verify, and run

Plugins are discovered through **installed entry points**. A `.py` file
dropped into a folder is not discovered; the package must be installed
in the environment where `tmaudit` runs.

```bash
pip install -e ./my-paper-checks     # editable, so edits are picked up

tmaudit plugins list                 # is it registered?
tmaudit plugins info my-symbol-defined   # metadata, module, version
```

Run it against **your own paper** — no `--paper N` needed:

```bash
tmaudit plugins run my-symbol-defined --paper-dir /path/to/your/paper
```

The directory must contain the manuscript's root `.tex` — named
`main.tex`, or the sole `.tex` that declares `\begin{document}`.
Findings print as
`[SEVERITY] CATEGORY L<line>: message`; exit code is 0 whether or not
findings were emitted.

To run it against one of the built-in papers instead, pass `--paper N`
(the plugin then also receives that paper's config):

```bash
tmaudit plugins run my-symbol-defined --paper 1
```

## What you do and do not get

**You get**: the paper's `main.tex` as a string, and a config dict.

- With `--paper-dir` (your own paper) the config is **empty**. Write
  your parameters into the plugin itself, as in the example above.
- With `--paper N` (papers 1..5) the config is that paper's full
  C1..C10 dict.

**You do not get**:

- A way to make `audit-all` scan an arbitrary directory. `audit-all`
  iterates papers 1..5 and runs your plugins there too; it does not
  walk other directories. Use `plugins run --paper-dir` for that.
- Enforcement of `requires_config`. It is metadata displayed by
  `plugins info`; tmaudit does not skip a plugin that declares it and
  then receives an empty config. Your check must tolerate `None`/`{}`.
- Error isolation on the single-plugin path. `plugins run` calls your
  function directly, so an exception surfaces as a traceback. Inside
  `audit-all`, a plugin that raises is logged and skipped, and the audit
  continues with the other plugins.

## Reference: where the built-in rules live

- Rule parameters per paper:
  [`src/tmaudit/configs/paper_configs.py`](../src/tmaudit/configs/paper_configs.py)
- The rule implementation the parameters are substituted into:
  [`src/tmaudit/templates/verify_TEMPLATE.py`](../src/tmaudit/templates/verify_TEMPLATE.py)
- The example plugin's own tests:
  [`tests/test_example_plugin.py`](../tests/test_example_plugin.py)
