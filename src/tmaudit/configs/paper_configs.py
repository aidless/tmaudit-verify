#!/usr/bin/env python3
"""gen_verify_scripts.py — fork the verify_p<N>.py audit script from TEMPLATE.

This tool:
  1. Reads the verify template (see TEMPLATE_DIR)
  2. Reads PAPER_CONFIGS (below) for the per-paper check configuration
  3. Substitutes the ROOT and CHECKS_CONFIG blocks
  4. Writes the result to <research>/PAPER<N>_CONSOLIDATED/verify_p<N>.py
  5. Backs up any existing target file to .bak_before_template

Usage:
    python gen_verify_scripts.py --list
    python gen_verify_scripts.py --paper 1
    python gen_verify_scripts.py --paper 1 --dry-run

Per-paper configuration is read from PAPER_CONFIGS below. To add a new
paper, append a new entry.

Note: this tool writes the *audit* (verify) script. For the *compile*
script (the 4-pass pdflatex+bibtex+pdflatex+pdflatex pipeline), use
`gen_compile_scripts.py` instead.
"""
from __future__ import annotations
import argparse
import re
import shutil
import os
import sys
from pathlib import Path

# Per-paper directories live under TMAUDIT_RESEARCH_DIR. There is no
# author-machine default. Unset, they resolve under ./papers, which this
# repository does not ship. `tmaudit list` then shows those paths as missing.
RESEARCH_DIR = Path(os.environ.get('TMAUDIT_RESEARCH_DIR', 'papers'))
TEMPLATE_DIR = Path(os.environ.get('TMAUDIT_TEMPLATE_DIR',
                               str(RESEARCH_DIR / 'TEMPLATE')))

