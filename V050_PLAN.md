# v0.5.0 — `c11_plugins_enabled` whitelist — Implementation Plan

> **Status**: ⏳ in progress (planned for ≤ 2026-10 per §15.6)
> **Date prepared**: 2026-07-10
> **Pattern**: 5-step TDD + meta-test (per §15.12)

## 0. Goal

Today (v0.4.0) we have a **blacklist** model:

```python
'c11_plugins_disabled': ['plugin-a', 'plugin-b']
# runs: all registered plugins EXCEPT 'plugin-a' and 'plugin-b'
```

v0.5.0 adds the **whitelist** model:

```python
'c11_plugins_enabled': ['plugin-a', 'plugin-c']
# runs: ONLY 'plugin-a' and 'plugin-c' (regardless of others installed)
```

This is the **inverse** — useful for:
- **Security**: paper maintainers want to lock down which
  plugins run on their paper (only trust a curated set).
- **Reproducibility**: explicitly enumerate the plugin
  set so a paper's audit output is deterministic.
- **CI gating**: in CI, only run a known-good plugin set;
  even if a hostile plugin is installed system-wide, it
  cannot run.

## 1. Conflict resolution rules

When **both** `c11_plugins_enabled` and `c11_plugins_disabled`
are set, we need a deterministic rule:

| `enabled` set | `disabled` set | Behaviour |
|---|---|---|
| empty (default) | empty | All registered plugins run (back-compat). |
| empty | `['a']` | Blacklist mode: all except 'a'. |
| `['a', 'b']` | empty | Whitelist mode: only 'a' and 'b'. |
| `['a', 'b']` | `['b']` | Whitelist wins. Plugin 'b' is in the whitelist so it runs. `disabled` is ignored. |
| `['a', 'b']` | `['c']` | Whitelist mode: only 'a' and 'b'. Plugin 'c' is not in enabled so it's not considered. |
| `['a']` | `['a']` | Whitelist wins. Plugin 'a' is in the whitelist so it runs. The user clearly wants 'a' — `disabled` is ignored. |

**The rule**: if `c11_plugins_enabled` is non-empty, it
**overrides** `c11_plugins_disabled` completely. This is
the simplest, most predictable rule. v0.5.0 emits a
warning log if both are set so the user notices the
override.

## 2. API design (new public surface)

### 2.1 `filter_active` signature change

```python
# v0.4.0:
def filter_active(
    plugins: Dict[str, CheckFn],
    disabled: Optional[List[str]] = None,
) -> Dict[str, CheckFn]:
    ...

# v0.5.0 (backward-compat: add `enabled` param, default None):
def filter_active(
    plugins: Dict[str, CheckFn],
    disabled: Optional[List[str]] = None,
    enabled: Optional[List[str]] = None,
) -> Dict[str, CheckFn]:
    """
    Return a subset of plugins with disabled ones removed
    and (if enabled is non-empty) only enabled ones kept.

    Resolution rule (per §15.6): if `enabled` is non-empty,
    it takes precedence over `disabled`.

    Args:
        plugins: full plugin dict from load_plugins().
        disabled: per-paper blacklist. Ignored if `enabled`
            is non-empty.
        enabled: per-paper whitelist. If non-empty, only
            plugins whose name is in this list are kept.

    Returns:
        A new dict containing only the active plugins.
    """
    enabled_set = set(enabled) if enabled else set()
    disabled_set = set(disabled) if disabled else set()

    if enabled_set:
        # Whitelist mode: enabled wins, disabled is ignored.
        if disabled_set:
            log.warning(
                "tmaudit: c11_plugins_enabled and c11_plugins_disabled "
                "are both set; enabled wins and disabled is ignored."
            )
        return {n: c for n, c in plugins.items() if n in enabled_set}

    if disabled_set:
        return {n: c for n, c in plugins.items() if n not in disabled_set}

    return dict(plugins)
```

### 2.2 `audit_plugins` signature change

```python
def audit_plugins(
    paper_n: int,
    paper_dir: "Path",
    config: Optional[Dict[str, Any]] = None,
    disabled: Optional[List[str]] = None,
    enabled: Optional[List[str]] = None,    # NEW
    use_cache: bool = True,
) -> List[Finding]:
    ...
    plugins = filter_active(load_plugins(), disabled, enabled)
    ...
```

### 2.3 `c11_plugins_enabled` per-paper config

Add to `paper_configs.py`:

```python
PAPER_CONFIGS = {
    1: {
        ...,
        'c11_plugins_disabled': [...],   # existing (optional)
        'c11_plugins_enabled':  [...],   # NEW (optional, default [])
    },
    ...
}
```

Backward-compat: existing papers have neither field; both
default to `[]` ⇒ "run all" (current behaviour).

### 2.4 CLI flag

```bash
tmaudit audit-all --enable-plugin nips-pagecheck --enable-plugin todo-marker
tmaudit audit-all --disable-plugin nips-pagecheck   # existing
```

