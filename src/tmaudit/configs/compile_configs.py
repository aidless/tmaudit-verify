#!/usr/bin/env python3
"""gen_compile_scripts.py — fork compile scripts from TEMPLATE/ into a paper dir.

This tool:
  1. Reads the compile-check template (see TEMPLATE_DIR)
  2. Reads the abstract-unicode template (see TEMPLATE_DIR)
  3. Substitutes the ROOT path (and TEX_BASENAME) per-paper
  4. Substitutes the ABSTRACT_REPLACEMENTS list per-paper (only for the
     abstract-unicode script; the compile script has no per-paper list)
  5. Writes the result under <research>/PAPER<N>_CONSOLIDATED/ as
     _compile_check.py and _fix_abstract_unicode.py
  6. Backs up any existing target file to .bak_before_template

Usage:
    python gen_compile_scripts.py --paper 2
    python gen_compile_scripts.py --paper 2 --dry-run        # show what would happen
    python gen_compile_scripts.py --paper 2 --list           # list known papers
    python gen_compile_scripts.py --list                     # show all known papers

Per-paper symbol configuration is read from PAPER_CONFIGS below. To add
a new paper, append a new entry to PAPER_CONFIGS.
"""
from __future__ import annotations
import argparse
import re
import shutil
import os
import sys
from pathlib import Path

# Same default as paper_configs.py: ./papers, never an author-machine path.
RESEARCH_DIR = Path(os.environ.get('TMAUDIT_RESEARCH_DIR', 'papers'))
TEMPLATE_DIR = Path(os.environ.get('TMAUDIT_TEMPLATE_DIR',
                               str(RESEARCH_DIR / 'TEMPLATE')))

# ---------------------------------------------------------------------------
# Per-paper configuration
# ---------------------------------------------------------------------------
# Each entry maps paper number -> {
#   'dir':           output directory,
#   'tex_basename':  basename of .tex file (default 'main'),
#   'replacements':  list of (raw_unicode, latex_replacement) for the abstract.
#                    Order matters: longer / more specific first.
# }
# ---------------------------------------------------------------------------
PAPER_CONFIGS: dict[int, dict] = {
    1: {
        'dir': RESEARCH_DIR / 'PAPER1_CONSOLIDATED',
        'tex_basename': 'main',
        'replacements': [
            ('ΔCAF = −0.11',          '$\\Delta$CAF = $-0.11$'),
            ('ΔECE = +0.228',         '$\\Delta$ECE = $+0.228$'),
            ('ΔCAF ≤ 0',              '$\\Delta$CAF $\\leq$ 0'),
            ('ΔECE ≤ 0',              '$\\Delta$ECE $\\leq$ 0'),
            ('(E_T = +0.228, Cohen\'s d = 4.70)',
             '($E_T = +0.228$, Cohen\'s $d = 4.70$)'),
            ('Δ',  '$\\Delta$'),
            ('−',  '$-$'),
            ('≤',  '$\\leq$'),
            ('≥',  '$\\geq$'),
            ('×',  '$\\times$'),
            ('·',  '$\\cdot$'),
        ],
    },
    2: {
        'dir': RESEARCH_DIR / 'PAPER2_CONSOLIDATED',
        'tex_basename': 'main',
        # Placeholder — Paper 2 symbols depend on the actual abstract.
        # Replace this list with Paper 2's specific symbols once known.
        'replacements': [
            ('Δ',  '$\\Delta$'),
            ('−',  '$-$'),
            ('≤',  '$\\leq$'),
            ('≥',  '$\\geq$'),
            ('×',  '$\\times$'),
            ('·',  '$\\cdot$'),
        ],
    },
    3: {
        'dir': RESEARCH_DIR / 'PAPER3_CONSOLIDATED',
        'tex_basename': 'main',
        'replacements': [
            ('Δ',  '$\\Delta$'),
            ('−',  '$-$'),
            ('≤',  '$\\leq$'),
            ('≥',  '$\\geq$'),
            ('×',  '$\\times$'),
        ],
    },
    4: {
        'dir': RESEARCH_DIR / 'PAPER4_CONSOLIDATED',
        'tex_basename': 'main',
        'replacements': [
            ('Δ',  '$\\Delta$'),
            ('−',  '$-$'),
            ('≤',  '$\\leq$'),
            ('≥',  '$\\geq$'),
            ('×',  '$\\times$'),
        ],
    },
    5: {
        'dir': RESEARCH_DIR / 'PAPER5_CONSOLIDATED',
        'tex_basename': 'main',
        'replacements': [
            ('Δ',  '$\\Delta$'),
            ('−',  '$-$'),
            ('≤',  '$\\leq$'),
            ('≥',  '$\\geq$'),
            ('×',  '$\\times$'),
        ],
    },
}


# ---------------------------------------------------------------------------
# Substitution logic
# ---------------------------------------------------------------------------

