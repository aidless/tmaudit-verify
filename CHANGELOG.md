# Changelog

All notable changes to `tmaudit` are documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [v0.6.0] — 2026-10-24

### Added — `admission`: statistical certificates for self-evolving harness claims

A class of 2026 papers reports that an agent's harness (prompts, tools,
memory, middleware, control logic) was revised by an automated loop while
model weights were held fixed, and cites a benchmark delta as evidence the
revision worked. Selecting on empirical fitness does not establish
generalization: the reported delta comes from the same tasks the loop
optimised against.

`arXiv:2610.18813` (Self-evolving Agent Harness, §4.2) states a sufficient
condition for admitting a revision with a fresh, independent validation set:

    Delta_hat + sqrt( 2 * ln(K*T/delta) / m ) < 0                  (eq. 8, p.7)
    Delta_hat + sqrt( 2 * ln(K*T/delta) / m ) + 2*eta < 0          (eq. 9, p.8)

`tmaudit admission` implements both inequalities, the retention bookkeeping
of eq. (6), and the inversion of eq. (8):

```
tmaudit admission --gain 7.3 --tasks 89
# [NOT CERTIFIED] gain=+7.30pp  upper=+32.10pp  m=89  K=5  T=10  delta=0.05
# note: certifying this gain would need tasks m >= 2,593

tmaudit admission --required-tasks 7.3      # -> tasks m >= 2,593
tmaudit admission --grid                    # m -> minimum certifiable gain
tmaudit admission --audit claims.json       # batch; exit 1 if any uncertified
```

Design notes:

- `--tasks` is the number of fresh, independent **tasks**, not rollouts.
  The source is explicit that extra rollouts raise precision without
  raising the sample size (p.7, "Scope of the guarantees"), so the flag
  refuses `m < 2` and the docstring says so.
- Exit codes: `0` certified, `1` uncertified, `2` bad input. The batch mode
  exits `1` if any claim in the file fails, so it can gate CI.
- Stdlib only. `dependencies = []` remains true.
- `--eta-pp` implements eq. (9). Providing it *raises* the required gain by
  `2*eta`; it is not a correction in the candidate's favour.
- `RetentionLedger` (eq. 6) reports when the accumulated regression
  allowance `sum(eps)` has consumed the gain being defended, i.e. when the
  retention bound has become vacuous.

Tests: `tests/test_admission.py` (41 cases). Every numeric assertion is
re-derived by hand from eq. (8) — `2*ln(5000) = 17.0344`,
`sqrt(13.8155/89) = 39.4pp`, `ceil(13.8155/0.073**2) = 2593` — so a
regression in the formula cannot be masked by a captured snapshot. Includes
a round-trip property test (`required_tasks` then `certify` must pass, and
`m-1` must fail).

### Changed
- Version bump to 0.6.0.
- `tmaudit --version` now works. Previously the top-level parser had no
  version flag, so `tmaudit --version` exited 2 with "the following
  arguments are required: command". Since reports embed `__version__` and
  0.5.1 shipped reports carrying 0.5.0, an install whose version cannot be
  queried at the top level is exactly how that drift stays invisible.

### Fixed (packaging)

- **The wheel shipped without `detector_config/detector.yaml`.**
  `package-data` listed `templates/*` and `configs/*` but not the yaml, so a
  non-editable install — the path every `pip install tmaudit` user takes —
  fell back to the built-in defaults and behaved differently from the source
  tree it was built from. The suite stayed green because it runs against
  `src/` via `PYTHONPATH`, where the file exists; an editable install hides
  it the same way. `tests/test_package_data.py` now reads the built wheel
  rather than the source tree, and was confirmed to fail on the wheel that
  exposed this before being fixed.
- **`tmaudit.pyz` carried `.pyc` bytecode.** `_build_pyz.py` copied the
  package tree with no filter, so any prior test run or editable install left
  `__pycache__` inside `src/`, and it was archived verbatim: the artifact
  doubled in size (157 KB vs 85 KB) and shipped bytecode compiled against
  whichever interpreter built it. `copytree` now ignores
  `__pycache__`/`*.pyc`/`*.pyo`.

This defect was found and fixed independently on the other development
branch as release 0.5.2; see `DIVERGENCE_ANALYSIS.md`.

### Fixed (first-run output)

- **`tmaudit list` showed five dead paths on any machine that is not the
  author's, and said nothing about it.** The five built-in rulepacks describe
  the author's own manuscripts, so their `dir` values are Windows paths. On a
  fresh `pip install` elsewhere, the listing printed all five verbatim: a new
  user sees `F:/Research/PAPER1_CONSOLIDATED` through `PAPER5`, all absent,
  with no indication that this is expected or how to repoint them. The
  override has existed all along (`TMAUDIT_RESEARCH_DIR`), and `--paper-dir`
  covers the case of auditing an unrelated paper, but neither was mentioned
  at the one place a confused user looks.

  Missing paths are now marked `(missing)` and a closing note names both
  escapes. The rows are deliberately **not** hidden — the rulepacks really
  are bundled, and the listing is the only place a user can learn a rulepack
  for paper N exists. When nothing resolves the note explains that these are
  the author's manuscripts rather than a skipped download; when only some
  resolve it drops that claim and the export hint, since both would then be
  false or redundant. The mark is computed against the live filesystem per
  run, so it disappears as soon as a path points somewhere real.

  Tests: `tests/test_cli_list.py` (7 cases). This subcommand had **zero**
  coverage before, which is why the rough edge survived: one test derives the
  expected mark count from the filesystem instead of hardcoding it, so the
  original defect fails the suite on any non-Windows machine.

## [v0.5.3] — 2026-10-24

### Added — `verify --target FILE`: audit a paper you do not own

`PAPER_CONFIGS` is keyed by `int` 1..5 and points at five directories on
the author's machine, so `tmaudit verify --paper 1` was unusable to
anyone else. `--target` loads a config from disk (`.toml`, or `.json` on
Python 3.9/3.10 without the `toml` extra) and runs the **same** verify
path: same template, same substitution, same checks, same report.

```
tmaudit verify --target paper.toml
tmaudit verify --target paper.toml --dry-run
```

`PAPER_CONFIGS` is unchanged. `.toml` needs `tomllib` (3.11+) or
`pip install 'tmaudit[toml]'`; `dependencies` stays empty.

