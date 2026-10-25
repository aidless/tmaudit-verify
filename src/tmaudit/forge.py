"""tmaudit.forge — fork templates into per-paper scripts.

This module reads the generic templates and per-paper configs and
materialises the three operational scripts (verify_p<N>.py,
_compile_check.py, _fix_abstract_unicode.py) into the target paper
directory. The substitution logic is the same as the legacy
gen_*.py scripts, but uses importlib.resources to load templates
from the package, so it works inside an installed distribution
(including a .pyz zipapp).

Public API:
    fork_verify(paper_dir, paper_number) -> Path
    fork_compile(paper_dir) -> Path
    fork_fix_unicode(paper_dir) -> Path
    fork_all(paper_number, paper_dir) -> dict[str, Path]
"""
from __future__ import annotations
import re
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from .configs.compile_configs import PAPER_CONFIGS as COMPILE_CONFIGS
from .configs.paper_configs import PAPER_CONFIGS as VERIFY_CONFIGS

# Default effect-size type; declared as a module-level constant so the
# f-string in _substitute_verify (Python 3.9) does not need an
# embedded backslash.
COHENS_D = "Cohen's d"


TEMPLATES = 'tmaudit.templates'


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

def _read_template(name: str) -> str:
    """Read a template file from the installed tmaudit package.

    Compatible with both normal pip-installed packages and zipapp-style
    .pyz files. We try `importlib.resources.files()` (Python 3.9+)
    first; if that fails (zipapp pre-3.12 has a known issue with
    .joinpath() on Traversable), we fall back to
    `importlib.resources.read_text()`.
    """
    try:
        return resources.files(TEMPLATES).joinpath(name).read_text(
            encoding='utf-8',
        )
    except (KeyError, AttributeError):
        # Fallback for older Python zipapp behaviour
        return resources.read_text(TEMPLATES, name, encoding='utf-8')


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------

def find_main_tex(paper_dir: Path, default_name: str = 'main.tex') -> Path | None:
    """Locate a paper directory's root .tex.

    Prefers ``main.tex``; otherwise the sole .tex that declares
    ``\\begin{document}`` -- the file that pulls the rest in. Returns
    None when that choice is ambiguous or there is no .tex at all, so the
    caller reports an operational error rather than guessing.

    Used by ``plugins run --paper-dir`` and the generic verify fork, both
    of which audit a directory the built-in rulepack was not written for
    and which therefore cannot assume the conventional ``main.tex``.
    """
    paper_dir = Path(paper_dir)
    default = paper_dir / default_name
    if default.exists():
        return default
    candidates = [p for p in sorted(paper_dir.glob('*.tex')) if p.is_file()]
    roots: list[Path] = []
    for p in candidates:
        try:
            if '\\begin{document}' in p.read_text(
                    encoding='utf-8', errors='replace'):
                roots.append(p)
        except OSError:
            continue
    if len(roots) == 1:
        return roots[0]
    if not roots and len(candidates) == 1:
        return candidates[0]
    return None

# ---------------------------------------------------------------------------
# Substitutions for the verify template
# ---------------------------------------------------------------------------

def _format_simple_value(value: Any) -> str:
    """Format a value as a Python source literal.

    For strings that look like regex patterns (containing backslash
    escape sequences), emit them as raw string literals (r'...') so
    Python does not interpret the backslashes.
    """
    if isinstance(value, str):
        regex_marker_re = re.compile(r'\\[bBdDsSwWnrtfv0]|\\\.|\\\{|\\\}')
        if regex_marker_re.search(value):
            escaped = value.replace("'", r"\'")
            return f"r'{escaped}'"
        return repr(value)
    if value is None:
        return 'None'
    return repr(value)


def _format_c1_symbols(symbols: list[dict]) -> str:
    if not symbols:
        return '    [],'
    lines = ['    [']
    for i, sym in enumerate(symbols):
        sep = ',' if i < len(symbols) - 1 else ','
        lines.append('        {')
        for k, v in sym.items():
            lines.append(f"            {k!r}: {_format_simple_value(v)},")
        lines.append(f'        }}{sep}')
    lines.append('    ],')
    return '\n'.join(lines)


def _format_c2_families(families: dict) -> str:
    if not families:
        return '    {},'
    items = ', '.join(f'{k!r}: {v!r}' for k, v in families.items())
    return f'    {{{items}}},'


