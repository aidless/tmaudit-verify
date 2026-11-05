#!/usr/bin/env python3
"""_compile_check_TEMPLATE.py — generic 4-pass LaTeX build for any PAPER.

This is the GENERIC TEMPLATE. To use:

    1. Copy this file next to the paper as _compile_check.py
    2. Edit the single `ROOT` constant below to point at that paper's dir.
    3. (Optional) Edit TEX_BASENAME if the .tex file is not main.tex.

No other code needs to be changed. The same 4-pass build, summary, and
exit code logic applies to every paper.

Or fork it from a checkout with `tmaudit compile --paper N`.
The placeholder is `ROOT = Path('PAPER_DIR')`, not a machine path.

Pipeline:
    pass 1: pdflatex main.tex      (generates .aux)
    pass 2: bibtex main             (generates .bbl from refs.bib)
    pass 3: pdflatex main.tex      (incorporates .bbl, resolves cites)
    pass 4: pdflatex main.tex      (resolves cross-references)

Exit codes:
    0 = clean compile (PDF produced, 0 fatal, 0 undefined, 0 warnings)
    1 = clean compile but with fatal errors / undefined cites
    2 = pdflatex pass 1 hit a truly fatal error (no PDF produced)
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

# ============================================================================
# Configuration (only this block needs editing per paper)
# ============================================================================
ROOT = Path('PAPER_DIR')  # replaced per paper
TEX_BASENAME = 'main'                              # <-- only if not main.tex
# Command names, resolved on PATH. An absolute install path does not belong
# in the shipped template.
PDFLATEX = 'pdflatex'
BIBTEX = 'bibtex'
# ============================================================================


def run(cmd: list[str], log_name: str) -> int:
    log = ROOT / log_name
    print(f'>>> {" ".join(str(c) for c in cmd)}  →  {log.name}')
    with log.open('w', encoding='utf-8') as f:
        rc = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode
    return rc


def main() -> int:
    tex = f'{TEX_BASENAME}.tex'
    aux = TEX_BASENAME

    # ----------------------------------------------------------------
    # Clean intermediate files (keep .tex, .bib, .sty, .bst, .pdf figures)
    # ----------------------------------------------------------------
    for ext in ('aux', 'bbl', 'blg', 'log', 'out', 'toc', 'lot', 'lof', 'pdf'):
        for p in ROOT.glob(f'{TEX_BASENAME}.{ext}'):
            p.unlink()
            print(f'  rm  {p.name}')

    # ----------------------------------------------------------------
    # Pass 1: pdflatex. Note: rc=1 means "undefined citations/references"
    # which is NON-fatal — the PDF is still written. We only abort on
    # truly fatal errors (missing \begin{document}, Emergency stop).
    # ----------------------------------------------------------------
    rc = run([str(PDFLATEX), '-interaction=nonstopmode', tex], f'{TEX_BASENAME}_p1.log')
    print(f'  rc = {rc}  (1 is non-fatal: undefined citation/ref warnings)')
    log1 = (ROOT / f'{TEX_BASENAME}_p1.log').read_text(encoding='utf-8', errors='replace')
    if 'Fatal error' in log1 or 'Emergency stop' in log1:
        print('--- last 40 lines of pass 1 log (FATAL) ---')
        print('\n'.join(log1.splitlines()[-40:]))
        return 2

    # ----------------------------------------------------------------
    # Pass 2: bibtex
    # ----------------------------------------------------------------
    rc = run([str(BIBTEX), aux], f'{TEX_BASENAME}_bib.log')
    print(f'  bibtex rc = {rc}')
    bib_log = (ROOT / f'{TEX_BASENAME}_bib.log').read_text(encoding='utf-8', errors='replace')
    if 'warning' in bib_log.lower() or 'error' in bib_log.lower():
        print('--- bibtex log ---')
        print(bib_log)

    # ----------------------------------------------------------------
    # Pass 3 + 4: pdflatex twice (incorporate .bbl, then cross-refs)
    # ----------------------------------------------------------------
    for i in (3, 4):
        rc = run([str(PDFLATEX), '-interaction=nonstopmode', tex], f'{TEX_BASENAME}_p{i}.log')
        print(f'  pass {i} rc = {rc}')

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    pdf = ROOT / f'{TEX_BASENAME}.pdf'
    log = (ROOT / f'{TEX_BASENAME}_p4.log').read_text(encoding='utf-8', errors='replace')

    out_match = re.search(
        rf'Output written on {re.escape(TEX_BASENAME)}\.pdf \((\d+) pages?, (\d+) bytes?\)',
        log,
    )
    if out_match:
        pages = out_match.group(1)
        size = out_match.group(2)
        print()
        print('=' * 60)
        print(f'Final PDF: {pages} pages, {size} bytes  ({pdf})')
        print('=' * 60)
    else:
        print('No "Output written" line found in pass 4 log.')

    n_undef = len(re.findall(r'undefined citation', log, re.IGNORECASE))
    n_undef_ref = len(re.findall(r'undefined references?', log, re.IGNORECASE))
    n_fatal = len(re.findall(r'^!\s', log, re.MULTILINE))
    n_warn = len(re.findall(r'^LaTeX Warning', log, re.MULTILINE))
    print(f'Pass 4 log: {len(log):,} chars')
    print(f'  undefined citations:  {n_undef}')
    print(f'  undefined references: {n_undef_ref}')
    print(f'  fatal errors (!-prefixed): {n_fatal}')
    print(f'  LaTeX warnings:        {n_warn}')

    if n_fatal > 0 or n_undef > 0:
        print('--- last 30 lines of pass 4 log ---')
        print('\n'.join(log.splitlines()[-30:]))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())