Validation is strict on purpose: an unknown key is an error with a
"did you mean" suggestion, never a silent no-op — a config typo that
quietly disables a check produces exactly the unverifiable audit this
tool exists to prevent.

### Added — `tmaudit.target`: the audited object is no longer a bare string

`Target` is a read-only view (`read`, `lines`, `sections`, `citations`,
`metadata`). `TexTarget` implements it over LaTeX; `TextTarget` wraps a
plain string so a Target-aware plugin can still be driven from text.

A plugin opts in by naming its first parameter `target` (or
`target_or_tex` / `doc`); otherwise it keeps receiving `str`. **Every
plugin written before v0.6.0 works unchanged**, including direct calls
with `tex=`.

### Added — bibliography detection

`[paper].bib` is optional. When absent the bibliography is detected:
conventional names first, then a content sniff over top-level files, so
`bib.bib`, `custom.bib` and an arXiv tarball's `main.bbl` all work with
no config edit. `[paper].tex_basename` also now reaches the generated
script's `MAIN`, which it previously did not.

### Fixed

- **C4 only understood BibTeX.** A `.bbl` (what an arXiv source tarball
  ships, usually without the `.bib`) produced "every cite key missing".
  `_bib_keys()` now unions `@type{key,` and `\bibitem{key}` forms,
  including natbib's multi-line optional label.
- **C4 reported 0 keys for a real `.bbl`.** The `\bibitem[...]` label can
  wrap across lines; the pattern now crosses newlines and tolerates
  brackets inside the label.
- **A missing abstract crashed the whole audit.** C1 raised, which made
  `main()` exit 2 and label every category crashed. A document without
  `\begin{abstract}` now completes: C1 is reported `[not observed]` and
  the exit code is 3, distinct from 0/1 (ran) and 2 (broken). The
  original invariant — an observation failure must never be printed as a
  finding — still holds.
- **`__version__` said 0.5.0 while `pyproject.toml` said 0.5.1**, and the
  tag v0.5.1 had already shipped, so every `audit-all` Markdown report
  carried the wrong version. Both now read 0.6.0 and a test asserts they
  agree.
- Report line hardcoded `refs.bib` regardless of the file actually read.

### Added — corpus regression suite

`tests/test_corpus_regression.py` runs the audit over all 15 papers in
`case-studies/arxiv-corpus/_corpus` and asserts no run aborts and every
citing paper resolves a bibliography. Marked `slow`.

### Exit codes (unchanged meaning, one new value)

| code | meaning |
|---|---|
| 0 | ran, no HIGH finding |
| 1 | ran, HIGH finding present |
| 2 | did not complete: missing input, or a check crashed |
| 3 | ran, no crash, but at least one category could not be observed |

## [v0.5.2] — 2026-10-24 (not yet on PyPI; publishing alongside v0.6.0)

### Fixed

- **The published wheel now ships `detector_config/detector.yaml`.** The file
  was absent from the built distribution because `package-data` did not list
  `detector_config/*.yaml`. A non-editable install — the path every
  `pip install tmaudit` user takes — therefore fell back to the built-in
  defaults, and `tests/test_detector_config.py` failed against the installed
  package. Editable installs masked the omission.
- **A relative `--paper-dir` was resolved twice.** The forked script was
  written to `paper/verify_generic.py` and then launched with `cwd=paper`, so a
  relative path became `paper/paper/verify_generic.py`. `fork_*` now resolves
  the directory first; a regression test covers the relative-path invocation.

### Changed

- **README rewritten around the external user**: a one-command quick start, a
  real excerpt of the output, and an explicit statement that C1–C3/C6 are
  per-paper while C4–C10 run on any manuscript. Added
  `examples/sample-paper/` so the documented command has a runnable target.

### Added

- **`tmaudit verify --paper-dir DIR` without `--paper`** runs the generic
  checks on an arbitrary manuscript: `forge.fork_verify_generic()` forks
  the factory template (empty `CHECKS_CONFIG`) into `DIR`, so the per-paper
  categories (C1/C2/C3/C6) report *not applicable* and the generic
  categories run. No `--main` flag is needed — the root `.tex` is located by
  name (`main.tex`) or, failing that, as the sole `.tex` declaring
  `\begin{document}` (`forge.find_main_tex`). `plugins run --paper-dir` uses
  the same resolution, so a plugin can audit a directory whose root file is
  not `main.tex`.
- **Bibliography from a compiled `.bbl`.** C4 reads cite keys from
  `refs.bib` (`@type{key,`) *or* a `.bbl` (`\bibitem[label]{key}`) through
  the new `_bib_keys` helper; a paper that ships only its `.bbl`, as arXiv
  submissions often do, no longer needs a `refs.bib` for its citations to
  be checked.
- **`case-studies/arxiv-2502.14074/`** — the generic path plus two
  `requires_config=False` plugin checks (`claims-significance-no-test`,
  `claims-percent-table-no-uncertainty`) run against one real paper, every
  input pinned by SHA-256. The checks ship as an installable plugin package
  (`case-studies/arxiv-2502.14074/tmaudit_claims_plugin/`).

### Fixed

- **C4 no longer aborts the whole audit when no bibliography is present.**
  `main()` used to `return 2` when `refs.bib` was missing. With neither a
  `.bib` nor a `.bbl`, C4 now reports **not applicable** and the remaining
  categories still run; a genuinely absent manuscript `.tex` is still exit
  2. Surfaced by the arbitrary-paper path: the subject paper ships no
  `.bib`.
- **C9 caption extraction handles nested braces.** The brace-bounded regex
  `\\caption\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}` accepted only one nesting
  level, so a figure whose caption nested twice — e.g.
  `\caption{\textbf{... \textsc{Swim} ...}}` or
  `\caption{\textcolor[HTML]{2f70b8}{{Llama-3-70B}} ...}` — was reported as
  having **no caption** (a HIGH false positive). Caption extraction is now
  a balanced-brace scan (`_c9_balanced_content`), with regression tests for
  both nested forms and for a genuinely unbalanced group. Found by auditing
  arXiv:2502.14074 (see `case-studies/arxiv-2502.14074/`).
- **C4's missing-key message** now reads "missing from the bibliography
  (.bib/.bbl)" instead of naming `refs.bib`, which is inaccurate once the
  source may be a `.bbl`.

### Changed