Add `--enable-plugin` flag (multi-value). It maps to
`c11_plugins_enabled` in CHECKS_CONFIG (or to a runtime
override that we thread into `audit_plugins`).

For now, **we only add the per-paper config knob**; the
CLI flag is a v0.5.x add-on if requested.

## 3. TDD red (write tests first)

In `tests/test_plugin_api.py`, add:

```python
def test_filter_active_whitelist_mode():
    """When `enabled` is non-empty, only those plugins are kept."""
    plugins = _make_plugins(['a', 'b', 'c'])
    active = filter_active(plugins, enabled=['a', 'c'])
    assert set(active) == {'a', 'c'}


def test_filter_active_whitelist_overrides_disabled():
    """When both are set, enabled wins and disabled is ignored."""
    plugins = _make_plugins(['a', 'b', 'c'])
    active = filter_active(plugins, enabled=['a', 'b'], disabled=['a'])
    # 'a' is in enabled so it runs even though it's in disabled.
    assert set(active) == {'a', 'b'}


def test_filter_active_whitelist_with_unknown_plugin():
    """An unknown plugin in the whitelist is silently skipped."""
    plugins = _make_plugins(['a', 'b'])
    active = filter_active(plugins, enabled=['a', 'nonexistent'])
    assert set(active) == {'a'}


def test_filter_active_empty_enabled_uses_disabled():
    """Empty `enabled` falls back to blacklist mode."""
    plugins = _make_plugins(['a', 'b', 'c'])
    active = filter_active(plugins, enabled=[], disabled=['b'])
    assert set(active) == {'a', 'c'}


def test_filter_active_both_empty_returns_all():
    """Empty `enabled` and `disabled` returns all plugins."""
    plugins = _make_plugins(['a', 'b'])
    active = filter_active(plugins, enabled=[], disabled=[])
    assert set(active) == {'a', 'b'}


def test_audit_plugins_respects_c11_plugins_enabled():
    """A paper with c11_plugins_enabled=['synth'] only runs 'synth'."""
    reset_loader_cache()
    import tmaudit.plugins as _plugins
    @check(name="synth-yes", severity="MEDIUM")
    def yes(tex, config=None):
        return [Finding(category="Y", severity="MEDIUM", message="yes", line=1)]
    @check(name="synth-no", severity="MEDIUM")
    def no(tex, config=None):
        return [Finding(category="N", severity="MEDIUM", message="no", line=1)]
    real_load = _plugins.load_plugins
    _plugins.load_plugins = lambda force_reload=False: {"synth-yes": yes, "synth-no": no}
    try:
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "main.tex").write_text("hi\n", encoding="utf-8")
            findings = _plugins.audit_plugins(
                paper_n=1,
                paper_dir=Path(td),
                config={},
                enabled=['synth-yes'],
            )
        assert len(findings) == 1
        assert findings[0].category == 'Y'
    finally:
        _plugins.load_plugins = real_load
        reset_loader_cache()


def test_paper_configs_can_carry_c11_plugins_enabled():
    """c11_plugins_enabled in PAPER_CONFIGS is validated as list[str]."""
    from tmaudit.configs.paper_configs import PAPER_CONFIGS
    for n, cfg in PAPER_CONFIGS.items():
        d = cfg.get('c11_plugins_enabled')
        assert d is None or (
            isinstance(d, list) and all(isinstance(x, str) for x in d)
        )
```

## 4. TDD green (implement)

In `src/tmaudit/plugins.py`:

1. Update `filter_active(...)` signature to add `enabled`
   param.
2. Implement the precedence rule (enabled wins).
3. Update `audit_plugins(...)` to read `enabled` from
   `config.get('c11_plugins_enabled', [])` and pass to
   `filter_active`.
4. Update `cli.cmd_audit_all` to thread `enabled` from
   `cfg.get('c11_plugins_enabled', [])`.

In `src/tmaudit/configs/paper_configs.py`:

1. Add `c11_plugins_enabled: []` (empty default) to each
   PAPER_CONFIGS entry. Optional, so a paper without it
   behaves as before.
2. Update the format writer to include the new field.

## 5. Driver wiring (CLI)

`src/tmaudit/cli.py`:

```python
# In cmd_audit_all:
plugin_findings = _plugins.audit_plugins(
    paper_n=n,
    paper_dir=Path(paper_dir),
    config=cfg,
    disabled=cfg.get('c11_plugins_disabled', []),
    enabled=cfg.get('c11_plugins_enabled', []),    # NEW
    use_cache=not no_cache,
)
```

That's it — no new CLI flag for v0.5.0; the per-paper
config knob is sufficient.

## 6. Meta-test (Bug 15 + Bug 16)

In `_check_all_regressions.py`, add two new bugs:

### Bug 15: filter_active ignores `enabled` whitelist