def _format_c6_blacklist(words: list[str]) -> str:
    if not words:
        return '    [],'
    return '    ' + repr(words) + ','


def _substitute_verify(
    template: str,
    cfg: dict,
    *,
    include_extended: bool = False,
) -> str:
    """Inject the per-paper CHECKS_CONFIG block into the verify template.

    Args:
        include_extended: also emit the C7..C11 keys. Off by default so
            the five in-repo papers keep producing byte-identical
            scripts (their C7..C10 values were never injected before);
            external configs opt in, because a stranger's config must be
            able to set C8/C9/C10 without editing the generated script.
    """
    out = template.replace(
        "ROOT = Path('F:/Research/PAPER1_CONSOLIDATED')",
        f"ROOT = Path({cfg['dir'].as_posix()!r})",
    )
    if cfg.get('tex_basename', 'main') != 'main':
        out = out.replace(
            "TEX_BASENAME = 'main'",
            f"TEX_BASENAME = {cfg['tex_basename']!r}",
        )
        # The verify template hardcodes MAIN = ROOT / 'main.tex'. Without
        # this, a paper whose source is paper.tex would fork a script
        # that audits a file which does not exist.
        out = out.replace(
            "MAIN = ROOT / 'main.tex'",
            f"MAIN = ROOT / {(cfg['tex_basename'] + '.tex')!r}",
        )
    bib_name = cfg.get('bib', 'refs.bib')
    if bib_name != 'refs.bib':
        # Same reasoning as MAIN: the template hardcodes the bibliography
        # filename, and a project using references.bib would otherwise be
        # audited against a file that does not exist.
        out = out.replace(
            "REFS = ROOT / 'refs.bib'",
            f"REFS = ROOT / {bib_name!r}",
        )

    parts = []
    parts.append('CHECKS_CONFIG: dict = {')
    parts.append("    'c1_symbols':")
    parts.append(_format_c1_symbols(cfg['c1_symbols']))
    parts.append('')
    parts.append("    'c2_families':")
    parts.append(_format_c2_families(cfg['c2_families']))
    parts.append("    'c2_section_pattern': "
                 f"{_format_simple_value(cfg['c2_section_pattern'])},")
    parts.append("    'c2_abstract_k_allowed': "
                 f"{_format_simple_value(cfg['c2_abstract_k_allowed'])},")
    parts.append('')
    parts.append("    'c3_concept': "
                 f"{_format_simple_value(cfg['c3_concept'])},")
    parts.append("    'c3_concept_token': "
                 f"{_format_simple_value(cfg['c3_concept_token'])},")
    parts.append("    'c3_formal': "
                 f"{_format_simple_value(cfg['c3_formal'])},")
    parts.append("    'c3_formal_secondary': "
                 f"{_format_simple_value(cfg.get('c3_formal_secondary'))},")
    parts.append('')
    parts.append("    'c4_self_cite_threshold': "
                 f"{repr(cfg.get('c4_self_cite_threshold', 0.30))},")
    parts.append("    'c4_self_cite_prefix': "
                 f"{_format_simple_value(cfg.get('c4_self_cite_prefix', 'liu2026'))},")
    parts.append("    'c4_max_self_cite_keys': "
                 f"{repr(cfg.get('c4_max_self_cite_keys', 3))},")
    parts.append('')
    parts.append("    'c5_d_type': "
                 f"{_format_simple_value(cfg.get('c5_d_type', COHENS_D))},")
    parts.append('')
    parts.append("    'c6_blacklist':")
    parts.append(_format_c6_blacklist(
        cfg.get('c6_blacklist', ['paradigm', 'yield', 'reveal'])))
    if include_extended:
        parts.append('')
        parts.append("    'c7_max_ceremonial': %r,"
                     % (cfg.get('c7_max_ceremonial', 2),))
        parts.append("    'c8_claimed_effects': %r,"
                     % (cfg.get('c8_claimed_effects', []),))
        parts.append("    'c9_figure_keywords': %r,"
                     % (cfg.get('c9_figure_keywords', []),))
        parts.append("    'c10_reproducibility_claims': %r,"
                     % (cfg.get('c10_reproducibility_claims', []),))
        parts.append("    'c11_plugins_enabled': %r,"
                     % (cfg.get('c11_plugins_enabled', []),))
        parts.append("    'c11_plugins_disabled': %r,"
                     % (cfg.get('c11_plugins_disabled', []),))
    parts.append('}')
    new_block = '\n'.join(parts)

    # Replace the existing CHECKS_CONFIG block with literal string slicing
    # (re.sub would misinterpret backslashes in the replacement text).
    marker = 'CHECKS_CONFIG: dict = {'
    start = out.find(marker)
    if start < 0:
        raise RuntimeError('CHECKS_CONFIG marker not found in template')
    depth = 0
    i = start
    in_str: str | None = None
    end = -1
    while i < len(out):
        c = out[i]
        if in_str is not None:
            if c == '\\' and i + 1 < len(out):
                i += 2
                continue
            if c == in_str:
                in_str = None
        else:
            if c in ('"', "'"):
                in_str = c
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        i += 1
    if end < 0:
        raise RuntimeError('CHECKS_CONFIG closing brace not found')
    if end < len(out) and out[end] == '\n':
        end += 1
    out = out[:start] + new_block + '\n' + out[end:]
    return out


