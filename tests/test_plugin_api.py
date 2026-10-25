"""Tests for the tmaudit plugin API (added in v0.4.0).

These tests cover the loader, the @check decorator, the
Finding dataclass, the lifecycle helpers, and the per-paper
disable mechanism. They do not depend on any installed
plugin; the test fixtures synthesise plugin functions
in-process.

Test layout:

- TestFinding — Finding dataclass semantics.
- TestCheckDecorator — @check behavior + validation.
- TestFilterActive — disabled-list subtraction.
- TestRunPlugin — paper_id stamping and exception safety.
- TestLoadPlugins — entry-points discovery (with mock).
- TestPerPaperDisable — the c11_plugins_disabled mechanism
  exercised by reading PAPER_CONFIGS.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tmaudit
from tmaudit.plugins import (
    Finding,
    VALID_SEVERITIES,
    PLUGIN_GROUP,
    _DecoratedCheck,
    check,
    filter_active,
    load_plugins,
    reset_loader_cache,
    run_plugin,
    run_all_plugins,
)


# =====================================================================
# Test fixtures: synthetic plugins (defined per test as needed)
# =====================================================================


def _no_op_plugin(tex, config=None):
    """A plugin that always returns an empty list."""
    return []


def _todo_plugin(tex, config=None):
    """A plugin that flags every TODO marker."""
    out = []
    for i, line in enumerate(tex.splitlines()):
        if "TODO" in line:
            out.append(Finding(
                category="TODO", severity="MED",
                message=f"TODO marker at line {i+1}",
                line=i + 1,
            ))
    return out


def _raising_plugin(tex, config=None):
    """A plugin that always raises (used to test exception safety)."""
    raise RuntimeError("synthetic failure")


# =====================================================================
# TestFinding: Finding dataclass semantics
# =====================================================================


def test_finding_basic_construction():
    """Finding() builds with the required fields."""
    f = Finding(category="X1", severity="HIGH", message="something")
    assert f.category == "X1"
    assert f.severity == "HIGH"
    assert f.message == "something"
    assert f.line == -1  # default
    assert f.paper_id is None  # default


def test_finding_to_tuple_backward_compat():
    """Finding.to_tuple() returns (category, message, line)."""
    f = Finding(category="X1", severity="HIGH",
                message="hi", line=42)
    assert f.to_tuple() == ("X1", "hi", 42)


def test_finding_med_normalises_to_medium():
    """'MED' short-form is accepted and normalised to 'MEDIUM'."""
    f = Finding(category="X1", severity="MED", message="x")
    assert f.severity == "MEDIUM"


def test_finding_rejects_invalid_severity():
    """Invalid severities raise ValueError at construction."""
    with pytest.raises(ValueError, match="severity"):
        Finding(category="X1", severity="WRONG", message="x")


def test_finding_lowercase_severity_normalises():
    """'high' / 'low' / 'medium' / 'med' are all accepted (case-folded)."""
    for s in ("high", "low", "medium", "med"):
        f = Finding(category="X1", severity=s, message="x")
        assert f.severity in ("HIGH", "LOW", "MEDIUM")


def test_finding_is_frozen():
    """Finding is frozen — attribute reassignment raises."""
    f = Finding(category="X1", severity="HIGH", message="x")
    with pytest.raises(Exception):  # FrozenInstanceError
        f.message = "different"  # type: ignore[misc]


def test_finding_rejects_empty_category():
    """Empty category raises ValueError."""
    with pytest.raises(ValueError, match="category"):
        Finding(category="", severity="HIGH", message="x")


# =====================================================================
# TestCheckDecorator: @check behavior + validation
# =====================================================================


def test_check_wraps_function_as_decorated_check():
    """The @check decorator returns a _DecoratedCheck, not the bare fn."""
    @check(name="noop", severity="LOW", help_text="does nothing")
    def noop(tex, config=None):
        return []
    assert isinstance(noop, _DecoratedCheck)
    assert noop.name == "noop"
    assert noop.severity == "LOW"
    assert noop.help_text == "does nothing"


def test_check_metadata_attached():
    """The decorator exposes metadata via __tmaudit_meta__."""
    @check(name="x", severity="HIGH",
           requires_config=True, help_text="hi", version="1.2.3")
    def f(tex, config=None):
        return []
    meta = f.__tmaudit_meta__
    assert meta["name"] == "x"
    assert meta["severity"] == "HIGH"
    assert meta["requires_config"] is True
    assert meta["help_text"] == "hi"
    assert meta["version"] == "1.2.3"


def test_check_rejects_empty_name():
    """An empty plugin name raises ValueError."""
    with pytest.raises(ValueError, match="name"):
        @check(name="", severity="LOW")
        def f(tex, config=None):
            return []


def test_check_rejects_invalid_severity():
    """An unknown severity in @check raises ValueError."""
    with pytest.raises(ValueError, match="severity"):
        @check(name="x", severity="WHATEVER")
        def f(tex, config=None):
            return []


def test_check_normalises_med_severity():
    """@check(name, severity='MED') normalises to 'MEDIUM'."""
    @check(name="x", severity="MED")
    def f(tex, config=None):
        return []
    assert f.severity == "MEDIUM"


def test_check_rejects_non_callable():
    """@check applied to a non-callable raises TypeError."""
    with pytest.raises(TypeError, match="callable"):
        check(name="x", severity="LOW")(42)  # type: ignore[arg-type]


def test_check_decorated_callable_invokes_original_fn():
    """Calling the wrapped plugin delegates to the original function."""
    captured = []

    @check(name="x", severity="LOW")
    def sample(tex, config=None):
        captured.append((tex, config))
        return [Finding(category="X", severity="LOW", message="ok")]

    fs = sample("hello", {"k": "v"})
    assert captured == [("hello", {"k": "v"})]
    assert len(fs) == 1
    assert fs[0].category == "X"


# =====================================================================
# TestFilterActive: disabled-list subtraction
# =====================================================================


def test_filter_active_removes_disabled():
    """filter_active() excludes names in the disabled list."""
    plugins = {
        "alpha": _DecoratedCheck(fn=_no_op_plugin, name="alpha", severity="LOW",
                                  requires_config=False, help_text="", version="0.1"),
        "beta":  _DecoratedCheck(fn=_no_op_plugin, name="beta",  severity="LOW",
                                  requires_config=False, help_text="", version="0.1"),
    }
    active = filter_active(plugins, disabled=["beta"])
    assert set(active) == {"alpha"}


def test_filter_active_empty_disabled_returns_full_dict():
    """When disabled is None or empty, all plugins are active."""
    plugins = {"a": object(), "b": object()}
    active = filter_active(plugins)
    assert set(active) == {"a", "b"}
    active = filter_active(plugins, disabled=[])
    assert set(active) == {"a", "b"}


def test_filter_active_with_unknown_disabled_keeps_unknown():
    """A name in disabled that isn't a known plugin is silently ignored."""
    plugins = {"a": object()}
    active = filter_active(plugins, disabled=["nonexistent"])
    assert set(active) == {"a"}