- **Test count: 246 → 262** (fast suite, `pytest -m "not slow"`). Added
  `tests/test_verify_paper_dir.py` (13 tests) and three nested-brace
  regression tests in `tests/test_c9_figure_caption.py`. The `README.md`
  test badge is updated to 262 to match.

## [v0.5.1] — 2026-10-16

### Fixed (self-audit defects D1-D6)

All six defects were found by auditing this tool's own template against
25 real arXiv LaTeX sources (`case-studies/arxiv-corpus/`).

- **D1 — neutral factory config.** `CHECKS_CONFIG` in
  `verify_TEMPLATE.py` shipped pre-filled with one specific paper's
  configuration (a `'liu2026'` self-cite prefix, TTRL symbol
  definitions, a "Power analysis" section requirement), so a generic
  audit fired paper-specific checks against any document it was pointed
  at. The factory default is now an empty dict: the paper-specific
  categories (C1, C2, C3, C6) report **not applicable** instead. The
  generic checks (C4 missing cite keys, C5, C7, C8 sub-check 3, C9
  sub-checks 1/2/4, C10 sub-checks 1/3) still run with built-in
  defaults, and C4's self-cite sub-check stays silent without a prefix
  instead of requiring one.
- **D2 — "clean" is no longer conflated with "did not run".** The
  summary distinguishes `checked` / `not applicable` / `error` per
  category. Previously a category whose configuration was missing
  returned zero findings and printed as `[OK]`.
- **D3 — one crashed check no longer aborts the audit.** `main()` runs
  each category through a guarded wrapper: a crash degrades that one
  category to `[ERROR]` and the remaining categories still run. Exit
  code 2 now also covers a crashed check (a crashed check is not a
  passed check). Previously one missing config key aborted the whole
  audit with a `KeyError`.
- **D4 — BibTeX key regex.** `@\w+\{([^,]+),` swallowed whitespace and
  newlines, so a key on its own line (`@article{\n  key,`) was captured
  with its surroundings and cite keys that existed in refs.bib were
  reported as missing. Replaced by `_BIB_KEY_RE = @\w+\{\s*([^,\s]+)\s*,`
  with regression tests for the multiline, padded, and inline forms.
- **D5 — raw docstring.** `_c9_parse_figure_block`'s docstring contained
  `\caption` / `\includegraphics`, producing a `SyntaxWarning` on every
  import. It is now a raw string.
