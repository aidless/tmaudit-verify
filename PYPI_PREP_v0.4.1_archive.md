# PyPI Upload Prep — v0.4.1

> **Status**: ⏳ in progress
> **Target release**: v0.4.1 (≤ 2026-08-10 per §15.5)
> **Date prepared**: 2026-07-10

## 0. Name-availability check (DONE)

PyPI name check on 2026-07-10:

| Name | Status |
|---|---|
| `tmaudit` | **FREE** (404 from PyPI JSON + simple index) |
| `tmaudit-cli` | FREE |
| `tmaudit-dryrun` | FREE |
| `tmaudit-plugin` | FREE |
| 25 candidates total | ALL FREE |

No name collision. We can ship under the canonical
name `tmaudit`.

See the local name-check script (not in this repository) for the full check
script (4 sections: candidate sweep, PEP 503
normalization, simple index, search).

## 1. Required changes to `pyproject.toml`

The current `pyproject.toml` is minimal and pre-release.
It needs to grow for PyPI publication. Here's the diff
we need to apply:

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "tmaudit"                                          # was: "tmaudit"
version = "0.4.1"                                        # was: "0.1.0"
description = "Config-driven TMLR paper audit + LaTeX compile pipeline"
readme = "README.md"                                      # NEW
requires-python = ">=3.9"
license = {text = "MIT"}                                  # NEW
authors = [
    {name = "Liu Zewen", email = "aidless@example.com"},
]
keywords = ["tmaudit", "tmlr", "audit", "latex", "compile", "plugins"]
classifiers = [                                            # NEW
    "Development Status :: 4 - Beta",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering",
    "Topic :: Software Development :: Quality Assurance",
]

[project.urls]                                            # NEW
Homepage = "https://github.com/aidless/tmaudit"
Issues = "https://github.com/aidless/tmaudit/issues"
Source = "https://github.com/aidless/tmaudit"
Changelog = "https://github.com/aidless/tmaudit/blob/main/CHANGELOG.md"

dependencies = []  # tmaudit has zero runtime deps in v0.4.x

[project.optional-dependencies]
dev = ["pytest>=7", "mypy>=1.0", "build>=0.10", "twine>=4"]

[project.scripts]
tmaudit = "tmaudit.cli:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
include = ["tmaudit*"]

[tool.setuptools.package-data]
tmaudit = [
    "templates/*.py",
    "templates/*.tex",
    "configs/*.py",
]
```

The key changes are:
- `name = "tmaudit"` (already was; the name is good)
- `version = "0.4.1"` (was 0.1.0; bump for v0.4.1)
- `readme = "README.md"` (NEW; PyPI renders this)
- `license = {text = "MIT"}` (NEW; needs LICENSE file)
- `authors` populated
- `classifiers` (NEW; helps PyPI categorise)
- `project.urls` (NEW; PyPI sidebar links)
- `dev` extras: add `build`, `twine` for PyPI upload

## 2. Required new files

### 2.1 `LICENSE` (MIT)

```
MIT License

Copyright (c) 2026 Liu Zewen

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
```

(~20 lines; place at `LICENSE` at repo root.)

### 2.2 `.github/workflows/publish-pypi.yml` (NEW)

A GitHub Actions workflow that uses **trusted publishing**
(no API tokens stored in secrets). Triggered by a
release on GitHub. Publishes to PyPI on tag push.

```yaml
name: Publish Python Package

on:
  release:
    types: [published]
  workflow_dispatch:

jobs:
  pypi-publish:
    name: Publish to PyPI
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write   # for trusted publishing (OIDC)
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install build tooling
        run: python -m pip install --upgrade build
      - name: Build sdist and wheel
        run: python -m build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        # No `password:` field — uses OIDC trusted publishing.
```

PyPI trusted publishing is set up at:
<https://pypi.org/manage/account/publishing/>

(Project: `aidless/tmaudit`, Owner: `aidless`, Workflow:
`publish-pypi.yml`, Environment: `pypi`.)

## 3. Manual dry-run (recommended)

Before tagging v0.4.1, do a **local dry-run**:

```bash
# Build the distribution
# from the repository root
python -m pip install --upgrade build
python -m build