# =====================================================================
# TestRunPlugin: paper_id stamping and exception safety
# =====================================================================


def test_run_plugin_stamps_paper_id():
    """run_plugin() stamps paper_id on every emitted Finding."""
    plugin = _DecoratedCheck(fn=_todo_plugin, name="todo-flag",
                              severity="MEDIUM",
                              requires_config=False, help_text="",
                              version="0.1")
    findings = run_plugin(plugin, tex="hello\nTODO: fix\nbye\n",
                          paper_id="paper-7")
    assert len(findings) == 1
    assert findings[0].paper_id == "paper-7"
    assert findings[0].category == "TODO"
    assert findings[0].line == 2


def test_run_plugin_no_paper_id_keeps_none():
    """run_plugin() with paper_id=None does not stamp anything."""
    plugin = _DecoratedCheck(fn=_todo_plugin, name="todo-flag",
                              severity="MEDIUM",
                              requires_config=False, help_text="",
                              version="0.1")
    findings = run_plugin(plugin, tex="hello\nTODO\n", paper_id=None)
    assert findings[0].paper_id is None


def test_run_plugin_does_not_overwrite_existing_paper_id():
    """If a plugin already set paper_id (rare), we don't overwrite."""
    def pre_stamped(tex, config=None):
        return [Finding(category="X", severity="LOW", message="x",
                        paper_id="preset")]
    plugin = _DecoratedCheck(fn=pre_stamped, name="x",
                              severity="LOW",
                              requires_config=False, help_text="",
                              version="0.1")
    findings = run_plugin(plugin, tex="any",
                          paper_id="outer")
    # 'preset' wins (pre-stamped by the plugin).
    assert findings[0].paper_id == "preset"