# ---------------------------------------------------------------------------
# Substitutions for the compile / fix-unicode templates
# ---------------------------------------------------------------------------

def _substitute_compile(template: str, cfg: dict) -> str:
    out = template.replace(
        "ROOT = Path('F:/Research/PAPER1_CONSOLIDATED')",
        f"ROOT = Path({cfg['dir'].as_posix()!r})",
    )
    if cfg.get('tex_basename', 'main') != 'main':
        out = out.replace(
            "TEX_BASENAME = 'main'",
            f"TEX_BASENAME = {cfg['tex_basename']!r}",
        )
    return out


def _unicode_to_python_repr(s: str) -> str:
    """Convert a Unicode string to a Python source-code-safe representation.

    For non-ASCII characters, emit a backslash escape sequence
    (e.g., '\\u0394') so the resulting .py file does not require a
    coding declaration to be parsed by Python 3.
    """
    out = []
    for ch in s:
        if ord(ch) < 128:
            out.append(ch)
        else:
            out.append(f'\\u{ord(ch):04x}')
    return ''.join(out)


def _format_replacements_block(replacements: list[tuple[str, str]]) -> str:
    lines = []
    for raw, repl in replacements:
        raw_safe = _unicode_to_python_repr(raw)
        repl_safe = repr(repl)
        lines.append(f"    ({raw_safe!r}, {repl_safe}),")
    return '\n'.join(lines)


def _substitute_fix_unicode(template: str, cfg: dict) -> str:
    out = template.replace(
        "ROOT = Path('F:/Research/PAPER1_CONSOLIDATED')",
        f"ROOT = Path({cfg['dir'].as_posix()!r})",
    )
    if cfg.get('tex_basename', 'main') != 'main':
        out = out.replace(
            "TEX_BASENAME = 'main'",
            f"TEX_BASENAME = {cfg['tex_basename']!r}",
        )
    repls_str = _format_replacements_block(cfg['replacements'])
    pattern = re.compile(
        r"ABSTRACT_REPLACEMENTS: list\[tuple\[str, str\]\] = \[.*?\]",
        re.DOTALL,
    )
    out = pattern.sub(
        f"ABSTRACT_REPLACEMENTS: list[tuple[str, str]] = [\n{repls_str}\n]",
        out,
        count=1,
    )
    return out


# ---------------------------------------------------------------------------
# Write targets
# ---------------------------------------------------------------------------

def _write_target(target: Path, content: str, suffix: str = '.bak_before_tmaudit') -> None:
    if target.exists():
        bak = target.with_suffix(target.suffix + suffix)
        if not bak.exists():
            shutil.copy2(target, bak)


def fork_verify(paper_number: int, paper_dir: Path | None = None) -> Path:
    """Fork verify_p<N>.py for the given paper."""
    if paper_number not in VERIFY_CONFIGS:
        raise KeyError(f'no VERIFY_CONFIGS for paper {paper_number}')
    cfg = VERIFY_CONFIGS[paper_number]
    if paper_dir is None:
        paper_dir = cfg['dir']
    target = paper_dir / f'verify_p{paper_number}.py'
    template = _read_template('verify_TEMPLATE.py')
    out = _substitute_verify(template, cfg)
    _write_target(target, out)
    target.write_text(out, encoding='utf-8')
    return target