# ---------------------------------------------------------------------------
# Per-paper CHECKS_CONFIG (6 categories of audit)
# ---------------------------------------------------------------------------
# Each entry has:
#   'dir':           output directory,
#   'c1_symbols':    list of {name, token, definition, window} dicts,
#   'c2_families':   {family_name: k_value},
#   'c2_section_pattern': regex (r-string) for the \\section / \\subsection
#                        that declares the statistical protocol.
#   'c2_abstract_k_allowed': list[int] of k values acceptable in the abstract.
#   'c3_concept':           human-readable label of the concept
#                           (e.g., "crossover", "Two Faces").
#   'c3_concept_token':     regex matching the concept in main.tex
#                           (e.g., r'\\textbf\{crossover\}|\bcrossover\b').
#   'c3_formal':            regex that must match a formal definition
#                           of the concept.
#   'c3_formal_secondary':  optional, second formal definition (used when
#                           the concept has two halves, e.g. Face 1 / Face 2).
#   'c4_self_cite_threshold': float (default 0.30).
#   'c4_self_cite_prefix':   str (default 'liu2026').
#   'c4_max_self_cite_keys': int (default 3).
#   'c5_d_type':             str (default "Cohen's d").
#   'c6_blacklist':          list[str] (default ['paradigm','yield','reveal']).
# ---------------------------------------------------------------------------
PAPER_CONFIGS: dict[int, dict] = {
    1: {
        'dir': RESEARCH_DIR / 'PAPER1_CONSOLIDATED',
        'c1_symbols': [
            {
                'name': r'$\Delta$CAF (consensus-against-field coefficient)',
                'token': r'\bCAF\b',
                'definition': r'\bCAF\b.{0,80}=|consensus.{0,30}agreement|strateg.{0,30}convergence',
            },
            {
                'name': r'$E_T$ (temporal-accumulation effect on calibration)',
                'token': r'\bE_T\b',
                'definition': r'E_T.{0,80}=|temporal.{0,30}accumulation|peer.anchored.{0,30}confidence',
            },
            {
                'name': r'$\Delta$ECE (calibration delta)',
                'token': r'\\Delta\s*ECE|\\Delta\\mathrm\{ECE\}',
                'definition': r'\\Delta\s*ECE.{0,80}=|calibration.{0,30}loss|calibration.{0,30}degrad',
            },
            {
                'name': 'TTRL (Test-Time Reinforcement Learning)',
                'token': r'\bTTRL\b',
                'definition': r'TTRL.{0,80}=|Test.Time.{0,40}Reinforcement.{0,40}Learning',
            },
        ],
        'c2_families': {'main': 3},
        'c2_section_pattern': (
            r'\\section\*?\{[^}]*Power analysis[^}]*\}|'
            r'\\subsection\*?\{[^}]*Power analysis[^}]*\}'
        ),
        'c2_abstract_k_allowed': [3],
        'c3_concept': 'Two Faces (Face 1 / Face 2)',
        'c3_concept_token': r'\\textbf\{Face 1\}|\\textbf\{Face 2\}|\bFace\s+1\b|\bFace\s+2\b',
        'c3_formal': r'\\section\{Face 1:',
        'c3_formal_secondary': r'\\section\{Face 2:',
        'c4_self_cite_threshold': 0.30,
        'c4_self_cite_prefix': 'liu2026',
        'c4_max_self_cite_keys': 3,
        'c5_d_type': "Cohen's d",
        'c6_blacklist': ['paradigm', 'yield', 'reveal'],
        # C7: Paper 1 has 1 self-cite per related-work pattern.
        'c7_max_ceremonial': 2,
        # C8: Paper 1 has 1 main effect (TTRL vs SFT, n=200,
        # claimed d=0.5). The paper's actual numbers can be
        # verified against this claim.
        'c8_claimed_effects': [
            {'name': 'TTRL_vs_SFT', 'd': 0.50, 'n1': 200, 'n2': 200, 'alpha': 0.05},
        ],
        # C9: Paper 1 has 3 figures (overview, results,
        # analysis). Each caption should mention the expected
        # keywords.
        'c9_figure_keywords': [
            {'fig_id': 'fig:overview', 'expected_keywords': ['overview', 'architecture', 'TTRL']},
            {'fig_id': 'fig:results', 'expected_keywords': ['results', 'accuracy', 'comparison']},
            {'fig_id': 'fig:analysis', 'expected_keywords': ['analysis', 'ablation']},
        ],
        # C10: Paper 1 has 1 SOTA claim (TTRL) and 1 standard
        # benchmark claim (TQA). Both are verifiable in
        # principle.
        'c10_reproducibility_claims': [
            {'type': 'claims_sota', 'dataset': 'TQA', 'expected_section': 'code'},
        ],
    },
    2: {
        # Paper 2 is the "Impossibility Triangle" paper.
        # The three vertices of the triangle are the three
        # properties that cannot all be satisfied simultaneously
        # (e.g., consistency, robustness, fairness; or
        # invariance, calibration, efficiency). The C1 symbols
        # are the vertex labels.
        #
        # TODO: confirm the actual symbol names against that paper's main.tex. The names
        # below are plausible based on the C3 concept and the
        # typical structure of impossibility-result papers.
        'dir': RESEARCH_DIR / 'PAPER2_CONSOLIDATED',
        'c1_symbols': [
            {
                'name': r'$V_1$ (first vertex of the impossibility triangle)',
                'token': r'\bV_1\b|\bV1\b',
                'definition': r'V_1.{0,80}=|first.{0,30}vertex|property.{0,30}one',
            },
            {
                'name': r'$V_2$ (second vertex of the impossibility triangle)',
                'token': r'\bV_2\b|\bV2\b',
                'definition': r'V_2.{0,80}=|second.{0,30}vertex|property.{0,30}two',
            },
            {
                'name': r'$V_3$ (third vertex of the impossibility triangle)',
                'token': r'\bV_3\b|\bV3\b',
                'definition': r'V_3.{0,80}=|third.{0,30}vertex|property.{0,30}three',
            },
        ],
        # Paper 2 has a single hypothesis family (the main
        # impossibility result) with no sub-families.
        'c2_families': {'main': 1},
        'c2_section_pattern': r'\\section\*?\{[^}]*(Power analysis|Statistical Protocol)[^}]*\}',
        'c2_abstract_k_allowed': [1],
        'c3_concept': 'Impossibility Triangle',
        'c3_concept_token': r'\\textbf\{Impossibility Triangle\}|\bimpossibility triangle\b',
        'c3_formal': r'\\subsection\{The Impossibility Triangle\}',
        'c3_formal_secondary': None,
        'c4_self_cite_threshold': 0.30,
        'c4_self_cite_prefix': 'liu2026',
        'c4_max_self_cite_keys': 3,
        'c5_d_type': "Cohen's d",
        'c6_blacklist': ['paradigm', 'yield', 'reveal'],
        # C7: Paper 2 has 0 self-cites (single-author paper).
        # Allow more ceremonial cites since the related-work
        # section is short.
        'c7_max_ceremonial': 3,
        # C8: Paper 2 is theoretical (impossibility result).
        # No statistical tests, so no C8 effects to verify.
        'c8_claimed_effects': [],
        # C9: Paper 2 is theoretical; no figures with
        # keywords to verify.
        'c9_figure_keywords': [],
        # C10: Paper 2 makes a general "impossibility result"
        # claim, not a benchmark SOTA claim. No C10 consistency
        # checks to run.
        'c10_reproducibility_claims': [],
    },
    3: {
        # Paper 3 introduces the "Coupling-Noise Decomposition
        # (Theorem 2)". The decomposition writes the total
        # noise in a coupled system as the sum of two
        # components: coupling noise (from the interaction
        # between variables) and intrinsic noise (from each
        # variable's own variability). The C1 symbols are
        # the two noise components and the total.
        #
        # TODO: confirm the actual symbol names against that paper's main.tex. The names
        # below are plausible based on the C3 concept.
        'dir': RESEARCH_DIR / 'PAPER3_CONSOLIDATED',
        'c1_symbols': [
            {
                'name': r'$\sigma_C$ (coupling noise component)',
                'token': r'\\sigma_C\b|\\sigma_\{C\}',
                'definition': r'\\sigma_C.{0,80}=|coupling.{0,30}noise|noise.{0,30}coupling',
            },
            {
                'name': r'$\sigma_I$ (intrinsic noise component)',
                'token': r'\\sigma_I\b|\\sigma_\{I\}',
                'definition': r'\\sigma_I.{0,80}=|intrinsic.{0,30}noise|own.{0,30}variability',
            },
            {
                'name': r'$\sigma_T$ (total noise, $\sigma_T^2 = \sigma_C^2 + \sigma_I^2$)',
                'token': r'\\sigma_T\b|\\sigma_\{T\}',
                'definition': r'\\sigma_T.{0,80}=|total.{0,30}noise|noise.{0,30}decomposition',
            },
        ],
        # Paper 3 has 1 main family (the coupling-noise
        # decomposition theorem) and 2 sub-families
        # (the simulation experiments and the analytic
        # bound).
        'c2_families': {
            'main': 1,
            'simulation': 1,
            'analytic-bound': 1,
        },
        'c2_section_pattern': r'\\section\*?\{[^}]*(Power analysis|Statistical Protocol)[^}]*\}',
        'c2_abstract_k_allowed': [1],
        'c3_concept': 'Coupling-Noise Decomposition (Theorem 2)',
        'c3_concept_token': r'\\textbf\{Coupling.Noise\}|Coupling.Noise Decomposition',
        'c3_formal': r'CNR.{0,80}=|Coupling.Noise.{0,80}\$',
        'c3_formal_secondary': None,
        'c4_self_cite_threshold': 0.30,
        'c4_self_cite_prefix': 'liu2026',
        'c4_max_self_cite_keys': 3,
        'c5_d_type': "Cohen's d",
        'c6_blacklist': ['paradigm', 'yield', 'reveal'],
        # C7: Paper 3 has 0 self-cites.
        'c7_max_ceremonial': 3,
        # C8: Paper 3 is theoretical (Theorem 2 about
        # coupling-noise decomposition). No C8 effects to verify.
        'c8_claimed_effects': [],
        # C9: Paper 3 has 1-2 figures (theorem illustration,
        # decomposition diagram).
        'c9_figure_keywords': [
            {'fig_id': 'fig:decomposition', 'expected_keywords': ['decomposition', 'theorem']},
        ],
        # C10: Paper 3 is theoretical (Theorem 2 about
        # coupling-noise decomposition). No benchmark claims.
        'c10_reproducibility_claims': [],
    },
    4: {
        # Paper 4 introduces the "N-Sensitivity" metric: how
        # sensitive a result is to the sample size N. The
        # paper argues that many published findings have
        # artificially high N-sensitivity (i.e., the result
        # would not replicate with a different N). The C1
        # symbols are the metric and the threshold.
        #
        # TODO: confirm the actual symbol names against that paper's main.tex. The names
        # below are plausible based on the C3 concept.
        'dir': RESEARCH_DIR / 'PAPER4_CONSOLIDATED',
        'c1_symbols': [
            {
                'name': r'$S_N$ (N-sensitivity metric)',
                'token': r'\bS_N\b|\\mathbf\{S\}_N',
                'definition': r'S_N.{0,80}=|N.sensitivity|sample.size.{0,30}sensitivity',
            },
            {
                'name': r'$N_0$ (baseline sample size for N-sensitivity computation)',
                'token': r'\bN_0\b|\\mathbf\{N\}_0',
                'definition': r'N_0.{0,80}=|baseline.{0,30}sample|reference.{0,30}sample',
            },
            {
                'name': r'$\Delta_S$ (sensitivity threshold, paper-specific)',
                'token': r'\\Delta_S\b|\\Delta_\{S\}',
                'definition': r'\\Delta_S.{0,80}=|sensitivity.{0,30}threshold|threshold.{0,30}sensitivity',
            },
        ],
        # Paper 4 has 2 main families (the empirical study
        # and the analytic bound) with no sub-families.
        'c2_families': {
            'empirical': 1,
            'analytic-bound': 1,
        },
        'c2_section_pattern': r'\\section\*?\{[^}]*(Power analysis|Statistical Protocol)[^}]*\}',
        'c2_abstract_k_allowed': [1],
        'c3_concept': 'N-Sensitivity',
        'c3_concept_token': r'\\textbf\{N.Sensitivity\}|N.Sensitivity\b',
        'c3_formal': r'N.Sensitivity.{0,80}=|S_N.{0,80}=|N_0',
        'c3_formal_secondary': None,
        'c4_self_cite_threshold': 0.30,
        'c4_self_cite_prefix': 'liu2026',
        'c4_max_self_cite_keys': 3,
        'c5_d_type': "Cohen's d",
        'c6_blacklist': ['paradigm', 'yield', 'reveal'],
        # C7: Paper 4 has 0 self-cites.
        'c7_max_ceremonial': 3,
        # C8: Paper 4 has 1 main effect (S_N on empirical,
        # n=100, claimed d=0.4).
        'c8_claimed_effects': [
            {'name': 'S_N_empirical', 'd': 0.40, 'n1': 100, 'n2': 100, 'alpha': 0.05},
        ],
        # C9: Paper 4 has 2 figures (S_N distribution, N effect).
        'c9_figure_keywords': [
            {'fig_id': 'fig:S_N_distribution', 'expected_keywords': ['S_N', 'distribution', 'sensitivity']},
            {'fig_id': 'fig:N_effect', 'expected_keywords': ['N', 'effect', 'replication']},
        ],
        # C10: Paper 4 has 1 SOTA claim (S_N on the empirical
        # benchmark).
        'c10_reproducibility_claims': [
            {'type': 'claims_sota', 'dataset': 'N-Sensitivity benchmark', 'expected_section': 'code'},
        ],
    },
    5: {
        'dir': RESEARCH_DIR / 'PAPER5_CONSOLIDATED',
        'c1_symbols': [
            {
                'name': r'$\Gamma_{\mathrm{temporal}}$ (Wasserstein-1 bias-propagation metric)',
                'token': r'\\Gamma',
                'definition': r'\\Gamma_\{\\text\{temporal\}\}\s*=|Wasserstein',
            },
            {
                'name': 'contamination rate (fraction of stored outputs modified)',
                'token': r'contamination rate',
                'definition': r'fraction of stored outputs|proportion of stored|modified at the start',
            },
            {
                'name': 'length bias',
                'token': r'length bias',
                'definition': r'expansion by a factor|expansion factor|output expansion|alpha=1\.5',
            },
            {
                'name': 'authority bias',
                'token': r'authority bias',
                'definition': r'explicit source|source.attribution|"according to',
            },
        ],
        'c2_families': {
            'dose-response': 9,
            'cross-model': 6,
            'authority-bias': 3,
        },
        'c2_section_pattern': (
            r'\\section\*?\{[^}]*Power analysis[^}]*\}|'
            r'\\subsection\*?\{[^}]*Statistical Protocol[^}]*\}'
        ),
        'c2_abstract_k_allowed': [9],
        'c3_concept': 'crossover',
        'c3_concept_token': r'\\textbf\{crossover\}|\bcrossover\b',
        'c3_formal': r'crossover.{0,80}\\arg\\?min',
        'c3_formal_secondary': None,
        'c4_self_cite_threshold': 0.30,
        'c4_self_cite_prefix': 'liu2026',
        'c4_max_self_cite_keys': 1,  # Paper 5 retains only memorycontagion
        'c5_d_type': "Cohen's d",
        'c6_blacklist': ['paradigm', 'yield', 'reveal'],
        # C7: Paper 5 found 15 ceremonial citations in v0.1.2.
        # Allow 2 ceremonial (the default), 13+ are reported.
        'c7_max_ceremonial': 2,
        # C8: Paper 5 has 3 main effects (dose-response,
        # cross-model, authority-bias). Each is verifiable
        # against a results table.
        'c8_claimed_effects': [
            {'name': 'dose_response', 'd': 0.50, 'n1': 50, 'n2': 50, 'alpha': 0.05},
            {'name': 'cross_model', 'd': 0.40, 'n1': 30, 'n2': 30, 'alpha': 0.05},
            {'name': 'authority_bias', 'd': 0.60, 'n1': 20, 'n2': 20, 'alpha': 0.05},
        ],
        # C9: Paper 5 has 4 figures (architecture, results,
        # length-bias, authority-bias).
        'c9_figure_keywords': [
            {'fig_id': 'fig:memorycontagion_arch', 'expected_keywords': ['memorycontagion', 'architecture', 'spread']},
            {'fig_id': 'fig:length_bias_results', 'expected_keywords': ['length', 'bias', 'results']},
            {'fig_id': 'fig:authority_bias_results', 'expected_keywords': ['authority', 'bias', 'attribution']},
            {'fig_id': 'fig:cross_model_comparison', 'expected_keywords': ['cross-model', 'comparison', 'GPT-4']},
        ],
        # C10: Paper 5 makes a "best in class" claim on the
        # length-bias benchmark. The dataset is real (paper
        # authors curated it), so the consistency check applies.
        'c10_reproducibility_claims': [
            {'type': 'claims_sota', 'dataset': 'length-bias benchmark', 'expected_section': 'data'},
        ],
        # v0.5.0 whitelist: lock the plugin set to only
        # the example plugin (the only one we currently
        # ship). This makes the audit deterministic:
        # future installs of additional plugins cannot
        # silently change the audit output for Paper 5.
        'c11_plugins_enabled': ['flag-todo-markers'],
    },
}