def substitute_compile_check(template: str, cfg: dict) -> str:
    """Substitute ROOT and TEX_BASENAME in the compile-check template."""
    out = template
    # Replace the ROOT line
    out = re.sub(
        r"ROOT\s*=\s*Path\('[^']*'\)",
        f"ROOT = Path('{cfg['dir'].as_posix()}')",
        out,
        count=1,
    )
    # Replace TEX_BASENAME (only if the paper's tex file is not main.tex)
    if cfg['tex_basename'] != 'main':
        out = re.sub(
            r"TEX_BASENAME\s*=\s*'[^']*'",
            f"TEX_BASENAME = '{cfg['tex_basename']}'",
            out,
            count=1,
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
    """Format a list of (raw, latex) tuples as a Python source list.

    Each tuple is emitted as `('<raw-as-Python-escaped>', '<latex>')` to
    ensure the resulting source file parses without a # coding: utf-8
    declaration.
    """
    lines = []
    for raw, repl in replacements:
        # Use repr() for the LaTeX side (it is ASCII, no escaping needed)
        # and manual escape for the raw Unicode side.
        raw_safe = _unicode_to_python_repr(raw)
        repl_safe = repr(repl)
        lines.append(f"    ({raw_safe!r}, {repl_safe}),")
    return '\n'.join(lines)


def substitute_abstract_unicode(template: str, cfg: dict) -> str:
    """Substitute ROOT, TEX_BASENAME, and ABSTRACT_REPLACEMENTS in the
    abstract-unicode template."""
    out = template
    out = re.sub(
        r"ROOT\s*=\s*Path\('[^']*'\)",
        f"ROOT = Path('{cfg['dir'].as_posix()}')",
        out,
        count=1,
    )
    if cfg['tex_basename'] != 'main':
        out = re.sub(
            r"TEX_BASENAME\s*=\s*'[^']*'",
            f"TEX_BASENAME = '{cfg['tex_basename']}'",
            out,
            count=1,
        )
    # Replace the ABSTRACT_REPLACEMENTS list. The replacement string uses
    # Python \\u-escape sequences for the raw Unicode side so the output
    # .py file parses on any Python 3 interpreter without a # coding: utf-8
    # declaration.
    repls_str = _format_replacements_block(cfg['replacements'])
    out = re.sub(
        r"ABSTRACT_REPLACEMENTS: list\[tuple\[str, str\]\] = \[.*?\]",
        f"ABSTRACT_REPLACEMENTS: list[tuple[str, str]] = [\n{repls_str}\n]",
        out,
        count=1,
        flags=re.DOTALL,
    )
    return out


def write_output(target: Path, content: str, dry_run: bool) -> None:
    print(f'\n--- {target} ---')
    print(f'  size: {len(content):,} chars')
    print(f'  first 80: {content.splitlines()[0][:80]!r}')

    if dry_run:
        print('  DRY-RUN: not writing')
        return

    if target.exists():
        bak = target.with_suffix(target.suffix + '.bak_before_template')
        if not bak.exists():
            shutil.copy2(target, bak)
            print(f'  [BACKUP] -> {bak.name}')
        else:
            print(f'  [BACKUP] {bak.name} already exists; not overwriting')

    target.write_text(content, encoding='utf-8')
    print(f'  [WRITE] {target} ({len(content):,} chars)')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper', type=int,
                        help='Paper number to generate scripts for (e.g. 2)')
    parser.add_argument('--list', action='store_true',
                        help='List all known paper configurations and exit')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be written, but make no changes')
    args = parser.parse_args()

    if args.list:
        print('Known paper configurations:')
        for n, cfg in sorted(PAPER_CONFIGS.items()):
            tex = f"{cfg['tex_basename']}.tex"
            print(f'  Paper {n}: {cfg["dir"]}  (tex={tex}, {len(cfg["replacements"])} replacement rules)')
        return 0

    if args.paper is None:
        print('ERROR: must specify --paper N or --list', file=sys.stderr)
        return 2

    if args.paper not in PAPER_CONFIGS:
        print(f'ERROR: no config for paper {args.paper}', file=sys.stderr)
        print(f'       known papers: {sorted(PAPER_CONFIGS)}', file=sys.stderr)
        print('       add an entry to PAPER_CONFIGS in gen_compile_scripts.py', file=sys.stderr)
        return 2

    cfg = PAPER_CONFIGS[args.paper]
    print('=' * 72)
    print(f'Generating compile scripts for Paper {args.paper}')
    print('=' * 72)
    print(f'  Target dir: {cfg["dir"]}')
    print(f'  Tex file:   {cfg["tex_basename"]}.tex')
    print(f'  Replacements: {len(cfg["replacements"])} rule(s)')
    print(f'  Mode: {"DRY-RUN" if args.dry_run else "APPLY"}')
    print()

    if not cfg['dir'].exists():
        print(f'ERROR: target dir does not exist: {cfg["dir"]}', file=sys.stderr)
        return 2

    # 1. _compile_check_TEMPLATE.py -> _compile_check.py
    cc_tpl = TEMPLATE_DIR / '_compile_check_TEMPLATE.py'
    if not cc_tpl.exists():
        print(f'ERROR: missing template {cc_tpl}', file=sys.stderr)
        return 2
    cc_target = cfg['dir'] / '_compile_check.py'
    cc_out = substitute_compile_check(cc_tpl.read_text(encoding='utf-8'), cfg)
    write_output(cc_target, cc_out, args.dry_run)

    # 2. _fix_abstract_unicode_TEMPLATE.py -> _fix_abstract_unicode.py
    au_tpl = TEMPLATE_DIR / '_fix_abstract_unicode_TEMPLATE.py'
    if not au_tpl.exists():
        print(f'ERROR: missing template {au_tpl}', file=sys.stderr)
        return 2
    au_target = cfg['dir'] / '_fix_abstract_unicode.py'
    au_out = substitute_abstract_unicode(au_tpl.read_text(encoding='utf-8'), cfg)
    write_output(au_target, au_out, args.dry_run)

    print()
    print('=' * 72)
    if args.dry_run:
        print('DRY-RUN: no files written.  Re-run without --dry-run to commit.')
    else:
        print(f'Done.  Next: cd {cfg["dir"]} && python _compile_check.py')
    print('=' * 72)
    return 0


if __name__ == '__main__':
    sys.exit(main())