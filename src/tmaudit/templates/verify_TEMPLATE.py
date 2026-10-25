#!/usr/bin/env python3
"""_verify_TEMPLATE.py — generic config-driven 6-category TMLR audit.

This is the GENERIC TEMPLATE. To use:

    1. Copy this file to F:/Research/PAPER<N>_CONSOLIDATED/_verify_p<N>.py
    2. Edit the `ROOT` constant.
    3. Edit the `CHECKS_CONFIG` block to match the paper.

Or, run `python gen_verify_scripts.py --paper N` from
F:/Research/TEMPLATE/ to fork this template automatically.

The ten categories of checks are:

  C1  Abstract symbol definitions
      - For each entry in CHECKS_CONFIG['c1_symbols'], verify that the
        abstract contains an inline definitional phrase within a
        250-character window of the first mention.
  C2  Bonferroni scheme consistency
      - Verify that the abstract, body, and table notes are consistent
        with the families declared in CHECKS_CONFIG['c2_families'].
      - Optionally verify that a section matching
        CHECKS_CONFIG['c2_section_pattern'] exists.
  C3  Formalization of a key concept
      - Verify that a concept (declared in CHECKS_CONFIG['c3_concept'])
        has a formal definition (matching CHECKS_CONFIG['c3_formal'])
        before being used qualitatively.
  C4  Citation hygiene (generic)
      - Every \\cite{...} key in the manuscript must have a
        corresponding entry in the bibliography, read from refs.bib
        (@...{key,...}) or a compiled .bbl (\\bibitem[l]{key}). When
        neither source is present, C4 is reported as not applicable.
      - Self-cite rate must be below the threshold declared in
        CHECKS_CONFIG['c4_self_cite_threshold'].
  C5  Sample size and effect-size transparency (generic)
      - Every p-value reported in the abstract must be paired with n
        and a test name.
      - Every d=... in the abstract must be declared as "Cohen's d"
        (or whichever effect size type is set in CHECKS_CONFIG['c5_d_type']).
  C6  Blacklisted vocabulary (generic)
      - Every word in CHECKS_CONFIG['c6_blacklist'] is flagged for
        replacement.
  C7  Citation context (ceremonial vs engaged) (generic, v0.1.2)
      - For each \\cite{...} in main.tex, classify the citing
        sentence as "engaged" or "ceremonial". A ceremonial
        citation has no engage verb (show, demonstrate, extend,
        build on, ...), no comparison word (however, while, ...),
        and the citing sentence is < 30 words. The check is
        lenient by default: up to c7_max_ceremonial (default 2)
        ceremonial cites are silent; (N+1)+ are reported as
        MED severity.
  C8  Statistical claims (generic, v0.3.0)
      - Effect-size re-derivation and post-hoc power per declared
        claim; every significance claim must carry a p-value.
  C9  Figure captions (generic, v0.3.0)
      - Every figure needs a caption below its graphic, and every
        defined fig: label must be referenced somewhere.
  C10 Reproducibility (generic, v0.3.0)
      - Availability statement, its tense, and metadata
        (hyperparameters, seeds, hardware, library versions).

Exit codes:
    0 = no HIGH-severity findings
    1 = at least one HIGH-severity finding
    2 = operational error (no manuscript .tex found, or a check that
        crashed — a crashed check is not a passed check). A missing
        bibliography is NOT an operational error: C4 degrades to
        "not applicable" instead.
"""
from __future__ import annotations
import re
import sys
from collections import defaultdict
from pathlib import Path

# ============================================================================
# Configuration (only this block needs editing per paper)
# ============================================================================
ROOT = Path('F:/Research/PAPER1_CONSOLIDATED')
MAIN = ROOT / 'main.tex'
REFS = ROOT / 'refs.bib'

# Each entry in CHECKS_CONFIG controls one of the ten categories. The
# check functions below read from this dict, so per-paper changes happen
# entirely here — no code edits required.
#
# The factory default is an EMPTY dict. Paper-specific categories (C1,
# C2, C3, C6) report "not applicable" on an unconfigured document
# instead of firing someone else's configuration at it. The generic
# checks still run with their built-in defaults: C4 (missing cite
# keys), C5, C7, C8 sub-check 3 (significance claims), C9 sub-checks
# 1/2/4 (captions, placement, references), C10 sub-checks 1/3
# (availability, metadata).
#
# Schema (see gen_verify_scripts.py for canonical examples):
#   c1_symbols: list of dicts, one per symbol that must be defined in the
#               abstract. Each dict has:
#                 - 'name'         (str): human-readable label
#                 - 'token'        (str): the raw token to search for in the
#                                       abstract (e.g., r'\Gamma', 'CAF',
#                                       'E_T', 'TTRL')
#                 - 'definition'   (str): a regex that must match within
#                                       250 chars of the first mention.
#                 - 'window'       (int, optional): window size in chars
#                                       (default 250)
#
#   c2_families: dict {family_name: k}. The auditor checks that the
#                abstract's k value, if any, is in this set.
#   c2_section_pattern: regex that must match a \\section / \\subsection
#                       title declaring the statistical protocol. Use
#                       r'\\section\*?\{[^}]*Power analysis[^}]*\}|...
#                       to also accept star-form sections.
#   c2_abstract_k_allowed: list[int] of k values that are acceptable in
#                         the abstract. Usually this is the family-level k.
#
#   c3_concept: str label of the concept that must be formally defined
#               (e.g., "crossover", "Two Faces", "impossibility triangle").
#   c3_concept_token: regex matching the concept as it appears in
#                     \\textbf{...} or as a bare word.
#   c3_formal: regex that must appear before the first qualitative use
#              of the concept. For example, the formal definition of a
#              "crossover" is `crossover.{0,80}\\arg\\?min`.
#
#   c4_self_cite_threshold: float, default 0.30. Self-cite rate above
#                          this triggers a finding.
#   c4_self_cite_prefix:   str, default 'liu2026'. Cite key prefix used
#                          to detect self-cites.
#   c4_max_self_cite_keys: int, default 3. Maximum number of self-cite
#                          keys allowed (for method-foundation retention).
#
#   c5_d_type: str, default "Cohen's d". Effect-size type that must be
#              declared in the abstract alongside every d=... value.
#
#   c6_blacklist: list[str] of words to flag. Each word is matched with
#                 case-insensitive word boundaries.
# v0.5.1 (defect D1): this dict ships EMPTY. The previous factory
# default was pre-filled with one specific paper's configuration
# (a 'liu2026' self-cite prefix, TTRL symbol definitions, a "Power
# analysis" section requirement), which made the generic audit fire
# that paper's checks against any document it was pointed at.
# `gen_verify_scripts.py` / forge replaces this whole block with the
# per-paper configuration; the schema comments above describe the keys.
CHECKS_CONFIG: dict = {}
# ============================================================================


# Default inflection regexes (override per-word by adding to INFLECTIONS).
DEFAULT_INFLECTIONS = {
    'paradigm': r'\bparadigms?\b',
    'yield':    r'\byields?\b',
    'reveal':   r'\breveals?\b|\brev\b|\brevealed\b',
}