def fork_verify_generic(paper_dir: Path) -> Path:
    """Fork a neutral verify script into ``paper_dir``.

    For auditing a manuscript the built-in rulepack was not written for.
    The script keeps the shipped factory ``CHECKS_CONFIG`` (empty), so
    the per-paper categories (C1/C2/C3/C6) report "not applicable" and
    the generic categories (C4/C5/C7/C8/C9/C10 sub-checks) run with their
    built-in defaults. Written as ``verify_generic.py``; reached through
    ``tmaudit verify --paper-dir DIR`` (no ``--paper``).
    """
    # Absolute: the generated script is later launched with cwd=target.parent,
    # so a relative paper_dir would be resolved twice and the launch would look
    # for examples/sample-paper/examples/sample-paper/verify_generic.py.
    paper_dir = Path(paper_dir).expanduser().resolve()
    template = _read_template('verify_TEMPLATE.py')
    out = template.replace(
        "ROOT = Path('F:/Research/PAPER1_CONSOLIDATED')",
        f"ROOT = Path({paper_dir.as_posix()!r})",
    )
    target = paper_dir / 'verify_generic.py'
    _write_target(target, out)
    target.write_text(out, encoding='utf-8')
    return target


def fork_verify_for_target(spec, paper_dir: Path | None = None) -> Path:
    """Fork a verify script for an external (on-disk) paper config.

    Same template, same substitution, same generated-script shape as
    ``fork_verify()``. The three differences are:

    1. the config comes from a file (``TargetSpec``) rather than
       ``PAPER_CONFIGS``, so no paper number is needed;
    2. the script is named after ``[paper].name`` instead of
       ``verify_p<N>.py``, so two strangers' scripts do not collide;
    3. C7..C11 keys are emitted, so an external config can configure
       C8/C9/C10 without hand-editing the generated file.

    ``paper_dir`` overrides only where the script is written. The
    script's ``ROOT`` stays ``spec.dir``, matching the ``--paper-dir``
    semantics of the in-repo path.
    """
    cfg = spec.to_cfg()
    target_dir = Path(paper_dir) if paper_dir is not None else Path(spec.dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / spec.script_name()
    template = _read_template('verify_TEMPLATE.py')
    out = _substitute_verify(template, cfg, include_extended=True)
    _write_target(target, out)
    target.write_text(out, encoding='utf-8')
    return target


def fork_compile(paper_number: int, paper_dir: Path | None = None) -> Path:
    """Fork _compile_check.py for the given paper."""
    if paper_number not in COMPILE_CONFIGS:
        raise KeyError(f'no COMPILE_CONFIGS for paper {paper_number}')
    cfg = COMPILE_CONFIGS[paper_number]
    if paper_dir is None:
        paper_dir = cfg['dir']
    target = paper_dir / '_compile_check.py'
    template = _read_template('compile_check_TEMPLATE.py')
    out = _substitute_compile(template, cfg)
    _write_target(target, out)
    target.write_text(out, encoding='utf-8')
    return target


def fork_fix_unicode(paper_number: int, paper_dir: Path | None = None) -> Path:
    """Fork _fix_abstract_unicode.py for the given paper."""
    if paper_number not in COMPILE_CONFIGS:
        raise KeyError(f'no COMPILE_CONFIGS for paper {paper_number}')
    cfg = COMPILE_CONFIGS[paper_number]
    if paper_dir is None:
        paper_dir = cfg['dir']
    target = paper_dir / '_fix_abstract_unicode.py'
    template = _read_template('fix_abstract_unicode_TEMPLATE.py')
    out = _substitute_fix_unicode(template, cfg)
    _write_target(target, out)
    target.write_text(out, encoding='utf-8')
    return target


def fork_all(paper_number: int, paper_dir: Path | None = None) -> dict[str, Path]:
    """Fork all three scripts. Returns a mapping of role -> path."""
    return {
        'verify':        fork_verify(paper_number, paper_dir),
        'compile':       fork_compile(paper_number, paper_dir),
        'fix_unicode':   fork_fix_unicode(paper_number, paper_dir),
    }