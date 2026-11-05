"""Shared pytest fixtures for tmaudit tests.

These fixtures provide:
  - A small representative PAPER_CONFIGS entry (Paper 1's C1/C2/C3
    rules) that exercises every forge code path.
  - A minimal verify_TEMPLATE.py source string that contains exactly
    the markers forge.py looks for (ROOT, CHECKS_CONFIG, etc.).
  - A minimal fix_abstract_unicode_TEMPLATE.py source string.

The point of the test fixtures is to keep the tests fast (no
filesystem access, no package import) and reproducible (every test
sees the same source).
"""
from __future__ import annotations
import pytest

from tmaudit.forge import _read_template


# ---------------------------------------------------------------------------
# PAPER_CONFIGS fixtures
# ---------------------------------------------------------------------------

PAPER1_CONFIG = {
    'dir': __import__('pathlib').Path('papers/PAPER1_CONSOLIDATED'),
    'c1_symbols': [
        {
            'name': r'$\Delta$CAF (consensus-against-field coefficient)',
            'token': r'\bCAF\b',
            'definition': r'\bCAF\b.{0,80}=|consensus.{0,30}agreement',
        },
        {
            'name': r'$E_T$ (temporal-accumulation effect)',
            'token': r'\bE_T\b',
            'definition': r'E_T.{0,80}=|temporal.{0,30}accumulation',
        },
    ],
    'c2_families': {'main': 3},
    'c2_section_pattern': (
        r'\section\*?\{[^}]*Power analysis[^}]*\}|'
        r'\subsection\*?\{[^}]*Power analysis[^}]*\}'
    ),
    'c2_abstract_k_allowed': [3],
    'c3_concept': 'Two Faces (Face 1 / Face 2)',
    'c3_concept_token': r'\textbf{Face 1}|\textbf{Face 2}|\bFace\s+1\b|\bFace\s+2\b',
    'c3_formal': r'\section{Face 1:',
    'c3_formal_secondary': r'\section{Face 2:',
    'c4_self_cite_threshold': 0.30,
    'c4_self_cite_prefix': 'liu2026',
    'c4_max_self_cite_keys': 3,
    'c5_d_type': "Cohen's d",
    'c6_blacklist': ['paradigm', 'yield', 'reveal'],
}

# Bug 4: the section_pattern contains a regex string with
# `\{...\{` (escaped braces) and `\|`. forge.py's brace counter
# must NOT count those as Python source-level braces.
BUG4_CONFIG = {
    'dir': __import__('pathlib').Path('papers/PAPER5_CONSOLIDATED'),
    'c1_symbols': [],
    'c2_families': {'dose-response': 9, 'cross-model': 6, 'authority-bias': 3},
    # The crucial part: regex with braces INSIDE a string literal.
    'c2_section_pattern': (
        r'\section\*?\{[^}]*Power analysis[^}]*\}|'
        r'\subsection\*?\{[^}]*Statistical Protocol[^}]*\}'
    ),
    'c2_abstract_k_allowed': [9],
    'c3_concept': 'crossover',
    'c3_concept_token': r'\textbf{crossover}|\bcrossover\b',
    'c3_formal': r'crossover.{0,80}\arg\?min',
    'c3_formal_secondary': None,
    'c4_self_cite_threshold': 0.30,
    'c4_self_cite_prefix': 'liu2026',
    'c4_max_self_cite_keys': 1,
    'c5_d_type': "Cohen's d",
    'c6_blacklist': ['paradigm', 'yield', 'reveal'],
}


# ---------------------------------------------------------------------------
# Template fixtures
# ---------------------------------------------------------------------------

# A minimal verify_TEMPLATE.py that contains all the markers forge.py
# looks for. We do not import the real template in these tests because:
#   1. The real template is ~22 KB; tests should be fast.
#   2. Some tests need to inject broken patterns to verify the bug-2
#      re.sub replacement-text bug.
MINIMAL_VERIFY_TEMPLATE = '''#!/usr/bin/env python3
"""Minimal verify template for testing forge._substitute_verify."""
from __future__ import annotations
from pathlib import Path

ROOT = Path('PAPER_DIR')
MAIN = ROOT / 'main.tex'
REFS = ROOT / 'refs.bib'

CHECKS_CONFIG: dict = {
    'c1_symbols': [],
    'c2_families': {},
    'c2_section_pattern': r'\\section\\*?\\{[^}]*Power analysis[^}]*\\}',
    'c2_abstract_k_allowed': [3],
    'c3_concept': 'X',
    'c3_concept_token': r'\\textbf{X}|\\bX\\b',
    'c3_formal': r'X.{0,80}=',
    'c3_formal_secondary': None,
    'c4_self_cite_threshold': 0.30,
    'c4_self_cite_prefix': 'liu2026',
    'c4_max_self_cite_keys': 3,
    'c5_d_type': "Cohen's d",
    'c6_blacklist': ['paradigm', 'yield', 'reveal'],
}
'''


# A minimal fix_abstract_unicode_TEMPLATE.py containing the marker
# forge.py looks for.
MINIMAL_FIX_UNICODE_TEMPLATE = '''#!/usr/bin/env python3
"""Minimal fix_unicode template for testing forge._substitute_fix_unicode."""
from __future__ import annotations
from pathlib import Path

ROOT = Path('PAPER_DIR')
TEX_BASENAME = 'main'

ABSTRACT_REPLACEMENTS: list[tuple[str, str]] = [
    ('\\u0394', '$\\\\Delta$'),
]
'''


@pytest.fixture
def paper1_config() -> dict:
    return PAPER1_CONFIG


@pytest.fixture
def bug4_config() -> dict:
    return BUG4_CONFIG


@pytest.fixture
def minimal_verify_template() -> str:
    return MINIMAL_VERIFY_TEMPLATE


@pytest.fixture
def minimal_fix_unicode_template() -> str:
    return MINIMAL_FIX_UNICODE_TEMPLATE


@pytest.fixture
def real_verify_template() -> str:
    """The real templates, as they are installed in the package.

    Used by happy-path tests that want to verify the end-to-end
    substitution produces parseable Python.
    """
    return _read_template('verify_TEMPLATE.py')


@pytest.fixture
def real_fix_unicode_template() -> str:
    return _read_template('fix_abstract_unicode_TEMPLATE.py')


@pytest.fixture
def real_compile_template() -> str:
    return _read_template('compile_check_TEMPLATE.py')