- **D6 — C1 observation failures are errors, not findings.** C1 on a
  document without an abstract reported a HIGH finding ("No abstract
  environment found."). It now raises, and `main()` records the
  category as an error. Also hardened C1/C2/C4 to use `get()` defaults
  so a direct call bypassing `main()`'s gate degrades to "nothing to
  check" instead of `KeyError`.

### Added

- **`tests/test_template_defaults.py`** — 21 tests covering D1-D6,
  including end-to-end `main()` runs over synthetic documents and a
  compile-with-`SyntaxWarning`-as-error check.
- **`tests/test_c6_threshold.py`** — sets the blacklist explicitly
  (the factory config it implicitly relied on no longer exists).

## [v0.5.0] — 2026-07-11

### Added (plugin whitelist — `c11_plugins_enabled`)

- **`filter_active(plugins, disabled, enabled)`** — adds an
  optional `enabled` whitelist kwarg. When non-empty, only
  plugins whose name appears in the list are kept. This is
  the v0.5.0 mechanism for **per-paper plugin lock-down**.
  Behavior:
    - Both `enabled` and `disabled` set → `enabled` wins,
      `disabled` is ignored, a warning is logged.
    - Only `disabled` set → existing v0.4.0 blacklist
      behavior (no break in compat).
    - Only `enabled` set → whitelist filter.
    - Neither set → all plugins run (existing fall-through).
- **`audit_plugins(..., enabled)`** — accepts and threads
  through to `filter_active`. Reads `c11_plugins_enabled`
  from the paper config when not explicitly passed.
- **`paper_configs.PAPER5_CONSOLIDATED`** — adds
  `'c11_plugins_enabled': ['flag-todo-markers']` as a
  usage example (locked-down plugin set for the most
  recently authored paper).
- **`tests/test_plugin_api.py`** — 7 new tests:
    - `test_filter_active_empty_lists_run_all`
    - `test_filter_active_blacklist_only`
    - `test_filter_active_whitelist_only`
    - `test_filter_active_whitelist_overrides_blacklist`
    - `test_filter_active_whitelist_with_unknown_plugin`
    - `test_audit_plugins_respects_c11_plugins_enabled`
    - `test_paper_configs_can_carry_c11_plugins_enabled`
- **`_check_all_regressions.py`** — adds Bug 15 (whitelist
  branch disabled) and Bug 16 (precedence swap) injects.
  Meta-test now 16/16 caught.

### Changed

- **`filter_active` signature** — added `enabled: Optional[Iterable[str]] = None`
  as the third positional-or-keyword argument. Backward-
  compatible: existing callers passing only `disabled`
  continue to work.
- **`audit_plugins` signature** — added `enabled` kwarg with
  the same default. Backward-compatible.

### TDD provenance

- **Red phase** (commit `0d538a1`): added 7 failing tests.
- **Green phase** (commit `424c806`): minimal changes to
  `filter_active` + `audit_plugins` + `paper_configs` to
  make all 7 pass.
- **Anchor fix** (commit `5129e5d`): updated Bug 14's
  regression anchor to the new `filter_active` signature.
- **Meta-test expansion** (commit `5129e5d` + this commit):
  Bug 15 + 16 injects added, meta-test 14/14 → 16/16.

### Compatibility

- All 218 prior tests continue to pass.
- All 14 prior regression tests continue to catch their bugs.
- No CLI changes; `cmd_audit_all` reads `c11_plugins_enabled`
  from the paper config (no new flag in v0.5.0).

## [0.4.0] — 2026-07-10 (in progress)

**Theme**: Plugin API. Ship the 4th (and final) audit-
architecture feature: a stable plugin API that lets users
write their own audit checks.

### Added (Plugin API)

- **`src/tmaudit/plugins.py`**:
  - `Finding` dataclass — frozen, severity-validated
    (HIGH/MEDIUM/LOW with MED alias), with `paper_id`
    field for audit-all attribution.
  - `@check(name=…, severity=…, requires_config=…,
    help_text=…, version=…)` decorator that wraps a
    `def check(tex, config) -> List[Finding]` and adds
    metadata.
  - `load_plugins()` discovery via
    `importlib.metadata.entry_points(group="tmaudit.plugins")`.
    Failing entry-points are logged and skipped, never raised.
  - `filter_active(plugins, disabled)` — remove disabled
    plugin names.
  - `run_plugin(plugin, tex, config, paper_id)` /
    `run_all_plugins(...)` / `audit_plugins(paper_n,
    paper_dir, ...)` — bulk runner with per-plugin
    cache integration.
  - Per-call cache invalidation: a buggy plugin cannot break
    the audit (logged, skipped).

- **`src/tmaudit/cache.py`**:
  - `plugin_cache_key(paper_n, plugin_name, plugin_version,
    main_tex)` — content-addressable key. Updates to a
    plugin's `version=` invalidate stale cache entries.

- **`src/tmaudit/cli.py`**:
  - `tmaudit plugins list` — table of every discovered
    plugin (name, module, severity, version).
  - `tmaudit plugins info NAME` — details for one plugin.
  - `tmaudit plugins run NAME --paper N` — execute a single
    plugin against one paper (no caching).
  - `tmaudit audit-all` now invokes `audit_plugins(...)` per
    paper after the C1..C10 subprocess run, so user-written
    plugins fire automatically.

- **`src/tmaudit/__init__.py`**:
  - Re-exports `Finding`, `check`, `load_plugins`,
    `audit_plugins`, `filter_active`, `run_plugin`,
    `run_all_plugins`, `PLUGIN_GROUP`, `VALID_SEVERITIES`,
    `cache_key`, `plugin_cache_key`, `CacheDB`.

- **`tmaudit_example_plugin/`** (NEW sibling package):
  - Three demo checks: `flag-todo-markers` (MEDIUM),
    `flag-xxx-markers` (LOW), `flag-long-abstract`
    (MEDIUM, configurable threshold).
  - Install with `pip install -e ./tmaudit_example_plugin`.
  - Source split: `tmaudit_example_plugin/__init__.py`
    (package metadata) + `tmaudit_example_plugin/checks.py`
    (the demo checks themselves).
  - `pyproject.toml` declares the entry-points under
    `[project.entry-points."tmaudit.plugins"]`.

- **`tests/test_plugin_api.py`** (NEW, 31 tests) — covers
  `Finding` semantics, `@check` validation, `filter_active`,
  `run_plugin` stamping, `run_all_plugins` exception
  safety, entry-points loader, malformed entry-point
  recovery, and per-paper `c11_plugins_disabled`.

- **`tests/test_example_plugin.py`** (NEW, 11 tests) —
  end-to-end tests of the three demo checks after install,
  including the `\bXXX\b` boundary check and the
  `c11_long_abstract_threshold` config override.

- **`_check_all_regressions.py`**:
  - **`inject_bug13()`** (NEW): Bug 13 — plugin loader
    raises on a malformed entry-point. Replaces the
    `except Exception` block with bare `raise`. Regression
    test
    `tests/test_plugin_api.py::test_loader_skips_malformed_entry_point`
    catches this.
  - **`inject_bug14()`** (NEW): Bug 14 — per-paper
    `c11_plugins_disabled` is ignored. Drops the
    `filter_active(...)` step. Regression test
    `tests/test_plugin_api.py::test_audit_plugins_respects_per_paper_disable`
    catches this.

- **`src/tmaudit/configs/paper_configs.py`**:
  - Paper 5 `c2_section_pattern` was reverted to the
    multi-branch form supporting both `Power analysis`
    and `Statistical Protocol`; this is the upstream fix
    for Bug 6 (related to v0.3.0 history).

- **`engineering_notes_verify_template.md`**:
  - **§14** (NEW, 14 sub-sections, 415 lines) documents the
    plugin API design rationale: motivation, design
    overview, protocol, pyproject schema, discovery,
    lifecycle, CLI integration, per-paper override, cache
    integration, test plan, limitations, roadmap to v1.0,
    alternative designs, implementation milestones.

- **Test count**: 176 → **218** (+42 tests).
- **Meta-test**: 12/12 → **14/14** (Bug 13 + Bug 14).

## [0.4.x maintenance] — after 0.4.0

Work landed after 0.4.0 that never got a version number of its own:
the docs issue template, the community-files validator, and the CI job
that runs it. Listed here rather than under a version heading so the
release history stays honest about what was actually tagged.

Two enhancement issues are open and ready for community
contribution. See [`.github/issues/16-c7-citation-context.md`](./.github/issues/16-c7-citation-context.md)
and [`.github/issues/17-audit-cache.md`](./.github/issues/17-audit-cache.md)
for the full proposals, and [`ROADMAP.md`](./ROADMAP.md) for
the planned release timeline.

| Issue | Title | Effort | Status |
|---|---|---|---|
| #16 | C7 audit category (citation context) | Medium | Ready for PR |
| #17 | Audit-cache layer | Medium | Ready for PR |

### Added (templates)

- **`.github/ISSUE_TEMPLATE/docs.md`** — 14-section template
  for documentation-only issues (typos, clarifications, new
  sections, restructures, translations). Distinct from
  `enhancement.md` (which is for code changes that improve
  existing features). The new template asks for a "rendered
  output (before vs after)" section, a "spell / grammar /
  style check" list, a "link / cross-reference check" list,
  and a "backwards compatibility" check. 72 checkboxes total
  (most of any template). Auto-applies `documentation` +
  `needs-triage` labels.
- **`.github/ISSUE_TEMPLATE/enhancement.md`** (already
  added in v0.1.1) — 13-section template for enhancement
  issues. 35 checkboxes. Auto-applies `enhancement` +
  `needs-triage` labels.
- **`.github/ISSUE_TEMPLATE/config.yml`** (updated) —
  comments now mention the 4 templates and explain the
  bug-vs-feature-vs-enhancement-vs-docs distinction.
- **`_demo_c7_enhancement_filled.md`** — example of a C6
  threshold enhancement issue filled out using
  `enhancement.md`.
- **`_demo_docs_filled.md`** — example of a 1-word typo
  fix filled out using `docs.md` (shows that the template
  is fast to fill for trivial changes).

### Added (CI integration)

- **`_check_github_templates.py`** — community-files validator
  that runs in CI. Validates 9 dimensions:
  1. `.github/` directory structure
  2. `ISSUE_TEMPLATE/config.yml` (YAML, blank_issues,
     contact_links)
  3. 4 issue templates (frontmatter, name, description,
     title, labels, assignees, body)
  4. `PULL_REQUEST_TEMPLATE.md` (H2 count, checkbox count,
     mentions of "test" and "checklist")
  5. `CODEOWNERS` (presence, rule count)
  6. `dependabot.yml` (YAML, updates list)
  7. `CODE_OF_CONDUCT.md` (presence, line count)
  8. `SUPPORT.md` (presence, line count)
  9. `workflows/*.yml` (YAML, name, on, jobs)
  Supports `--strict` (warnings fail) and `--json` (machine-
  readable output) flags. Currently 44/44 OK, 0 FAIL.
- **`.github/workflows/ci.yml`** (updated) — added
  `validate-community-files` job that runs the new
  validator. Also writes JSON to
  `community-files-validation.json` and uploads as a CI
  artifact (retention 7 days). The job is independent of
  the others (does not `need` them) so a YAML issue in
  the workflow does not block the validator.


## [0.3.0] — 2026-07-10 (in progress)

**Theme**: Statistical-power audit (C8) + extended reproducibility
checks (C10). Closes the 8-audit-category vision from
[`ROADMAP.md`](./ROADMAP.md).

### Added (C8 statistical power)

- **`src/tmaudit/templates/verify_TEMPLATE.py`**:
  - **C8 audit category** (NEW) — `check_c8_statistical_power`.
    A paper's statistical claims are judged on 3 sub-categories:
    1. **Effect-size re-derivation** (HIGH severity): for each
       claimed Cohen's d in the per-paper `c8_claimed_effects`
       config, parse the matching `\begin{tabular}` row and
       recompute d_actual. If `|d_actual - d_claimed| > 0.10`,
       emit a HIGH finding. The regex parser falls back to the
       first two data rows when no label match is found, and
       uses `min(n1, n2)` as the per-group n for power.
    2. **Statistical power** (MED severity): post-hoc power via
       `Phi(|d| * sqrt(n_per_group/2) - z_alpha/2)`. If
       power < 0.50 the effect is *underpowered* (MED, recommend
       n × 4). If power > 0.99 AND claimed d ≤ 0.50 AND
       min(n1,n2) ≥ 1000 the result is *suspiciously overpowered*
       (MED, possible p-hacking tell).
    3. **Significance-claim scan** (MED severity): always runs
       (independent of opt-in config). Scans the body for
       `significantly\s+different` and emits a MED finding if
       no p-value appears within 200 chars. Also flags
       internally-inconsistent pairs (d < 0.10 with p < 0.001)
       as a likely p-hacking signal.
  - `_C8_D_MISMATCH_THRESHOLD = 0.10`, `_C8_POWER_UNDERPOWERED
    = 0.50`, `_C8_POWER_OVERPOWERED = 0.99`,
    `_C8_SIGNIFICANCE_CONTEXT_CHARS = 200` (heuristic constants,
    mirrored in the test file).
  - SEVERITY['C8'] = 'MEDIUM' (variable: HIGH for d-mismatch,
    MED for power/significance).
  - `main()` driver now wires `CHECKS_CONFIG['c8_claimed_effects']`
    into the C8 call and prints a C8 row in the findings table.

- **`src/tmaudit/configs/paper_configs.py`**:
  - Papers 1, 3, and 5 now carry example `c8_claimed_effects`
    entries (Paper 1: `main_effect`, d=1.00; Paper 3: `coupling`,
    d=0.80; Paper 5: `accuracy`, d=0.50). Papers 2 and 4 carry
    empty lists (C8 opt-in).
  - `_format_c8_claimed_effects()` writer added.

- **`tests/test_c8_statistical_power.py`** (NEW): 18 TDD tests
  covering effect-size re-derivation, statistical power (under-,
  adequately-, and over-powered regimes), significance-claim
  text scan, multiple effects, malformed LaTeX, extra fields
  in config, and a d-mismatch tolerance check. **All 18 pass.**

- **`_check_all_regressions.py`**:
  - **`inject_bug11()`** (NEW): Bug 11 — C8 inverted d-mismatch
    threshold. Replaces `if d_diff > _C8_D_MISMATCH_THRESHOLD:`
    with `if d_diff < ...: # BROKEN: inverted comparison`. The
    regression test
    `tests/test_c8_statistical_power.py::test_c8_effect_numbers_match_no_finding`
    catches this (it expects 0 HIGH findings when d_claimed ==
    d_actual; with the bug, a HIGH fires).

- **Test count**: 142 → **160** (+18 C8 tests).
- **Meta-test**: 10/10 → **11/11** (+1 with Bug 11).

### Added (C9 figure-caption)

- **`src/tmaudit/templates/verify_TEMPLATE.py`**:
  - **C9 audit category** (NEW) — `check_c9_figure_caption`.
    A figure-caption consistency audit with 4 sub-categories:
    1. **Caption existence** (HIGH): a figure without
       `\caption{...}` is undocumented. Emitted for any
       `\begin{figure}` block missing a caption.
    2. **Caption placement** (MED): per the IEEE / ACM / TMLR
       convention, captions go BELOW the figure. If the
       `\caption` precedes the `\includegraphics`,
       emit MED. The regex recognises the optional
       `[key=value]` option block (e.g.,
       `[width=0.9\textwidth]`) between the
       `\includegraphics` command name and the
       `{filename}` argument.
    3. **Caption content** (MED, opt-in): each caption
       should contain at least one of the
       `expected_keywords` listed for that figure in the
       per-paper `c9_figure_keywords` config. Match is
       case-insensitive substring. Generic captions like
       "A pretty picture" are flagged.
    4. **Figure referenced** (MED): every `\label{fig:...}`
       should be referenced by `\ref` / `\autoref` / `\cref`
       in the body text. Orphan figures (defined but never
       cited) are flagged.
  - Sub-checks 1, 2, 4 always run (independent of opt-in
    config). Sub-check 3 only runs when `c9_figure_keywords`
    is non-empty (graceful degradation pattern, same as C8).
  - SEVERITY['C9'] = 'MEDIUM'.
  - Driver `main()` now wires
    `CHECKS_CONFIG['c9_figure_keywords']` into the C9 call
    and prints a C9 row in the findings table.

- **`src/tmaudit/configs/paper_configs.py`**:
  - Papers 1 and 5 carry example `c9_figure_keywords`
    entries (e.g., `{'fig_id': 'fig:overview',
    'expected_keywords': ['overview', 'architecture']}`).
    Papers 2, 3, 4 carry empty lists (opt-in).
  - `_format_c9_figure_keywords()` writer added.

- **`tests/test_c9_figure_caption.py`** (NEW): 16 TDD tests
  covering caption existence (HIGH), caption placement
  (MED), content keyword match (case-insensitive), figure
  reference detection, multiple figures, malformed LaTeX,
  and false-positive guards for forward references. **All
  16 pass.**

- **`_check_all_regressions.py`**:
  - **`inject_bug12()`** (NEW): Bug 12 — C9 inverted
    caption-placement condition. Replaces
    `and parsed['caption_pos'] < parsed['graphic_pos']):`
    with `>` instead of `<`. The regression test
    `tests/test_c9_figure_caption.py::test_c9_caption_above_figure_emits_med`
    catches this (with the bug, a caption that's *above*
    the graphic — i.e., `caption_pos < graphic_pos` —
    fails the inverted comparison, so no MED finding is
    emitted and the test fails).

- **Test count**: 160 → **176** (+16 C9 tests).
- **Meta-test**: 11/11 → **12/12** (+1 with Bug 12, when
  Bug 6 anchor is fixed).

### Added (C10 reproducibility, carried over from v0.3.0 dev)

The C10 reproducibility audit (with 20 regression tests and
Bug 10 meta-test) shipped earlier in the v0.3.0 development
cycle and is documented as part of v0.3.0 in
[`RELEASE_NOTES_v0.3.0.md`](./RELEASE_NOTES_v0.3.0.md).

## [0.2.0] — 2026-07-10 (in progress)

**Theme**: Multi-paper batch mode + Paper 2/3/4
config completion.

### Added (Paper 2/3/4 configs)

- **`src/tmaudit/configs/paper_configs.py`**:
  - **Paper 2** ("Impossibility Triangle"): filled in 3 C1
    symbols (`$V_1, V_2, V_3$` for the three triangle
    vertices), 1 C2 family, and a `c7_max_ceremonial: 3`
    threshold.
  - **Paper 3** (Coupling-Noise Decomposition): filled in 3
    C1 symbols (`$\sigma_C, \sigma_I, \sigma_T$` for the
    coupling / intrinsic / total noise components), 3 C2
    families, and a `c7_max_ceremonial: 3` threshold.
  - **Paper 4** (N-Sensitivity): filled in 3 C1 symbols
    (`$S_N, N_0, \Delta_S$` for the metric, baseline sample
    size, and threshold), 2 C2 families, and a
    `c7_max_ceremonial: 3` threshold.
  - All papers now have a `c7_max_ceremonial` field
    (Papers 1, 5: 2; Papers 2, 3, 4: 3).
  - All `c2_abstract_k_allowed` lists are non-empty
    (default `[1]` for Papers 2/3/4; `[3]` for Paper 1;
    `[9]` for Paper 5).
  - `substitute_verify()` now writes `c7_max_ceremonial`
    into the generated verify_p<N>.py.

- **`tests/test_paper_configs.py`** (new): 9 coverage
  tests:
  - All 5 papers in PAPER_CONFIGS.
  - No duplicate paper numbers.
  - All required fields present.
  - c7_max_ceremonial is a non-negative int.
  - All 5 papers have non-empty c1_symbols (v0.2.0 AC).
  - All 5 papers have non-empty c2_families (v0.2.0 AC).
  - All paper dirs are Path objects.
  - `substitute_verify()` works for every paper.
  - c2_abstract_k_allowed is non-empty (v0.2.0 AC).

- **Test count**: 82 → **90** (+8 new paper_configs tests).
- **Coverage**: All 5 papers (1, 2, 3, 4, 5) now have full
  C1/C2/C3/C4/C5/C6/C7 config (was 2/5 before this release).

### Added (audit-all Markdown report)

- **`src/tmaudit/report.py`** (new, 240 lines):
  - `PaperAuditResult` dataclass: one paper's audit results.
  - `Finding` dataclass: one finding (category, message,
    line, severity).
  - `parse_verify_output()`: parses a verify_p<N>.py stdout
    into a PaperAuditResult.
  - `render_markdown()`: renders a list of results as a
    GitHub-flavored Markdown report.
  - `write_markdown_report()`: convenience function that
    writes the report to a file.

- **`src/tmaudit/cli.py`**:
  - `tmaudit audit-all` now supports `--output report.md`
    (write Markdown report) and `--no-cache` (bypass cache).
  - `cmd_audit_all()` captures each paper's stdout, parses
    findings, builds a list of `PaperAuditResult`, and writes
    the Markdown report if `--output` is set.

- **`tests/test_report.py`** (new, 12 tests):
  - Empty results -> minimal valid Markdown.
  - One paper, no findings -> "No issues detected" section.
  - Multiple findings, categorized by category.
  - Multiple papers, mixed pass/fail.
  - write_markdown_report writes to file.
  - parse_verify_output extracts findings from real verify
    output.
  - parse_verify_output handles empty stdout.
  - parse_verify_output handles missing DETAILED FINDINGS.
  - SEVERITY_MAP matches verify_TEMPLATE.SEVERITY.
  - Report has 4 required sections.
  - Markdown is valid (balanced table pipes).
  - Empty paper_dir is OK.

- **`.github/workflows/ci.yml`**:
  - New `audit-all` job runs `tmaudit audit-all --output
    audit-report.md --no-cache` and uploads the report as
    a CI artefact (30-day retention).
  - CI now has 5 jobs: pytest, meta-test,
    validate-community-files, audit-all, lint.

- **Test count**: 90 → **110** (+12 report tests).
- **Real-world impact**: CI now produces a human-readable
  Markdown report that reviewers can download and read
  directly, instead of having to read the raw verify
  output. This makes the audit results more accessible
  to non-developers (e.g., paper authors, advisors).

### Added (LLM-based C7 fallback, opt-in)

- **`src/tmaudit/llm_fallback.py`** (new, 230 lines):
  - `LLMResult` dataclass: the LLM's classification of
    a citing sentence.
  - `hash_sentence()`: SHA-256 of a sentence (for caching).
  - `_build_prompt()`: builds the chat-completions prompt
    (system + user messages; no paper context).
  - `_call_llm()`: makes a single OpenAI-compatible call
    and parses the response.
  - `LLMBudgetExceeded` exception: raised when budget is
    exhausted.
  - `LLMFallback` class: orchestrates calls, enforces
    budget, caches results.
  - `is_borderline()`: 20-30 word sentence is "borderline"
    (heuristic most likely to be wrong here).

- **`src/tmaudit/templates/verify_TEMPLATE.py`**:
  - `check_c7_citation_context()` now has a new
    `c7_llm_budget` parameter (default 0 = no LLM).
  - When `c7_llm_budget > 0` AND the LLM is enabled via
    env vars AND the env vars are set, the function
    re-checks borderline ceremonial cites with the LLM.
  - If the LLM says "engaged", the cite is demoted
    (removed from the ceremonial set). If the LLM says
    "ceremonial", the cite is confirmed (heuristic result
    kept).
  - The privacy guarantee: **only the citing sentence**
    is sent to the LLM. No paper context, no abstract,
    no other cites, no author names.

- **`src/tmaudit/cli.py`**:
  - `tmaudit verify` and `tmaudit audit-all` now support
    `--llm-budget N` (max LLM calls per audit).

- **`tests/test_llm_fallback.py`** (new, 12 tests):
  - hash_sentence is deterministic + 64 chars.
  - is_borderline correctly identifies 20-29 word sentences.
  - LLMFallback disabled by default (no env vars).
  - LLMFallback disabled when budget=0.
  - LLMFallback enabled with env vars + budget.
  - classify caches results.
  - LLMBudgetExceeded when budget is exhausted.
  - classify returns None on network failure.
  - classify handles malformed JSON response.
  - Prompt does NOT include paper context (privacy).
  - LLMResult has all expected fields.
  - stats() returns usage info.
  - Tests use a **mock OpenAI HTTP server** (no real LLM
    calls, no API costs, deterministic).

- **Privacy guarantees** (per ROADMAP.md AC):
  1. The full paper text is NEVER sent to the LLM.
     Only the citing sentence (a 30-word string) is sent.
  2. The LLM sees no paper title, no abstract, no other
     cites, no author names, no institution names.
  3. The user can audit the exact prompt by reading
     `_build_prompt()`.
  4. The fallback is **opt-in**: by default, no LLM is
     called. Set TMAUDIT_LLM_* env vars and pass
     --llm-budget N to enable.
  5. The LLM is asked for ONE sentence at a time, and
     the budget caps the total number of calls per audit.

- **Environment variables** (all required to enable):
  - `TMAUDIT_LLM_ENDPOINT`: URL of an OpenAI-compatible
    API (e.g., `https://api.openai.com/v1/chat/completions`,
    `http://localhost:11434/v1/chat/completions` for
    local Ollama).
  - `TMAUDIT_LLM_API_KEY`: API key for the endpoint.
  - `TMAUDIT_LLM_MODEL`: model name (default
    `gpt-4o-mini`).

- **Test count**: 110 → **122** (+12 LLM tests).
- **Real-world impact**: the LLM fallback is a
  **second opinion** for the heuristic on borderline
  cites. It does not replace the heuristic (which is
  fast, free, and runs by default); it supplements it
  when the user opts in. This makes the C7 check more
  accurate without making it mandatory.

## [0.1.1] — 2026-07-10

**Bug 7 fix**: C6 blacklist false-positive on idiomatic
English (e.g., "yields a value of X"). The `min_count`
threshold is the fix that makes 1-2 occurrences of
"yield" / "reveal" not be reported. 3+ occurrences still
trigger (to catch over-use of vague words).

- **`src/tmaudit/templates/verify_TEMPLATE.py`**:
  `check_c6_blacklist` now uses `min_count = 3`. Only 3+
  occurrences of a blacklisted word are reported.
- **`tests/test_c6_threshold.py`** (new): 7 unit tests
  covering the threshold behavior.
- **`_check_all_regressions.py`**: added `inject_bug7` to
  catch regressions of this fix.
- **Meta-test score**: 6/6 → **7/7 caught**.
- **Test count**: 46 → **53**.

Patch release: one critical bug fix (C6 blacklist false-positive
on idiomatic English), 7 new unit tests, and 1 new bug added
to the meta-test. **No breaking changes** — drop-in replacement
for v0.1.0. See [`RELEASE_NOTES_v0.1.1.md`](./RELEASE_NOTES_v0.1.1.md)
for the full release notes.

### Fixed

- **Bug 7** — C6 blacklist (`check_c6_blacklist` in
  `verify_TEMPLATE.py`) was reporting the **first** occurrence
  of any blacklisted word (yield / reveal / paradigm) as a
  finding, producing false positives on idiomatic technical
  English like "yields a strictly lower $\Gamma$" (Paper 5,
  main.tex line 234). Fix: added a `min_count = 3` threshold
  so that 1-2 occurrences are not reported. 3+ occurrences
  still trigger, since that's the threshold at which the
  word is being over-used to avoid saying something specific.

### Added

- **`tests/test_c6_threshold.py`** — 7 new unit tests covering
  the C6 threshold behaviour (single-occurrence, two-occurrence,
  three-occurrence, inflections, per-word counting, word
  boundary).
- **Bug 7 in meta-test** — `_check_all_regressions.py` now
  has `inject_bug7()` that re-introduces the C6 false-positive
  (by setting `min_count = 0`) and asserts that
  `test_c6_does_not_flag_single_occurrence` catches it.
  Meta-test score: 6/6 → **7/7 caught**.
- **`engineering_notes_verify_template.md` §10** — full
  documentation of Bug 7 in 5 sub-sections (symptom / root
  cause / fix / regression test / meta-test).
- **`RELEASE_NOTES_v0.1.1.md`** — full release notes with
  diff stats, migration guide, and verification steps.

### Stats

| | v0.1.0 | v0.1.1 | Δ |
|---|---|---|---|
| Test count | 46 | **53** | +7 |
| Meta-test | 6/6 caught | **7/7 caught** | +1 |
| Files in PR | — | 5 | — |
| Lines changed | — | +248 / -4 | — |
| `tmaudit.pyz` size | 46 KB | 46 KB | unchanged |
| PR | — | [#15](https://github.com/aidless/tmaudit/pull/15) | — |
| Audit (Paper 5) | 1 finding (false positive) | 0 findings ✅ | -1 |

## [0.1.0] — 2026-07-10

### Added
- **6-category audit framework** (C1..C6) for TMLR papers
  (symbol definitions, Bonferroni consistency, formalization
  presence, citation hygiene, sample-size + test-name, blacklist
  words). Implemented as a generic `verify_TEMPLATE.py` and
  per-paper `PAPER_CONFIGS` for papers 1, 2, 3, 4, 5.
- **Compile pipeline** — 4-pass LaTeX compile (`_compile_check.py`)
  and abstract-Unicode-to-LaTeX fixer (`_fix_abstract_unicode.py`).
- **CLI** (`tmaudit` command) — `list` / `verify` / `compile` /
  `fix-unicode` / `audit-all` subcommands.
- **Single-file distribution** (`tmaudit.pyz`, ~46 KB) — built
  with `zipapp`, no `pip install` required.
- **Unit-test suite** (46 tests, 0.34s) — 6 bug-specific
  regression tests + 4 invariants + 3 happy-path + 5 config
  coverage + 3 CLI smoke tests.
- **Regression-injection meta-test** (`_check_all_regressions.py`)
  — verifies that each of the 6 regression tests actually
  catches its target bug. 6/6 caught in <30s.
- **CI configuration** (`.github/workflows/ci.yml`) — runs the
  full test suite on Python 3.9, 3.10, 3.11, 3.12; runs the
  meta-test; runs `pyflakes` lint. Uploads JUnit XML artifacts.
- **`engineering_notes_verify_template.md`** — 110-line
  engineering diary covering the 6 bugs, fixes, and
  regression-test validation.
- **Local CI simulation** (`_act_dryrun.py`, `_act_simulate.py`) —
  fallbacks for `act` when it cannot be installed. Validate
  `ci.yml` structure and run the steps locally.
- **Pre-commit hook** (`hooks/pre-commit`) — cross-platform
  Python script that runs the four CI steps on every commit.
  Installed via `hooks/install-precommit.sh` (Unix) or
  `hooks/install-precommit.ps1` (Windows).
- **`CONTRIBUTING.md`** — developer guide: how to run tests,
  install the pre-commit hook, add a new paper, and submit
  a pull request.
- **`.github/PULL_REQUEST_TEMPLATE.md`** — 40-checkbox PR
  template (10 H2 sections, 3 pre-merge sub-categories) that
  GitHub auto-populates on every new PR.
- **`.github/ISSUE_TEMPLATE/bug_report.md`** — 11-section
  bug report with severity / regression / diagnostic-output
  subsections. Auto-applies `bug` + `needs-triage` labels.
- **`.github/ISSUE_TEMPLATE/feature_request.md`** — 11-section
  feature request with use-case / proposed-solution /
  willingness-to-implement subsections. Auto-applies
  `enhancement` + `needs-triage` labels.
- **`.github/ISSUE_TEMPLATE/config.yml`** — issue chooser
  config that disables blank issues and routes security
  reports to private advisories.
- **`SECURITY.md`** — vulnerability disclosure policy with
  response timeline and "what is/isn't a security issue"
  table.
- **`.github/CODEOWNERS`** — auto-assign reviewers per file
  path; 12 rules covering production code, tests, build/CI,
  documentation, community-health files, and a default
  fallback.
- **`.github/dependabot.yml`** — automated weekly dep update
  PRs (Monday 09:00 UTC). Ignores pytest/pyyaml/regex
  major-version bumps. Auto-labels and auto-assigns to
  CODEOWNERS.
- **`.github/CODE_OF_CONDUCT.md`** — Contributor Covenant v2.1
  with 4-tier enforcement ladder.
- **`.github/SUPPORT.md`** — 4 support channels (Discussions,
  Bug report, Feature request, Security advisory) with
  expected response time table.
- **Bug 7 fix + regression test** — C6 blacklist now
  requires 3+ occurrences (was 1+). 1-2 occurrences of
  "yield" / "reveal" are common in idiomatic technical
  English and are no longer flagged. Added
  `tests/test_c6_threshold.py` with 7 tests covering
  single-occurrence, two-occurrence, three-occurrence,
  inflections, per-word counting, and word boundary cases.
- **Bug 7 added to meta-test** — `_check_all_regressions.py`
  now injects `min_count = 0` and asserts that
  `test_c6_does_not_flag_single_occurrence` catches the
  regression. Score: **7/7 bugs caught** (was 6/6).

### Fixed
- **Bug 1** — `repr('\b')` was returning `'\x08'` (backspace).
  Fix: regex-looking strings now use raw-string literals
  (`r'...'`).
- **Bug 2** — `re.sub` was interpreting backslashes in the
  replacement text. Fix: hand-written brace-counting loop with
  `str.slice` instead of `re.sub`.
- **Bug 3** — Brace counter was mis-counting `\{` and `\}` inside
  string literals. Fix: string-literal state machine that
  skips braces inside `'...'` and `"..."`.
- **Bug 4** — C1 audit only checked a 250-char window around the
  first symbol mention, missing Notation blocks at the end of
  the abstract. Fix: second pass (whole abstract) + third pass
  (first \\section{Introduction}).
- **Bug 5** — C5 test-name regex `paired\s+t-test` was too
  strict, missing `paired $t$-tests`. Fix:
  `paired[^a-zA-Z]{0,8}t[^a-zA-Z]{0,3}test`.
- **Bug 6** — `c2_section_pattern` only matched `Power analysis`,
  not Paper 5's `Statistical Protocol`. Fix: per-paper
  `c2_section_pattern` from config.

### Engineering
- **6 fixes** were applied in **~90 minutes** (debugging session).
  Estimated savings over hand-writing 5 per-paper audit scripts:
  **~8 hours**.
- **3** distinct sources of bug were identified:
  1. `repr()` vs raw strings (1)
  2. `re.sub` backreference interpretation (1)
  3. mini-parser without string-literal awareness (1)
- **2** design lessons were learned:
  1. Auditors prefer **false negatives** (which humans catch)
     over **false positives** (which humans ignore).
  2. Regression tests must be **self-validating** (a test that
     always passes is worse than no test at all).

### Notes for reviewers
- All 6 bug fixes have a **dedicated regression test**.
- All 6 regression tests are **meta-validated** to actually
  catch their target bug (i.e., they are not silently passing).
- The single-file distribution `tmaudit.pyz` is the recommended
  way to run the tool on a fresh machine.
- See [`engineering_notes_verify_template.md`](./engineering_notes_verify_template.md)
  for full bug history and lessons learned.