SEVERITY = {
    'C1': 'HIGH',
    'C2': 'HIGH',
    'C3': 'MEDIUM',
    'C4': 'MEDIUM',
    'C5': 'MEDIUM',
    'C6': 'LOW',
    'C7': 'MEDIUM',
    # C8 is variable: HIGH for d-mismatch, MED for power
    # issues. We default to MEDIUM.
    'C8': 'MEDIUM',
    # C9 is variable: HIGH for missing caption, MED for
    # placement/content/referenced. We default to MEDIUM.
    'C9': 'MEDIUM',
    # C10 is variable: HIGH for missing availability, MED for
    # consistency / future-tense, LOW for missing metadata.
    # We default to LOW since most C10 findings are LOW; the
    # function itself emits the per-finding severity in the
    # message.
    'C10': 'LOW',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def line_of(tex: str, pos: int) -> int:
    return tex.count('\n', 0, pos) + 1


def extract_abstract(tex: str) -> tuple[str, int] | None:
    """Return (abstract_text, abs_start_position) or None if no abstract."""
    m = re.search(r'\\begin\{abstract\}(.+?)\\end\{abstract\}', tex, re.DOTALL)
    if m is None:
        return None
    return m.group(1), m.start(1)


# ---------------------------------------------------------------------------
# C1: Abstract symbol definitions
# ---------------------------------------------------------------------------

def check_c1_abstract_definitions(tex: str) -> list[tuple[str, str, int]]:
    cfg_syms = CHECKS_CONFIG.get('c1_symbols', [])
    if not cfg_syms:
        return []

    abs_result = extract_abstract(tex)
    if abs_result is None:
        # v0.5.1 (defect D6): "no abstract" is an observation failure, not a
        # violation — it used to be reported as a HIGH finding.
        #
        # Raising here made main() exit 2 and label the *whole* audit crashed.
        # That is defensible for the author's own papers, where an abstract is
        # a precondition, but wrong for an external document: a missing
        # abstract says nothing about the other nine categories. Recorded as
        # an observation failure and returned as no findings — C1 could not
        # see, so it does not claim the paper passed C1 either.
        OBSERVATION_FAILURES['C1'] = (
            'no abstract environment found: C1 cannot be observed')
        return []
    abstract, abs_start = abs_result
    abs_line_start = line_of(tex, abs_start)

    findings: list[tuple[str, str, int]] = []
    for sym in cfg_syms:
        name = sym['name']
        token = sym['token']
        defn = sym['definition']
        window = sym.get('window', 250)
        m = re.search(token, abstract, re.IGNORECASE)
        if not m:
            continue  # symbol not in abstract — fine
        # First pass: definition within `window` chars of first mention.
        win_start = max(0, m.start() - window)
        win_end = min(len(abstract), m.end() + window)
        if re.search(defn, abstract[win_start:win_end], re.IGNORECASE | re.DOTALL):
            continue
        # Second pass: definition anywhere within the abstract (e.g., a
        # "Notation" block at the end of the abstract).
        if re.search(defn, abstract, re.IGNORECASE | re.DOTALL):
            continue
        # Third pass: definition in the first \\section{Introduction}
        # that immediately follows the abstract (a common style choice).
        intro_match = re.search(
            r'\\section\{Introduction\}(.+?)\\section\{',
            tex, re.DOTALL,
        )
        if intro_match and re.search(
            defn, intro_match.group(1), re.IGNORECASE | re.DOTALL,
        ):
            continue
        line_no = abs_line_start + abstract[:m.start()].count('\n')
        findings.append((
            'C1',
            f'{name} appears in abstract without inline definition. '
            f'Reviewer §3 #1.',
            line_no,
        ))
        break  # one finding per abstract is enough

    return findings


# ---------------------------------------------------------------------------
# C2: Bonferroni scheme consistency
# ---------------------------------------------------------------------------

def check_c2_bonferroni_consistency(tex: str) -> list[tuple[str, str, int]]:
    findings: list[tuple[str, str, int]] = []

    # get() with empty defaults so a direct call (bypassing main()'s
    # not-applicable gate) degrades to "no config, nothing to check"
    # instead of KeyError'ing on the factory-default config.
    families = CHECKS_CONFIG.get('c2_families', {})
    section_pat = CHECKS_CONFIG.get('c2_section_pattern')
    if not families:
        return findings
    abstract_k_allowed = CHECKS_CONFIG.get('c2_abstract_k_allowed',
                                           sorted(set(families.values())))

    # Check whether the declared section exists
    if section_pat and not re.search(section_pat, tex):
        findings.append((
            'C2',
            'No Power analysis section declaring Bonferroni k found. '
            'Reviewer §3 #4.',
            -1,
        ))

    # Check the abstract for k=N mention
    abs_result = extract_abstract(tex)
    if abs_result:
        abstract, abs_start = abs_result
        abstract_k = re.search(r'Bonferroni[^.]*?k\s*=\s*(\d+)', abstract)
        if abstract_k:
            k_val = int(abstract_k.group(1))
            if k_val not in abstract_k_allowed:
                abs_line_start = line_of(tex, abs_start)
                line_in_abs = abstract[:abstract_k.start()].count('\n')
                findings.append((
                    'C2',
                    f'Abstract quotes Bonferroni k={k_val} but the '
                    f'authoritative scheme has k values '
                    f'{sorted(set(families.values()))}. The abstract must '
                    f'quote the family-level correction; otherwise readers '
                    f'are misled. Reviewer §4 #1.',
                    abs_line_start + line_in_abs,
                ))

    return findings


# ---------------------------------------------------------------------------
# C3: Formalization of a key concept
# ---------------------------------------------------------------------------

def check_c3_formalization(tex: str) -> list[tuple[str, str, int]]:
    findings: list[tuple[str, str, int]] = []

    concept = CHECKS_CONFIG.get('c3_concept')
    concept_token = CHECKS_CONFIG.get('c3_concept_token')
    formal_pat = CHECKS_CONFIG.get('c3_formal')
    formal_secondary = CHECKS_CONFIG.get('c3_formal_secondary')

    if not concept_token or not formal_pat:
        return findings

    m = re.search(concept_token, tex)
    if not m:
        return findings
    first_line = line_of(tex, m.start())

    if not re.search(formal_pat, tex, re.IGNORECASE | re.DOTALL):
        findings.append((
            'C3',
            f'"{concept}" is used but no formal definition matching '
            f'{formal_pat!r} is given. Reviewer §3 #2.',
            first_line,
        ))

    if formal_secondary and not re.search(formal_secondary, tex,
                                          re.IGNORECASE | re.DOTALL):
        findings.append((
            'C3',
            f'"{concept}" second-half formal definition matching '
            f'{formal_secondary!r} not found. Reviewer §3 #2.',
            first_line,
        ))

    return findings


# ---------------------------------------------------------------------------
# C4: Citation hygiene (generic)
# ---------------------------------------------------------------------------

# A BibTeX entry key. The key may sit on its own line after the entry
# type, so whitespace (including newlines) is allowed around it:
#
#     @article{key,          and        @article{
#         author = {...},                   somekey2024,
#     }                                     author = {...},
#                                      }
#
# The pre-v0.5.1 pattern `@\w+\{([^,]+),` swallowed whitespace and
# newlines into the captured key whenever the key sat on its own line,
# so cite keys that existed in refs.bib were reported as missing.
# (Defect D4, found by auditing this tool against 25 real arXiv LaTeX
# sources; see case-studies/arxiv-corpus/.)
_BIB_KEY_RE = re.compile(r'@\w+\{\s*([^,\s]+)\s*,')

# A \bibitem key from a compiled .bbl, e.g. \bibitem[Smith et al.(2020)]{smith2020}
# or \bibitem{smith2020}. arXiv source tarballs ship the .bbl and usually NOT
# the .bib, so a C4 that only understands BibTeX reports every cite key as
# missing on exactly the papers most likely to be audited by a stranger.
#
# The optional label can wrap across lines (natbib) and can itself contain
# brackets ([see [Smith 2020]]), so it cannot be matched with [^\]]* alone.
_BBL_KEY_RE = re.compile(
    r'\\bibitem\s*(?:\[(?:[^\]\[]|\[[^\]]*\])*\])?\s*\{\s*([^}\s]+)\s*\}',
    re.DOTALL,
)


def _bib_keys(bib: str) -> set[str]:
    """Keys declared by a bibliography file.

    Accepts both formats because both arrive in practice: a .bib from an
    author's project, a .bbl from an arXiv tarball. A file that contains
    neither yields the empty set, which C4 reports as "every key missing"
    rather than silently passing.
    """
    return set(_BIB_KEY_RE.findall(bib)) | set(_BBL_KEY_RE.findall(bib))

def check_c4_citation_hygiene(
    tex: str, bib: str | None,
) -> list[tuple[str, str, int]]:
    findings: list[tuple[str, str, int]] = []

    cite_keys: list[str] = []
    for m in re.finditer(r'\\cite[a-zA-Z]*\{([^}]+)\}', tex):
        for k in m.group(1).split(','):
            k = k.strip()
            if k and not any(c in k for c in '$&'):
                cite_keys.append(k)

    cited_keys = set(cite_keys)

    # The missing-key sub-check needs a bibliography to compare against.
    # `bib` is None when the paper ships neither a .bib nor a .bbl; main()
    # reports C4 as not applicable in that case instead of calling us, but
    # we still tolerate None so a direct call degrades to the self-cite
    # sub-check rather than raising.
    if bib is not None:
        missing = cited_keys - _bib_keys(bib)
        if missing:
            first_missing_line = -1
            for k in sorted(missing):
                m = re.search(
                    r'\\cite[a-zA-Z]*\{[^}]*\b' + re.escape(k) + r'\b', tex)
                if m:
                    ln = line_of(tex, m.start())
                    if first_missing_line < 0 or ln < first_missing_line:
                        first_missing_line = ln
            findings.append((
                'C4',
                f'{len(missing)} cite key(s) in the manuscript missing from '
                f'the bibliography (.bib/.bbl): '
                f'{sorted(missing)[:5]}{"..." if len(missing) > 5 else ""}',
                first_missing_line,
            ))

    # Self-citation hygiene. Needs c4_self_cite_prefix: without it the
    # check cannot know what a self-cite looks like, so this sub-check
    # stays silent (the factory-default config has no prefix).
    threshold = CHECKS_CONFIG.get('c4_self_cite_threshold', 0.30)
    prefix = CHECKS_CONFIG.get('c4_self_cite_prefix', '')
    max_keys = CHECKS_CONFIG.get('c4_max_self_cite_keys', 3)
    self_cites = sorted(k for k in cited_keys
                        if prefix and k.lower().startswith(prefix))
    if self_cites:
        rate = len(self_cites) / len(cited_keys) if cited_keys else 0
        if len(self_cites) > max_keys or rate >= threshold:
            findings.append((
                'C4',
                f'Self-cite keys present: {self_cites} '
                f'({len(self_cites)}/{len(cited_keys)} = {rate:.1%}). '
                f'Target: <{threshold:.0%} key-level; max {max_keys} keys '
                f'for method-foundation retention.',
                -1,
            ))

    return findings


# ---------------------------------------------------------------------------
# C5: Sample size and effect-size transparency (generic)
# ---------------------------------------------------------------------------

def check_c5_sample_size_and_test(tex: str) -> list[tuple[str, str, int]]:
    findings: list[tuple[str, str, int]] = []

    abs_result = extract_abstract(tex)
    if abs_result is None:
        return findings
    abstract, abs_start = abs_result
    abs_line_start = line_of(tex, abs_start)

    # Helper: where do n, N, and test names appear?  We accept three
    # sources: (a) within 250 chars of the p-value in the abstract,
    # (b) anywhere else in the abstract (Notation block at end), and
    # (c) in the first \\section{Introduction} that immediately follows.
    intro_match = re.search(
        r'\\section\{Introduction\}(.+?)\\section\{', tex, re.DOTALL,
    )
    intro_section = intro_match.group(1) if intro_match else ''

    def _has_n_and_test(window: str) -> tuple[bool, bool]:
        has_n = bool(re.search(
            r'n\s*=\s*\d+|N\s*=\s*\d+|seeds?|conditions?',
            window, re.IGNORECASE,
        ))
        # Note: the test-name pattern intentionally allows arbitrary
        # non-letter characters between "paired" and "t", between "t"
        # and "test", and uses "test[s]?" to allow "tests" plural. This
        # matches "paired $t$-test", "paired $t$-tests", "paired\\s+t-test",
        # "paired t-tests", etc.
        has_test = bool(re.search(
            r'(Wilcoxon|'
            r'paired[^a-zA-Z]{0,8}t[^a-zA-Z]{0,3}test|'
            r'\bt[^a-zA-Z]{0,3}test|'
            r'Mann.Whitney|permutation)',
            window, re.IGNORECASE,
        ))
        return has_n, has_test

    # p-values in abstract
    p_patterns = (
        re.compile(r'p\s*<\s*0\.0+\d+'),
        re.compile(r'p_\\text\{adj\}|p\\text\{adj\}'),
    )
    for pat in p_patterns:
        for m in pat.finditer(abstract):
            line_in_abs = abstract[:m.start()].count('\n')
            line_no = abs_line_start + line_in_abs
            win_start = max(0, m.start() - 250)
            win_end = min(len(abstract), m.end() + 50)
            has_n, has_test = _has_n_and_test(abstract[win_start:win_end])
            if not (has_n and has_test):
                # Second pass: check the entire abstract.
                has_n_b, has_test_b = _has_n_and_test(abstract)
                if has_n_b:
                    has_n = True
                if has_test_b:
                    has_test = True
            if not (has_n and has_test) and intro_section:
                # Third pass: check the intro section.
                has_n_i, has_test_i = _has_n_and_test(intro_section)
                if has_n_i:
                    has_n = True
                if has_test_i:
                    has_test = True
            if not (has_n and has_test):
                missing = []
                if not has_n:
                    missing.append('n (sample size) or seeds/conditions qualifier')
                if not has_test:
                    missing.append('test name')
                findings.append((
                    'C5',
                    f'Reported p-value at abstract line {line_no} is missing '
                    f'{", ".join(missing)}. Reviewer §4 #1.',
                    line_no,
                ))

    # d= in abstract
    d_type = CHECKS_CONFIG.get('c5_d_type', "Cohen's d")
    d_pattern = re.compile(r'd\s*=\s*[\d.]+')
    for m in d_pattern.finditer(abstract):
        line_in_abs = abstract[:m.start()].count('\n')
        line_no = abs_line_start + line_in_abs
        win_start = max(0, m.start() - 150)
        win_end = min(len(abstract), m.end() + 50)
        if re.search(re.escape(d_type.split()[0]),
                     abstract[win_start:win_end], re.IGNORECASE):
            continue
        if re.search(re.escape(d_type.split()[0]), abstract, re.IGNORECASE):
            continue
        if intro_section and re.search(
            re.escape(d_type.split()[0]), intro_section, re.IGNORECASE,
        ):
            continue
        findings.append((
            'C5',
            f'Effect size d=... at abstract line {line_no} does not '
            f'explicitly declare "{d_type}". Reviewer §4 #1.',
            line_no,
        ))

    return findings


# ---------------------------------------------------------------------------
# C6: Blacklisted vocabulary (generic)
# ---------------------------------------------------------------------------

def check_c6_blacklist(tex: str) -> list[tuple[str, str, int]]:
    findings: list[tuple[str, str, int]] = []
    counts: dict[str, int] = defaultdict(int)
    samples: dict[str, list[tuple[int, str]]] = defaultdict(list)

    # Minimum occurrences before a blacklist word is reported.
    # 1-2 occurrences of "yield" / "reveal" is common in
    # idiomatic technical English ("yields a value of X")
    # and does not indicate vague writing. 3+ is the
    # threshold for "this word is being over-used to avoid
    # saying something specific".
    min_count: int = 3

    blacklist = CHECKS_CONFIG.get('c6_blacklist', [])
    for word in blacklist:
        pattern = DEFAULT_INFLECTIONS.get(word, rf'\b{word}\b')
        for m in re.finditer(pattern, tex, re.IGNORECASE):
            counts[word] += 1
            if len(samples[word]) < 3:
                ln = line_of(tex, m.start())
                samples[word].append((ln, word))

    for word, n in sorted(counts.items()):
        if n < min_count:
            continue  # 1-2 occurrences are OK
        first_line = samples[word][0][0] if samples[word] else -1
        findings.append((
            'C6',
            f'Blacklist word "{word}" appears {n}x in main.tex '
            f'(e.g., line {first_line}). Reviewer §5 #5.',
            first_line,
        ))

    return findings


# ---------------------------------------------------------------------------
# C7: Citation context (ceremonial vs engaged)
# ---------------------------------------------------------------------------
#
# A citation is "ceremonial" if it appears in the text but the
# citing sentence does not actually engage with the cited work.
# Reviewers notice this and dock the paper for it. The check
# detects citations whose citing sentence has no engagement
# signal (no engage verb, no comparison word, short sentence).
#
# Engagement signals (a sentence is "engaged" if ANY of these hold):
#   1. contains an engage verb (show, demonstrate, extend, ...)
#   2. contains a comparison word (however, in contrast, while, ...)
#   3. is 30+ words long (elaboration = engagement by length)
#
# Per-paper threshold (c7_max_ceremonial, default 2):
#   0 = strict (every ceremonial cite flagged)
#   1 = one ceremonial OK, two+ flagged
#   2 = up to two ceremonial OK, three+ flagged
#
# Severity: MEDIUM (stylistic, not correctness).
# ---------------------------------------------------------------------------

# Engagement signals (lowercase, matched as substrings).
_C7_ENGAGE_VERBS = (
    'show', 'shows', 'showed', 'demonstrate', 'demonstrates',
    'demonstrated', 'extend', 'extends', 'extended',
    'build on', 'builds on', 'built on', 'follow', 'follows',
    'followed', 'use', 'uses', 'used', 'apply', 'applies',
    'applied', 'compare', 'compares', 'compared',
    'improve', 'improves', 'improved', 'outperform',
    'outperforms', 'outperformed', 'validate', 'validates',
    'validated', 'verify', 'verifies', 'verified',
    'propose', 'proposes', 'proposed', 'argue', 'argues',
    'argued', 'claim', 'claims', 'claimed',
    'find', 'finds', 'found', 'observe', 'observes', 'observed',
    'measure', 'measures', 'measured', 'report', 'reports',
    'reported', 'confirm', 'confirms', 'confirmed',
    'exploit', 'exploits', 'exploited',
    'leverage', 'leverages', 'leveraged',
    'utilize', 'utilizes', 'utilized',
    'adopt', 'adopts', 'adopted',
    'generalize', 'generalizes', 'generalized',
    'specialize', 'specializes', 'specialized',
    'reduce', 'reduces', 'reduced',
    'combine', 'combines', 'combined',
    'investigate', 'investigates', 'investigated',
    'analyze', 'analyzes', 'analyzed', 'analysis',
    'examine', 'examines', 'examined',
    'introduce', 'introduces', 'introduced',
    'present', 'presents', 'presented',
    'derive', 'derives', 'derived',
    'compute', 'computes', 'computed',
)

_C7_COMPARISON_WORDS = (
    'however', 'in contrast', 'unlike', 'while',
    'although', 'whereas', 'but ', 'conversely',
    'on the other hand', 'nevertheless', 'nonetheless',
)

_C7_MIN_CITED_SENTENCE_WORDS = 30


def _c7_extract_sentence(tex: str, pos: int) -> str:
    r"""Extract the sentence containing position ``pos`` in ``tex``.

    A "sentence" is the text between the nearest sentence-end
    punctuation (`. `, `! `, `? `, `.\n`, `!\\n`, `?\\n`) before
    pos and the nearest one after pos. Periods that are part of
    common abbreviations (e.g., "et al.", "e.g.", "i.e.") are
    NOT treated as sentence boundaries.

    To handle the common LaTeX pattern where the cite is at the
    END of a sentence (after the engagement verb), the function
    returns up to TWO sentences: the current sentence plus the
    previous one. This way, a sentence like

        We extend Smith et al. \cite{smith2020} by ...

    is correctly identified as engaged (because "extend" is in
    the previous sentence).
    """
    sentence_end_re = re.compile(r'[.!?](?:\s|\n)')

    # Find all sentence-end positions.
    ends = [m.end() for m in sentence_end_re.finditer(tex)]

    # The end of the current sentence is the smallest end > pos.
    end_idx = None
    for i, e in enumerate(ends):
        if e > pos:
            end_idx = i
            break
    if end_idx is None:
        end = len(tex)
    else:
        end = ends[end_idx]

    # The start of the current sentence is the largest end <= pos.
    # If end_idx is 0, the start is 0. Otherwise it's ends[end_idx - 1].
    if end_idx is None or end_idx == 0:
        start = 0
        # No previous sentence.
        return tex[start:end]

    # Otherwise, start at the previous sentence boundary.
    start = ends[end_idx - 1]

    return tex[start:end]


def _c7_is_engaged(sentence: str) -> bool:
    """True if ``sentence`` engages with the cited work.

    Engagement is any of:
      1. an engage verb (substring match, case-insensitive)
      2. a comparison word (substring match, case-insensitive)
      3. sentence is 30+ words long (elaboration heuristic)
    """
    s = sentence.lower()
    for verb in _C7_ENGAGE_VERBS:
        if verb in s:
            return True
    for comp in _C7_COMPARISON_WORDS:
        if comp in s:
            return True
    if len(s.split()) >= _C7_MIN_CITED_SENTENCE_WORDS:
        return True
    return False


def check_c7_citation_context(
    tex: str,
    c7_max_ceremonial: int = 2,
    c7_llm_budget: int = 0,
) -> list[tuple[str, str, int]]:
    """C7: detect ceremonial citations (cited but not engaged with).

    A citation is "ceremonial" if the citing sentence does not
    engage with the cited work (no engage verb, no comparison
    word, short sentence). The check is **lenient** by default:
    1-2 ceremonial cites are OK; only 3+ ceremonial cites
    produce a finding. Set c7_max_ceremonial=0 for strict mode
    (every ceremonial cite is flagged).

    The optional `c7_llm_budget` parameter enables an LLM-based
    second opinion for **borderline** ceremonial cites (citing
    sentences that are 20-30 words long). When the LLM
    says "engaged", the cite is demoted (removed from the
    ceremonial set). When it says "ceremonial", the cite
    is confirmed. The LLM fallback is opt-in: set
    c7_llm_budget > 0 AND the TMAUDIT_LLM_ENDPOINT and
    TMAUDIT_LLM_API_KEY env vars to enable. See
    `src/tmaudit/llm_fallback.py` for details.

    Returns:
        0 or 1 finding of the form:
            ('C7', 'MED: <N> ceremonial citation(s) ...', first_line)
        The finding message includes the threshold, the count of
        ceremonial cites, and the first 5 keys (sorted).

    Acceptance criteria:
      - Per-cite classification (engaged vs ceremonial) is
        correct (see tests/test_c7_citation_context.py).
      - Per-paper threshold (c7_max_ceremonial) is respected.
      - All cite variants (\\cite, \\citep, \\citet) are detected.
      - Multi-key cites (\\cite{a,b,c}) are counted per key.
      - Unique keys are counted, not occurrences.
    """
    findings: list[tuple[str, str, int]] = []

    # The threshold is taken from the function argument (caller
    # decides). The per-paper CHECKS_CONFIG['c7_max_ceremonial'] is
    # NOT used here because it would override the function arg,
    # which the unit tests rely on. The driver (main) is
    # responsible for reading CHECKS_CONFIG and passing it as the
    # function arg.

    # 1. Find all \cite{...} matches and classify each citing sentence.
    ceremonial_keys: dict[str, int] = {}  # key -> first line
    all_cited_keys: set[str] = set()

    for m in re.finditer(r'\\cite[a-zA-Z]*\{([^}]+)\}', tex):
        for k in m.group(1).split(','):
            k = k.strip()
            if not k or any(c in k for c in '$&'):
                continue
            all_cited_keys.add(k)
            # Extract the citing sentence.
            sentence = _c7_extract_sentence(tex, m.start())
            if not _c7_is_engaged(sentence):
                ln = line_of(tex, m.start())
                # Count unique keys, not occurrences.
                if k not in ceremonial_keys:
                    ceremonial_keys[k] = ln

    # 1b. (v0.2.0) Optional LLM-based second opinion for
    # BORDERLINE ceremonial cites. A sentence is "borderline"
    # if it's 20-30 words long and the heuristic marked it
    # as ceremonial. For these cases, the heuristic is
    # most likely to be wrong, so we ask an LLM for
    # confirmation.
    #
    # The fallback is opt-in: it makes zero LLM calls unless
    # the user has set TMAUDIT_LLM_* env vars and the driver
    # has passed c7_llm_budget > 0.
    if c7_llm_budget > 0:
        try:
            from .. import llm_fallback as _llm
            fb = _llm.LLMFallback(budget=c7_llm_budget)
            if fb.is_enabled():
                # Collect borderline cites with their sentences.
                # We need to re-extract the sentence for each
                # ceremonial cite.
                borderline_to_recheck: list[str] = []
                for k, ln in ceremonial_keys.items():
                    # Find a cite with this key (use first match)
                    for m2 in re.finditer(
                        r'\\cite[a-zA-Z]*\{[^}]*\b' + re.escape(k) + r'\b[^}]*\}',
                        tex,
                    ):
                        sentence = _c7_extract_sentence(tex, m2.start())
                        if _llm.is_borderline(sentence):
                            borderline_to_recheck.append((k, sentence))
                        break  # only first match per key
                # Re-check each borderline cite
                for k, sentence in borderline_to_recheck:
                    try:
                        result = fb.classify(sentence)
                    except _llm.LLMBudgetExceeded:
                        break  # out of budget
                    if result is not None and result.engaged:
                        # LLM says engaged: demote (remove from ceremonial).
                        del ceremonial_keys[k]
        except ImportError:
            pass  # llm_fallback module not available

    # 2. Report per-ceremonial-cite findings, but only if count
    # exceeds the threshold. Up to `c7_max_ceremonial` ceremonial
    # cites are silently OK (default 2); (N+1)+ ceremonial cites
    # each get a per-cite finding.
    n_ceremonial = len(ceremonial_keys)
    if n_ceremonial > c7_max_ceremonial:
        # Per-cite findings (sorted by line, then key for stability).
        sorted_keys = sorted(
            ceremonial_keys.items(), key=lambda kv: (kv[1], kv[0])
        )
        # Only report the (N+1)+ ceremonial cites that exceed
        # the threshold. The first N are silent.
        excess = sorted_keys[c7_max_ceremonial:]
        for k, ln in excess:
            findings.append((
                'C7',
                f'MED: citation {k!r} at line {ln} is ceremonial '
                f'(citing sentence does not engage with the cited '
                f'work: no engage verb, no comparison, no '
                f'elaboration >= {_C7_MIN_CITED_SENTENCE_WORDS} '
                f'words). {n_ceremonial} ceremonial cite(s) total '
                f'(threshold: {c7_max_ceremonial}). Reviewer §5 #6.',
                ln,
            ))

    return findings


# ---------------------------------------------------------------------------
# C10: Reproducibility (added in v0.3.0)
# ---------------------------------------------------------------------------
#
# A paper's reproducibility is judged on 3 sub-categories:
#   1. Availability statement: does the paper say where the
#      code/data can be obtained?
#   2. Statement consistency: if the paper claims "we achieve
#      SOTA on dataset X" but the availability statement says
#      "we do not release", that's a real reviewer concern.
#   3. Reproducibility metadata: hyperparameters, random seed,
#      hardware, library version.
#
# Severity:
#   HIGH: no availability statement at all.
#   MED:  consistency issue or future-tense release.
#   LOW:  one or more metadata categories missing.
#
# The check is opt-in via the per-paper c10_reproducibility_claims
# config. If the config is empty/None, only the availability
# and metadata checks run (the consistency check is skipped).
# ---------------------------------------------------------------------------

# Regex patterns for the availability statement.
_C10_AVAILABILITY_SECTION_RE = re.compile(
    r'\\section\*?\{[^}]*Availability[^}]*\}',
    re.IGNORECASE,
)
# URLs pointing to known code/data hosting sites.
_C10_AVAILABILITY_URL_RES = [
    re.compile(r'github\.com/[^\s\)\}\]]+', re.IGNORECASE),
    re.compile(r'gitlab\.com/[^\s\)\}\]]+', re.IGNORECASE),
    re.compile(r'huggingface\.co/[^\s\)\}\]]+', re.IGNORECASE),
    re.compile(r'doi\.org/[^\s\)\}\]]+', re.IGNORECASE),
    re.compile(r'dx\.doi\.org/[^\s\)\}\]]+', re.IGNORECASE),
    re.compile(r'zenodo\.org/[^\s\)\}\]]+', re.IGNORECASE),
    re.compile(r'anonymous\.4open\.science/[^\s\)\}\]]+', re.IGNORECASE),
    re.compile(r'openreview\.net/[^\s\)\}\]]+', re.IGNORECASE),
]
# Phrases indicating a release statement.
_C10_AVAILABILITY_PHRASE_RES = [
    re.compile(r'code\s+is\s+available\s+at', re.IGNORECASE),
    re.compile(r'data\s+is\s+available\s+at', re.IGNORECASE),
    re.compile(r'source\s+code\s+is\s+released', re.IGNORECASE),
    re.compile(r'we\s+release\s+', re.IGNORECASE),
    re.compile(r'we\s+make\s+available', re.IGNORECASE),
    re.compile(r'publicly\s+available', re.IGNORECASE),
    re.compile(r'open[\s\-]source', re.IGNORECASE),
]
# Phrases indicating NO release (used for consistency check).
_C10_NO_RELEASE_PHRASE_RES = [
    re.compile(r'we\s+do\s+not\s+release', re.IGNORECASE),
    re.compile(r'will\s+not\s+release', re.IGNORECASE),
    re.compile(r'not\s+publicly\s+available', re.IGNORECASE),
    re.compile(r'proprietary\s+restrictions', re.IGNORECASE),
    re.compile(r'cannot\s+be\s+released', re.IGNORECASE),
]
# Phrases indicating future-tense release.
_C10_FUTURE_TENSE_RES = [
    re.compile(r'we\s+will\s+release', re.IGNORECASE),
    re.compile(r'we\s+plan\s+to\s+release', re.IGNORECASE),
    re.compile(r'will\s+be\s+released', re.IGNORECASE),
    re.compile(r'upon\s+(?:paper\s+)?acceptance', re.IGNORECASE),
]

# Reproducibility metadata patterns.
# Each is a (pattern, label) tuple. The label is used in
# the LOW finding message.
_C10_HYPERPARAM_PATTERNS = [
    re.compile(r'\blearning[\s_]rate\b', re.IGNORECASE),
    re.compile(r'\bbatch[\s_]size\b', re.IGNORECASE),
    re.compile(r'\boptimizer\b', re.IGNORECASE),
    re.compile(r'\bepochs?\b', re.IGNORECASE),
    re.compile(r'\blearning[\s_]rate[\s=]+\d', re.IGNORECASE),
]
_C10_SEED_PATTERNS = [
    re.compile(r'\brandom[\s_]seed\b', re.IGNORECASE),
    re.compile(r'\bseed[\s=]+\d', re.IGNORECASE),
    re.compile(r'torch\.manual_seed', re.IGNORECASE),
    re.compile(r'np\.random\.seed', re.IGNORECASE),
    re.compile(r'\bset[\s_]seed\(', re.IGNORECASE),
]
_C10_HARDWARE_PATTERNS = [
    re.compile(r'\bGPU\b'),
    re.compile(r'\bRTX[\s\-]?\d{4}', re.IGNORECASE),
    re.compile(r'\bA\d{2,4}\b'),  # A100, A1000, etc.
    re.compile(r'\bV\d{2,4}\b'),  # V100, V1000, etc.
    re.compile(r'\bT\d{1,2}\b'),   # T4, T40, etc.
    re.compile(r'\bTesla\s+[A-Z]?\d+', re.IGNORECASE),
    re.compile(r'\bH\d{2}\b'),     # H100, H200
    re.compile(r'\bnvidia[\s\-]?tesla\b', re.IGNORECASE),
    re.compile(r'\bcuda\b', re.IGNORECASE),
]
_C10_LIBRARY_VERSION_PATTERNS = [
    re.compile(r'PyTorch\s+\d', re.IGNORECASE),
    re.compile(r'TensorFlow\s+\d', re.IGNORECASE),
    re.compile(r'transformers\s+\d', re.IGNORECASE),
    re.compile(r'pytorch\s+\d', re.IGNORECASE),
    re.compile(r'tensorflow\s+\d', re.IGNORECASE),
    re.compile(r'scikit[\s\-]learn\s+\d', re.IGNORECASE),
    re.compile(r'pandas\s+\d', re.IGNORECASE),
    re.compile(r'numpy\s+\d', re.IGNORECASE),
    re.compile(r'CUDA\s+\d', re.IGNORECASE),
]


def _c10_has_availability_statement(tex: str) -> bool:
    """Return True if tex contains any of the availability patterns."""
    if _C10_AVAILABILITY_SECTION_RE.search(tex):
        return True
    for pat in _C10_AVAILABILITY_URL_RES:
        if pat.search(tex):
            return True
    for pat in _C10_AVAILABILITY_PHRASE_RES:
        if pat.search(tex):
            return True
    return False


def _c10_has_no_release_phrase(tex: str) -> bool:
    """Return True if tex says 'we do not release' (or similar)."""
    for pat in _C10_NO_RELEASE_PHRASE_RES:
        if pat.search(tex):
            return True
    return False


def _c10_has_future_tense_release(tex: str) -> bool:
    """Return True if tex says 'we will release' (or similar)."""
    for pat in _C10_FUTURE_TENSE_RES:
        if pat.search(tex):
            return True
    return False


def _c10_has_metadata(pattern_list, tex: str) -> bool:
    """Return True if any pattern in the list matches in tex."""
    for pat in pattern_list:
        if pat.search(tex):
            return True
    return False


def check_c10_reproducibility(
    tex: str,
    c10_reproducibility_claims: list = None,
) -> list[tuple[str, str, int]]:
    """C10: detect missing or inconsistent reproducibility info.

    Sub-check 1: Availability statement
      - If no \\section{...Availability...}, no GitHub/GitLab/
        Zenodo/anonymous URL, and no "code is available" phrase:
        emit HIGH finding.
      - If a future-tense release ("we will release",
        "upon acceptance"): emit MED finding (the release is
        conditional, not a real release).

    Sub-check 2: Statement consistency
      - For each entry in c10_reproducibility_claims:
        - If the body makes a "SOTA" or "state-of-the-art" claim
          and the availability statement says "we do not release":
          emit MED finding (inconsistency).
      - This sub-check is SKIPPED if c10_reproducibility_claims
        is None or empty.

    Sub-check 3: Reproducibility metadata
      - For each missing category (hyperparameters, random seed,
        hardware, library version): emit LOW finding.

    Severity:
      - HIGH: no availability statement at all
      - MED:  consistency issue or future-tense release
      - LOW:  missing metadata category

    Returns:
        A list of (category, message, line) tuples, one per
        finding. Lines are -1 for global findings, positive
        integers for findings tied to a specific source line.
    """
    findings = []
    c10_claims = c10_reproducibility_claims or []

    # Sub-check 1: Availability statement exists
    has_availability = _c10_has_availability_statement(tex)
    if not has_availability:
        # No availability statement at all -> HIGH
        findings.append((
            'C10',
            'HIGH: paper has no code/data availability statement '
            '(no \\section{...Availability...}, no GitHub/GitLab/Zenodo '
            'URL, and no "code is available" phrase). Reviewer §5 #10.',
            -1,
        ))
    else:
        # Has a statement, but is it future-tense? -> MED
        if _c10_has_future_tense_release(tex):
            findings.append((
                'C10',
                'MED: availability statement uses future tense '
                '("we will release" or "upon acceptance"). The release '
                'is conditional, not a real release. Reviewer §5 #10.',
                -1,
            ))

    # Sub-check 2: Statement consistency with claims
    # Only run if c10_claims is non-empty.
    if c10_claims:
        for claim in c10_claims:
            claim_type = claim.get('type', '')
            if claim_type == 'claims_sota':
                # Check if the paper claims SOTA and the statement
                # says "we do not release".
                # First, find a SOTA claim in the body.
                sota_pat = re.compile(
                    r'(state[\s\-]of[\s\-]the[\s\-]art|SOTA|best[\s\-]in[\s\-]class)',
                    re.IGNORECASE,
                )
                sota_match = sota_pat.search(tex)
                if sota_match and _c10_has_no_release_phrase(tex):
                    ln = line_of(tex, sota_match.start())
                    findings.append((
                        'C10',
                        f'MED: paper claims SOTA (line {ln}) but the '
                        f'availability statement says "we do not release". '
                        f'This is an inconsistency: a SOTA claim should be '
                        f'verifiable. Reviewer §5 #10.',
                        ln,
                    ))

    # Sub-check 3: Reproducibility metadata
    has_hyperparams = _c10_has_metadata(_C10_HYPERPARAM_PATTERNS, tex)
    has_seed = _c10_has_metadata(_C10_SEED_PATTERNS, tex)
    has_hardware = _c10_has_metadata(_C10_HARDWARE_PATTERNS, tex)
    has_lib_version = _c10_has_metadata(_C10_LIBRARY_VERSION_PATTERNS, tex)

    if not has_hyperparams:
        findings.append((
            'C10',
            'LOW: no hyperparameters reported (no "learning rate", '
            '"batch size", or "optimizer" found). Reviewer §5 #10.',
            -1,
        ))
    if not has_seed:
        findings.append((
            'C10',
            'LOW: no random seed reported (no "random seed" or '
            '"torch.manual_seed" found). Reviewer §5 #10.',
            -1,
        ))
    if not has_hardware:
        findings.append((
            'C10',
            'LOW: no hardware specs reported (no "GPU", "RTX", "A100", '
            'or "T4" found). Reviewer §5 #10.',
            -1,
        ))
    if not has_lib_version:
        findings.append((
            'C10',
            'LOW: no library version reported (no "PyTorch 2", '
            '"TensorFlow 2", or "transformers 4" found). Reviewer §5 #10.',
            -1,
        ))

    return findings


# ---------------------------------------------------------------------------
# C8: Statistical Power (added in v0.3.0)
# ---------------------------------------------------------------------------
#
# A paper's statistical claims are judged on 3 sub-categories:
#   1. Effect size re-derivation: the claimed Cohen's d should
#      be consistent with the (mean, sd, n) reported in the
#      results table. A mismatch suggests misrepresentation.
#   2. Statistical power: with the claimed d and n, the power
#      should be at least 0.50 (else the study is underpowered)
#      and at most 0.99 (else suspiciously overpowered).
#   3. Significance claim: a "significantly different" claim
#      should be accompanied by a p-value, and the p-value
#      should be consistent with the claimed d.
#
# Severity:
#   HIGH: d_claimed differs from d_actual by more than 0.10.
#   MED:  power < 0.50 (underpowered) or power > 0.99 (overpowered).
#   MED:  "significantly different" without a p-value.
#   MED:  d_claimed is small but p_claimed is very small (inconsistent).
#
# The effect-size and power sub-checks are opt-in via the per-paper
# c8_claimed_effects config; if it is empty/None they are skipped.
# Sub-check 3 (significance claims) is generic and always runs.
# ---------------------------------------------------------------------------

# Heuristic constants (mirrored in tests/test_c8_statistical_power.py).
_C8_D_MISMATCH_THRESHOLD = 0.10
_C8_POWER_UNDERPOWERED = 0.50
_C8_POWER_OVERPOWERED = 0.99
_C8_SIGNIFICANCE_CONTEXT_CHARS = 200  # how many chars around the claim
                                     # to search for a p-value.

# Regex patterns.
_C8_TABLE_RE = re.compile(
    r'\\begin\{tabular\}.*?\\end\{tabular\}',
    re.DOTALL,
)
_C8_ROW_SEP_RE = re.compile(r'\\\\')  # '\\' is the LaTeX row separator.
_C8_COL_SEP_RE = re.compile(r'&')
# Pattern for "significantly different" claims.
_C8_SIG_DIFF_RE = re.compile(
    r'significantly\s+different',
    re.IGNORECASE,
)
# Pattern for p-values like 'p < 0.05', 'p = 0.03', 'p-value = 0.04'.
_C8_P_VALUE_RE = re.compile(
    r'p[\s\-]*(?:value)?\s*[<=<]\s*\d+\.\d+',
    re.IGNORECASE,
)
# Pattern for "Cohen's d" (used to extract claimed d in body text).
_C8_CLAIMED_D_RE = re.compile(
    r"Cohen['\u2019]s\s+d\s*[=:<>]\s*(-?\d+\.?\d*)",
    re.IGNORECASE,
)
# Pattern for numeric values (mean, sd, n) in a row.
_C8_NUMBER_RE = re.compile(r'-?\d+\.?\d*')
# Pattern for the label column (e.g., "A", "B").
_C8_LABEL_RE = re.compile(r'^\s*([A-Za-z]\w*|\d+)\s*&')
# Pattern for "n=NN per group" declarations outside the tabular.
_C8_N_DECL_RE = re.compile(
    r'n\s*[=:]\s*(\d+)\s*(?:per\s+group|per\s+condition|per\s+cell|each)?',
    re.IGNORECASE,
)


def _c8_try_scipy():
    """Try to import scipy.stats.norm. Return None if unavailable."""
    try:
        from scipy.stats import norm
        return norm
    except ImportError:
        return None


def _c8_compute_d(mean1: float, mean2: float, sd1: float, sd2: float,
                  n1: int, n2: int) -> float:
    """Compute Cohen's d from (mean, sd, n) of two groups.

    d = (mean1 - mean2) / pooled_sd
    pooled_sd = sqrt(((n1-1)*sd1^2 + (n2-1)*sd2^2) / (n1+n2-2))
    """
    if n1 + n2 - 2 <= 0:
        return 0.0
    pooled_var = ((n1 - 1) * sd1**2 + (n2 - 1) * sd2**2) / (n1 + n2 - 2)
    if pooled_var <= 0:
        return 0.0
    return (mean1 - mean2) / (pooled_var ** 0.5)


def _c8_compute_power(d: float, n1: int, n2: int, alpha: float = 0.05) -> float:
    """Compute post-hoc power for a two-sample t-test.

    Uses per-group n = min(n1, n2) for a conservative power estimate:
      ncp = |d| * sqrt(n_per_group / 2)
      power = Phi(ncp - z_alpha/2)
    where z_alpha/2 = norm.ppf(1 - alpha/2).
    """
    norm = _c8_try_scipy()
    if norm is None:
        return 0.5  # fallback: assume adequate power
    n_per_group = max(1, min(n1, n2))
    z_alpha = norm.ppf(1 - alpha / 2)
    return float(norm.cdf(abs(d) * (n_per_group / 2) ** 0.5 - z_alpha))


def _c8_parse_table_row(row_text: str) -> dict:
    """Parse a single table row, returning a dict with optional
    fields: 'label', 'mean1', 'sd1', 'n1', 'mean2', 'sd2', 'n2'.

    This is a best-effort parser. It assumes a 2-group design
    (A vs B) with columns in some order. The row is the raw
    LaTeX text between two `\\` separators.
    """
    cells = _C8_COL_SEP_RE.split(row_text)
    cells = [c.strip() for c in cells if c.strip()]
    if len(cells) < 2:
        return {}
    result = {}
    # First cell is the label
    label_match = _C8_LABEL_RE.match(row_text)
    if label_match:
        result['label'] = label_match.group(1)
    # Extract all numbers from the cells
    all_numbers = []
    for cell in cells[1:]:  # skip label column
        for m in _C8_NUMBER_RE.finditer(cell):
            try:
                val = float(m.group(0))
                all_numbers.append(val)
            except ValueError:
                pass
    # Heuristic: if 2 numbers, assume (mean, sd) per group.
    # If 4 numbers, assume (mean, sd, n) per group.
    # If 6 numbers, assume (mean, sd, n) for both groups.
    if len(all_numbers) >= 2:
        result['mean1'] = all_numbers[0]
        result['sd1'] = all_numbers[1]
    if len(all_numbers) >= 4:
        result['mean2'] = all_numbers[2]
        result['sd2'] = all_numbers[3]
    if len(all_numbers) >= 6:
        result['n1'] = int(all_numbers[4])
        result['n2'] = int(all_numbers[5])
    elif len(all_numbers) >= 5:
        # 5 numbers: (mean1, sd1, n1, mean2, sd2) for first group with n
        result['n1'] = int(all_numbers[2])
        result['n2'] = 50  # default
    else:
        # default n
        result['n1'] = result.get('n1', 50)
        result['n2'] = result.get('n2', 50)
    return result


def _c8_find_table_for_effect(tex: str, effect_name: str) -> dict:
    """Find a table row for the given effect.

    The matching strategy is:
    1. Look for a row whose label matches the effect_name
       (case-insensitive substring match).
    2. If no match, return the first 2 data rows combined
       (assumes the table has 2 groups: A vs B, etc.).

    Returns a dict with 'mean1', 'sd1', 'mean2', 'sd2', 'n1',
    'n2' (or {} if not found).
    """
    for table_match in _C8_TABLE_RE.finditer(tex):
        table_text = table_match.group(0)
        # Split by row separator
        rows = _C8_ROW_SEP_RE.split(table_text)
        # First, try to find a row whose label matches the effect_name
        for row in rows:
            # Skip header rows
            if 'Condition' in row or 'Group' in row or 'Mean' in row:
                continue
            parsed = _c8_parse_table_row(row)
            label = parsed.get('label', '').lower()
            # Require label to be at least 2 chars to avoid
            # spurious matches like "a" in "main_effect".
            if label and len(label) >= 2 and (
                effect_name.lower() in label
                or label in effect_name.lower()
            ):
                return parsed
        # If no match, use the first 2 data rows (assuming A vs B).
        data_rows = []
        for row in rows:
            if 'Condition' in row or 'Group' in row or 'Mean' in row:
                continue
            parsed = _c8_parse_table_row(row)
            if parsed.get('mean1') is not None:
                data_rows.append(parsed)
        if len(data_rows) >= 2:
            # Combine the first 2 data rows.
            r1, r2 = data_rows[0], data_rows[1]
            combined = {
                'label': f"{r1.get('label', '?')}_vs_{r2.get('label', '?')}",
                'mean1': r1['mean1'], 'sd1': r1.get('sd1', 0.0),
                'mean2': r2['mean1'], 'sd2': r2.get('sd1', 0.0),
                'n1': r1.get('n1', 50), 'n2': r2.get('n1', 50),
            }
            return combined
    return {}


def check_c8_statistical_power(
    tex: str,
    c8_claimed_effects: list = None,
) -> list[tuple[str, str, int]]:
    """C8: detect inconsistencies in statistical claims.

    Sub-check 1: Effect size re-derivation
      - For each claimed effect, find the corresponding table
        row and extract (mean1, mean2, sd1, sd2, n1, n2).
      - Compute d_actual.
      - If |d_actual - d_claimed| > 0.10 -> emit HIGH.

    Sub-check 2: Statistical power
      - For each claimed effect, compute post-hoc power.
      - If power < 0.50 -> emit MED (underpowered).
      - If power > 0.99 -> emit MED (suspiciously overpowered).

    Sub-check 3: Significance claim
      - For each 'significantly different' claim in the body,
        look for a p-value within 200 chars.
      - If no p-value -> emit MED.
      - If d_claimed is small but p is small -> emit MED
        (inconsistency, possible p-hacking).

    Returns:
        A list of (category, message, line) tuples, one per
        finding. Lines are -1 for global findings, positive
        integers for findings tied to a specific source line.
    """
    findings = []
    c8_claims = c8_claimed_effects or []

    # Sub-checks 1 and 2 (effect-size and power) require
    # c8_claimed_effects. Sub-check 3 (significance claim) is
    # independent: it scans the body for "significantly
    # different" claims regardless of c8_claims.

    for claim in c8_claims:
        effect_name = claim.get('name', '')
        d_claimed = claim.get('d', 0.0)
        n1 = claim.get('n1', 50)
        n2 = claim.get('n2', 50)
        alpha = claim.get('alpha', 0.05)

        # Sub-check 1: Effect size re-derivation
        # Find the table row for this effect.
        row = _c8_find_table_for_effect(tex, effect_name)
        if row and 'mean1' in row and 'mean2' in row:
            d_actual = _c8_compute_d(
                row['mean1'], row['mean2'],
                row.get('sd1', 0.0), row.get('sd2', 0.0),
                row.get('n1', n1), row.get('n2', n2),
            )
            d_diff = abs(d_actual - d_claimed)
            if d_diff > _C8_D_MISMATCH_THRESHOLD:
                findings.append((
                    'C8',
                    f"HIGH: claimed d={d_claimed:.2f} for '{effect_name}' is "
                    f"inconsistent with reported table numbers "
                    f"(computed d={d_actual:.2f}, diff={d_diff:.2f}). "
                    f'Reviewer §5 #8.',
                    -1,
                ))

        # Sub-check 2: Statistical power
        # Sub-checks 1 and 2 are independent: an effect with both
        # a d-mismatch (HIGH) and an underpowered design (MED)
        # will produce both findings.
        power = _c8_compute_power(d_claimed, n1, n2, alpha)
        if power < _C8_POWER_UNDERPOWERED:
            findings.append((
                'C8',
                f'MED: statistical power for {effect_name!r} is '
                f'{power:.2f} (underpowered; recommend n >= '
                f'{n1 * 4} for d={d_claimed:.2f} at '
                f'alpha={alpha:.2f}). Reviewer §5 #8.',
                -1,
            ))
        elif power > _C8_POWER_OVERPOWERED and d_claimed <= 0.50 \
                and min(n1, n2) >= 1000:
            # Suspiciously overpowered: only flag when claimed d
            # is small (a tiny effect that becomes significant
            # with N>1000 is a p-hacking tell).
            findings.append((
                'C8',
                f'MED: statistical power for {effect_name!r} is '
                f'{power:.4f} with n={min(n1, n2)} '
                f'(suspiciously high for a small claimed d; '
                f'possible p-hacking). Reviewer §5 #8.',
                -1,
            ))

    # Sub-check 3: Significance claim
    for sig_match in _C8_SIG_DIFF_RE.finditer(tex):
        sig_start = sig_match.start()
        # Look for a p-value within 200 chars after the
        # 'significantly different' claim.
        context_start = sig_start
        context_end = min(len(tex), sig_start + _C8_SIGNIFICANCE_CONTEXT_CHARS)
        context = tex[context_start:context_end]
        if not _C8_P_VALUE_RE.search(context):
            ln = line_of(tex, sig_start)
            findings.append((
                'C8',
                f'MED: "significantly different" claim (line {ln}) has no '
                f'p-value within {_C8_SIGNIFICANCE_CONTEXT_CHARS} chars. '
                f'A significance claim should be accompanied by '
                f'the actual p-value. Reviewer §5 #8.',
                ln,
            ))
        else:
            # Check for d/p inconsistency: tiny d but very small p
            # (impossible without p-hacking).
            p_match = _C8_P_VALUE_RE.search(context)
            try:
                p_value = float(p_match.group(0).split()[-1])
            except (ValueError, IndexError):
                p_value = 0.5
            # Find the d in the same context.
            d_match = _C8_CLAIMED_D_RE.search(context)
            if d_match:
                try:
                    d_in_text = float(d_match.group(1))
                except ValueError:
                    d_in_text = 0.5
                # If d < 0.10 (tiny) and p < 0.001 (very small),
                # it's inconsistent.
                if d_in_text < 0.10 and p_value <= 0.001:
                    ln = line_of(tex, sig_start)
                    findings.append((
                        'C8',
                        f'MED: d={d_in_text:.2f} with p<{p_value:.3f} on '
                        f'line {ln} is internally inconsistent '
                        f'(a tiny effect size cannot produce a very '
                        f'small p without p-hacking). '
                        f'Reviewer §5 #8.',
                        ln,
                    ))

    return findings


# ---------------------------------------------------------------------------
# C9: Figure-Caption Consistency (added in v0.3.0)
# ---------------------------------------------------------------------------
#
# A paper's figures are judged on 4 sub-categories:
#   1. Caption exists: each figure should have a \caption{...}.
#   2. Caption placement: the caption should be BELOW the
#      \includegraphics (per IEEE/ACM/TMLR convention).
#   3. Caption content: the caption should mention at least
#      one expected_keyword (per the c9_figure_keywords config).
#   4. Figure referenced: each figure with a \label{fig:...}
#      should be referenced in the body via \ref or \autoref.
#
# Severity:
#   HIGH: missing caption.
#   MED:  wrong placement, content mismatch, unreferenced.
#
# The check is opt-in via the per-paper c9_figure_keywords
# config. Sub-checks 1, 2, 4 are independent of the config
# (they don't need the keywords); sub-check 3 is skipped
# when c9_figure_keywords is None or empty.
# ---------------------------------------------------------------------------

# Regex patterns for figure environments.
_C9_FIGURE_RE = re.compile(
    r'\\begin\{figure\*?\}.*?\\end\{figure\*?\}',
    re.DOTALL,
)
# \caption{...} cannot be matched with a brace-bounded regex once its
# content nests braces, which real captions do:
#
#     \caption{\textbf{Rankings ... \textsc{Swim} tournaments ...}}
#     \caption{\textcolor[HTML]{2f70b8}{{Llama-3-70B}} are used ...}
#
# Both have two brace levels. The earlier pattern
# `\\caption\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}` accepted only one, so a
# figure that *did* carry a caption was reported as having none. (Found
# by auditing arXiv:2502.14074 — see case-studies/arxiv-2502.14074/.)
# The content is extracted by a brace-counting scan instead.
def _c9_balanced_content(text: str, open_pos: int) -> tuple[str, int] | None:
    r"""Return ``(content, index_after_close)`` for the ``{...}`` group.

    ``open_pos`` is the index of the opening brace. Nested braces are
    counted, and an escaped char (``\{``, ``\}``) is skipped so it does
    not disturb the depth. Returns None when the group never closes.
    """
    if open_pos >= len(text) or text[open_pos] != '{':
        return None
    depth = 0
    i = open_pos
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            i += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[open_pos + 1:i], i + 1
        i += 1
    return None


# Pattern for \includegraphics (or other graphic body).
# The optional `[key=value]` option block (e.g. `[width=0.9\textwidth]`)
# may appear between the command name and the `{filename}`.
_C9_GRAPHIC_RE = re.compile(
    r'\\(?:includegraphics|includegraphixt\*?|includegraphics\*?)'
    r'(?:\[[^\]]*\])?\s*\{|'
    r'\\begin\{tikzpicture\}',
)
# Pattern for \label{fig:...}.
_C9_LABEL_RE = re.compile(
    r'\\label\{(fig:[^}]+)\}',
)
# Pattern for \ref{fig:...} or \autoref{fig:...}.
_C9_REF_RE = re.compile(
    r'\\(?:ref|autoref|cref|Cref)\{((?:fig:)?[^}]+)\}',
)


def _c9_parse_figure_block(figure_text: str) -> dict:
    r"""Parse a single figure environment.

    Returns a dict with optional fields:
      - 'has_caption': bool (whether \caption{...} exists)
      - 'caption_text': str (the text inside \caption{...})
      - 'caption_pos': int (position of \caption in figure_text)
      - 'graphic_pos': int (position of \includegraphics or tikzpicture)
      - 'label': str (the fig:... label, if any)
    """
    result = {
        'has_caption': False,
        'caption_text': '',
        'caption_pos': -1,
        'graphic_pos': -1,
        'label': '',
    }
    # Find caption (balanced-brace scan; see _c9_balanced_content).
    cap_at = figure_text.find('\\caption')
    if cap_at >= 0:
        brace_at = figure_text.find('{', cap_at)
        got = _c9_balanced_content(figure_text, brace_at) if brace_at >= 0 else None
        if got is not None:
            result['has_caption'] = True
            result['caption_text'] = got[0]
            result['caption_pos'] = cap_at
    # Find graphic
    graph_match = _C9_GRAPHIC_RE.search(figure_text)
    if graph_match:
        result['graphic_pos'] = graph_match.start()
    # Find label
    label_match = _C9_LABEL_RE.search(figure_text)
    if label_match:
        result['label'] = label_match.group(1)
    return result


def check_c9_figure_caption(
    tex: str,
    c9_figure_keywords: list = None,
) -> list[tuple[str, str, int]]:
    """C9: detect figure-caption issues.

    Sub-check 1: Caption exists (HIGH if missing)
    Sub-check 2: Caption placement (MED if above graphic)
    Sub-check 3: Caption content (MED if no expected_keyword)
    Sub-check 4: Figure referenced (MED if label has no \ref)

    Returns:
        A list of (category, message, line) tuples, one per
        finding. Lines are -1 for global findings, positive
        integers for findings tied to a specific source line.
    """
    findings = []
    c9_keywords = c9_figure_keywords or []

    # Build a map from label -> keyword entries for sub-check 3.
    keyword_map = {}
    for kw in c9_keywords:
        fig_id = kw.get('fig_id', '')
        if fig_id:
            keyword_map[fig_id] = kw.get('expected_keywords', [])

    # Track all defined labels and referenced labels for sub-check 4.
    all_labels = set()  # \label{fig:...} defined
    referenced_labels = set()  # \ref{fig:...} or \autoref{...} in body
    for m in _C9_LABEL_RE.finditer(tex):
        all_labels.add(m.group(1))
    for m in _C9_REF_RE.finditer(tex):
        ref = m.group(1)
        # \ref can refer to any label (e.g., sec:, tab:); only
        # count fig: refs for unreferenced-figure check.
        if ref.startswith('fig:'):
            referenced_labels.add(ref)
        # Also add without prefix in case the ref doesn't use
        # the prefix (some styles use just 'overview' instead
        # of 'fig:overview').
        all_labels.add(ref)  # mark as referenced even if not fig:

    # Sub-checks 1, 2, 3 (per figure).
    for fig_match in _C9_FIGURE_RE.finditer(tex):
        figure_text = fig_match.group(0)
        parsed = _c9_parse_figure_block(figure_text)
        fig_line = line_of(tex, fig_match.start())

        # Sub-check 1: Caption exists
        if not parsed['has_caption']:
            findings.append((
                'C9',
                f'HIGH: figure (line {fig_line}) has no \\caption{{...}}. '
                f'Reviewer §5 #9.',
                fig_line,
            ))

        # Sub-check 2: Caption placement (above vs below graphic)
        # Only check if both caption and graphic are present.
        if (parsed['has_caption']
                and parsed['graphic_pos'] >= 0
                and parsed['caption_pos'] >= 0
                and parsed['caption_pos'] < parsed['graphic_pos']):
            findings.append((
                'C9',
                f'MED: figure (line {fig_line}) has caption ABOVE the '
                f'\\includegraphics (line {fig_line + figure_text[:parsed["caption_pos"]].count(chr(10))}). '
                f'Captions should be BELOW the graphic per IEEE/ACM '
                f'convention. Reviewer §5 #9.',
                fig_line,
            ))

        # Sub-check 3: Caption content (matches expected keywords)
        if parsed['label'] and parsed['label'] in keyword_map:
            expected_kws = keyword_map[parsed['label']]
            caption_text_lower = parsed['caption_text'].lower()
            found = any(
                kw.lower() in caption_text_lower
                for kw in expected_kws
            )
            if not found and expected_kws:
                findings.append((
                    'C9',
                    f'MED: figure {parsed["label"]} (line {fig_line}) has '
                    f'caption that does NOT mention any of the '
                    f'expected keywords: {expected_kws}. '
                    f'Reviewer §5 #9.',
                    fig_line,
                ))

    # Sub-check 4: Figure referenced (unreferenced figures)
    # Only check fig: labels (not sec:, tab:, eq:).
    fig_labels = {lbl for lbl in all_labels if lbl.startswith('fig:')}
    unreferenced = fig_labels - referenced_labels
    for lbl in sorted(unreferenced):
        findings.append((
            'C9',
            f'MED: figure {lbl} is defined but never referenced in the '
            f'body text (no \\ref{{{lbl}}} or \\autoref{{{lbl}}}). '
            f'Reviewer §5 #9.',
            -1,
        ))

    return findings


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------
#
# The template is forked into a paper directory and run there, so it must
# find the manuscript itself. `MAIN` / `REFS` name the conventional layout
# (main.tex + refs.bib); when a paper uses another name, or ships only a
# compiled .bbl, the resolvers below locate what is actually present.

def _resolve_main(default: Path) -> Path | None:
    """Locate the manuscript's root .tex.

    Prefers `default` (main.tex). Otherwise picks the single .tex that
    declares ``\\begin{document}`` -- the file that pulls the rest in.
    Returns None when that choice is ambiguous or nothing is found, so
    the caller can report an operational error rather than guess.
    """
    if default.exists():
        return default
    root = default.parent
    candidates = [p for p in sorted(root.glob('*.tex')) if p.is_file()]
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


# Categories that ran without crashing but had nothing to look at. Kept
# separate from `errors` (a crashed check) and from findings (a violation):
# a document with no \begin{abstract} says nothing about its other nine
# categories, so C1 must not be silently reported as a pass, and must not
# take the whole audit down with it either. Reported as [not observed] and
# reflected in the exit code (3).
OBSERVATION_FAILURES: dict[str, str] = {}


def _resolve_bib(default: Path) -> Path | None:
    """Locate a bibliography source for the cite-key check.

    Prefers refs.bib (the authored source); otherwise the .bbl matching
    the manuscript, then any .bbl in the directory. Returns None when
    neither a .bib nor a .bbl is present -- C4 is then reported as not
    applicable instead of aborting the whole audit.
    """
    if default.exists():
        return default
    root = default.parent
    bbls = sorted(p for p in root.glob('*.bbl') if p.is_file())
    return bbls[0] if bbls else None


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    main_tex = _resolve_main(MAIN)
    if main_tex is None:
        print(f'ERROR: no manuscript .tex found in {MAIN.parent} '
              f'(looked for main.tex and a sole .tex with \\begin{{document}})',
              file=sys.stderr)
        return 2

    bib_path = _resolve_bib(REFS)
    tex = read(main_tex)
    bib = read(bib_path) if bib_path is not None else None

    # v0.5.1: every category runs through run_check, which records one of
    # three states:
    #   checked         — the check ran
    #   not applicable  — the category has no per-paper configuration, so
    #                     it did NOT run (this is not the same as "ran and
    #                     found nothing", which was the old silent behaviour)
    #   error           — the check crashed; recorded in `errors` and the
    #                     remaining categories still run (previously one
    #                     missing config key aborted the whole audit with
    #                     a KeyError)
    run_status: dict[str, str] = {}
    errors: list[tuple[str, str]] = []

    # Categories that are pure per-paper configuration: with the
    # factory-default (empty) CHECKS_CONFIG there is nothing to check.
    _REQUIRED_KEYS = {
        'C1': ('c1_symbols',),
        'C2': ('c2_families',),
        'C3': ('c3_concept_token', 'c3_formal'),
        'C6': ('c6_blacklist',),
    }

    def run_check(cat: str, fn, *args, applicable: bool = True,
                  reason: str = 'no per-paper config'):
        if not applicable:
            run_status[cat] = f'not applicable: {reason}'
            return []
        required = _REQUIRED_KEYS.get(cat, ())
        if any(not CHECKS_CONFIG.get(k) for k in required):
            run_status[cat] = f'not applicable: {reason}'
            return []
        run_status[cat] = 'checked'
        try:
            return fn(*args)
        except Exception as exc:
            errors.append((cat, f'{type(exc).__name__}: {exc}'))
            run_status[cat] = 'error'
            return []

    all_findings: list[tuple[str, str, int]] = []
    all_findings += run_check('C1', check_c1_abstract_definitions, tex)
    all_findings += run_check('C2', check_c2_bonferroni_consistency, tex)
    all_findings += run_check('C3', check_c3_formalization, tex)
    # C4 runs only when a bibliography source was found; without a .bib or
    # .bbl there are no keys to compare against, so it is reported as not
    # applicable rather than crashing the audit (the old template exited 2
    # on a missing refs.bib).
    all_findings += run_check(
        'C4', check_c4_citation_hygiene, tex, bib,
        applicable=(bib is not None),
        reason='no .bib or .bbl found to verify cite keys against')
    all_findings += run_check('C5', check_c5_sample_size_and_test, tex)
    all_findings += run_check('C6', check_c6_blacklist, tex)
    # C7: read the per-paper threshold from CHECKS_CONFIG.
    all_findings += run_check(
        'C7', check_c7_citation_context, tex,
        int(CHECKS_CONFIG.get('c7_max_ceremonial', 2)))
    # C8-C10 (added in v0.3.0): per-paper config read here and passed in;
    # their generic sub-checks run regardless.
    all_findings += run_check(
        'C8', check_c8_statistical_power, tex,
        CHECKS_CONFIG.get('c8_claimed_effects', []) or [])
    all_findings += run_check(
        'C9', check_c9_figure_caption, tex,
        CHECKS_CONFIG.get('c9_figure_keywords', []) or [])
    all_findings += run_check(
        'C10', check_c10_reproducibility, tex,
        CHECKS_CONFIG.get('c10_reproducibility_claims', []) or [])

    summary = {k: 0 for k in SEVERITY}
    for cat, _, _ in all_findings:
        summary[cat] += 1

    print('=' * 72)
    print(f'PAPER AUDIT  ({Path(__file__).name})')
    print('=' * 72)
    print(f'Source: {main_tex}')
    print(f'Size:   {len(tex):,} chars')
    if bib is None:
        print('Refs:   none found (no .bib or .bbl)')
    else:
        print(f'Refs:   {len(_bib_keys(bib))} entries in {bib_path.name}')
    print()
    print('Findings by category:')
    for cat in ('C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9', 'C10'):
        sev = SEVERITY[cat]
        n = summary[cat]
        marker = '[OK]' if n == 0 else f'[{sev}]'
        st = run_status.get(cat, '')
        note = f'  [{st}]' if st.startswith('not applicable') else ''
        if cat in OBSERVATION_FAILURES and not note:
            note = '  [not observed: %s]' % OBSERVATION_FAILURES[cat]
        print(f'  {cat}  {marker:7s}  {n} finding(s){note}')
    for cat, err in errors:
        print(f'  {cat}  [ERROR]   check crashed: {err}')
    print()

    if all_findings:
        sev_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        all_findings.sort(
            key=lambda x: (sev_order[SEVERITY[x[0]]], x[0],
                           x[2] if x[2] > 0 else 99999)
        )
        print('-' * 72)
        print('DETAILED FINDINGS')
        print('-' * 72)
        for cat, msg, line in all_findings:
            sev = SEVERITY[cat]
            loc = f'line {line}' if line > 0 else 'global'
            print(f'\n[{sev}] {cat}  ({loc})')
            for m in msg.splitlines():
                print(f'    {m}')
        print()

    print('=' * 72)
    print(f'TOTAL: {len(all_findings)} findings '
          f'(HIGH={sum(summary[c] for c in summary if SEVERITY[c] == "HIGH")}, '
          f'MEDIUM={sum(summary[c] for c in summary if SEVERITY[c] == "MEDIUM")}, '
          f'LOW={sum(summary[c] for c in summary if SEVERITY[c] == "LOW")})')
    print('=' * 72)

    if errors:
        # A crashed check is not a passed check. Exit 2, the same code
        # as a missing input file: the audit did not run to completion.
        print(f'{len(errors)} check(s) crashed — a crashed check is not a '
              'passed check; exit code 2.')
        return 2

    if OBSERVATION_FAILURES:
        # Exit 3: every check that could run, ran and did not crash, but at
        # least one category had nothing to look at. Kept distinct from 0/1
        # so a pipeline cannot read "unobserved" as "clean", and from 2 so a
        # caller can tell a blind spot from a broken tool.
        print('%d categor(y/ies) could not be observed: %s — exit code 3.'
              % (len(OBSERVATION_FAILURES),
                 ', '.join(sorted(OBSERVATION_FAILURES))))
        return 3

    return 1 if any(SEVERITY[c] == 'HIGH' for c, _, _ in all_findings) else 0


if __name__ == '__main__':
    sys.exit(main())