# Inspect the output
ls -la dist/
# Should contain:
#   tmaudit-0.4.1-py3-none-any.whl
#   tmaudit-0.4.1.tar.gz

# Verify metadata
python -m zipfile -e dist/tmaudit-0.4.1-py3-none-any.whl /tmp/whl-check/
cat /tmp/whl-check/tmaudit-0.4.1.dist-info/METADATA
```

Verify that:
- `Name: tmaudit`
- `Version: 0.4.1`
- `Requires-Python: >=3.9`
- `License: MIT` (or whatever)
- `Provides-Extra: dev`

```bash
# Optional: TestPyPI dry-run
python -m pip install --upgrade twine
twine upload --repository testpypi dist/*
# Installs from:
#   pip install --index-url https://test.pypi.org/simple/ tmaudit==0.4.1
```

If TestPyPI accepts the upload, the actual PyPI upload
should be a no-op. The only thing that can go wrong at
real PyPI is name collision (we've checked) or
classification (we've chosen well-formed ones).

## 4. Tag and release

```bash
# from the repository root
git tag -a v0.4.1 -m "v0.4.1 - first PyPI release (bug fixes, docs, no API change)"
git push origin v0.4.1
# GitHub Action triggers automatically (after first manual
# approval of the trusted-publisher on PyPI).
```

## 5. Post-release verification

```bash
# In a fresh venv:
python -m venv /tmp/tmaudit-test
source /tmp/tmaudit-test/bin/activate
pip install tmaudit==0.4.1
tmaudit list            # should show 5 papers
tmaudit plugins list    # should show 3 example plugins (if tmaudit-example-plugin also uploaded)
python -c "import tmaudit; print(tmaudit.__version__)"  # should print 0.4.1
tmaudit --version
```

If all 4 checks pass, v0.4.1 is live on PyPI and the
public release cycle is unblocked.

## 6. Risks

- **PyPI upload can fail for non-name reasons**:
  network errors, missing classifiers, unsupported
  python version, malformed description. These show up
  in `twine upload` output and are fixable.
- **Trusted-publishing approval**: the first
  `pypa/gh-action-pypi-publish` run will fail with
  "no trusted publisher configured" until you add the
  publisher at <https://pypi.org/manage/account/publishing/>.
  This is a 5-minute manual setup.
- **License debate**: I chose MIT. If the maintainer
  prefers Apache 2.0, the LICENSE file + `license =`
  field need to change. Apache 2.0 has a patent grant;
  MIT is simpler. We can flip in v0.4.2 if there's
  pushback.

## 7. What's NOT in v0.4.1

- **No new audit category** (that's v0.5.0+).
- **No new feature** (that's v0.5.0+).
- **No plugin API change** (that would be v0.5.0).
- **No C1..C10 → Finding migration** (that's v0.6.0).

v0.4.1 is purely: **ship v0.4.0 to PyPI + fix any
community-reported bugs + add `pyproject.toml` fields
PyPI requires**.

## 8. Effort estimate

| Task | Effort |
|---|---|
| Edit `pyproject.toml` (10 fields) | 5 min |
| Add `LICENSE` (MIT) | 5 min |
| Add `.github/workflows/publish-pypi.yml` | 10 min |
| Configure PyPI trusted publisher (web UI) | 5 min |
| Build + twine dry-run | 5 min |
| Tag v0.4.1 + push | 1 min |
| Post-release verification | 5 min |
| **Total** | **~35 min** |

Most of the work is the trusted-publisher setup (one
click on PyPI's web UI). The code changes are
mechanical.

---

**Maintainer action**: review the 10 `pyproject.toml`
field changes, choose license (MIT vs Apache 2.0), and
run through the 8 steps above. Then update CHANGELOG +
RELEASE_NOTES_v0.4.1.md with the "now on PyPI" callout.

**Status of this doc**: ⏳ 30% done (sections 0-2 written;
sections 3-8 are placeholders for the maintainer to fill
in during the actual upload).