def test_run_all_plugins_skips_raising_plugin():
    """A plugin that raises is logged and skipped, others still run."""
    plugins = {
        "raiser": _DecoratedCheck(fn=_raising_plugin, name="raiser",
                                   severity="HIGH",
                                   requires_config=False, help_text="",
                                   version="0.1"),
        "quiet":  _DecoratedCheck(fn=_no_op_plugin,  name="quiet",
                                   severity="LOW",
                                   requires_config=False, help_text="",
                                   version="0.1"),
    }
    findings = run_all_plugins(plugins, tex="anything")
    # The raising plugin is skipped, the quiet one returns []. No findings.
    assert findings == []


def test_run_all_plugins_collects_from_multiple():
    """Multiple plugins' findings are concatenated into one list."""
    plugins = {
        "todo": _DecoratedCheck(fn=_todo_plugin, name="todo",
                                  severity="MEDIUM",
                                  requires_config=False, help_text="",
                                  version="0.1"),
        "noop": _DecoratedCheck(fn=_no_op_plugin, name="noop",
                                  severity="LOW",
                                  requires_config=False, help_text="",
                                  version="0.1"),
    }
    findings = run_all_plugins(plugins, tex="first\nTODO\nsecond\nTODO\n")
    assert len(findings) == 2
    assert all(f.category == "TODO" for f in findings)


# =====================================================================
# TestLoadPlugins: entry-points discovery
# =====================================================================


def test_load_plugins_returns_dict():
    """load_plugins() returns a dict (possibly empty)."""
    reset_loader_cache()
    plugins = load_plugins()
    assert isinstance(plugins, dict)


def test_load_plugins_caches_result():
    """Second call returns the same content without re-importing."""
    reset_loader_cache()
    first = load_plugins()
    second = load_plugins()
    # The cached dict is reused; we verify by content equality.
    assert first == second


def test_load_plugins_force_reload_refreshes_cache_separately():
    """force_reload=True is a separate call path that rebuilds the cache."""
    reset_loader_cache()
    first = load_plugins()
    second = load_plugins(force_reload=True)
    # Both must be dicts; content is equal here because no
    # plugins are registered in the test environment.
    assert isinstance(first, dict)
    assert isinstance(second, dict)


def test_load_plugins_handles_entry_point_group():
    """The loader uses the documented entry-point group."""
    # We can't install a real plugin in tests, but we can
    # verify the constant.
    assert PLUGIN_GROUP == "tmaudit.plugins"


def test_loader_skips_malformed_entry_point():
    """A plugin that fails to import is logged but does not raise.

    Synthetic test: register a fake entry-point whose target
    module does not exist. The loader must skip it gracefully,
    not crash the audit.
    """
    from importlib.metadata import EntryPoint

    reset_loader_cache()

    # Save the real entry_points and patch it for this test.
    import tmaudit.plugins as _plugins
    real_ep = _plugins.entry_points

    class _FakeEPS:
        """Mimics the entry_points() return type enough for the loader."""
        def __init__(self, eps):
            self._eps = eps

        def __iter__(self):
            return iter(self._eps)

        def __len__(self):
            return len(self._eps)

    fake_ep = EntryPoint(
        name="definitely-broken",
        group="tmaudit.plugins",
        value="nonexistent_module_xyz:not_a_function",
    )
    try:
        _plugins.entry_points = lambda *, group: _FakeEPS([fake_ep]) \
            if group == "tmaudit.plugins" else _FakeEPS([])
        reset_loader_cache()
        # Must NOT raise:
        plugins = _plugins.load_plugins()
        assert isinstance(plugins, dict)
        # The fake entry point may or may not appear in the dict
        # depending on whether load() returned None; what matters
        # is that load() did not crash the loader.
    finally:
        _plugins.entry_points = real_ep
        reset_loader_cache()


