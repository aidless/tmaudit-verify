# Roadmap
> ⚠️ 本 ROADMAP 的规划部分停留在 v0.1.x 时期；v0.1.0–v0.6.0 均已发布，最新状态见 [CHANGELOG.md](CHANGELOG.md)。v0.7.0 起为尚未开始的计划。

This document describes the planned future direction of
`tmaudit`. It is **not a commitment** — features may be
added, removed, or re-prioritised as we learn from real
usage. Issues on GitHub are the source of truth for what
is currently being worked on.

## Released

### v0.1.0 — 2026-07-10

Initial release. 6-category audit framework (C1..C6),
5-paper support, single-file distribution, 46-test
suite, 6-bug meta-test, full GitHub community-health
files.

### v0.1.1 — 2026-07-10

**Bug 7 fix**: C6 blacklist false-positive on idiomatic
English. Added `min_count = 3` threshold. 7 new unit
tests in `tests/test_c6_threshold.py`. Meta-test score
6/6 → **7/7 caught**. 46 → **53 tests**.

## In progress

### v0.1.2 — Planned Q3 2026

**Theme**: Performance + a new audit category.

Two enhancement issues are open and ready for community
contribution:

| Issue | Title | Area | Effort |
|---|---|---|---|
| [#16](.github/issues/16-c7-citation-context.md) | C7 audit category (citation context) | audit | Medium (1-3 days) |
| [#17](.github/issues/17-audit-cache.md) | Audit-cache layer | performance | Medium (1-3 days) |

### v0.1.2 acceptance criteria

A v0.1.2 release requires:

- [ ] Both issues implemented and merged via PR.
- [ ] All existing tests still pass (53/53 minimum).
- [ ] New tests for the new functionality (target: 60+
      total tests, 8/8 caught in the meta-test).
- [ ] `engineering_notes_verify_template.md` gets §11 (C7)
      and §12 (cache) sections.
- [ ] `CHANGELOG.md` v0.1.2 entry added.
- [ ] `tmaudit.pyz` rebuilt and attached to the release.
- [ ] No new bugs introduced (meta-test score does not
      drop below 8/8).

### v0.1.2 release process

1. Implement Issue #16 (C7) → PR #16 → merge.
2. Implement Issue #17 (cache) → PR #17 → merge.
3. Add `inject_bug8` to the meta-test for the new
   functionality.
4. Bump version to 0.1.2 in `pyproject.toml` and
   `src/tmaudit/__init__.py`.
5. Build and tag `v0.1.2`.
6. Write `RELEASE_NOTES_v0.1.2.md`.
7. Update `CHANGELOG.md`.
8. Push to GitHub and create the release.

## Planned

### v0.2.0 — Planned Q4 2026 / Q1 2027

**Theme**: Multi-paper batch mode + Paper 2/3/4
config completion.

| Issue | Title | Area | Status |
|---|---|---|---|
| (TBD) | `tmaudit audit-all --output report.md` | CLI | Not yet filed |
| (TBD) | Complete Paper 2 config | configs | Not yet filed |
| (TBD) | Complete Paper 3 config | configs | Not yet filed |
| (TBD) | Complete Paper 4 config | configs | Not yet filed |
| (TBD) | Markdown / HTML report output | output | Not yet filed |
| (TBD) | LLM-based C7 fallback (GPT-4 / Claude) | audit | Not yet filed |

### v0.2.0 acceptance criteria

- [ ] All Paper 2/3/4 configs complete (5/5 papers
      auditable, not just 2/5).
- [ ] `tmaudit audit-all` generates a single Markdown
      report covering all configured papers.
- [ ] The report is included in the CI artefacts.
- [ ] LLM-based C7 fallback is opt-in (env var
      `TMAUDIT_LLM_ENDPOINT`) and respects the user's
      privacy (no paper content sent without consent).

## Long-term

### v0.3.0 — DONE (released 2026-07-10)

**Theme**: Plugin system + new audit categories.

| Idea | Description | Status |
|---|---|---|
| C8 (statistical power) | Re-derive the paper's claimed effect size and power from the reported numbers, and flag if the paper's claims are not supported. | ✅ Released in v0.3.0 |
| C9 (figure–caption consistency) | Check that each figure has a caption, the caption is in the right place, and the caption matches the figure's content. | ✅ Released in v0.3.0 |
| C10 (reproducibility) | Check that the paper includes a code/data availability statement, and that the statement is consistent with the paper's claims. | ✅ Released in v0.3.0 |
| Plugin API | Allow users to write their own audit checks (Python module with a `check(main.tex) -> list[Finding]` function) and register them via `pyproject.toml`. | 🚧 In progress (v0.4.0) |

See [`RELEASE_NOTES_v0.3.0.md`](./RELEASE_NOTES_v0.3.0.md) for the
v0.3.0 changelog. Also published on
[github.com/aidless/tmaudit/releases/tag/v0.3.0](https://github.com/aidless/tmaudit/releases/tag/v0.3.0).

### v0.4.0 — DONE (released 2026-07-10)

**Theme**: Plugin API + ecosystem. Ship the 4th (and final)
audit-architecture feature: a stable plugin API that lets
users write their own audit checks.

| Milestone | Status |
|---|---|
| `Finding` dataclass + `@check` decorator + entry-points loader | ✅ Shipped (commit `3ad2825`) |
| `tmaudit plugins list/info/run` CLI | ✅ Shipped (same commit) |
| 29 unit tests for the plugin API | ✅ Shipped (`tests/test_plugin_api.py`) |
| §14 engineering notes (design rationale, 14 sub-sections) | ✅ Shipped (`ed9d8f4`) |
| GitHub issue draft (`.github/issues/18-plugin-api.md`) | ✅ Shipped (commit `de1f4c7`) |
| Wire `tmaudit audit-all` to invoke active plugins | ✅ Shipped (commit `d1c266c`) |
| Add `plugin_cache_key()` to `cache.py` (plugin-fingerprint cache) | ✅ Shipped (same commit) |
| Author `tmaudit_example_plugin/` (3 demo checks) | ✅ Shipped (commits `b798ca9`, `d1c266c`) |
| Meta-test Bug 13 (loader skips malformed entry-point) | ✅ Shipped (commit `b798ca9`) |
| Meta-test Bug 14 (per-paper `c11_plugins_disabled` is honoured) | ✅ Shipped (same commit) |
| `RELEASE_NOTES_v0.4.0.md` + tag v0.4.0 + push | ✅ Shipped (commit `bcbc2ae`) |
| `CHANGELOG.md` updated for v0.4.0 | ✅ Shipped (same commit) |
| GitHub release published for v0.4.0 | ✅ Shipped (live at github.com/aidless/tmaudit/releases/tag/v0.4.0) |
| §15 v1.0.0 roadmap + freeze window | ✅ Shipped (commit `cbcdf37`) |
| Publish to PyPI (or document sideload install) | ⏳ TODO (planned for v0.4.1) |

**Test count: 218 pass, 1 skip. Meta-test: 14/14 caught, 3-run stability verified.**

See [`RELEASE_NOTES_v0.4.0.md`](./RELEASE_NOTES_v0.4.0.md) for the
v0.4.0 changelog. Published on
[github.com/aidless/tmaudit/releases/tag/v0.4.0](https://github.com/aidless/tmaudit/releases/tag/v0.4.0).

### v0.5.0 — DONE (released 2026-07-11)

**Theme**: First minor release after the plugin API ships.
Absorb community feedback; allow breaking changes to the
plugin API before the v0.7.0 lock.

Shipped features (this release):
1. ✅ **`c11_plugins_enabled` (whitelist mode)** — per-paper
   opt-in for "only these plugins". Complements the v0.4.0
   `c11_plugins_disabled` (blacklist) with a clear
   precedence rule: enabled wins, disabled is ignored,
   warning logged. Backward-compatible.
2. ✅ **Meta-test expanded** from 14/14 → **16/16** caught.
   Bug 15 (whitelist branch disabled) and Bug 16
   (precedence swap) added to `_check_all_regressions.py`.

Deferred to v0.5.1 or v0.7.0:
- Plugin configuration schema validator (JSON Schema).
- Plugin hot-reload (dev-only) — `tmaudit plugins reload`.
- Async plugins (preview) — `async def check()` shape.

Stats:
- Unit tests: 218 → **225** (+7 whitelist tests)
- Meta-test: 14/14 → **16/16** caught
- Community-files checks: 44/44 (unchanged)
- Per-paper plugin filter: `c11_plugins_disabled` (v0.4.0)
  + **`c11_plugins_enabled`** (v0.5.0)

See [`RELEASE_NOTES_v0.5.0.md`](./RELEASE_NOTES_v0.5.0.md)
for the v0.5.0 changelog. (GitHub release tag will be
created in a follow-up release-process commit.)

### v0.6.0 — DONE (released 2026-10-24)

**Theme**: Audit a paper the rulepack was not written for.

Shipped features (this release):
1. ✅ **`verify --target FILE`** — a six-line TOML/JSON config next to
   any manuscript forks a custom verify script. Unknown keys are errors
   with a `difflib` suggestion, not silent no-ops.
2. ✅ **`Target` protocol** — plugins can be handed a document object
   instead of a bare `tex` string; old plugins keep working unchanged.
3. ✅ **`admission`** — certifies a self-evolving-harness gain against
   arXiv:2610.18813 eq. (8)/(9), including the eq. (8) inversion
   (`--required-tasks`) and the retention ledger of eq. (6).
4. ✅ **`--paper-dir` + generic fork** (merged from the 0.5.x line) —
   audit a directory with no per-paper config; the root `.tex` is
   detected at runtime and `.bbl` is accepted as a bibliography.
5. ✅ **Exit code 3** — "ran, but a category could not be observed" is
   now distinct from "crashed" (2) and "found nothing" (0).

DOD: 422 tests passing; the same 25-paper arXiv corpus that scored
21/25 in v0.5.1 completes 25/25 through `--target` with 0 aborts.

See [CHANGELOG.md](CHANGELOG.md) for the full entry.

### v0.7.0 — PLANNED (≤ 2026-12)

**Theme**: API lock. Last release that can break the
plugin API. After v0.7.0, only additive changes.

Lock-day changes:
1. Plugin `__version__` is required (no default). Plugins
   without an explicit `version=` raise `TypeError` at
   registration.
2. C1..C10 migrate to `Finding` (legacy tuple form via
   `to_tuple()` is deprecated; removed in v1.0.0).
3. Severity normalization finalised: `MED` alias for
   `MEDIUM` stays; `HIGH`/`MEDIUM`/`LOW` (long-form) are
   canonical.

DOD: 16/16 meta-test caught (added Bug 15 + Bug 16); 3
successful `tmaudit audit-all` runs on 3 different papers.

### v0.8.0 — PLANNED (≤ 2027-04)

**Theme**: Polish. Performance + documentation + 10-paper
support. No API changes.

Planned work:
1. Performance: < 1 second per paper (benchmark suite in
   `bench/`).
2. 10 papers out-of-the-box (5 more paper configs).
3. Full API reference (sphinx-apidoc / mkdocstrings).
4. Plugin author guide (`docs/PLUGIN_AUTHOR_GUIDE.md`).
5. 3 tutorial videos on the project website.

DOD: 10/10 papers in `tmaudit list`; benchmark shows < 1s;
`docs/api/` complete; 3 videos live.

### v1.0.0 — PLANNED (≤ 2027-04)

**Theme**: First stable release. The 6-month API freeze
begins.

**v1.0.0 acceptance criteria** (each measurable):

| Criterion | Measurable as |
|---|---|
| All 10 audit categories (C1..C10) implemented | `tmaudit list` shows 10 categories. ✅ done in v0.3.0. |
| Plugin API ships | `tmaudit plugins list` shows ≥ 1 plugin. ✅ done in v0.4.0. |
| At least 10 papers supported out-of-the-box | `tmaudit list` shows ≥ 10 papers. Currently 5. ⏳ pending v0.8.0. |
| API stable (no breaking changes for 6 months) | `git diff v1.0.0..HEAD -- src/tmaudit/plugins.py` shows zero public-symbol renames or deletions. ⏳ freezes at v1.0.0. |
| Performance: < 1 second per paper, including cache | `time tmaudit verify --paper 1` reports < 1s. ⏳ pending v0.8.0. |
| Full API reference | `docs/api/` has a generated reference for every public symbol. ⏳ pending v0.8.0. |
| Contributor guide updated | `docs/PLUGIN_AUTHOR_GUIDE.md` exists. ⏳ pending v0.8.0. |
| 3 tutorial videos | Live on the project website. ⏳ pending v0.8.0. |
| Used in ≥ 3 real submission cycles | Self-reported by 3 different TMLR / NeurIPS / ICLR submitters. ⏳ **long pole** — drives the calendar. |

### Plugin API freeze window

The plugin API is **frozen at v0.7.0** (not v0.4.0). v0.4.0
is the first release that ships the API, but breaking
changes are still allowed until v0.7.0:

- **v0.4.x (now)**: API is *introduced*. Patch releases may
  add fields, deprecate (not remove) methods.
- **v0.5.0**: First minor release with the API. Breaking
  changes allowed (still 0.x phase).
- **v0.7.0**: API is *locked*. From v0.7.0 onward, only
  additive changes (new fields, new methods, new
  subcommands) are allowed.
- **v1.0.0**: API is *frozen* (no changes for 6 months).

**What's frozen at v0.7.0** (the public surface):

| Module | Public symbols |
|---|---|
| `tmaudit` | `Finding`, `check`, `load_plugins`, `audit_plugins`, `filter_active`, `run_plugin`, `run_all_plugins`, `plugin_cache_key`, `cache_key`, `PLUGIN_GROUP`, `VALID_SEVERITIES`, `__version__` |
| `tmaudit.plugins` | Same as above (re-exported). |
| `tmaudit.cache` | `CacheDB`, `cache_key`, `plugin_cache_key`. |
| `tmaudit.cli` | Subcommand names + flags listed in `cmd_*` dispatch. |
| `tmaudit.configs.paper_configs` | `PAPER_CONFIGS` keys: `dir`, `c1_symbols`…`c11_plugins_disabled` (the C1..C11 schema). |

**What's NOT frozen** (internal implementation details):
the internal `SEVERITY` dict, `check_cN_...` function
bodies, regex patterns, the `verify_p<N>.py` generated
output format, the cache key format itself.

The boundary: **public symbols and CLI flags are frozen;
their internals are not.**

### Calendar (release dates)

| Version | Target | Milestone | Source of truth |
|---|---|---|---|
| **v0.4.0** | **2026-07-10** | Plugin API ships | ✅ live |
| v0.4.1 | 2026-08-10 | Patch (community bug fixes + PyPI) | CI failure log |
| v0.4.2 | 2026-09-10 | Patch (if needed) | CI failure log |
| v0.5.0 | 2026-10-10 | First minor (community feedback) | GitHub issues |
| v0.7.0 | 2026-12-10 | API lock | `_check_all_regressions.py` |
| v0.8.0 | 2027-04-10 | Polish (perf + docs + 10 papers) | `bench/` + `tmaudit list` |
| **v1.0.0** | **2027-04-10** | First stable release | 3 submission cycles |

Total: 9 months from v0.4.0 to v1.0.0. The 3-month
v0.4.0 → v0.5.0 window absorbs community feedback; the
2-month cadence after that is to keep momentum.

### Risk register

The two **real risks** for v1.0.0:

| # | Risk | Probability | Impact | Mitigation |
|---|---|---|---|---|
| 1 | The plugin API has a papercut that only surfaces in real use | **High** | Medium (v0.5.0 delay) | Use v0.4.0 in our own papers (1, 3, 5) to exercise it. |
| 2 | No 3rd author reports a submission cycle | **High** | **Critical** (blocks v1.0.0) | Recruit from the maintainer's academic network; advertise on the TMLR Discord. |

See [`engineering_notes_verify_template.md`](./engineering_notes_verify_template.md) §15.11
for the full 8-row register.

### Cross-cutting lessons (C7–C10 → v1.0.0)

The 5-step pattern that emerged for every audit category
(§11, §12, §13, §14):

1. **TDD red** — write the tests first.
2. **TDD green** — implement to make them pass.
3. **Driver wiring** — call from `main()`, add to
   `SEVERITY` dict, thread per-paper config.
4. **Meta-test** — `inject_bugN()` that re-introduces a
   bug; verify the regression test catches it.
5. **Documentation** — `CHANGELOG.md`, `RELEASE_NOTES_*.md`,
   and the §X engineering notes.

We followed this 14 times (Bug 1 through Bug 14). The
next 4–6 audit categories (if any) will follow the same
pattern. This is the **operational definition of "we
know how to add a new audit category"**.

### What v1.0.0 is NOT

To manage expectations:

- v1.0.0 is not "feature-complete". Domain-specific checks
  belong in plugins, not in core.
- v1.0.0 is not "API-final". v1.x can add fields freely.
  v1.0 just means the next 6 months have no breaking
  changes.
- v1.0.0 is not "ready for every workflow". PyPI install
  ships in v0.4.1; 10-paper support in v0.8.0; tutorial
  videos in v0.8.0. v1.0.0 is the **combination** of all
  of these.
- v1.0.0 is not "abandoned". After v1.0.0 we ship v1.1,
  v1.2 on the same 2-month cadence. v1.0 is the
  **start** of the stable series, not the end.

### What success looks like

When v1.0.0 ships in 9 months, the maintainer's
checklist is:

- [ ] 10 papers supported out-of-the-box.
- [ ] 3 documented real-world submission cycles.
- [ ] 14+ meta-test bugs caught (currently 14; expected
  to grow as new categories ship).
- [ ] `pip install tmaudit` works on PyPI.
- [ ] `git tag v1.0.0` is signed by ≥ 2 maintainers.
- [ ] The release is announced on the project website.
- [ ] **The maintainer can take a 2-week vacation without
  breaking anything** — the API is frozen; no one is
  depending on the maintainer for a fix. That last item
  is the **truest test of stability**.

See [`engineering_notes_verify_template.md`](./engineering_notes_verify_template.md) §15
for the full 15-sub-section v1.0.0 plan.

## Versioning policy

`tmaudit` follows [Semantic Versioning](https://semver.org/):

- **Major (X.0.0)**: breaking changes to the public API
  (CLI subcommands, `paper_configs.py` schema, output
  format).
- **Minor (0.X.0)**: new features, new audit categories,
  new paper configs. Backward-compatible.
- **Patch (0.0.X)**: bug fixes only. No new features.

We are currently in the **0.x.y** phase, which means the
API is not yet stable. Breaking changes may occur in
minor releases until v1.0.0.

## Decision-making

Major roadmap decisions are made by the maintainer(s) on
GitHub Discussions. The process is:

1. Anyone can open a Discussion in the "Roadmap" category.
2. The maintainer triages and replies within 7 days.
3. If the proposal is accepted, an issue is filed in the
   appropriate milestone.
4. The issue is then open for community contribution.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the
contribution workflow and [SUPPORT.md](./.github/SUPPORT.md)
for the support channels.

## See also

- [`CHANGELOG.md`](./CHANGELOG.md) — what was done
- [`engineering_notes_verify_template.md`](./engineering_notes_verify_template.md) — why
- [`.github/issues/`](./.github/issues/) — draft issues
  ready to be filed
- [`RELEASE_NOTES_v0.1.1.md`](./RELEASE_NOTES_v0.1.1.md) — last release
- [`.github/ISSUE_TEMPLATE/feature_request.md`](./.github/ISSUE_TEMPLATE/feature_request.md)
  — how to file a new feature

---

*Last updated: 2026-07-10. Next review: when v0.1.2 is
released or when a major design decision is needed.*