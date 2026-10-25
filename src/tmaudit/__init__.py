"""tmaudit — config-driven TMLR paper audit + LaTeX compile pipeline.

This package bundles:
  * The generic 10-category audit template (C1..C10)
  * The generic 4-pass LaTeX compile script
  * The generic abstract-Unicode -> LaTeX-math fixer
  * Per-paper PAPER_CONFIGS for all five TMLR papers
  * A plugin API (added in v0.4.0) for user-written audit checks
  * External paper configs (added in v0.6.0): `verify --target FILE`
    runs the same audit path on a paper that is not in PAPER_CONFIGS
  * A read-only `Target` view (added in v0.6.0) over the audited object,
    so a plugin can ask for sections and citations instead of re-parsing
    LaTeX

and exposes a single CLI:

    tmaudit --list
    tmaudit verify --paper N [--paper-dir PATH]
    tmaudit verify --paper N
    tmaudit verify --paper-dir PATH        # generic checks, empty config
    tmaudit verify --target paper.toml     # external config, rules included
    tmaudit admission --gain 7.3 --tasks 89
    tmaudit compile --paper N
    tmaudit fix-unicode --paper N
    tmaudit audit-all
    tmaudit plugins list

The package can be installed with `pip install tmaudit/` (or
`pip install -e .` for editable mode) and shipped as a single
executable .pyz file with `python -m zipapp`.
"""
# Keep in lockstep with pyproject.toml — the published 0.5.1 wheel
# previously reported 0.5.0 from this constant, and the cache key is
# derived from it (cache.cache_key).
__version__ = '0.6.0'

# Re-export the plugin API at the package level so users can
# `from tmaudit import Finding, check` instead of
# `from tmaudit.plugins import ...`. The submodule is still
# the canonical home for the implementation.
from .plugins import (
    Finding,
    CheckFn,
    PLUGIN_GROUP,
    VALID_SEVERITIES,
    audit_plugins,
    check,
    filter_active,
    load_plugins,
    reset_loader_cache,
    run_all_plugins,
    run_plugin,
)

# The audited-object view, re-exported for plugin authors.
from .target import (
    CitationRef,
    Section,
    Target,
    TexTarget,
    TextTarget,
    as_target,
    as_text,
)

__all__ = [
    "__version__",
    "Finding",
    "CheckFn",
    "PLUGIN_GROUP",
    "VALID_SEVERITIES",
    "audit_plugins",
    "check",
    "filter_active",
    "load_plugins",
    "reset_loader_cache",
    "run_all_plugins",
    "run_plugin",
    "CitationRef",
    "Section",
    "Target",
    "TexTarget",
    "TextTarget",
    "as_target",
    "as_text",
    # Re-exported for plugin authors. CHANGELOG.md records them as public API, so
    # listing them here is what tells pyflakes they are not dead imports.
    "CacheDB",
    "cache_key",
    "plugin_cache_key",
]  # type: ignore

# Re-export cache helpers that plugin authors will need.
from .cache import (
    CacheDB,
    cache_key,
    plugin_cache_key,
)