# ---------------------------------------------------------------------------
# Substitution logic
# ---------------------------------------------------------------------------

def _format_c1_symbols(symbols: list[dict]) -> str:
    """Format the c1_symbols list as Python source."""
    if not symbols:
        return '    # (no symbols configured for this paper)\n    [],'
    lines = ['    [']
    for i, sym in enumerate(symbols):
        sep = ',' if i < len(symbols) - 1 else ','
        lines.append('        {')
        for k, v in sym.items():
            if isinstance(v, str):
                # Use repr() so the result is a Python string literal.
                # For raw r-strings the user is expected to have escaped
                # backslashes already.
                lines.append(f"            {k!r}: {v!r},")
            else:
                lines.append(f"            {k!r}: {v!r},")
        lines.append(f'        }}{sep}')
    lines.append('    ],')
    return '\n'.join(lines)


def _format_simple_value(value) -> str:
    """Format a value as a Python source literal.

    For strings that look like regex patterns (contain backslash escape
    sequences such as \\b, \\d, \\s, \\w, \\., \\{, \\}, etc.), emit them
    as raw string literals (r'...') so Python does not interpret the
    backslashes. For other strings, use repr() (which produces a normal
    string literal with appropriate escaping).
    """
    if isinstance(value, str):
        # Heuristic: any of these regex-only escape sequences implies
        # the user intended a raw regex string.
        regex_marker_re = re.compile(r'\\[bBdDsSwWnrtfv0]|\\\.|\\\{|\\\}')
        if regex_marker_re.search(value):
            # Use r-string literal. We must still escape any embedded
            # single-quote (rare in our configs).
            escaped = value.replace("'", r"\'")
            return f"r'{escaped}'"
        return repr(value)
    if value is None:
        return 'None'
    return repr(value)