def test_audit_plugins_respects_per_paper_disable():
    """A paper with c11_plugins_disabled=['name'] skips that plugin.

    This is the regression test for Bug 14: per-paper disable
    must be honoured. We register a synthetic plugin that
    always emits a finding, then disable it for a paper and
    assert no findings come back.
    """
    reset_loader_cache()

    import tmaudit.plugins as _plugins

    @check(name="synthetic-emit-one", severity="MEDIUM",
           help_text="always emits one LOW finding")
    def _synthetic(tex, config=None):
        return [Finding(category="SYN", severity="MEDIUM",
                        message="synthetic finding", line=1)]

    real_load = _plugins.load_plugins
    plugins_dict = {"synthetic-emit-one": _synthetic}
    # Stub load_plugins() so audit_plugins() sees our plugin.
    try:
        _plugins.load_plugins = lambda force_reload=False: dict(plugins_dict)
        _plugins.filter_active = _plugins.filter_active  # unchanged
        # Active: no disable → 1 finding.
        from pathlib import Path as _Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "main.tex").write_text("hello world\n", encoding="utf-8")
            findings_active = _plugins.audit_plugins(
                paper_n=1,
                paper_dir=_Path(td),
                config={},
                disabled=[],
            )
        assert len(findings_active) == 1
        # Disabled: same plugin but in disabled list → 0 findings.
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "main.tex").write_text("hello world\n", encoding="utf-8")
            findings_disabled = _plugins.audit_plugins(
                paper_n=1,
                paper_dir=_Path(td),
                config={},
                disabled=["synthetic-emit-one"],
            )
        assert findings_disabled == [], (
            f"Disabled plugin still emitted findings: {findings_disabled}"
        )
    finally:
        _plugins.load_plugins = real_load
        reset_loader_cache()


# =====================================================================
# TestPerPaperDisable: c11_plugins_disabled is read from PAPER_CONFIGS
# =====================================================================


def test_paper_configs_can_carry_c11_plugins_disabled():
    """PAPER_CONFIGS schema permits c11_plugins_disabled (it is optional)."""
    from tmaudit.configs.paper_configs import PAPER_CONFIGS
    # No assertion on actual values (any paper may or may not
    # have this field), but import must succeed and the field,
    # if present, must be a list of strings.
    for n, cfg in PAPER_CONFIGS.items():
        d = cfg.get("c11_plugins_disabled")
        assert d is None or (
            isinstance(d, list) and
            all(isinstance(x, str) for x in d)
        ), f"paper {n}: c11_plugins_disabled must be None or list[str]"


# =====================================================================
# TestPluginRunCLI: `plugins run` on an arbitrary paper directory
# =====================================================================


def test_plugins_run_accepts_an_arbitrary_paper_dir(tmp_path, capsys):
    """A plugin author outside this project must be able to audit their
    own paper.

    `plugins run --paper-dir DIR` is the supported path for a
    manuscript the built-in C1..C10 rulepack was not written for: the
    plugin receives that directory's main.tex and an empty config.
    Before this existed, the subcommand required `--paper N` in 1..5,
    so a plugin author could write checks but never point them at
    their own paper.
    """
    import tmaudit.plugins as _plugins
    from tmaudit.cli import main

    @_plugins.check(
        name="synthetic-arbitrary-dir",
        severity="HIGH",
        help_text="emits one finding regardless of config",
    )
    def _synthetic(tex, config=None):
        assert config == {}, (
            f"an arbitrary --paper-dir run must yield an empty config, "
            f"got {config!r}"
        )
        return [Finding(category="SYN", severity="HIGH",
                        message="synthetic finding", line=1)]

    paper_dir = tmp_path / "my-paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text("hello world\n", encoding="utf-8")

    real_load = _plugins.load_plugins
    try:
        _plugins.load_plugins = lambda force_reload=False: {
            "synthetic-arbitrary-dir": _synthetic,
        }
        rc = main(["plugins", "run", "synthetic-arbitrary-dir",
                   "--paper-dir", str(paper_dir)])
    finally:
        _plugins.load_plugins = real_load
        reset_loader_cache()

    assert rc == 0, "--paper-dir on an arbitrary paper must not be rejected"
    out = capsys.readouterr().out
    assert "[HIGH]" in out
    assert "synthetic finding" in out