```python
def inject_bug15() -> None:
    """Bug 15: c11_plugins_enabled whitelist is ignored.
    The fix replaces `enabled_set = set(enabled)` with
    `enabled_set = set()` (or just drops the param). The
    regression test `test_filter_active_whitelist_mode` will
    fail because the bug returns all plugins instead of
    just the whitelisted ones.
    """
    plugins_path = TEMPLATE / 'src' / 'tmaudit' / 'plugins.py'
    with _patched(plugins_path):
        original = plugins_path.read_text(encoding='utf-8')
        old = '    enabled_set = set(enabled) if enabled else set()'
        new = '    enabled_set = set()  # BROKEN: ignore enabled'
        if old not in original:
            raise RuntimeError(f'bug-15 anchor not found in {plugins_path}')
        plugins_path.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '15',
            'tests/test_plugin_api.py::test_filter_active_whitelist_mode',
        )
```

### Bug 16: enabled whitelist doesn't override disabled blacklist

```python
def inject_bug16() -> None:
    """Bug 16: when both `enabled` and `disabled` are set, the
    blacklist accidentally wins (precedence reversed). The
    fix changes the `if enabled_set:` block to skip
    `disabled` filtering even when present.
    """
    plugins_path = TEMPLATE / 'src' / 'tmaudit' / 'plugins.py'
    with _patched(plugins_path):
        original = plugins_path.read_text(encoding='utf-8')
        old = '    if enabled_set:'
        new = '    if False:  # BROKEN: enabled no longer takes precedence'
        if old not in original:
            raise RuntimeError(f'bug-16 anchor not found in {plugins_path}')
        plugins_path.write_text(
            original.replace(old, new, 1),
            encoding='utf-8',
        )
        _check_bug_inside_patch(
            '16',
            'tests/test_plugin_api.py::test_filter_active_whitelist_overrides_disabled',
        )
```

Add both to the `cases` list in `_check_all_regressions()`.

## 7. Documentation

- **`CHANGELOG.md`** — add v0.5.0 entry citing the 2 new
  tests + 2 new meta-test bugs.
- **`RELEASE_NOTES_v0.5.0.md`** — new file explaining the
  whitelist feature, migration path, and breaking-change
  status (none, additive).
- **`engineering_notes_verify_template.md`** — add §16
  documenting the v0.5.0 design rationale (mirrors §14's
  plugin API design but for the whitelist).
- **`ROADMAP.md`** — bump v0.5.0 from PLANNED to
  IN PROGRESS or DONE.
- **`.github/issues/19-whitelist-mode.md`** — close the
  open follow-up with a "shipped in v0.5.0" comment.

## 8. Effort estimate

| Task | Effort |
|---|---|
| 7 new tests in `test_plugin_api.py` | 30 min |
| Update `filter_active` + `audit_plugins` | 30 min |
| Update `paper_configs.py` (`c11_plugins_enabled` field) | 15 min |
| Update `cmd_audit_all` | 5 min |
| Bug 15 + 16 injects in `_check_all_regressions.py` | 30 min |
| §16 engineering notes (v0.5.0 design rationale) | 1-2 hr |
| CHANGELOG + RELEASE_NOTES_v0.5.0 + ROADMAP | 30 min |
| **Total** | **~3-4 hours** |

## 9. v0.5.0 release scope (per §15.6)

This doc covers **only** `c11_plugins_enabled` (the
whitelist feature). The full v0.5.0 release also includes:

- Plugin configuration schema validator (JSON Schema)
- Plugin hot-reload (`tmaudit plugins reload`)
- Async plugins (preview)

These are separate concerns and have their own TDD
plans. We can ship `c11_plugins_enabled` in **v0.5.0a**
(a patch release on the v0.5.x line) if we want the
whitelist sooner, or in **v0.5.0** (the main release) if
we want to bundle it with the schema validator.

**Recommendation**: ship whitelist in v0.5.0 alongside
the schema validator. The schema validator is what
makes the whitelist safe (you can declare "this paper
requires plugin `nips-pagecheck` with config `{}`" and
the validator catches typos at audit time).

## 10. Migration / backward-compat

The `filter_active` signature adds a new keyword arg with
a default of `None`. This is **backward compatible**:
existing callers (`audit_plugins(..., disabled=...)`)
continue to work. No existing code is broken.

The new `c11_plugins_enabled` per-paper config is
**optional** with default `[]`. Papers that don't set
it continue to run all plugins (the v0.4.0 behaviour).
No migration is required for existing papers.

## 11. Status of this doc

⏳ 30% done — design decisions are made (§1, §2); tests
and code are described (§3-§6) but not yet written. The
implementation is queued for the v0.5.0 work session.

**Maintainer review requested** on:
- §1 (precedence rule: enabled wins, no exceptions)
- §2.4 (skip `--enable-plugin` CLI flag for v0.5.0)
- §9 (ship whitelist in v0.5.0 vs v0.5.0a)