def _format_c2_families(families: dict) -> str:
    if not families:
        return '    {},'
    items = ', '.join(f'{k!r}: {v!r}' for k, v in families.items())
    return f'    {{{items}}},'


def _format_c6_blacklist(words: list[str]) -> str:
    if not words:
        return '    [],'
    return '    ' + repr(words) + ','


def _format_c10_claims(claims: list) -> str:
    """Format the c10_reproducibility_claims list as Python source."""
    if not claims:
        return '    [],'
    lines = ['    [']
    for i, claim in enumerate(claims):
        sep = ',' if i < len(claims) - 1 else ','
        lines.append('        {')
        for k, v in claim.items():
            lines.append(f"            {k!r}: {v!r},")
        lines.append(f'        }}{sep}')
    lines.append('    ],')
    return '\n'.join(lines)


def _format_c8_claimed_effects(effects: list) -> str:
    """Format the c8_claimed_effects list as Python source."""
    if not effects:
        return '    [],'
    lines = ['    [']
    for i, eff in enumerate(effects):
        sep = ',' if i < len(effects) - 1 else ','
        lines.append('        {')
        for k, v in eff.items():
            lines.append(f"            {k!r}: {v!r},")
        lines.append(f'        }}{sep}')
    lines.append('    ],')
    return '\n'.join(lines)