def test_plugins_run_without_paper_dir_points_at_the_arbitrary_route(
    tmp_path, capsys
):
    """An unknown --paper must still fail, and say how to audit a paper
    that has no built-in config."""
    import tmaudit.plugins as _plugins
    from tmaudit.cli import main

    @_plugins.check(name="synthetic-unknown-paper", severity="LOW",
                    help_text="never runs in this test")
    def _synthetic(tex, config=None):
        return []

    real_load = _plugins.load_plugins
    try:
        _plugins.load_plugins = lambda force_reload=False: {
            "synthetic-unknown-paper": _synthetic,
        }
        rc = main(["plugins", "run", "synthetic-unknown-paper", "--paper", "999"])
    finally:
        _plugins.load_plugins = real_load
        reset_loader_cache()

    assert rc == 1, "an unknown built-in paper must not silently succeed"
    err = capsys.readouterr().err
    assert "--paper-dir" in err, (
        "the error must name the arbitrary-paper route, else a plugin "
        f"author is left without a path forward; got: {err!r}"
    )



# =====================================================================
# TestReExports: the public surface is correct
# =====================================================================


def test_plugin_api_re_exported_at_package_root():
    """The plugin API is importable from `tmaudit` (not just `tmaudit.plugins`)."""
    assert tmaudit.Finding is Finding
    assert tmaudit.check is check
    assert tmaudit.PLUGIN_GROUP == PLUGIN_GROUP


def test_valid_severities_includes_canonical_forms():
    """The exposed VALID_SEVERITIES tuple lists the canonical strings."""
    for s in ("HIGH", "MEDIUM", "LOW"):
        assert s in VALID_SEVERITIES


# =====================================================================
# v0.5.0 whitelist mode (c11_plugins_enabled)
# Added in v0.5.0; see engineering_notes_verify_template.md §16.
# =====================================================================


def _make_check(name, severity="LOW", return_findings=None):
    """Create a stub plugin for testing filter_active.

    The plugin's behaviour is rarely exercised in these
    tests; we mostly care that `filter_active` returns
    the right keys. Test 6 (audit_plugins integration)
    is the one that actually runs the plugin.
    """
    @check(name=name, severity=severity,
           help_text=f"{name}-help")
    def _fn(tex, config=None):
        return return_findings or []
    return _fn


def test_filter_active_empty_lists_run_all():
    """Both enabled=[] and disabled=[] return all plugins.

    The v0.4.0 default behaviour ("run all") is
    preserved in v0.5.0. The fall-through path
    triggers when neither `enabled` nor `disabled` is
    non-empty. Regression-tested in v0.4.0 (see
    test_filter_active_empty_disabled_returns_full_dict);
    this v0.5.0 test extends the same behaviour to the
    new `enabled` parameter.
    """
    plugins = {
        'a': _make_check('a'),
        'b': _make_check('b'),
        'c': _make_check('c'),
    }
    active = filter_active(plugins, enabled=[], disabled=[])
    assert set(active) == {'a', 'b', 'c'}


def test_filter_active_blacklist_only():
    """enabled=[] falls through to blacklist mode.

    The v0.4.0 blacklist behaviour is unchanged when
    `enabled` is empty. This is a regression test for
    the v0.4.0 path: v0.5.0 must not break the old
    blacklist-only mode.
    """
    plugins = {
        'a': _make_check('a'),
        'b': _make_check('b'),
        'c': _make_check('c'),
    }
    active = filter_active(
        plugins, enabled=[], disabled=['a'],
    )
    assert set(active) == {'b', 'c'}


