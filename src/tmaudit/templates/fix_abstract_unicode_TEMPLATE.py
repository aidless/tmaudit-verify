#!/usr/bin/env python3
"""_fix_abstract_unicode_TEMPLATE.py — generic abstract Unicode→LaTeX fix.

This is the GENERIC TEMPLATE. To use:

    1. Copy this file next to the paper as _fix_abstract_unicode.py
    2. Edit the `ROOT` constant to point at that paper's dir.
    3. Edit `ABSTRACT_REPLACEMENTS` to match the symbols used in that
       paper's abstract (e.g., for Paper 2, replace ΔCAF with Δγ etc.).

Or, run `python gen_compile_scripts.py --paper N` to fork automatically.

Why this exists:
    Raw Unicode (Δ, −, ≤, etc.) in a LaTeX abstract triggers
        ! LaTeX Error: Unicode character 螖 (U+0394)
    when the document does not declare utf8 input encoding. The fix is
    to replace these glyphs with their LaTeX math equivalents
    ($\\Delta$, $-$, $\\leq$, etc.) so the document compiles cleanly.

Scope:
    Inside \\begin{abstract} ... \\end{abstract} only — the rest of the
    document is left untouched. (If you also need to fix body Unicode,
    extend `ABSTRACT_REPLACEMENTS` to cover the full document.)

Usage:
    python _fix_abstract_unicode.py            # dry-run (prints diff)
    python _fix_abstract_unicode.py --apply    # actually write changes
"""
from __future__ import annotations
import argparse
import re
import shutil
import sys
from pathlib import Path

# ============================================================================
# Configuration (only this block needs editing per paper)
# ============================================================================
ROOT = Path('PAPER_DIR')  # replaced per paper
TEX_BASENAME = 'main'                                # <-- only if not main.tex
BAK_SUFFIX = 'pre_unicode_fix'

# Token-level replacements inside the abstract only.
# Order matters: longer / more specific sequences first to avoid greedy
# partial matches. Each tuple is (raw Unicode, LaTeX replacement).
ABSTRACT_REPLACEMENTS: list[tuple[str, str]] = [
    # ----- Paper 1 example (delete / replace for other papers) -----
    # Specific sequences first
    ('ΔCAF = −0.11',          '$\\Delta$CAF = $-0.11$'),
    ('ΔECE = +0.228',         '$\\Delta$ECE = $+0.228$'),
    ('ΔCAF ≤ 0',              '$\\Delta$CAF $\\leq$ 0'),
    ('ΔECE ≤ 0',              '$\\Delta$ECE $\\leq$ 0'),
    # E_T in plain text mode triggers LaTeX "_" subscript error.
    ('(E_T = +0.228, Cohen\'s d = 4.70)',
     '($E_T = +0.228$, Cohen\'s $d = 4.70$)'),
    # Generic fallbacks (in case any raw Unicode remains in other parts of the abstract)
    ('Δ',                     '$\\Delta$'),
    ('−',                     '$-$'),
    ('≤',                     '$\\leq$'),
    ('≥',                     '$\\geq$'),
    ('×',                     '$\\times$'),
    ('·',                     '$\\cdot$'),
]
# ============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='actually write changes (default is dry-run)')
    args = parser.parse_args()

    main_tex = ROOT / f'{TEX_BASENAME}.tex'
    if not main_tex.exists():
        print(f'ERROR: missing {main_tex}', file=sys.stderr)
        return 2

    tex = main_tex.read_text(encoding='utf-8')

    # Locate abstract
    m = re.search(r'\\begin\{abstract\}(.+?)\\end\{abstract\}', tex, re.DOTALL)
    if m is None:
        print('ERROR: no abstract environment found', file=sys.stderr)
        return 2

    abstract_start = m.start(1)
    abstract_end = m.end(1)
    abstract = tex[abstract_start:abstract_end]

    print('=' * 72)
    print(f'Abstract Unicode -> LaTeX math pass  ({Path(__file__).name})')
    print('=' * 72)
    print(f'Mode: {"APPLY" if args.apply else "DRY-RUN"}')
    print(f'Abstract size: {len(abstract):,} chars')
    print()

    new_abstract = abstract
    total_edits = 0
    for raw, repl in ABSTRACT_REPLACEMENTS:
        n = new_abstract.count(raw)
        if n > 0:
            print(f'  [EDIT] {raw!r}')
            print(f'      -> {repl!r}  ({n} occurrence(s))')
            new_abstract = new_abstract.replace(raw, repl)
            total_edits += n
    print()
    print(f'Total edits: {total_edits}')
    print(f'New abstract size: {len(new_abstract):,} chars '
          f'(+{len(new_abstract) - len(abstract)})')
    print()

    if total_edits == 0:
        print('No raw Unicode remaining; nothing to do.')
        return 0

    if not args.apply:
        print('DRY-RUN: no files written. Pass --apply to commit.')
        return 0

    bak = ROOT / f'{TEX_BASENAME}.tex.bak_{BAK_SUFFIX}'
    if not bak.exists():
        shutil.copy2(main_tex, bak)
        print(f'[BACKUP] {main_tex.name} -> {bak.name}')
    else:
        print(f'[BACKUP] {bak.name} already exists; not overwriting')

    new_tex = tex[:abstract_start] + new_abstract + tex[abstract_end:]
    main_tex.write_text(new_tex, encoding='utf-8')
    print(f'[WRITE]  {main_tex.name} ({len(new_tex):,} chars)')
    print()
    print('Done.  Re-run _compile_check.py to confirm 0 fatal errors.')
    return 0


if __name__ == '__main__':
    sys.exit(main())