def _format_c9_figure_keywords(figures: list) -> str:
    """Format the c9_figure_keywords list as Python source."""
    if not figures:
        return '    [],'
    lines = ['    [']
    for i, fig in enumerate(figures):
        sep = ',' if i < len(figures) - 1 else ','
        lines.append('        {')
        for k, v in fig.items():
            lines.append(f"            {k!r}: {v!r},")
        lines.append(f'        }}{sep}')
    lines.append('    ],')
    return '\n'.join(lines)


def substitute_verify(template: str, cfg: dict) -> str:
    """Substitute ROOT and CHECKS_CONFIG in the verify template."""
    out = template
    out = re.sub(
        r"ROOT\s*=\s*Path\('[^']*'\)",
        f"ROOT = Path('{cfg['dir'].as_posix()}')",
        out, count=1,
    )

    # Build a replacement for the entire CHECKS_CONFIG block
    parts = []
    parts.append('CHECKS_CONFIG: dict = {')
    parts.append("    'c1_symbols':")
    parts.append(_format_c1_symbols(cfg['c1_symbols']))
    parts.append('')
    parts.append("    'c2_families':")
    parts.append(_format_c2_families(cfg['c2_families']))
    parts.append("    'c2_section_pattern': " + _format_simple_value(cfg['c2_section_pattern']) + ',')
    parts.append("    'c2_abstract_k_allowed': " + _format_simple_value(cfg['c2_abstract_k_allowed']) + ',')
    parts.append('')
    parts.append("    'c3_concept': " + _format_simple_value(cfg['c3_concept']) + ',')
    parts.append("    'c3_concept_token': " + _format_simple_value(cfg['c3_concept_token']) + ',')
    parts.append("    'c3_formal': " + _format_simple_value(cfg['c3_formal']) + ',')
    parts.append("    'c3_formal_secondary': " + _format_simple_value(cfg.get('c3_formal_secondary')) + ',')
    parts.append('')
    parts.append("    'c4_self_cite_threshold': " + repr(cfg.get('c4_self_cite_threshold', 0.30)) + ',')
    parts.append("    'c4_self_cite_prefix': " + _format_simple_value(cfg.get('c4_self_cite_prefix', 'liu2026')) + ',')
    parts.append("    'c4_max_self_cite_keys': " + repr(cfg.get('c4_max_self_cite_keys', 3)) + ',')
    parts.append('')
    parts.append("    'c5_d_type': " + _format_simple_value(cfg.get('c5_d_type', "Cohen's d")) + ',')
    parts.append('')
    parts.append("    'c6_blacklist':")
    parts.append(_format_c6_blacklist(cfg.get('c6_blacklist', ['paradigm', 'yield', 'reveal'])))
    parts.append('')
    # C7 is on every built-in paper config. Leaving it out meant a fork from
    # this generator silently kept the template default.
    parts.append("    'c7_max_ceremonial': " + repr(cfg.get('c7_max_ceremonial', 2)) + ',')
    parts.append('')
    # C8 (added in v0.3.0): per-paper list of claimed effects
    # to verify. If empty/None, C8 is a no-op.
    parts.append("    'c8_claimed_effects':")
    parts.append(_format_c8_claimed_effects(cfg.get('c8_claimed_effects', [])))
    parts.append('')
    # C9 (added in v0.3.0): per-paper list of figure
    # expected keywords. If empty/None, sub-checks 1, 2, 4
    # still run; sub-check 3 (content) is skipped.
    parts.append("    'c9_figure_keywords':")
    parts.append(_format_c9_figure_keywords(cfg.get('c9_figure_keywords', [])))
    parts.append('')
    # C10 (added in v0.3.0): per-paper list of reproducibility
    # claims. If empty/None, only the availability + metadata
    # checks run; the consistency check is skipped.
    parts.append("    'c10_reproducibility_claims':")
    parts.append(_format_c10_claims(cfg.get('c10_reproducibility_claims', [])))
    parts.append('}')

    new_block = '\n'.join(parts)

    # Replace the entire CHECKS_CONFIG block. We use a small brace-matching
    # loop that ignores braces inside string literals (single- and
    # double-quoted) so that c2_section_pattern strings like
    # r'\\section\*?\{...Power analysis[^}]*\}|...' do not throw off
    # the count. We also use literal string replacement (str.slice) so
    # that backslashes in the replacement text are not interpreted as
    # regex backreferences (which would raise "bad escape" errors).
    marker = 'CHECKS_CONFIG: dict = {'
    start = out.find(marker)
    if start < 0:
        raise RuntimeError('CHECKS_CONFIG marker not found in template')

    # Walk forward, tracking depth. Skip characters inside string literals.
    depth = 0
    i = start
    in_str: str | None = None  # quote char if inside a string
    while i < len(out):
        c = out[i]
        if in_str is not None:
            if c == '\\' and i + 1 < len(out):
                # Skip escaped character (handles \\, \', \", \n, etc.)
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
    else:
        raise RuntimeError('CHECKS_CONFIG closing brace not found')
    if end < len(out) and out[end] == '\n':
        end += 1
    out = out[:start] + new_block + '\n' + out[end:]
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
                        help='Paper number to generate the verify script for')
    parser.add_argument('--list', action='store_true',
                        help='List all known paper configurations and exit')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be written, but make no changes')
    args = parser.parse_args()

    if args.list:
        print('Known verify configurations:')
        for n, cfg in sorted(PAPER_CONFIGS.items()):
            n_c1 = len(cfg['c1_symbols'])
            n_fam = len(cfg['c2_families'])
            print(f'  Paper {n}: c1_symbols={n_c1}, c2_families={n_fam}, '
                  f'c3="{cfg.get("c3_concept", "")}", '
                  f'c4_max_keys={cfg.get("c4_max_self_cite_keys", 3)}')
        return 0

    if args.paper is None:
        print('ERROR: must specify --paper N or --list', file=sys.stderr)
        return 2

    if args.paper not in PAPER_CONFIGS:
        print(f'ERROR: no config for paper {args.paper}', file=sys.stderr)
        print(f'       known papers: {sorted(PAPER_CONFIGS)}', file=sys.stderr)
        print('       add an entry to PAPER_CONFIGS in gen_verify_scripts.py', file=sys.stderr)
        return 2

    cfg = PAPER_CONFIGS[args.paper]
    print('=' * 72)
    print(f'Generating verify script for Paper {args.paper}')
    print('=' * 72)
    print(f'  Target dir:  {cfg["dir"]}')
    print(f'  c1_symbols:  {len(cfg["c1_symbols"])} rule(s)')
    print(f'  c2_families: {cfg["c2_families"]}')
    print(f'  c3_concept:  {cfg["c3_concept"]!r}')
    print(f'  c5_d_type:   {cfg.get("c5_d_type")!r}')
    print(f'  c6_blacklist: {cfg.get("c6_blacklist")}')
    print(f'  Mode: {"DRY-RUN" if args.dry_run else "APPLY"}')
    print()

    if not cfg['dir'].exists():
        print(f'ERROR: target dir does not exist: {cfg["dir"]}', file=sys.stderr)
        return 2

    tpl = TEMPLATE_DIR / '_verify_TEMPLATE.py'
    if not tpl.exists():
        print(f'ERROR: missing template {tpl}', file=sys.stderr)
        return 2

    out = substitute_verify(tpl.read_text(encoding='utf-8'), cfg)

    # Output file name: verify_p<N>.py
    target = cfg['dir'] / f'verify_p{args.paper}.py'
    write_output(target, out, args.dry_run)

    print()
    print('=' * 72)
    if args.dry_run:
        print('DRY-RUN: no files written.  Re-run without --dry-run to commit.')
    else:
        print(f'Done.  Next: cd {cfg["dir"]} && python verify_p{args.paper}.py')
    print('=' * 72)
    return 0


if __name__ == '__main__':
    sys.exit(main())