def test_filter_active_whitelist_only():
    """enabled=['a', 'b'] + disabled=[] returns {a, b}.

    New whitelist mode: only the named plugins run.
    No blacklist filtering happens because `disabled` is
    empty.
    """
    plugins = {
        'a': _make_check('a'),
        'b': _make_check('b'),
        'c': _make_check('c'),
    }
    active = filter_active(
        plugins, enabled=['a', 'b'], disabled=[],
    )
    assert set(active) == {'a', 'b'}


def test_filter_active_whitelist_overrides_blacklist():
    """When both are non-empty, whitelist wins (§16.4).

    enabled=['a', 'b'] + disabled=['a'] returns {a, b}.
    The whitelist is authoritative; the blacklist is
    silently ignored. A warning log is emitted (per
    §16.4); we don't assert on the log here to keep
    the test focused on the data behaviour.
    """
    plugins = {
        'a': _make_check('a'),
        'b': _make_check('b'),
        'c': _make_check('c'),
    }
    active = filter_active(
        plugins, enabled=['a', 'b'], disabled=['a'],
    )
    assert set(active) == {'a', 'b'}


def test_filter_active_whitelist_with_unknown_plugin():
    """Unknown plugin names in the whitelist are silently
    skipped (§16.5).

    Per §16.5: a forward-compatible whitelist should not
    fail when run on a stripped-down environment. An
    unknown name is a no-op. (This matches the v0.4.0
    behaviour for the blacklist: an unknown name in
    `disabled` is silently skipped too.)
    """
    plugins = {
        'a': _make_check('a'),
        'b': _make_check('b'),
    }
    active = filter_active(
        plugins, enabled=['a', 'nonexistent'], disabled=[],
    )
    assert set(active) == {'a'}


def test_audit_plugins_respects_c11_plugins_enabled():
    """End-to-end: a paper with c11_plugins_enabled=
    ['synth-yes'] only runs the synth-yes plugin, even
    if more plugins are installed.

    This is the integration test for the v0.5.0 per-paper
    config + audit_plugins path. The whitelist is read
    from the per-paper config dict (the canonical
    entry point); `audit_plugins` is expected to filter
    before running.
    """
    reset_loader_cache()
    import tmaudit.plugins as _plugins

    @check(name="synth-yes", severity="MEDIUM",
           help_text="y")
    def synth_yes(tex, config=None):
        return [Finding(category='Y', severity='MEDIUM',
                        message='yes', line=1)]

    @check(name="synth-no", severity="MEDIUM",
           help_text="n")
    def synth_no(tex, config=None):
        return [Finding(category='N', severity='MEDIUM',
                        message='no', line=1)]

    real_load = _plugins.load_plugins
    _plugins.load_plugins = lambda force_reload=False: {
        'synth-yes': synth_yes,
        'synth-no': synth_no,
    }
    try:
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'main.tex').write_text(
                'hi\n', encoding='utf-8',
            )
            findings = _plugins.audit_plugins(
                paper_n=1,
                paper_dir=Path(td),
                config={
                    'c11_plugins_enabled': ['synth-yes'],
                },
            )
        assert len(findings) == 1
        assert findings[0].category == 'Y'
    finally:
        _plugins.load_plugins = real_load
        reset_loader_cache()


def test_paper_configs_can_carry_c11_plugins_enabled():
    """PAPER_CONFIGS schema permits c11_plugins_enabled.

    The field is optional (None or missing is fine). If
    present, it must be a `list[str]`. This is a
    forward-compat check: future maintainers can add
    the field to any paper without breaking the audit.

    The check is purely structural — it does not assert
    the v0.5.0 implementation logic. The implementation
    lives in `audit_plugins` and `filter_active`; this
    test only verifies that the schema is honoured.
    """
    from tmaudit.configs.paper_configs import PAPER_CONFIGS
    for n, cfg in PAPER_CONFIGS.items():
        d = cfg.get('c11_plugins_enabled')
        assert d is None or (
            isinstance(d, list)
            and all(isinstance(x, str) for x in d)
        ), (
            f'paper {n}: c11_plugins_enabled must be None '
            f'or list[str], got {type(d).__name__}'
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
