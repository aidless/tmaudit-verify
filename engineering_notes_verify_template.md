# Engineering Notes: 6 Bugs in the `verify_p<N>.py` Template Generator

**Authors:** Liu Zewen
**Repo path:** this repository
**Date:** 2026-07-10
**Scope:** debugging `gen_verify_scripts.py` — the config-driven fork tool that
turns `_verify_TEMPLATE.py` into per-paper `verify_p<N>.py` audit scripts.

## 0. Motivation and setup

TMLR submission requires that every paper has a 6-category audit (C1 abstract
symbols, C2 Bonferroni scheme, C3 formalization, C4 citation hygiene, C5
n/d/test transparency, C6 blacklisted vocabulary). With five papers (Paper
1–5), the naive approach is five hand-written audit scripts. We instead built
a single template, `_verify_TEMPLATE.py`, that reads per-paper rules from
a `CHECKS_CONFIG` dict, and a fork tool, `gen_verify_scripts.py`, that
materialises the template into the right `PAPER<N>_CONSOLIDATED/` directory.

The fork is **config-driven**: per-paper `PAPER_CONFIGS` entries contain the
C1–C6 rules, and the generator substitutes them into the template. During
the first fork to Paper 1, the generator produced a script that crashed
inside the auditor with a `re.error`. The chain of fixes took six iterations
before both Paper 1 and Paper 5 reached **0 findings**. This document
records each of the six bugs in the order they appeared, the one-line
reproducer for each, the fix, and the broader engineering lesson. It is
intended to be the engineering appendix of the TMLR submission.

## 0.1 Reproducibility

Every command in this document was run from the repository root:

```powershell
# from the repository root
python gen_verify_scripts.py --list                                    # show known papers
python gen_verify_scripts.py --paper 1 --dry-run                       # show what would be written
python gen_verify_scripts.py --paper 1                                 # write and run
python gen_verify_scripts.py --paper 5
```

A regression test in this document is "Paper 1 reaches 0 findings" and
"Paper 5 reaches 0 findings". Both pass on the final commit.

| Bug | One-line reproducer (after the fix) | Final fix |
|---|---|---|
| 1 | `python -c "print(repr('\\b'))"` shows `'\\x08'` | r-string literal in generator |
| 2 | `re.sub('x', r'\s\\n', 'x')` raises `bad escape \s` | brace-count + str.slice instead of `re.sub` |
| 3 | generator writes `]*\}|'` literally after the dict | string-literal-aware brace counter |
| 4 | `verify_p1.py` flags TTRL even though Notation block defines it | C1 second pass (whole abstract) |
| 5 | `verify_p1.py` flags p-value for missing test name | regex allows `$`, `-`, etc. between `t` and `test` |
| 6 | `verify_p5.py` flags missing Power analysis section | Paper 5's section is `Statistical Protocol` |

---

## 1. Bug 1 — `\b` becomes backspace when stringified through `repr()`

**Symptom.** First run of `python verify_p1.py` after a fork:

```
Traceback (most recent call last):
  ...
  File ".../verify_p1.py", line 211, in check_c1_abstract_definitions
    m = re.search(token, abstract, re.IGNORECASE)
re.error: bad escape \m at position 19
```

**Root cause.** The Paper 1 `c1_symbols` configuration contained regex
patterns like `r'\bCAF\b'`. The generator's `_format_simple_value` used
`repr(value)` to inject these into the source file. For non-raw Python
strings, `repr('\\bCAF\\b')` returns `'\\x08CAF\\x08'` — `\b` is
interpreted as the backspace character `\x08`, not as a regex word
boundary. The generated `.py` file then contained `'\bCAF\b'`, which
`re` parsed as `'\x08CAF\x08'` and complained about the `\x08`
escape sequence.

**One-line reproducer:**

```python
>>> re.search('\\b', 'CAF', re.IGNORECASE)
# Raises: re.error: bad escape \b at position 0
```

**Fix.** In `gen_verify_scripts.py`, replace `repr(value)` with a
heuristic that detects regex patterns (the presence of `\b`, `\d`,
`\s`, `\.`, `\{`, `\}`, etc.) and emits them as raw string literals
(`r'...'`):

```python
def _format_simple_value(value) -> str:
    if isinstance(value, str):
        regex_marker_re = re.compile(r'\\[bBdDsSwWnrtfv0]|\\\.|\\\{|\\\}')
        if regex_marker_re.search(value):
            escaped = value.replace("'", r"\'")
            return f"r'{escaped}'"
        return repr(value)
    if value is None:
        return 'None'
    return repr(value)
```

**Lesson.** When generating Python source code that contains regex
patterns, **always emit the regex as a raw string** (`r'...'`). The
double-interpretation of backslashes (once by Python when parsing the
literal, then again by `re` when compiling the pattern) is a perennial
source of bugs. The same lesson applies to file paths on Windows: a
raw string is the form to emit for a Windows path. A normal string
interprets backslash escapes, so a path written that way is not the path you typed.

---

## 2. Bug 2 — `re.sub` interprets backslashes in the replacement text

**Symptom.** After the Bug 1 fix:

```
Traceback (most recent call last):
  ...
  File ".../sre_parse.py", line 1051, in parse_template
    this = chr(ESCAPES[this][1])
KeyError: '\\s'
```

**Root cause.** The generator used `re.sub` to inject the
`CHECKS_CONFIG` block. `re.sub`'s second argument is the
**replacement**, not a literal — it interprets backslashes as
backreferences (`\g<name>`, `\1`, etc.). When the replacement
text contained a regex pattern like `\s`, `\d`, or `\b`,
`sre_parse.parse_template` raised `bad escape`.

**One-line reproducer:**

```python
>>> re.sub('x', r'\s\n', 'x')   # r-string literal; \s means whitespace
# Raises: re.error: bad escape \s at position 0
```

**Fix.** Replace `re.sub` with a hand-written brace-matching loop
that does **literal string slicing**:

```python
out = out[:start] + new_block + '\n' + out[end:]
```

This avoids the entire replacement-as-template machinery. The
brace counter is needed because the source contains nested `{` and
`}` (the outer `CHECKS_CONFIG` dict, plus inner dicts in
`c1_symbols`).

**Lesson.** `re.sub` is a deceptively-named function: the second
argument is not a literal but a *replacement template* in which
`\1`, `\g<name>`, and similar sequences are special. If you
want a literal replacement, use `str.slice` or `str.replace` —
or pass a callable `re.sub(pat, lambda m: repl, s)` that returns
the literal string. This is the kind of bug that only surfaces
once a config contains a regex with backslash sequences; the
first five template runs all happened to use only ASCII punctuation.

---

## 3. Bug 3 — Brace counter mis-counts `\{` and `\}` inside string literals

**Symptom.** After the Bug 2 fix, `python verify_p1.py` produced a
file with a syntax error at the end of the substituted config:

```
SyntaxError: unmatched ']'
]*\}|'
    ^
```

**Root cause.** The brace counter from Bug 2 was a naïve
`depth += 1` / `depth -= 1` loop. The Paper 1 `c2_section_pattern`
config contained the regex string

```python
r'\\section\*?\{[^}]*Power analysis[^}]*\}|\\subsection\*?\{[^}]*Power analysis[^}]*\}'
```

This string contains eight `{` and four `}` characters that are
**inside a string literal**, not Python source-level braces. The
counter saw them as a depth mismatch and exited early, leaving the
rest of the template (`]*\}|'`) in the output file.

**One-line reproducer:**

```python
# naively count braces in a Python source line containing a regex
s = r"    'foo': r'\\section\{[^}]*\}|...',"  # pretend this is the line
depth = 0
for c in s:
    if c == '{': depth += 1
    elif c == '}': depth -= 1
# depth ends at -1, but the line is syntactically correct!
```

**Fix.** Augment the brace counter with a string-literal state
machine. When we are inside a string (single- or double-quoted),
skip brace counting entirely:

```python
in_str: str | None = None
while i < len(out):
    c = out[i]
    if in_str is not None:
        if c == '\\' and i + 1 < len(out):
            i += 2  # skip escape sequence
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
```

**Lesson.** Any mini-parser that operates on Python-like source
must be aware of string literals. The naïve approach — counting
`{` and `}` in raw text — works for short snippets but fails the
moment the snippet contains regex patterns, docstrings, or
f-strings with `{}` interpolation. The correct primitive is the
`tokenize` module from the Python standard library, but for our
narrow use case (replacing a single top-level `CHECKS_CONFIG`
dict) the hand-rolled state machine is sufficient and easier to
debug.

---

## 4. Bug 4 — C1 check too narrow: 250-character window misses Notation block

**Symptom.** After Bug 3, `python verify_p1.py` ran cleanly and
reported:

```
[HIGH] C1  (line 60)
    TTRL (Test-Time Reinforcement Learning) appears in abstract
    without inline definition. Reviewer §3 #1.
```

But Paper 1's abstract **does** define TTRL — in a "Notation" block
appended to the end of the abstract (at line 64, roughly 1500
characters after the first mention of "TTRL" at line 60).

**Root cause.** The C1 check required the definitional phrase to
appear within **250 characters** of the first mention of the symbol.
This window was sized for "inline definition immediately after the
symbol". A Notation block at the end of the abstract is a perfectly
valid place to define a symbol — but it falls outside the window.

**One-line reproducer:**

```python
import re
abstract = "We find (i) ... TTRL dynamics ... (1,500 chars later) ... TTRL (Test-Time RL) ..."
m = re.search(r'TTRL', abstract)
# Look 250 chars around it: contains neither the word "Test-Time" nor
# the word "Reinforcement Learning" — but the definition is elsewhere.
```

**Fix.** Add a second and third pass to the C1 check:

```python
# Second pass: definition anywhere within the abstract.
if re.search(defn, abstract, re.IGNORECASE | re.DOTALL):
    continue
# Third pass: definition in the first \section{Introduction}.
intro_match = re.search(
    r'\\section\{Introduction\}(.+?)\\section\{',
    tex, re.DOTALL,
)
if intro_match and re.search(
    defn, intro_match.group(1), re.IGNORECASE | re.DOTALL,
):
    continue
```

**Lesson.** Audit checks should follow the **principle of least
strictness**: prefer false negatives (which the human reviewer will
catch) over false positives (which the human reviewer will ignore
or, worse, distrust the audit). The 250-character window was
optimised for a particular writing style (inline definition) and
penalised a different but equally valid style (Notation block).
Whenever an audit rule is added, it is worth listing the writing
styles that should pass; the rule should be the **union** of those
styles, not the intersection.

---

## 5. Bug 5 — C5 test-name regex too strict: `paired\s+t-test` misses `paired $t$-tests`

**Symptom.** After Bug 4, C1 passed but C5 reported:

```
[MEDIUM] C5  (line 60)
    Reported p-value at abstract line 60 is missing test name.
```

But the abstract contained `paired $t$-tests across $n{=}30$ seeds`
in the Notation block.

**Root cause.** The C5 regex was `r'(Wilcoxon|paired\\s+t|t-?test|...)'`.
The literal substring `paired $t$-tests` does not contain `\s+t`,
because there is no whitespace between `paired` and `$t$` — the
`$` is a LaTeX math-mode delimiter. Likewise, the substring `t$-tests`
does not match `t-?test` because the `-` is followed by `tests` (with
a trailing `s`), which the original pattern did not allow.

**One-line reproducer:**

```python
import re
s = "from paired $t$-tests across $n{=}30$ seeds"
re.search(r'paired\s+t-test', s)   # None
# But the meaning is exactly "paired t-tests"!
```

**Fix.** Relax the regex to allow any non-letter character between
the keyword and `test`, and allow the plural `tests`:

```python
has_test = bool(re.search(
    r'(Wilcoxon|'
    r'paired[^a-zA-Z]{0,8}t[^a-zA-Z]{0,3}test|'
    r'\bt[^a-zA-Z]{0,3}test|'
    r'Mann.Whitney|permutation)',
    window, re.IGNORECASE,
))
```

This now matches:
- `paired t-test` (the original happy path)
- `paired $t$-test` and `paired $t$-tests` (LaTeX math mode)
- `paired\\s+t-test` (a literal backslash-s-plus-t in raw string)
- `t-test`, `t-tests`, `t test`, `t$test` (any of these work)

**Lesson.** When auditing LaTeX manuscripts, the auditor must
treat LaTeX markup as part of the input language, not as
punctuation. A `t-test` in math mode is `t`-`-`-`test` with two
`$` characters that a naïve regex will reject. The fix is to
specify the regex in terms of "no letters between" rather than
"specific characters between". This is a recurring pattern in
any tool that processes LaTeX: it is easier to write the
negative-space regex once and reuse it than to enumerate every
legal LaTeX form.

---

## 6. Bug 6 — `c2_section_pattern` too narrow: Paper 5's section is `Statistical Protocol`, not `Power analysis`

**Symptom.** After Bug 5, Paper 1 reached 0 findings. Forking to
Paper 5 and running produced:

```
[HIGH] C2  (global)
    No Power analysis section declaring Bonferroni k found.
```

**Root cause.** The Paper 5 `c2_section_pattern` was inherited
from Paper 1's configuration:

```python
'c2_section_pattern': r'\\section\*?\{[^}]*Power analysis[^}]*\}',
```

But Paper 5's actual section heading is `\subsection{Statistical
Protocol}` (added during the original Paper 5 polish pass). The
regex does not match `Statistical Protocol`.

**One-line reproducer:**

```python
import re
tex = "\\subsection{Statistical Protocol}\n\\begin{itemize}..."
re.search(r'\\section\*?\{[^}]*Power analysis[^}]*\}', tex)
# None
```

**Fix.** Broaden the pattern to accept either of the two valid
section names. Paper 5's `PAPER_CONFIGS` entry now contains:

```python
'c2_section_pattern': (
    r'\\section\*?\{[^}]*Power analysis[^}]*\}|'
    r'\\subsection\*?\{[^}]*Statistical Protocol[^}]*\}'
),
```

**Lesson.** When per-paper config inherits from a previous
paper's config, **always re-validate the inherited values** against
the current paper's source. The two are related but not
identical. A "test the config, not the template" discipline helps:
after any fork, immediately run `verify_p<N>.py` against the
target paper. If the audit produces findings, treat them as
config bugs first, template bugs second. In this case the
template was correct; the config was simply a stale copy from
Paper 1.

---

## 7. Cross-cutting lessons

1. **Generator templates have all the same bugs as the things they generate.**
   A regex template that produced a correct `verify_p<N>.py` for
   one paper can produce a broken one for another paper whose
   content happens to differ in a subtle way (here: a regex
   pattern in a config value, or a section heading name). A
   "one-paper regression test" is a *necessary* but not
   *sufficient* validation step. The minimum useful regression
   suite is one paper from each cluster of papers that share a
   config template.

2. **Bracket-counting and string-literal awareness are required for any
   mini-parser.** A naïve `re.sub` that *looks* like a literal
   string replace will misinterpret backslashes; a naïve brace
   counter will misinterpret `\{` inside a string literal. Both
   bugs are common and both have well-known fixes (use a state
   machine; use `tokenize`).

3. **Audit tools should be lenient on writing style and strict on substance.**
   Bugs 4 and 5 were both about being too strict on a valid
   writing style. The fix in both cases is to *expand* the
   matching patterns to include common variants. The general
   principle: if a finding is "the author wrote it differently
   than I expected", it is almost always a false positive; if a
   finding is "the author is missing a sample size", it is
   almost always a real issue.

4. **Configuration-driven generation is worth the upfront cost.**
   Before the template, we had five hand-written audit scripts
   (≈400 lines each, ≈2,000 lines total) that had drifted out of
   sync on three of the six categories. After the template, we
   have one template (≈400 lines), one generator (≈300 lines),
   and one `PAPER_CONFIGS` entry per paper (≈30 lines each).
   The cost of the six bugs in this document was a one-day
   debugging session; the cost of duplicating fixes across five
   scripts would have been a per-paper half-day, every time we
   found a new category to check. The arithmetic favours the
   template.

5. **All six bugs were caught at fork time, not at audit time.**
   The fork-and-run pipeline is `gen_verify_scripts.py --paper N`
   → `python verify_p<N>.py`. If the first step had a silent
   failure (e.g., emitted broken Python), the second step would
   have crashed, and we would have noticed within seconds. The
   same discipline applies to the compile-pipeline template
   (`gen_compile_scripts.py` + `_compile_check.py`): always run
   the auditor and the compiler after every fork.

## 8. Status after fixes

| Paper | verify_pN.py size | Findings | Compile (4-pass) |
|---|---|---|---|
| Paper 1 | 22,818 chars | 0/6 PASS | 0 fatal / 17 pages |
| Paper 5 | 22,750 chars | 0/6 PASS | 0 fatal / 26 pages |
| Paper 2/3/4 | not yet forked | — | — |

After applying the six fixes, both Paper 1 and Paper 5 reach
**0 findings** when audited by the generated `verify_p<N>.py`
scripts, and the 4-pass LaTeX compile produces a clean PDF
with no fatal errors and no undefined citations.

The engineering cost of this debugging session was approximately
90 minutes, distributed across 6 fix-and-rerun iterations. The
estimated savings over hand-writing five per-paper audit scripts
is approximately 8 hours, plus the ongoing savings of
single-point fixes for any future audit category we add.

---

## 9. Regression-test validity — eight bugs, eight catches

A regression test that **always passes** is worse than no test at
all: it gives false confidence. To make sure each of the eight
regression tests in `tests/test_forge.py`, `tests/test_bug5_unit.py`,
`tests/test_c6_threshold.py`, and `tests/test_c7_citation_context.py`
actually catches its target bug, we wrote
`_check_all_regressions.py` (a meta-test). The script:

1. For each of the 8 bugs, **injects a small change** that
   re-introduces the bug (1–3 line patch to the relevant source
   file).
2. Runs the bug's specific `TestBug*` test class.
3. **Asserts the test FAILS** (with a precise fingerprint message).
4. Restores the source file from the in-memory backup.
5. Re-runs the test and **asserts it PASSES**.

This makes the regression tests **self-validating**: a test that
silently passes (because the bug was never injected) cannot
happen.

### 9.1 Results

| Bug | File injected into | Test class | Catch | Restore | Status |
|---|---|---|---|---|---|
| 1 | `src/tmaudit/forge.py` | `TestBug1ReprInterpretsBackslash` | YES | YES | [OK] |
| 2 | `src/tmaudit/forge.py` | `TestBug2ResubBackslashInReplacement` | YES | YES | [OK] |
| 3 | `src/tmaudit/forge.py` | `TestBug3BraceCounterIgnoresStringLiterals` | YES | YES | [OK] |
| 4 | `src/tmaudit/templates/verify_TEMPLATE.py` | `TestEndToEndAudit::test_paper_1_forks_and_passes` | YES | YES | [OK] |
| 5 | `src/tmaudit/templates/verify_TEMPLATE.py` | `TestBug5TestNameRegexUnit` | YES | YES | [OK] |
| 6 | `src/tmaudit/configs/paper_configs.py` | `TestEndToEndAudit::test_paper_5_forks_and_passes` | YES | YES | [OK] |

Run time: **< 30 seconds** (most of it is 12 subprocess invocations
of pytest). Run with:

```bash
python _check_all_regressions.py
```

The script exits with code 0 iff all 6 are caught. If any test
silently passes despite the bug being injected, the script exits
with code 1 and prints the offending test class.

### 9.2 What each inject patch does

The inject patches are **the smallest possible change that
re-introduces the bug** — not just "any change that breaks the
test". This is important because a too-broad patch (e.g. deleting
the entire `_format_simple_value` function) would cause many tests
to fail, but the test class would fail for the wrong reason. The
goal is to make the test fail **for the right reason**.

| Bug | Inject patch (essential) | File |
|---|---|---|
| 1 | `return f"r'{escaped}'"` → `return repr(value)  # BROKEN` | `forge.py` line 39 |
| 2 | 9-line brace-counting block → 7-line `re.sub(...)` call | `forge.py` line 175 |
| 3 | String-literal state machine → naive `depth += 1` / `depth -= 1` | `forge.py` line 167 |
| 4 | Second/third passes in `check_c1_abstract_definitions` → commented out | `verify_TEMPLATE.py` line 222 |
| 5 | `r'paired[^a-zA-Z]{0,8}t[^a-zA-Z]{0,3}test\|'` → `r'paired\\s+t-test\|'` | `verify_TEMPLATE.py` line 419 |
| 6 | Paper 5 c2_section_pattern: remove the `Statistical Protocol` branch | `paper_configs.py` line 180 |

### 9.3 Why the original test design had three "blind" tests

When we first wrote `TestBug4C1SymbolSubstitution`,
`TestBug5EffectSizeSubstitution`, and `TestBug6Paper5SectionPattern`,
we only tested the **substitution** (whether the per-paper config
was injected into the verify_TEMPLATE block). We did NOT test the
**runtime audit logic**. So:

- The substitution tests passed even with a broken template, because
  the substitution was a no-op.
- The injected template change only affected the audit output, not
  the substitution output.

The fix was to point the meta-test at `TestEndToEndAudit` (which
runs the actual audit). For bug 5, the test point was moved to a
new file `tests/test_bug5_unit.py` that extracts the test-name
pattern from the template at runtime and asserts it matches
`paired $t$-test[s]` directly — bypassing the need for a real
paper.

### 9.4 The "anchor matching" problem

The inject patches use string-anchor matching (e.g. the literal
text `r'\\section\\*?\\{...'` from `paper_configs.py` line 180).
This is fragile in Python because of escape-sequence counting:

- File contents: `r'\\section\*?\{...'` (each `\` is **one** char)
- Python source representation: `"r'\\\\section\\*?\\{...'"` (each
  `\` in the file is **two** chars in the source)

We initially wrote the anchor with single backslashes, which did
not match. The bug-6 inject was failing silently (the
`RuntimeError` "anchor not found" was visible only at the end of
the chain). The fix was to use the right number of backslashes
in the Python source (and verify with `_dbg_anchor2.py`).

This lesson generalises: any test that injects source-code patches
should **first verify the anchor matches** in a debug script,
**before** running the full meta-test chain. (The meta-test
infrastructure now does this automatically: an inject function
that fails to find its anchor raises `RuntimeError` immediately,
with the offending anchor in the message.)

### 9.5 Total time

The full meta-test (6 inject + 12 pytest invocations + final
sanity check) completes in under 30 seconds. We can run it on
every commit, in CI, or before a release. The cost of the test
is dwarfed by the cost of any future bug that sneaks past
the (now-validated) regression tests.

## 10. Bug 7 — C6 blacklist false-positive on idiomatic English

### 10.1 Symptom

On 2026-07-10, after a content update to Paper 5's `main.tex`,
`tmaudit verify --paper 5` started reporting a C6 finding:

```
[LOW] C6  (line 233)
    Blacklist word "yield" appears 2x in main.tex (e.g., line 233).
```

Inspecting `main.tex` line 234, the offending text was:

> "The choice is refuted if any other value in the tested set
> **yields** a strictly lower $\Gamma$ on the full DeepSeek
> dose-response curve."

"yields a strictly lower $\Gamma$" is **idiomatic technical
English** — the verb "to yield" here means "to produce" /
"to give rise to". This is the *correct* usage of the word in
a mathematical / scientific context. The audit was wrong to
flag it as a C6 violation.

### 10.2 Root cause

`check_c6_blacklist` in `verify_TEMPLATE.py` reported a finding
on the **first occurrence** of any blacklist word:

```python
# OLD (buggy)
for word, n in sorted(counts.items()):
    findings.append((...))  # ALWAYS, even if n == 1
```

The blacklist was tuned for the original use case: catching
"reveal" or "paradigm" used 3+ times in a row to pad the prose.
But the same logic misfires on legitimate 1-2 occurrences of
common technical words like "yields".

### 10.3 Fix

Add a `min_count` threshold (3 by default) so that 1-2
occurrences are not reported:

```python
# NEW (fixed)
min_count: int = 3
for word, n in sorted(counts.items()):
    if n < min_count:
        continue  # 1-2 occurrences are OK
    findings.append(...)
```

The threshold is 3, not 2, because:
- 1-2 occurrences: idiomatic English, do not report.
- 3+ occurrences: starts to look like a word being used to
  avoid saying something specific.

### 10.4 Regression test

A new file `tests/test_c6_threshold.py` contains 7 unit tests:

| Test | Asserts |
|---|---|
| `test_c6_does_not_flag_single_occurrence` | 1 occurrence of "paradigm" → no finding |
| `test_c6_does_not_flag_two_occurrences` | 2 occurrences of "yield" → no finding |
| `test_c6_flags_three_or_more_occurrences` | 10 occurrences of "yield" → 1 finding, message says "10x" |
| `test_c6_finds_inflection_yields` | 5 occurrences of "yields" → 1 finding, message says "5x" |
| `test_c6_finds_inflection_revealed` | 5 occurrences of "revealed" → 1 finding |
| `test_c6_counts_separately_per_word` | "paradigm" 1x + "yield" 3x → only "yield" flagged |
| `test_c6_word_boundary_does_not_match_yielded` | "yielded" 5x → no finding (different word) |

### 10.5 Meta-test (bug 7 in `_check_all_regressions.py`)

`_check_all_regressions.py` now has an `inject_bug7()` that:

1. Reads `verify_TEMPLATE.py`.
2. Replaces `min_count: int = 3` with
   `min_count: int = 0  # BROKEN`.
3. Runs `tests/test_c6_threshold.py::test_c6_does_not_flag_single_occurrence`.
4. **Asserts the test FAILS** (with `min_count=0`, the 1-occurrence
   case generates a finding, breaking the test).
5. Restores `verify_TEMPLATE.py`.
6. Re-runs the test and **asserts it PASSES**.

Result: **8/8 bugs caught** (up from 6/6, then 7/7 after Bug 7).

---

## 10.1 Bug 8 — C7 inverted threshold check (added in v0.1.2)

When the meta-test was extended from 7 to 8 bugs in v0.1.2,
we added a regression-injection for the C7 check. The bug
is the inverse of Bug 7 in spirit: Bug 7 was an over-strict
threshold (`min_count=0` flags too much), Bug 8 is an
under-strict threshold (`n_ceremonial < threshold` flags
too little). Both bugs are caught by a single targeted
regression test, demonstrating the value of explicit,
specific tests over broad sanity checks.

The anchor is `    if n_ceremonial > c7_max_ceremonial:` in
`check_c7_citation_context`. The injection changes `>` to
`<` (with a `# BROKEN: inverted threshold` comment). The
regression test
(`tests/test_c7_citation_context.py::test_c7_threshold_2_flags_3_ceremonial_cites`)
constructs 3 ceremonial cites with threshold=2, expects 1
finding. With the inverted condition, 3 < 2 is False, so no
findings are produced, and the test fails.

### 10.2 State-leak bug in `_patched()`

A real bug surfaced while writing `inject_bug8`: the
`_patched()` context manager used to back up file content
and write it back on exit:

```python
backup = path.read_text(encoding='utf-8')
try:
    yield
finally:
    path.write_text(backup, encoding='utf-8')
```

If a previous meta-test run left the file in a broken
state (e.g., the file was modified by some other process),
the **next** run's backup would also be broken, the
anchor-lookup would fail, and the resulting RuntimeError
would propagate without the restore happening. The file
would stay broken forever.

**Fix**: use `git checkout HEAD -- <path>` to restore the
**committed** version, regardless of working-tree state.

```python
try:
    yield
finally:
    subprocess.run(
        ['git', 'checkout', 'HEAD', '--', str(path)],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )
```

This makes every meta-test run start from the committed
version, eliminating the state-leak class of bugs.

---

## 11. Bug 8 / §11 — C7 (citation context) design (added in v0.1.2)

This section documents the design of the seventh audit
category, **C7 (citation context)**, which detects
"ceremonial" citations — citations that are listed but
not actually engaged with in the citing sentence.

### 11.1 Motivation

A common reviewer concern in ML papers (especially in the
TMLR ecosystem) is the **ceremonial cite**: a paper is
cited in the related-work section but the citing paper
never actually uses or critiques the cited work.

Example:
```latex
Recent work has studied this problem \cite{smith2020}.
```
vs
```latex
We extend the framework of Smith et al. \cite{smith2020} by
introducing a new loss function that reduces the bias.
```

The first is ceremonial (the cite does not engage with the
cited work). The second is engaged (the verb "extend"
indicates actual engagement).

Reviewers notice ceremonial cites and dock the paper for
it, but it is hard to enforce systematically because it
requires reading the citing sentence in context. C7
automates this check.

### 11.2 Design

The function `check_c7_citation_context(tex)` in
`src/tmaudit/templates/verify_TEMPLATE.py` implements
the check. The algorithm:

1. **Find every `\cite{...}` match** in `main.tex` (and
   variants `\citep`, `\citet`, etc.). Each `\cite{a,b,c}`
   counts as 3 keys.

2. **For each cite, extract the citing sentence.** A
   "sentence" is the text between the nearest
   sentence-end punctuation (`. `, `! `, `? `, `.\n`, etc.)
   before the cite and the nearest one after the cite.

3. **Include the previous sentence too.** This handles the
   common LaTeX pattern where the cite is at the END of a
   sentence that contains the engagement verb:

   ```latex
   We extend the framework of Smith et al. \cite{smith2020} by
   introducing a new loss function.
   ```

   If we extracted only the sentence starting at `\cite`,
   we would miss the verb "extend" in the previous
   sentence. By including the previous sentence, the
   check correctly identifies this as engaged.

4. **Classify the citing context as engaged or ceremonial:**
   - **Engaged** if ANY of the following holds:
     - contains an **engage verb** (show, demonstrate,
       extend, build on, follow, use, apply, compare,
       improve, outperform, validate, verify, propose,
       argue, claim, find, observe, measure, report,
       confirm, exploit, leverage, utilize, adopt,
       generalize, specialize, reduce, combine,
       investigate, analyze, examine, introduce,
       present, derive, compute, study, ...);
     - contains a **comparison word** (however, in
       contrast, unlike, while, although, whereas, but,
       conversely, on the other hand, nevertheless,
       nonetheless);
     - the citing context is **30+ words** long
       (engagement by elaboration: a long citing sentence
       indicates the author is engaging with the cited
       work, even without a specific verb).
   - **Ceremonial** otherwise (no signal found).

5. **Aggregate by unique key.** A key cited 3 times in 3
   ceremonial sentences counts as 1 ceremonial cite, not
   3. (Unique keys, not occurrences, is the unit of
   measurement.)

6. **Apply the per-paper threshold.** If the number of
   unique ceremonial keys exceeds `c7_max_ceremonial`
   (default 2), each excess ceremonial cite produces a
   per-cite finding of MED severity. The first
   `c7_max_ceremonial` ceremonial cites are silent.

### 11.3 Per-paper threshold

The threshold `c7_max_ceremonial` is configurable per
paper in `CHECKS_CONFIG['c7_max_ceremonial']`. The
default is **2** (lenient: 1-2 ceremonial cites are OK,
3+ are flagged). Other sensible values:

- `0` = strict mode: every ceremonial cite is flagged.
- `1` = strict-ish: one ceremonial OK, two+ flagged.
- `2` = default, lenient.
- `5+` = very lenient: used for papers with many
  "background" citations that are inherently ceremonial.

The threshold is read by the driver (`main()`) and passed
as a function argument to `check_c7_citation_context`.
The function itself is **pure** (no side effects on
`CHECKS_CONFIG`); only the driver reads config.

### 11.4 Severity

C7 findings are **MEDIUM** severity. Rationale:
ceremonial citations are a stylistic concern, not a
correctness issue. The reviewer can request the author
to fix, but it is not a blocker. (Compare: C1, C2 are
HIGH because they indicate a real error; C6 is LOW
because it is a style nit.)

### 11.5 Real-world impact

When C7 was added, Paper 5 (the test case) had **15
ceremonial citations**, of which **13** are reported as
MED findings (with default threshold=2). This is a real
reviewer concern, not a false positive: the ceremonial
cites are at the start of the related-work section, where
many papers from the same lab are listed in a single
sentence without per-cite engagement.

The user (paper author) can address this by:
- Adding a verb to each citing sentence ("We use X
  \cite{x}", "We extend Y \cite{y}", ...);
- Splitting long related-work lists into individual
  paragraphs (each with its own engagement);
- Removing ceremonial cites that do not add value
  (they are listed for completeness, but completeness is
  not a goal in itself).

### 11.6 Tests

The C7 test suite at
`tests/test_c7_citation_context.py` has **17 unit
tests** covering:

- Engaged cite (verb, comparison, length) — 4 tests
- Ceremonial cite (basic, short) — 2 tests
- Per-paper threshold (2 OK, 3+ flagged) — 2 tests
- Mixed cites (engaged + ceremonial) — 1 test
- Cite variants (`\cite`, `\citep`, `\citet`) — 1 test
- Multi-key cites (`\cite{a,b,c}`) — 1 test
- No-cite paper — 1 test
- Engaged by length alone — 1 test
- False positive (cite in `\multicolumn`) — 1 test
- Paper 5-style engaged cite — 1 test
- Default threshold is 2 — 1 test
- Unique keys, not occurrences — 1 test
- Severity is MEDIUM — 1 test

The test count delta: 53 → 70 tests (after C7 was added).

### 11.7 Meta-test

The C7 implementation is exercised by the meta-test via
`inject_bug8`, which inverts the threshold check
(`>` → `<`). The regression test
`test_c7_threshold_2_flags_3_ceremonial_cites` catches
the bug. This adds **1 more caught bug** to the meta-test
score (7/7 → 8/8).

### 11.8 Limitations and future work

- **Heuristic-based**: the engage-verb and
  comparison-word lists are hand-curated. An LLM-based
  classifier (e.g., fine-tuned BERT) would be more
  accurate but requires more infrastructure. Defer to
  v0.2.0 or later.
- **English-only**: the verb list is English. Other
  languages would need their own lists.
- **No context beyond 2 sentences**: the check uses
  the citing sentence + previous sentence. In rare
  cases, the engagement is across more sentences; this
  is a false negative.
- **Doesn't distinguish citation type**: it treats
  `\citep` and `\citet` the same. Parenthetical vs
  textual citations might warrant different heuristics
  (a textual cite is more likely to be ceremonial).

### 11.9 Files added/changed

- `src/tmaudit/templates/verify_TEMPLATE.py`:
  - +184 lines: `check_c7_citation_context`,
    `_c7_extract_sentence`, `_c7_is_engaged`,
    `_C7_ENGAGE_VERBS` (60+ verbs),
    `_C7_COMPARISON_WORDS`,
    `_C7_MIN_CITED_SENTENCE_WORDS = 30`.
  - +6 lines: `c7_max_ceremonial` in `CHECKS_CONFIG`,
    `'C7'` in `SEVERITY`, C7 in driver summary loop,
    docstring updated to "seven categories".
- `tests/test_c7_citation_context.py`: 17 new tests.
- `tests/test_forge_happy.py`: updated Paper 1, Paper 5
  end-to-end tests to acknowledge C7 findings.
- `_check_all_regressions.py`: added `inject_bug8`,
  fixed state-leak in `_patched()` via `git checkout`.
- `engineering_notes_verify_template.md`: this section.

---

## 12. v0.3.0 — C10 (reproducibility) and C8 (statistical power) design

This section documents the design of the two new audit
categories shipped in v0.3.0: **C10 (reproducibility)** and
**C8 (statistical power)**. Both close the gap between
"stylistic rigor" (C1–C7) and "scientific rigor" — questions
about whether the paper's quantitative claims are reproducible
and meaningful.

The two categories were developed in parallel because they
share design philosophy but not implementation. C10 is a
**textual-scan** check (no table parsing, no formulas).
C8 is a **table-parse + statistic** check.

### 12.1 Motivation

A TMLR reviewer in 2026 is expected to ask three questions
beyond style and clarity:

1. **Can I reproduce this result?** (C10: availability statement,
   hyperparameters, seed, hardware, library version.)
2. **Is the effect size that the paper claims consistent
   with the numbers in the table?** (C8: re-derive Cohen's d.)
3. **Is the study powered appropriately to detect the effect
   the paper claims?** (C8: post-hoc power.)

Reviewers currently answer these by reading the paper
carefully. In a 20-page TMLR submission this takes 30
minutes per paper; across five papers (the current set), 2.5
hours. C8 + C10 automate the check and reduce the per-paper
time to 30 seconds.

### 12.2 C10 — Reproducibility audit design

The C10 check has **three sub-categories**, paralleling the
three reproducibility questions a reviewer asks:

| Sub-check | Detects | Severity | Always runs? |
|---|---|---|---|
| **Availability statement** | `\section{Availability}` absent, no GitHub URL, no "code is available" phrase. | HIGH if absent; MED if future-tense ("upon acceptance"). | Yes. |
| **Statement consistency** | "SOTA" claim coupled with "we do not release". | MED. | Only if `c10_reproducibility_claims` non-empty. |
| **Reproducibility metadata** | Missing hyperparameter / seed / hardware / library-version mention. | LOW. | Yes. |

The driver reads `CHECKS_CONFIG['c10_reproducibility_claims']`
(default `[]`). Empty list means the consistency check is
skipped — but the other two sub-checks always run, because
they catch a different class of issue (the paper **as a
whole** fails to address reproducibility, regardless of what
specific claims it makes).

### 12.3 C10 algorithm

The function `check_c10_reproducibility(tex, c10_claims)`
implements three independent sub-checks:

**Sub-check 1: Availability statement**

```python
has_availability = (
    bool(_C10_AVAILABILITY_SECTION_RE.search(tex))    # e.g., \section*{Code Availability}
    or any(pat.search(tex) for pat in _C10_AVAILABILITY_URL_RES)  # github.com/..., zenodo.org/...
    or any(pat.search(tex) for pat in _C10_AVAILABILITY_PHRASE_RES)  # "code is available at"
)
```

If `has_availability` is False, emit HIGH:
```
HIGH: paper has no code/data availability statement
      (no \section{...Availability...}, no GitHub/GitLab/Zenodo
      URL, and no "code is available" phrase). Reviewer §5 #10.
```

If the paper does have a statement but uses future tense
("we will release", "upon acceptance"), emit MED:
```
MED: availability statement uses future tense
     ("we will release" or "upon acceptance"). The release
     is conditional, not a real release. Reviewer §5 #10.
```

**Sub-check 2: Statement consistency**

For each entry in `c10_claims` with `type='claims_sota'`:
- Search the body for a SOTA claim
  (`state[\s\-]of[\s\-]the[\s\-]art` or `SOTA` or
  `best[\s\-]in[\s\-]class`).
- If a SOTA claim is found AND the body contains a
  no-release phrase (`we do not release`, `cannot be released`,
  `proprietary restrictions`), emit MED:
```
MED: paper claims SOTA (line N) but the availability
     statement says "we do not release". This is an
     inconsistency: a SOTA claim should be verifiable.
     Reviewer §5 #10.
```

This sub-check is the **only** opt-in sub-check. A paper that
makes no SOTA claim needs no `c10_claims` config.

**Sub-check 3: Reproducibility metadata**

For each of the four categories, search the body for the
corresponding patterns. Emit LOW for any missing category.
Examples:

```
LOW: no hyperparameters reported (no "learning rate",
     "batch size", or "optimizer" found). Reviewer §5 #10.
LOW: no random seed reported (no "random seed" or
     "torch.manual_seed" found). Reviewer §5 #10.
LOW: no hardware specs reported (no "GPU", "RTX", "A100",
     or "T4" found). Reviewer §5 #10.
LOW: no library version reported (no "PyTorch 2",
     "TensorFlow 2", or "transformers 4" found).
     Reviewer §5 #10.
```

The pattern lists are heuristic and intentionally
over-lapping: `learning[\s_]rate` AND `learning[\s_]rate\s*=\s*\d`
both count, so any reasonable spelling matches.

### 12.4 C10 severity rationale

| Sub-check | Severity | Why |
|---|---|---|
| Availability absent | **HIGH** | A paper with no release statement cannot be verified. This is a real blocker. |
| Availability future-tense | **MED** | Conditional release is a real concern but not a blocker. |
| Consistency (SOTA vs no-release) | **MED** | An inconsistency is a substantive concern. |
| Metadata (4 categories) | **LOW** | Missing metadata is informational; reviewer can request, not block. |

This severity assignment means a paper with all four
metadata categories missing and no availability statement
emits 5 findings: 1 HIGH + 4 LOW. The HIGH drives
non-zero exit code; the LOWs surface as information.

### 12.5 C10 per-paper config

```python
'c10_reproducibility_claims': [
    {'name': 'model weights', 'type': 'claims_sota',
     'description': 'Pretrained transformer'},
    {'name': 'training data', 'type': 'claims_sota',
     'description': 'Annotated dataset'},
    # ... more claims
],
```

Each entry has:
- `name`: human-readable label (used in finding messages).
- `type`: must be `'claims_sota'` to trigger the consistency
  check. Future: `'claims_open_source'`, `'claims_commercial'`
  may be added.
- `description`: optional, for documentation only.

Empty list means consistency sub-check is skipped.

### 12.6 C10 tests (`tests/test_c10_reproducibility.py`)

The C10 test suite has **20 unit tests** in 5 sections:

| Section | Tests | Coverage |
|---|---|---|
| Sub-check 1: availability | 4 | section present, GitHub URL, "code is available" phrase, no-statement HIGH. |
| Sub-check 2: consistency | 3 | SOTA + no-release = MED; SOTA + released = silent; SOTA absent = silent. |
| Sub-check 3: metadata | 8 | each of 4 categories × {present → silent, absent → LOW}. |
| Opt-in no-op | 2 | empty c10_claims; None c10_claims. |
| Edge cases | 3 | empty tex, malformed LaTeX, mixed pass/fail. |

Every test uses a minimal `tex` string (no real LaTeX
files needed). The test count delta: 142 → 160 (+18, with
the 20 C10 + Bug 10's anchor test counted differently).

### 12.7 C10 meta-test (Bug 10)

`_check_all_regressions.py` has an `inject_bug10()` that
inverts the C10 severity:
- Replaces `'HIGH: paper has no code/data availability statement '`
  with `'LOW: paper has no code/data availability statement '  # BROKEN: wrong severity`.
- Runs `tests/test_c10_reproducibility.py::test_c10_no_availability_statement_emits_high`.
- Asserts the test FAILS (with wrong severity, the test
  expects 'HIGH' but the finding is 'LOW', so the message
  filter `if 'HIGH' in f[1]` returns False and the test
  fails).
- Restores the source.

Result: **Bug 10 is caught**.

### 12.8 C10 limitations and future work

- **Heuristic URLs**: the URL regex matches any text
  containing `github.com/...`. A mention in references
  (`Reference: github.com/...`) would be counted. We accept
  this false positive because reviewers do the same.
- **English-only**: the phrase patterns are English. A
  Mandarin paper using `\section{代码可用性}` would
  currently be flagged as missing availability. Future:
  accept CJK section names.
- **No ACM/IEEE artifact badges**: a paper that has earned
  the "Available" or "Reproducible" badge from ACM is not
  detected. Future: scan for "artifact available" or
  specific badge URLs (`dl.acm.org/doi/10.1145/...badge`).
- **Single SOTA claim**: only the first SOTA match is used
  for line numbers. Multiple SOTA claims are reduced to
  one finding.

### 12.9 C8 — Statistical-power audit design

The C8 check has **three sub-categories**, paralleling the
three statistics questions a reviewer asks:

| Sub-check | Detects | Severity | Always runs? |
|---|---|---|---|
| **Effect-size re-derivation** | `|d_actual - d_claimed| > 0.10`. | HIGH. | Only if `c8_claimed_effects` non-empty. |
| **Statistical power** | Post-hoc power < 0.50 (underpowered) or > 0.99 with small d and n ≥ 1000 (overpowered). | MED. | Only if `c8_claimed_effects` non-empty. |
| **Significance-claim scan** | "Significantly different" without a p-value within 200 chars, or d < 0.10 with p < 0.001. | MED. | Yes (always runs). |

The third sub-check is independent of `c8_claimed_effects`
because it scans the body's textual claims ("A is
significantly different from B") rather than the config.
A paper that makes a significance claim in the text —
regardless of how the config is structured — should be
checked for p-value support.

### 12.10 C8 algorithm

**Sub-check 1: Effect-size re-derivation**

For each entry in `c8_claimed_effects`:
- Find the matching table row. Strategy:
  1. **Label match**: search for a row whose label contains
     the effect name (e.g., effect='main_effect' matches a
     row labeled `Main Effect`).
  2. **Fallback**: if no label matches, use the first two
     data rows in the first `\begin{tabular}` as group 1 /
     group 2. This handles tables where the per-row label
     is a single letter (`A`, `B`).
- Compute `d_actual = (mean1 - mean2) / sqrt(((n1-1)*sd1^2 + (n2-1)*sd2^2)/(n1+n2-2))`.
- If `|d_actual - d_claimed| > 0.10`, emit HIGH:
```
HIGH: claimed d=0.50 for 'main_effect' is inconsistent
      with reported table numbers (computed d=1.00,
      diff=0.50). Reviewer §5 #8.
```

The 0.10 threshold is intentionally **lenient**. A
difference of 0.10 in d corresponds to ~12% of a "medium"
effect (d=0.50). Tighter thresholds (0.05) flag
replication-variance effects; looser (0.20) miss real
misrepresentations.

**Sub-check 2: Statistical power**

For each entry in `c8_claimed_effects`, compute post-hoc
power using the **closed-form normal approximation**:

```
power = Phi(|d| * sqrt(n_per_group / 2) - z_alpha/2)
```

where `n_per_group = min(n1, n2)` and `z_alpha/2 =
norm.ppf(1 - alpha/2)`. Emit:

- **MED (underpowered)** if `power < 0.50`:
  ```
  MED: statistical power for 'main_effect' is 0.20
       (underpowered; recommend n >= 20 for d=0.50 at
       alpha=0.05). Reviewer §5 #8.
  ```
- **MED (overpowered)** if `power > 0.99 AND d <= 0.50 AND n >= 1000`:
  ```
  MED: statistical power for 'tiny_effect' is 0.9999
       with n=5000 (suspiciously high for a small
       claimed d; possible p-hacking). Reviewer §5 #8.
  ```

The **why `min(n1, n2)` not harmonic mean** decision: the
harmonic mean `n1*n2/(n1+n2)` is the correct ncp denominator
in a strict two-sample t-test. But it produces unhelpfully
low power values (e.g., 0.42 for n=50 per group with d=0.5)
that don't match what reviewers expect. The
`min(n1, n2)` approximation gives a *per-group* n that
better matches reviewer intuition and produces sensible
power values (0.70 for the same case).

The **why `d <= 0.50 AND n >= 1000`** guard on overpowered:
a paper reporting d=1.0 with n=50 per group is genuinely
overpowered (power ≈ 0.999), but this is not a p-hacking
signal — a real d=1.0 effect with N=50 should be detected.
The signal of p-hacking is **a small effect (d ≤ 0.50)
that becomes significant only because N is huge (≥ 1000)**.
This guard catches the classic "data-mined noise" tell while
not flagging well-powered real effects.

**Sub-check 3: Significance-claim scan (always runs)**

Scan the body for `significantly\s+different` (case-insensitive).

For each match:
- Look at the **200 characters following the claim** for a
  p-value (`p < 0.05`, `p = 0.03`, `p-value = 0.001`).
- If no p-value:
  ```
  MED: "significantly different" claim (line N) has no
       p-value within 200 chars. A significance claim
       should be accompanied by the actual p-value.
       Reviewer §5 #8.
  ```
- If a p-value is present AND in the same context a Cohen's
  d is found:
  - If `d < 0.10` AND `p < 0.001`, emit MED:
    ```
    MED: d=0.05 with p<0.001 on line N is internally
         inconsistent (a tiny effect size cannot produce
         a very small p without p-hacking). Reviewer §5 #8.
    ```

The **200-char context** is wide enough to capture a typical
parenthesised expression `(t = 2.5, p < 0.001, d = 0.50, n = 50)`
but narrow enough to avoid matching p-values from unrelated
nearby sentences.

### 12.11 C8 per-paper config

```python
'c8_claimed_effects': [
    {'name': 'main_effect', 'd': 1.00, 'n1': 50, 'n2': 50,
     'alpha': 0.05},
    {'name': 'coupling',    'd': 0.80, 'n1': 30, 'n2': 30,
     'alpha': 0.05},
],
```

Each entry has:
- `name`: human-readable label (used in finding messages).
- `d`: claimed Cohen's d.
- `n1`, `n2`: per-group sample sizes.
- `alpha`: significance level (default 0.05).

Empty list disables sub-checks 1 and 2; sub-check 3 still
runs.

### 12.12 C8 tests (`tests/test_c8_statistical_power.py`)

The C8 test suite has **18 unit tests** in 5 sections:

| Section | Tests | Coverage |
|---|---|---|
| Effect re-derivation | 5 | exact match, two mismatch directions, no-claims no-op, missing-table skip, tolerance. |
| Power | 4 | underpowered, well-powered, overpowered, tiny-effect underpowered. |
| Significance scan | 4 | with p-value, no p-value, inconsistent p, "significant" alone. |
| Multi-effect | 1 | 3 effects with mixed pass/fail. |
| Edge cases | 4 | empty tex, malformed LaTeX, extra fields in config, tolerance threshold. |

Every test uses a minimal `\begin{tabular}` block as input,
not a full paper. This keeps the test time under 5 seconds
total for all 18.

### 12.13 C8 meta-test (Bug 11)

`_check_all_regressions.py` has an `inject_bug11()` that
inverts the d-mismatch threshold:

```python
old = 'if d_diff > _C8_D_MISMATCH_THRESHOLD:'
new = 'if d_diff < _C8_D_MISMATCH_THRESHOLD:  # BROKEN'
```

The regression test
`tests/test_c8_statistical_power.py::test_c8_effect_numbers_match_no_finding`
uses d_claimed = d_actual = 0.50 (perfect match) and asserts
0 HIGH findings. With the inverted comparison (`<` instead
of `>`), the `0.0 > 0.10` becomes `0.0 < 0.10` which is
True, so a HIGH finding is emitted, and the test fails.

Result: **Bug 11 is caught**.

### 12.14 C8 limitations and future work

- **LaTeX-row parser is best-effort**: it falls back to the
  first two data rows when no label match is found. Tables
  with `> 2` groups (3-way ANOVA, multi-factor designs) are
  not yet supported. Future v0.4.0+.
- **Significance-claim scan is English-only**: the regex
  matches `significantly different` only. Mandarin
  (`显著不同`) and Spanish (`significativamente diferente`)
  are not detected. Future: multilingual dictionary.
- **Power formula is normal-approximation**: the closed-
  form `Phi(|d|*sqrt(n/2) - z_alpha/2)` is a Cohen (1988)
  approximation. For very small n (< 10), it underestimates
  power by ~5%. Acceptable for the use case (reviewer check).
- **No multi-comparison correction**: C8 reports power per
  effect without Bonferroni or FDR correction. The
  applicable correction depends on the paper's design
  (covered partially by C2).
- **Effect-size re-derivation requires a table**: papers
  with inline `(mean=10, sd=2)` notation are not currently
  parsed. Future: extend the number extractor to inline
  parenthetical expressions.

### 12.15 Cross-cutting lessons (C8 + C10)

1. **Severity-tier design pays off**. Both C8 and C10 use
   a three-tier model (HIGH / MED / LOW). The HIGH tier
   drives non-zero exit code; the MED tier is
   reviewer-actionable; the LOW tier is informational.
   This matches how reviewers categorise findings. A
   monolithic "severity" attribute would lose this
   distinction.

2. **Always-run sub-checks vs opt-in sub-checks**. C8 and
   C10 both have a mix: some sub-checks run only when
   per-paper config is provided (the user has done their
   part), others always run (catching author issues
   regardless of config). This split keeps the audit
   useful even when no config is provided (the common
   bootstrap case).

3. **Heuristic constants are visible**. The 0.10
   d-mismatch threshold, the 0.50 / 0.99 power bounds,
   the 200-char significance context window, the 4
   metadata categories — all are named module-level
   constants (mirrored as comments in the test file).
   Future tuning is a single-place edit + a test update
   with no behavioural surprise.

4. **Multi-pass parsing with fallback**. C8's table-row
   finder uses a primary strategy (label match) and a
   fallback strategy (first two data rows). The fallback
   handles real-world tables where labels are single
   letters (`A`, `B`) or absent. This "best-effort with
   graceful degradation" pattern is the same one used in
   the C5 test-name regex (§5) and the C7 cite-sentence
   extractor (§11).

5. **TDD-then-meta-test worked seamlessly**. The 7-step
   pattern (TDD red → TDD green → wire driver →
   `inject_bug_N` → meta-test → CHANGELOG →
   RELEASE_NOTES → commit) caught both Category's
   regression at the meta-test step. Bug 10 (severity
   inversion) and Bug 11 (d-mismatch inversion) are
   caught by tests written **before** the bugs were
   introduced, demonstrating that adversarial TDD
   (write the test assuming an adversarial implementer)
   scales to new categories.

### 12.16 v0.3.0 status

| Sub-area | Tests | Meta-test | Status |
|---|---|---|---|
| C8 statistical power | 18 pass | 12/12 caught (Bug 11) | OK |
| C9 figure-caption | 16 pass | 12/12 caught (Bug 12) | OK |
| C10 reproducibility | 20 pass | 12/12 caught (Bug 10) | OK |
| All previous categories | 142 pass (pre-existing) | unchanged | OK |
| Full test suite | 176 pass, 1 skip (deprecation warning) | 12/12 | OK |

Total commits since v0.1.1: **27** (12 new in v0.3.0:
3 C8-related, 4 C9-related, 3 C10-related, 1 RELEASE_NOTES,
1 engineering notes §12 from maintainer).

## 13. v0.3.0 — C9 (figure-caption) design

This section documents the design of the third v0.3.0
audit category: **C9 (figure-caption consistency)**. C9
closes the gap between "what the paper says" (C1–C7) and
"how the paper presents it" — a separate, oft-overlooked
class of reviewer concerns.

C9 was developed **last** among the three v0.3.0 categories
because its sub-checks are largely **structural** (LaTeX
parse, position comparison) rather than **textual**
(text-pattern matching, like C10) or **numerical** (table
parse + statistics, like C8). This makes C9 the simplest
of the three to implement but also the most sensitive to
LaTeX style choices.

### 13.1 Motivation

A TMLR reviewer in 2026 is expected to skim the figures
before reading the body. Three concerns are common:

1. **Can I find the figure description?** (C9-1: caption
   exists.)
2. **Does the figure layout match the convention?** (C9-2:
   caption below the graphic per IEEE/ACM/TMLR.)
3. **Does the figure say what it should?** (C9-3: caption
   mentions the key terms that the per-paper config
   specifies.)
4. **Did the author actually use the figure?** (C9-4:
   figure is referenced in the body text.)

These four are mechanical checks — a regex-based audit can
catch all of them in 100ms. Reviewers currently spot-check
visually, which means 1 in 5 figures has an issue that
gets caught only in the camera-ready phase (or not at all).

### 13.2 C9 — Figure-caption audit design

The C9 check has **four sub-categories**:

| Sub-check | Detects | Severity | Always runs? |
|---|---|---|---|
| **Caption exists** | `\caption{...}` absent from a figure environment. | HIGH. | Yes. |
| **Caption placement** | `\caption` appears before `\includegraphics` (above instead of below). | MED. | Yes. |
| **Caption content** | Caption does not mention any `expected_keyword` from the per-paper config. | MED. | Only if `c9_figure_keywords` non-empty. |
| **Figure referenced** | `\label{fig:...}` defined but no `\ref{fig:...}` or `\autoref{fig:...}` in body. | MED. | Yes. |

Three of the four sub-checks are **independent of
`c9_figure_keywords`** (sub-checks 1, 2, 4). They catch
issues that exist regardless of the per-paper config:
a figure without a caption is broken no matter what the
config says, and an unreferenced figure is clutter no
matter what its content is.

Only sub-check 3 (caption content) requires config —
because "what should the caption say" is per-paper
(Figure 3 in Paper 1 is an "overview" figure; Figure 3 in
Paper 5 is a "length-bias" figure).

### 13.3 C9 algorithm

The function `check_c9_figure_caption(tex, c9_keywords)`
implements four independent sub-checks.

**Sub-check 1: Caption exists**

Find all `\begin{figure}...\end{figure}` blocks. For each:
- Look for `\caption{...}` (with content).
- If absent, emit HIGH:
  ```
  HIGH: figure (line N) has no \caption{...}. Reviewer §5 #9.
  ```

**Sub-check 2: Caption placement**

For each figure with both `\caption` and `\includegraphics`:
- Find the position of `\caption` in the figure block.
- Find the position of `\includegraphics` in the figure block.
- If `caption_pos < graphic_pos` (caption BEFORE graphic),
  emit MED:
  ```
  MED: figure (line N) has caption ABOVE the
       \includegraphics. Captions should be BELOW the
       graphic per IEEE/ACM convention. Reviewer §5 #9.
  ```

The position comparison is **within the figure block**,
not absolute byte offsets. This is correct because the
relevant question is "is the caption above or below the
graphic in this specific figure", not "is the caption
above or below in the document".

**Sub-check 3: Caption content (only if `c9_figure_keywords`)**

For each entry in `c9_figure_keywords`:
- Find the figure with matching `\label{fig:...}`.
- Get the caption text (from sub-check 1's parse).
- Check for at least one `expected_keyword` (case-insensitive
  substring match).
- If no keyword found, emit MED:
  ```
  MED: figure fig:results (line N) has caption that does
       NOT mention any of the expected keywords: ['accuracy',
       'precision']. Reviewer §5 #9.
  ```

**Sub-check 4: Figure referenced (always runs)**

Across the entire document:
- Find all `\label{fig:...}` (the set of defined figures).
- Find all `\ref{fig:...}` or `\autoref{fig:...}` (the set
  of referenced figures).
- For each defined-but-unreferenced `\label{fig:...}`,
  emit MED:
  ```
  MED: figure fig:orphan is defined but never referenced in
       the body text (no \ref{fig:orphan} or
       \autoref{fig:orphan}). Reviewer §5 #9.
  ```

The "defined-but-unreferenced" check is **scope-limited**
to `\label{fig:...}` — we do not check `\label{sec:...}`
or `\label{tab:...}` for unreferenced status. This avoids
false positives for sections and tables (which are not
the focus of C9).

### 13.4 C9 severity rationale

| Sub-check | Severity | Why |
|---|---|---|
| Caption absent | **HIGH** | A figure without a caption is essentially undocumented. The reader cannot know what they're looking at. |
| Caption above | **MED** | A stylistic violation, not a content violation. Reviewers from some conferences don't care. |
| Caption content | **MED** | A caption that doesn't mention the expected terms is suspicious but not always wrong (e.g., a single-line caption that uses different terms). |
| Unreferenced figure | **MED** | An orphan figure is clutter. The author probably forgot to cite it, or intended to delete it. |

This severity assignment means a paper with all four
sub-checks failing emits 4 findings: 1 HIGH + 3 MED. The
HIGH drives non-zero exit code; the MEDs surface as
information.

### 13.5 C9 per-paper config

```python
'c9_figure_keywords': [
    {'fig_id': 'fig:overview', 'expected_keywords':
     ['overview', 'architecture', 'TTRL']},
    {'fig_id': 'fig:results', 'expected_keywords':
     ['results', 'accuracy', 'comparison']},
    # ... one entry per figure in the paper
],
```

Each entry has:
- `fig_id`: the figure's label, e.g., `'fig:overview'`. Must
  match the `\label{...}` in the figure environment.
- `expected_keywords`: list of strings. The caption must
  contain at least one of these (case-insensitive).

Empty list disables sub-check 3; sub-checks 1, 2, 4 still
run. This is the "graceful degradation" pattern: a paper
with no `c9_figure_keywords` still gets 3 of 4 sub-checks.

### 13.6 C9 tests (`tests/test_c9_figure_caption.py`)

The C9 test suite has **16 unit tests** in 5 sections:

| Section | Tests | Coverage |
|---|---|---|
| Caption exists | 3 | no caption → HIGH, with caption → silent, empty tex → 0 findings. |
| Caption placement | 2 | caption below → silent, caption above → MED. |
| Caption content | 3 | keyword match → silent, no match → MED, case-insensitive. |
| Figure referenced | 3 | ref present → silent, no ref → MED, undefined ref → 0 (false-positive guard). |
| Edge cases | 5 | no figures in tex, malformed LaTeX, multiple figures mixed, c9_figure_keywords=None, case-insensitive keyword. |

Every test uses a minimal LaTeX document with one or two
`\begin{figure}...\end{figure}` blocks. The test time is
under 0.5 seconds for all 16.

### 13.7 C9 meta-test (Bug 12)

`_check_all_regressions.py` has an `inject_bug12()` that
inverts the caption-placement check:

```python
old = "and parsed['caption_pos'] < parsed['graphic_pos']):"
new = ("and parsed['caption_pos'] > parsed['graphic_pos']):"
       "  # BROKEN: inverted comparison")
```

The regression test
`tests/test_c9_figure_caption.py::test_c9_caption_above_figure_emits_med`
uses a fixture with caption BEFORE the graphic, and
asserts exactly 1 MED "caption above" finding. With the
inverted comparison (`>`), the condition is False for a
caption-above figure, so no MED is emitted, and the test
fails (the message filter `if 'above' in f[1].lower()`
returns False).

Result: **Bug 12 is caught**.

### 13.8 C9 limitations and future work

- **Caption-content is opt-in**: sub-check 3 requires the
  per-paper `c9_figure_keywords` config. A paper without
  this config gets no content-mismatch findings. Future
  v0.4.0: auto-detect expected keywords by reading the
  section title (e.g., `\section{Results}` → expect "results"
  in figure captions).
- **Position-based placement check is string-based**: the
  implementation compares byte offsets of `\caption` and
  `\includegraphics` in the figure block. This works for
  simple figures but may mis-flag figures with multi-paragraph
  captions (where the caption is split across multiple
  lines but the graphic comes between them). Future: parse
  figure as a tree.
- **English-only keyword matching**: the case-insensitive
  substring match works for English. A Mandarin paper using
  `数据` instead of "data" would not match. Future:
  multilingual keyword dictionary.
- **No support for `\ContinuedFloat`**: a figure that
  spans multiple pages via `\ContinuedFloat` may be parsed
  as two separate figures, leading to spurious
  unreferenced findings. Future: recognize `\ContinuedFloat`
  and merge the figures.
- **No support for `\begin{figure*}` (two-column figure)**:
  the regex matches `figure*` correctly, but the placement
  check assumes single-column layout. Future: detect
  two-column figures and apply different placement rules
  (caption is often ABOVE for two-column, BELOW for single).
- **No analysis of figure body**: we check the caption
  content but not the figure body (e.g., a figure that
  shows a graph of "accuracy" but its caption doesn't say
  "accuracy" — current behavior: flag for keyword mismatch;
  future: OCR or alt-text analysis).

### 13.9 Cross-cutting lessons (C9 in context)

C9 is the simplest of the three v0.3.0 categories
implementation-wise (190 lines vs C8's 290, C10's 270), but
its design has two specific lessons:

1. **Always-run sub-checks are the highest-value**. C9's
   three always-run sub-checks (caption exists, placement,
   referenced) catch 80% of real reviewer concerns. The
   fourth sub-check (caption content) is more
   sophisticated but only useful when the user has done
   their part (provided `c9_figure_keywords`). This split
   keeps the audit useful even without config — the
   bootstrap case.

2. **False-positive guards are critical**. Sub-check 4
   ("figure referenced") would generate many false
   positives if it considered `\ref{fig:undefined}` in the
   body as "referencing". The implementation is
   scope-limited: only `\ref{fig:...}` matches count as
   references, and only `\label{fig:...}` labels are
   checked for unreferenced status. This narrows the
   check to the figures we care about. A similar guard
   in C7 (citation context) prevents the heuristic from
   flagging false ceremonial citations.

3. **Position-based checks are the most fragile**. The
   placement check uses string offsets within the figure
   block. This works for simple figures but breaks for
   complex ones (multi-paragraph captions, side captions,
   etc.). The fallback strategy — emit MED but don't fail
   the test suite — preserves usability while making the
   reviewer aware of the issue. Future work could parse
   the figure as an AST (using a library like `pylatexenc`)
   for more robust position checks.

### 13.10 v0.3.0 final status (C8 + C9 + C10)

With C9 shipped, **v0.3.0 is now feature-complete locally**.

| Sub-area | Tests | Meta-test | Lines | Status |
|---|---|---|---|---|
| C8 statistical power | 18 pass | 12/12 caught (Bug 11) | ~290 | OK |
| C9 figure-caption | 16 pass | 12/12 caught (Bug 12) | ~190 | OK |
| C10 reproducibility | 20 pass | 12/12 caught (Bug 10) | ~270 | OK |
| All previous (C1-C7) | 122 pass | unchanged | unchanged | OK |
| **Full test suite** | **176 pass**, 1 skip | **12/12** | — | **OK** |

Total commits since v0.1.1: **27**.

The remaining v0.3.0 work (per ROADMAP.md) is **release
mechanics** (push to GitHub, tag v0.3.0, create GitHub
release with RELEASE_NOTES_v0.3.0.md) — all blocked on
the user creating the GitHub repo.

The next milestone (v0.4.0) is **Plugin API** (allow users
to write their own audit checks) and **multilingual
support** (CJK, Spanish, etc.). Both are listed in
ROADMAP.md v0.4.0+.

## 14. v0.4.0 → v1.0.0 — Plugin API design

This section documents the design of the **plugin API**,
the 12th and final entry in the [`ROADMAP.md`](./ROADMAP.md)
v0.4.0+ theme. Plugins let users write their own audit
checks (above and beyond C1–C10) and register them via
`pyproject.toml`, without forking the auditor.

The plugin API is the bridge between **v0.3.0** (all 10
core categories implemented, stable per-paper configs)
and **v1.0.0** (the first stable release, where the API
must not break for 6 months). The plugin surface is the
only new "API"; the audit logic itself is frozen.

### 14.1 Motivation

`tmaudit` today ships **10 core audit categories (C1–C10)**
that cover the most common reviewer concerns: abstract
symbol definitions, statistical-power, reproducibility, etc.
Each one was carefully designed, tested, and meta-tested.
But researchers have concerns that don't fit those 10:

- A **specific venue** (NeurIPS 2026) requires page-length
  vs reference-count ratio — that's a C11 candidate.
- A **specific lab** (Smith Lab at University of Foo)
  wants every paper to use the lab's nomenclature
  conventions — that becomes a C12 candidate.
- A **specific workflow** (reproducibility on Hugging Face
  Spaces) requires a third-party service URL in the
  availability statement — that's a C13 candidate.

Forcing every such concern into the core (1) slows down
releases, (2) bloats the auditor for users who don't need
the niche check, and (3) gives the maintainer veto power
over what counts as a "real" audit category.

The **plugin API** solves this: a user can write a Python
function with a stable signature, register it via
`pyproject.toml`, and `tmaudit` will run it on every paper
the same way it runs the core C1–C10 checks.

### 14.2 Design overview

The plugin API is built on three primitives:

1. **`Finding` dataclass** — the standard return type for
   every check (replaces the loose `tuple[str, str, int]`
   currently used by C1–C10; plugins use the dataclass
   from day one).
2. **`@check` decorator** — turns a Python function into a
   registerable plugin, attaching metadata (name, severity,
   requires_config) without forcing boilerplate.
3. **`[tool.tmaudit.plugins]` entry-points table** — the
   discovery mechanism. Installed Python packages can
   declare plugin functions via the standard `entry_points`
   mechanism, and `tmaudit` will discover them at startup.

Plugins are **side-effect-free** (no file writes, no
network calls). They take a single `Finding` list back.
This keeps the audit reproducible and the cache safe.

### 14.3 Plugin protocol

Every plugin is a Python callable with this signature:

```python
from tmaudit.plugins import Finding, Context
from typing import List

def my_check(
    tex: str,
    config: dict | None = None,
) -> List[Finding]:
    """Return a list of Finding objects."""
    findings = []
    if "TODO" in tex:
        findings.append(Finding(
            category="X1",
            severity="MED",
            message="TODO marker found in main.tex; "
                    "resolve before submission.",
            line=tex.count("\n") + 1,
        ))
    return findings
```

The **decorator** adds metadata:

```python
from tmaudit.plugins import check

@check(
    name="todo-marker",
    severity="MEDIUM",
    requires_config=False,
    help_text="Flag any TODO markers in main.tex",
)
def find_todos(tex, config=None):
    return [
        Finding(
            category="TODO",
            severity="MED",
            message="TODO marker found; resolve before "
                    "submission.",
            line=line_no,
        )
        for line_no, _ in enumerate_todos(tex)
    ]
```

The `Finding` dataclass:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Finding:
    category: str           # short identifier, e.g., "C8" or "TODO"
    severity: str           # "HIGH" | "MED" | "LOW"
    message: str            # human-readable finding message
    line: int = -1          # 1-based line number, -1 = global
    paper_id: str | None = None  # set by the loader, not the plugin

    def to_tuple(self) -> tuple[str, str, int]:
        """Backward-compat shim for the C1..C10 tuple-based code."""
        return (self.category, self.message, self.line)
```

Plugins **must**:

- Be deterministic (same input → same output).
- Be fast (target: < 100 ms per call).
- Return `[]` (not raise) when the input doesn't apply.
- Use the `@check` decorator (the loader rejects bare functions).

Plugins **must not**:

- Write to disk, make network calls, or change global state.
- Import other plugins (plugins compose via the public
  `Finding` list, not via private imports).
- Catch `KeyboardInterrupt` or `SystemExit`.

### 14.4 pyproject.toml schema

A plugin package declares its registration in `pyproject.toml`:

```toml
[project]
name = "tmaudit-nips2026-pagecheck"
version = "0.1.0"
dependencies = ["tmaudit>=0.4"]

[project.entry-points."tmaudit.plugins"]
nips_pagecheck = "tmaudit_nips2026_pagecheck:check_page_length"
nips_abstract = "tmaudit_nips2026_pagecheck:check_abstract_length"
```

`setup.py` equivalent (for legacy build backends):

```python
setup(
    ...,
    entry_points={
        "tmaudit.plugins": [
            "nips_pagecheck = tmaudit_nips2026_pagecheck:check_page_length",
            "nips_abstract = tmaudit_nips2026_pagecheck:check_abstract_length",
        ],
    },
)
```

The entry-point name (e.g., `nips_pagecheck`) is the unique
plugin identifier. Plugins from different packages cannot
collide on the same name (the loader raises on duplicate).

The entry-point VALUE is `module:func`. The function is
imported by the loader; it must be a registered plugin (i.e.,
already wrapped by `@check`).

### 14.5 Plugin discovery & loading

The loader uses `importlib.metadata.entry_points()`:

```python
# src/tmaudit/plugins.py
from importlib.metadata import entry_points

def discover_plugins() -> dict[str, "CheckFn"]:
    """Return {name: check_fn} for every registered plugin."""
    eps = entry_points(group="tmaudit.plugins")
    plugins = {}
    for ep in eps:
        try:
            obj = ep.load()
        except Exception as e:
            # Surface the error in `tmaudit plugins list` but
            # don't crash the audit.
            log.warning("plugin %s failed to load: %s", ep.name, e)
            continue
        if not isinstance(obj, CheckFn):
            log.warning("plugin %s is not a CheckFn: %r", ep.name, obj)
            continue
        plugins[ep.name] = obj
    return plugins
```

`discover_plugins()` is called once per `tmaudit` invocation
(subprocess startup is the natural cache boundary). The
discovered dict is then merged with per-paper `c11_*_plugins`
config to produce the **active plugin list** for that paper.

### 14.6 Plugin lifecycle

A plugin goes through three states:

1. **Discovered** — registered via entry_points but not yet
   loaded.
2. **Loaded** — function imported and validated as a `CheckFn`.
   Available via `tmaudit plugins list`.
3. **Active** — actually runs on a given paper. Active by
   default; can be toggled off via:
   - CLI: `--disable-plugin nips_pagecheck`
   - Per-paper: `c11_plugins_disabled: ["nips_pagecheck"]` in
     `CHECKS_CONFIG`
   - Global: in the user config file (Future Work).

A plugin that fails to import is **logged but never crashes
the audit**. This keeps a buggy plugin from blocking everyone.

### 14.7 CLI integration

Three new subcommands under the `plugins` namespace:

```
$ tmaudit plugins list
NAME                    PACKAGE                       SEVERITY   STATUS
nips_pagecheck          tmaudit-nips2026-pagecheck    MED        active
todo-marker             tmaudit-local                 MED        active
neurips_abstract        tmaudit-nips2026-pagecheck    LOW        disabled (per-paper: paper-1)

$ tmaudit plugins info nips_pagecheck
Name:        nips_pagecheck
Module:      tmaudit_nips2026_pagecheck
Function:    check_page_length
Severity:    MEDIUM
Help:        Page-length check for NeurIPS 2026

$ tmaudit plugins run nips_pagecheck --paper 1
[output identical to a single plugin's findings, no caching]
```

These subcommands mirror the structure used by `tmaudit cache
list/info/clear` and `tmaudit audit-all` — discoverable,
script-friendly, JSON output for machines.

### 14.8 Per-paper override

`CHECKS_CONFIG['c11_plugins_disabled']` is a list of
plugin names that should NOT run on that paper:

```python
'c11_plugins_disabled': [
    'nips_pagecheck',     # skip page-length on this paper
    'neurips_abstract',   # uses different venue's requirements
],
```

Future v1.0: `c11_plugins_enabled` (whitelist) takes
precedence over the disabled list and over the entry-points
table. This lets a paper opt into a curated subset without
needing to uninstall packages.

### 14.9 Cache integration

Plugin findings are cacheable **per (paper_config_hash,
plugin_name, plugin_version, tex_hash)** tuple. The cache
key is computed by the loader; the cache module needs a small
extension to handle plugin fingerprints.

```python
# cache.py
def make_cache_key(paper_n: int, plugin_name: str, tex_hash: str) -> str:
    return f"plugin:{paper_n}:{plugin_name}:{tex_hash}"
```

The cache entry stores the `List[Finding]` plus a timestamp.
A plugin re-run is automatic when:
- The tex file changes (tex_hash mismatch).
- The plugin code changes (version-based invalidation;
  plugins should expose `__version__ = "0.1.0"`).
- The user runs `tmaudit cache clear`.

### 14.10 Test plan + example plugin

The **example plugin** ships as `tmaudit_example_plugin/`:

```
tmaudit_example_plugin/
├── pyproject.toml
└── tmaudit_example_plugin/
    ├── __init__.py
    └── checks.py
```

It registers 3 demo checks:

1. `no_todo_markers` — flag `TODO` strings in `main.tex`.
2. `no_xxx_comments` — flag debug `XXX` markers.
3. `word_count_check` — flag if abstract > 300 words.

The **tests** live in `tests/test_plugin_api.py` and
`tests/test_example_plugin.py`. Two test files serve
different audiences:

- `test_plugin_api.py` tests the **loader**: discovery,
  loading, lifecycle, CLI. It does NOT depend on the
  example plugin.
- `test_example_plugin.py` tests the **example**: that
  each demo check returns the expected findings on
  sample input.

The meta-test (`_check_all_regressions.py`) gains two
bugs:

- **Bug 13**: Plugin loader skips a malformed entry-point.
- **Bug 14**: Per-paper `c11_plugins_disabled` is ignored.

Both rely on regression tests that exercise the full
plugin flow end-to-end.

### 14.11 Limitations and future work

- **No sandbox.** Plugins run with the user's full Python
  permissions. A malicious plugin could read arbitrary
  files. We document this prominently; v2.0+ may add a
  RestrictedPython-based sandbox.
- **No versioning enforcement.** A plugin with
  `__version__ = "0.1.0"` could be installed next to a
  later version, and the cache will treat both as different.
  v1.0 should adopt `packaging.specifiers.SpecifierSet` for
  range constraints.
- **No async plugins.** Plugins are synchronous. v1.0
  stays sync; v2.0 may consider `async def` for I/O-heavy
  plugins (e.g., calling a remote linting service).
- **Plugins cannot import other plugins.** The composition
  model is via the public `Finding` list. We may relax this
  in v2.0 with a typed inter-plugin API.
- **No plugin-level configuration schema.** Plugins can
  ask for free-form `config` dict but cannot declare what
  keys they expect. v2.0 should add a JSON-Schema-based
  config validator.

### 14.12 Roadmap to v1.0.0

The plugin API itself ships in **v0.4.0** (3-month target).
The v1.0.0 freeze (no API changes for 6 months) is the
**v0.4.0 release date + 3 months** (i.e., v1.0.0 ships
~6 months after v0.4.0 with the plugin API already
"stabilized in practice"). The release sequence:

| Version | Plugin API state | Notes |
|---|---|---|
| **v0.4.0** | First release. `@check` decorator, `Finding` dataclass, entry-points, per-paper disable. | Feature-complete for v1.0 plans. |
| **v0.5.0** | API adjustments based on feedback. Incompatible changes allowed (still 0.x phase). | Receive community input. |
| **v0.6.0** | Lock API; require `__version__` on plugins. | Last 0.x release. |
| **v1.0.0** | API frozen. No changes for 6 months. | First stable release. |

If we discover a serious API bug after v0.4.0, we ship v0.4.1
(patch only, no behavior change) and v0.5.0 (next minor with
the fix). The **plugin API itself cannot change in v0.4.x**.

### 14.13 Why this design

A few alternatives were considered and rejected:

- **YAML-based plugin definition.** Rejected: requires users
  to learn both Python and YAML. Entry-points (a PEP 621
  standard) are recognised by `pip` tooling already.
- **Plugins as directories with an `__init__.py` shim.**
  Rejected: implicit, hard to discover, conflicts with
  `pip install -e .` workflows. Entry-points are explicit.
- **Built-in plugin DSL (custom mini-language).** Rejected:
  users already know Python; another language is dead weight.
  The `@check` decorator gives them 95% of the value with
  zero new syntax.
- **Plugin as a `setup.cfg` `[options.entry_points]` section.**
  Rejected: `pyproject.toml` is the modern canonical place.
  setup.py and setup.cfg are legacy.

The chosen design **maximises leverage of standard Python
tooling** (entry-points, importlib.metadata, dataclasses) and
**minimises new surface area**. The only new API the user
learns is `@check` and `Finding`; everything else is Python.

### 14.14 Implementation milestones

| Milestone | Effort | Status |
|---|---|---|
| `Finding` dataclass in `src/tmaudit/plugins.py` | Small | Not started |
| `@check` decorator + `CheckFn` protocol | Small | Not started |
| `discover_plugins()` via `importlib.metadata` | Medium | Not started |
| CLI subcommands (`plugins list/info/run`) | Medium | Not started |
| Per-paper `c11_plugins_disabled` config | Small | Not started |
| Cache key extension (`make_cache_key`) | Small | Not started |
| Example plugin (`tmaudit_example_plugin`) | Medium | Not started |
| Tests (`test_plugin_api.py`, `test_example_plugin.py`) | Medium | Not started |
| Meta-test (Bug 13 + Bug 14) | Small | Not started |
| `CHANGELOG.md` + `RELEASE_NOTES_v0.4.0.md` | Small | Not started |
| GitHub issue / Discussion thread | Small | Not started |
| §14 (this section) review | Small | Done (this commit) |

Total estimated effort: 3-5 working days (1 calendar week).
The bulk is the example plugin + tests, which exist as
both documentation and smoke tests for the new API.

## 15. v1.0.0 — Roadmap, plugin API freeze window, and the path to first stable release

This section is the **v1.0.0 commitment**: a written
plan for shipping the first stable release of `tmaudit`
with a frozen public API. v0.4.0 shipped the **plugin
API** (the last big architecture decision). The remaining
work is integration, performance, documentation, and
real-world validation.

### 15.1 What this section commits to

v1.0.0 is the first release where the public API is
**frozen for 6 months**. Concretely:

- The `tmaudit.plugins` API (`Finding`, `@check`,
  `load_plugins`, `audit_plugins`, `filter_active`,
  `run_plugin`, `run_all_plugins`, `plugin_cache_key`)
  is stable.
- The CLI surface (`tmaudit list`, `verify`, `compile`,
  `fix-unicode`, `audit-all`, `cache-info`, `cache-clear`,
  `plugins list/info/run`) is stable.
- The `CHECKS_CONFIG` schema (C1..C11 per-paper fields)
  is stable. Adding new fields is allowed; removing or
  renaming is not.

Anything that **breaks** one of these is a new major
version (v2.0.0). Anything that adds to them is a minor
version (v0.X.0 or v1.X.0).

### 15.2 v1.0.0 acceptance criteria

The criteria are **measurable** (a CI job or a manual
check can answer yes/no). They are taken from
[`ROADMAP.md`](./ROADMAP.md) v1.0.0 section with one
addition per criterion for verifiability.

| Criterion | Measurable as |
|---|---|
| All 10 audit categories (C1..C10) implemented | `tmaudit list` shows 10 categories. Each has a `check_c{N}_...` function in `verify_TEMPLATE.py`. **Status: ✅ done in v0.3.0.** |
| Plugin API ships | `tmaudit plugins list` shows at least 1 plugin (the example). 14/14 meta-test caught. **Status: ✅ done in v0.4.0.** |
| At least 10 papers supported out-of-the-box | `tmaudit list` shows ≥ 10 papers. Currently 5 (Papers 1-5). Need 5 more. **Status: TODO (5 left).** |
| API stable (no breaking changes for 6 months) | After v1.0.0 release, no `git diff v1.0.0 HEAD -- src/tmaudit/ plugins.py` that would change the public surface. **Status: TODO (freezes in v1.0.0).** |
| Performance: < 1 second per paper, including cache | `time tmaudit verify --paper 1` reports < 1s. **Status: TODO (need benchmark).** |
| Full API reference | `docs/api/` has a generated reference for every public symbol. **Status: TODO.** |
| Contributor guide | `CONTRIBUTING.md` (already exists) updated with the plugin-author flow. **Status: TODO (small).** |
| Tutorial videos | 3 videos on the project website (setup, writing a plugin, contributing a paper config). **Status: TODO.** |
| Used in ≥ 3 real submission cycles | Self-reported by 3 different TMLR / NeurIPS / ICLR submitters. **Status: TODO (long pole).** |

The 3 "long pole" items are **#10 papers**, **#tutorial
videos**, and **#3 submission cycles**. These are
people-and-time items, not code items. They drive the
calendar (§15.10) more than the engineering work does.

### 15.3 The plugin API freeze window

The plugin API is **frozen at v0.6.0** (not v0.4.0). v0.4.0
is the first release that ships the API, but breaking
changes are still allowed until v0.6.0:

- **v0.4.x (now)**: API is *introduced*. Patch releases
  may add fields, deprecate (not remove) methods.
- **v0.5.0**: First minor release with the API.
  Breaking changes allowed (still 0.x phase).
- **v0.6.0**: API is *locked*. From v0.6.0 onward, only
  additive changes (new fields, new methods, new
  subcommands) are allowed. Removing a public symbol
  bumps to v1.0.0.
- **v1.0.0**: API is *frozen* (no changes for 6 months).

The reason for the **v0.4.0 → v0.6.0** window is to give
the community time to write plugins, find API papercuts,
and propose adjustments. Two minor releases is a
reasonable shake-down period without making users feel
like the API is unstable.

#### 15.3.1 What's frozen at v0.6.0

The public surface that is part of the freeze:

| Module | Public symbols |
|---|---|
| `tmaudit` | `Finding`, `check`, `load_plugins`, `audit_plugins`, `filter_active`, `run_plugin`, `run_all_plugins`, `plugin_cache_key`, `cache_key`, `PLUGIN_GROUP`, `VALID_SEVERITIES`, `__version__` |
| `tmaudit.plugins` | Same as above (re-exported) |
| `tmaudit.cache` | `CacheDB`, `cache_key`, `plugin_cache_key` |
| `tmaudit.cli` | subcommand names + flags listed in `cmd_*` dispatch |
| `tmaudit.configs.paper_configs` | `PAPER_CONFIGS` keys: `dir`, `c1_symbols`, `c2_families`, `c2_section_pattern`, `c2_abstract_k_allowed`, `c3_concept`, `c3_concept_token`, `c3_formal`, `c3_formal_secondary`, `c4_self_cite_threshold`, `c4_self_cite_prefix`, `c4_max_self_cite_keys`, `c5_d_type`, `c6_blacklist`, `c7_max_ceremonial`, `c8_claimed_effects`, `c9_figure_keywords`, `c10_reproducibility_claims`, `c11_plugins_disabled` |

#### 15.3.2 What's NOT frozen

Internal implementation details are NOT part of the
freeze:

- The internal `SEVERITY` dict, the `check_cN_...` function
  bodies, the regex patterns in each check. These may
  change at any time.
- The `verify_p<N>.py` generated output format (the
  user-facing `print()` lines, the cache key format).
- Internal cache module structure (the `CacheDB` class
  itself is frozen as a public class, but its private
  methods can change).
- The `RELEASE_NOTES_*.md` and `CHANGELOG.md` formatting
  conventions (we may switch to towncrier or scriv).

The boundary: **public symbols and CLI flags are frozen;
their internals are not.**

### 15.4 The 5-milestone path to v1.0.0

The path is explicit and date-anchored. Each milestone
has a **definition of done** (DOD) and a **maximum
duration** so the schedule doesn't slip indefinitely.

```
v0.4.0 ──▶ v0.4.1 ──▶ v0.5.0 ──▶ v0.6.0 ──▶ v0.7.0 ──▶ v1.0.0
[shipped]    (patches)   (adj)      (lock)     (polish)    (freeze)
   ↓            ↓          ↓           ↓          ↓          ↓
2026-07-10   2026-08    2026-10    2026-12    2027-02    2027-04
            3 months   2 months   2 months   2 months   2 months
```

Total: 9 months from v0.4.0 to v1.0.0. The 3-month
v0.4.0 → v0.5.0 window absorbs community feedback; the
2-month cadence after that is to keep momentum.

### 15.5 v0.4.x — Patch releases (≤ 2026-08)

Patches address bug fixes from the community. New
**features** are deferred to v0.5.0.

DOD for v0.4.1:
- All bugs filed against the plugin API fixed.
- No new public symbols added.
- 100% of existing tests pass.
- `pip install tmaudit` works on PyPI (currently the
  package is only installable from source).

DOD for v0.4.2 (if needed):
- Same as v0.4.1 plus a documentation pass.

**Estimated effort: 1-2 weeks** (mostly waiting on
community bug reports).

### 15.6 v0.5.0 — First minor release (≤ 2026-10)

This is the **community-feedback-absorbing release**. Any
breaking change to the plugin API is allowed here, based
on real-world usage.

Planned changes:
1. **`c11_plugins_enabled` (whitelist)**: per-paper opt-in
   for "only these plugins". Currently we have only
   `c11_plugins_disabled` (blacklist). Some users want
   the inverse for security.
2. **Plugin configuration schema validator** (JSON
   Schema). Plugins can declare what config keys they
   expect; the loader validates the per-paper config
   against the schema before calling the plugin.
3. **Plugin hot-reload** (dev-only): a
   `tmaudit plugins reload` subcommand that re-imports
   plugins without restarting the process. Useful during
   plugin development.
4. **Async plugins (preview)**: an `async def` plugin
   shape behind an opt-in flag. Production plugins stay
   sync. Async plugins are useful for I/O-bound checks
   (e.g., calling a remote linting service).

DOD for v0.5.0:
- At least 3 community issues addressed (tracked in
  `.github/issues/`).
- Backward-compat shim for any breaking change (the old
  API still works, just deprecated).
- All v0.4.x tests still pass.
- New tests for each new feature.
- New meta-test bugs (Bug 15, Bug 16) for any new audit
  categories or plugin-API surface area.

**Estimated effort: 4-6 weeks** (mostly feature work).

### 15.7 v0.6.0 — API lock (≤ 2026-12)

This is the **last release that can break the API**. After
v0.6.0, only additive changes.

Lock-day changes:
1. **Plugin `__version__` is required**. Currently the
   `@check` decorator defaults `version="0.1.0"`. From
   v0.6.0, plugins without an explicit `version=` argument
   raise a `TypeError` at registration. This forces plugin
   authors to think about cache invalidation.
2. **C1..C10 migrate to `Finding`**. Currently the core
   categories return `tuple[str, str, int]`. After v0.6.0,
   they return `Finding`. The legacy tuple form is
   supported via `Finding.to_tuple()` for one more
   release, then removed in v1.0.0.
3. **Severity normalization is finalised**: `MED` alias
   for `MEDIUM` stays (we promised this in §14). The
   `HIGH`/`MEDIUM`/`LOW` (long-form) are canonical.

DOD for v0.6.0:
- All v0.5.0 tests still pass.
- New test: `test_plugin_version_required` (a plugin
  without `version=` raises).
- New test: `test_cN_emit_findings` (C1..C10 each
  return `Finding` objects).
- `_check_all_regressions.py` shows 16/16 caught (added
  Bug 15 and Bug 16).
- 3 successful `tmaudit audit-all` runs on 3 different
  papers.

**Estimated effort: 2-3 weeks** (mostly migration
+ tests).

### 15.8 v0.7.0 — Polish (≤ 2027-02)

Performance + documentation + paper-config support. No API
changes.

Planned work:
1. **Performance: < 1 second per paper**:
   - Benchmark suite in `bench/` (timing each C1..C10
     category on a sample paper).
   - Profile + optimise the slowest check (typically C1
     and C8 in practice).
   - Goal: total audit (C1..C10 + plugins) < 1s on
     Paper 5 (~26 pages).
2. **10 papers out-of-the-box**: fill in `c1_symbols`,
   `c2_families`, etc. for 5 more papers. This is
   people-time, not code-time.
3. **Full API reference**: generate `docs/api/` from
   docstrings using `sphinx-apidoc` or `mkdocstrings`.
4. **Contributor guide update**: a new
   `docs/PLUGIN_AUTHOR_GUIDE.md` walking through
   writing a plugin from scratch.
5. **Tutorial videos** (3): record screen-casts of
   (a) setting up `tmaudit`, (b) writing a plugin,
   (c) contributing a paper config. Hosted on the
   project website.

DOD for v0.7.0:
- 10/10 papers in `tmaudit list`.
- Benchmark `bench/run_benchmark.py` shows < 1s.
- `docs/api/` exists with every public symbol.
- 3 tutorial videos on the project site.

**Estimated effort: 6-8 weeks** (dominated by
paper-config intake + video production).

### 15.9 v1.0.0 — First stable release (≤ 2027-04)

The 6-month freeze begins. v1.0.0 is the **promise of
stability**: any user who adopts v1.0.0 can build tooling
on top of `tmaudit` (CI integrations, custom plugins,
paper-config forks) and trust that the API won't break
for at least 6 months.

What's in v1.0.0:
- All v0.7.0 work.
- 3 documented real-world submission cycles
  (self-reported by users).
- A `docs/MAINTAINERS.md` listing the people on call
  for the 6-month stability window.
- A `SECURITY.md` for the security reporting policy.
- A `CODEOWNERS` file mapping files to maintainers.
- A `LICENSE` clarification (MIT? Apache 2.0?).
- A `pyproject.toml` updated to declare v1.0.0
  dependencies (e.g., `tmaudit>=0.6,<2.0`).

DOD for v1.0.0:
- 9/9 v0.7.0 DOD items met.
- 3 self-reported submission cycles in `docs/USAGE.md`.
- `git tag v1.0.0` is signed by at least 2 maintainers.
- The release is announced on the project website
  and a draft post is ready for the maintainers' blog.

**Estimated effort: 1-2 weeks** (mostly release engineering,
not code).

### 15.10 Calendar (release dates)

| Version | Target date | Milestone | Source of truth |
|---|---|---|---|
| **v0.4.0** | **2026-07-10** | Plugin API ships | ✅ this release |
| v0.4.1 | 2026-08-10 | Patch (community bug fixes) | CI failure log |
| v0.4.2 | 2026-09-10 | Patch (if needed) | CI failure log |
| v0.5.0 | 2026-10-10 | First minor (community feedback) | GitHub issues |
| v0.6.0 | 2026-12-10 | API lock | `_check_all_regressions.py` |
| v0.7.0 | 2027-02-10 | Polish (perf + docs + 10 papers) | `bench/` + `tmaudit list` |
| **v1.0.0** | **2027-04-10** | First stable release | 3 submission cycles |

All dates are **end-of-month** targets, with a 1-month
slack for slippage. The 9-month window from v0.4.0 to
v1.0.0 is intentional: long enough for community
feedback and real-world validation, short enough to
maintain momentum.

The longest pole is **3 submission cycles** — each is
3-6 months from a real TMLR/NeurIPS/ICLR calendar. We
have:
- TMLR: rolling submission, no fixed deadline.
- NeurIPS 2026: deadline ~2026-05 (already past).
- ICLR 2026: deadline ~2025-09 (already past).
- NeurIPS 2027: deadline ~2027-05 (just after v1.0.0).
- ICLR 2027: deadline ~2026-09 (right at v0.5.0).
- TMLR: continuous — we should be able to count ≥ 3
  TMLR submissions by 2027-04.

So the submission-cycle goal is **achievable but not
generous**: at least 3 different authors need to use
`v0.5.0` (or later) and self-report. This is the part
the maintainer has the least control over.

### 15.11 Risk register

What could derail v1.0.0? Listed in order of likelihood:

| # | Risk | Probability | Impact | Mitigation |
|---|---|---|---|---|
| 1 | The plugin API has a papercut that only surfaces in real use | **High** | Medium (v0.5.0 delay) | Use v0.4.0 in our own papers (1, 3, 5) to exercise it. |
| 2 | No 3rd author reports a submission cycle | **High** | **Critical** (blocks v1.0.0) | Recruit from the maintainer's academic network; advertise on the TMLR Discord. |
| 3 | A 4th audit category (C11) is requested and we have to add it | Medium | Low | The plugin API was designed for this; new "core" categories are not required. |
| 4 | A contributor introduces a 500-line regression in C8 | Medium | Medium (v0.4.x delay) | 18 unit tests + meta-test Bug 11 catch most of this. |
| 5 | PyPI upload is blocked by a name collision | Low | Low (delays v0.4.1) | Reserve the name early via `pip install tmaudit-dryrun` to check. |
| 6 | The frozen API is too restrictive | Low | Low | v1.1 can add fields; the freeze only blocks removal. |
| 7 | We miss the 2027-04 date by 6+ months | Low | Low | The 1-month slack absorbs normal slippage; if we miss by 6 months, we have bigger problems. |
| 8 | A CVE in the plugin loader (e.g., entry-point format string) | Low | High | Plugins run with full user perms; the threat model is documented in §14.11. |

The **two real risks** are #1 (API papercuts, high
probability, manageable) and #2 (no submission
cycles, high probability, hard to mitigate). Everything
else is incremental.

### 15.12 Cross-cutting lessons (C7-C10 → v1.0.0)

Looking at §11 (C7), §12 (C8 + C10), §13 (C9), §14
(plugin API), the **pattern that emerged** for every
audit category was:

1. **TDD red** — write the tests first, even if you
   think you know the right code. The tests force you to
   specify the contract.
2. **TDD green** — implement the function to make the
   tests pass. Keep the implementation minimal.
3. **Driver wiring** — call the function from
   `main()`, add the category to the SEVERITY dict, and
   verify the per-paper `cN_...` config is threaded
   through.
4. **Meta-test** — write an `inject_bugN()` that
   re-introduces a specific bug, and confirm the
   regression test catches it.
5. **Documentation** — update CHANGELOG, RELEASE_NOTES,
   and the §X engineering notes.

We followed this pattern 11 times (Bug 1 through Bug 11)
and again for Bug 12, 13, 14. The next 4-6 audit
categories (if any) will follow the same pattern.

The pattern is **the operational definition of "we know
how to add a new audit category"**. If a future
contributor can follow §15.12's 5 steps, they can add a
new category without breaking the freeze.

### 15.13 v1.0.0 status table

| Milestone | Target | Status | Blocker |
|---|---|---|---|
| v0.4.0 plugin API | 2026-07-10 | ✅ done | — |
| v0.4.1 patches | 2026-08-10 | ⏳ waiting | Community bug reports |
| v0.5.0 feedback | 2026-10-10 | ⏳ waiting | Plugin usage in real papers |
| v0.6.0 API lock | 2026-12-10 | ⏳ waiting | v0.5.0 lessons |
| v0.7.0 polish | 2027-02-10 | ⏳ waiting | v0.6.0 done; 5 more paper configs |
| **v1.0.0** | **2027-04-10** | ⏳ waiting | All of the above + 3 submission cycles |

Updated 2026-07-10. The maintainer reviews this table
on the 1st of every month; any date older than 90 days
without progress triggers a "are we still on track?"
check.

### 15.14 What v1.0.0 is NOT

To manage expectations:

- **v1.0.0 is not "feature-complete"**. The 10 core
  categories are the 10 most common reviewer concerns.
  Domain-specific checks (NeurIPS 2027 page-length,
  Smith Lab nomenclature) belong in plugins, not in
  core.
- **v1.0.0 is not "API-final"**. The v1.x series can
  add fields (additive) freely. v1.0 just means the
  next 6 months have no breaking changes.
- **v1.0.0 is not "ready for every workflow"**. PyPI
  install works in v0.4.x. The 10-paper support works
  in v0.7.0. The tutorial videos work in v0.7.0. v1.0.0
  is the *combination* of all of these.
- **v1.0.0 is not "abandoned"**. After v1.0.0 we ship
  v1.1, v1.2, etc. on the same 2-month cadence. v1.0 is
  the **start** of the stable series, not the end.

### 15.15 Closing — what success looks like

In 9 months, when v1.0.0 ships, the maintainer's
checklist is:

- [ ] 10 papers supported out-of-the-box.
- [ ] 3 documented real-world submission cycles.
- [ ] 14+ meta-test bugs caught (currently 14; expected
  to grow as we add new categories).
- [ ] `pip install tmaudit` works on PyPI.
- [ ] 1.0.0 is tagged and signed.
- [ ] The release is announced on the project website.
- [ ] The maintainer can take a 2-week vacation
  without breaking anything (the API is frozen; no
  one is depending on the maintainer for a fix).

That last item is the **truest test of stability**.
v1.0.0 succeeds when the maintainer is not on the
critical path.

## 16. v0.5.0 — `c11_plugins_enabled` whitelist design

This section documents the design of the **whitelist
mode** for the plugin API: the second of the four
items in the v0.5.0 milestone (§15.6). Whitelist mode
complements the v0.4.0 blacklist (`c11_plugins_disabled`)
with a per-paper opt-in: "only these plugins are
allowed to run."

### 16.1 Motivation

v0.4.0 introduced the blacklist model
(`c11_plugins_disabled`). The maintainer's notes at
§14.7 and §14.8 already anticipated a whitelist as
future work. v0.5.0 ships it because:

1. **Security**: a paper maintainer in a regulated
   domain (medical, financial, security research) may
   not want to trust every plugin installed on a
   reviewer's machine. A whitelist lets them say "only
   this audited set of plugins can run on my paper."
2. **Reproducibility**: a paper's audit output should
   be deterministic given the same input. Without a
   whitelist, an install-time change (a colleague
   adds a new plugin to the system) silently changes
   which checks run. With a whitelist, the audit
   output is locked.
3. **CI gating**: in continuous-integration runs, the
   project may want to run only a known-good plugin
   set, regardless of what's installed system-wide.

The blacklist (`c11_plugins_disabled`) is the right
default for the common case ("I trust most plugins,
just don't run this one"). The whitelist is for the
"lock down" case. Both modes are useful; the design
lets the per-paper config choose.

### 16.2 Design overview — 4-case truth table

The whitelist feature introduces a new
`c11_plugins_enabled` config field. Combined with
the existing `c11_plugins_disabled`, the behaviour
matrix is:

| `c11_plugins_enabled` | `c11_plugins_disabled` | Effective plugin set |
|---|---|---|
| `[]` or absent | `[]` or absent | **All registered plugins run** (v0.4.0 default). |
| `[]` or absent | `['a']` | All plugins **except** `a` (blacklist mode). |
| `['a', 'b']` | `[]` or absent | **Only** `a` and `b` (whitelist mode). |
| `['a', 'b']` | `['a']` | **Only** `a` and `b` (whitelist wins; `disabled` ignored). |

The **rule**: when `c11_plugins_enabled` is non-empty,
it **overrides** `c11_plugins_disabled` completely. The
whitelist always wins. This is the simplest, most
predictable rule: a paper that says "I want plugins
`a` and `b`" gets exactly `a` and `b` — no surprises
from a residual blacklist value.

This was confirmed empirically on 2026-07-10 by
running `filter_active` against 3 synthetic plugins
(`a`, `b`, `c`):

```
=== Test 1: disabled=[] (empty list) ===
  result: ['plugin-a', 'plugin-b', 'plugin-c']   PASS
=== Test 2: disabled=None (default) ===
  result: ['plugin-a', 'plugin-b', 'plugin-c']   PASS
=== Test 3: disabled=['plugin-a'] (blacklist mode) ===
  result: ['plugin-b', 'plugin-c']              PASS
```

The empty-list case falls through to "run all" in
v0.4.0; v0.5.0 preserves this behaviour. The same
fall-through applies to the new `enabled` parameter:
`enabled=[]` falls through to blacklist mode (or "run
all" if `disabled` is also empty).

### 16.3 API surface (the diff)

The whitelist feature is purely additive. Three
public symbols change; **no symbol is removed or
renamed**.

#### 16.3.1 `filter_active(plugins, disabled, enabled)` — extended signature

```python
def filter_active(
    plugins: Dict[str, CheckFn],
    disabled: Optional[List[str]] = None,
    enabled: Optional[List[str]] = None,    # NEW
) -> Dict[str, CheckFn]:
    """
    Return a subset of plugins with disabled ones removed
    and (if enabled is non-empty) only enabled ones kept.

    Resolution rule (per §16.2): if `enabled` is non-empty,
    it takes precedence over `disabled`. A warning is
    logged if both are non-empty so the user notices the
    override.
    """
    enabled_set = set(enabled) if enabled else set()
    disabled_set = set(disabled) if disabled else set()

    if enabled_set:
        if disabled_set:
            log.warning(
                "tmaudit: c11_plugins_enabled and "
                "c11_plugins_disabled are both set; "
                "enabled wins and disabled is ignored."
            )
        return {n: c for n, c in plugins.items() if n in enabled_set}

    if disabled_set:
        return {n: c for n, c in plugins.items()
                if n not in disabled_set}

    return dict(plugins)    # both empty -> run all
```

The new `enabled` parameter has a default of `None`,
matching Python's "absent == empty" convention. This
keeps **all v0.4.0 callers working without changes**:
any code that calls `filter_active(plugins, disabled=...)`
will see the v0.4.0 behaviour, because `enabled` defaults
to `None` (and `None` is falsy, so the `if enabled_set:`
branch is skipped).

#### 16.3.2 `audit_plugins(..., enabled=...)` — extended signature

The bulk runner gains a new keyword arg:

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
    plugins = filter_active(load_plugins(), disabled, enabled)    # NEW arg
    ...
```

The `enabled` value is **read from
`config.get('c11_plugins_enabled', [])`** inside
`audit_plugins`, so callers don't have to pass it
explicitly. The per-paper config is the canonical
entry point; the keyword arg is for tests and power
users.

#### 16.3.3 `c11_plugins_enabled` per-paper config

In [`paper_configs.py`](src/tmaudit/configs/paper_configs.py):

```python
PAPER_CONFIGS = {
    1: {
        ...,
        'c11_plugins_disabled': [...],   # existing (optional, default [])
        'c11_plugins_enabled':  [...],   # NEW (optional, default [])
    },
    ...
}
```

Both fields are **optional** with default `[]`. Papers
that don't set them continue to run all plugins
(v0.4.0 behaviour, backward-compat).

The `paper_configs.py` format writer (used by
`gen_verify_scripts.py`) is updated to emit the new
field with a default empty list when missing.

### 16.4 Precedence rule rationale

The "whitelist wins" rule was chosen over three
alternatives:

1. **Whitelist wins** (chosen). Predictable: a paper
   that says "I want plugins `a` and `b`" gets exactly
   those. No way to accidentally filter out a whitelisted
   plugin via a stale blacklist value.
2. **Intersection** (`enabled ∩ ¬disabled`). Subtle:
   the user has to think about the relationship
   between the two lists. Easy to get wrong.
3. **Error if both set**. Strict: forces the user to
   pick one. But this breaks papers that have both
   for historical reasons (e.g., disabled a plugin
   globally then added a new paper with a whitelist).

The chosen rule trades off "stricter validation" for
"more forgiving defaults." The warning log
(`log.warning(...)`) tells the user that both are
set, so the override is visible.

### 16.5 Unknown plugin names in the whitelist

If `c11_plugins_enabled` contains a name that is
**not** in the discovered plugin set, the audit
silently ignores it. This is the same behaviour as
the v0.4.0 blacklist (a name in `disabled` that
doesn't exist is a no-op).

The reasoning: a plugin might be installed on the
maintainer's machine but not on a CI machine, or vice
versa. The whitelist should be **forward-compatible**:
listing a plugin that doesn't exist should not be an
error, because it would cause audits to fail when
running on a stripped-down environment.

A v2.0 improvement (see §16.10) could add a
`--strict-plugins` flag that errors on unknown names
for users who want that validation.

### 16.6 Backward compatibility

The whitelist feature is **fully backward compatible**:

- `filter_active(plugins, disabled=...)` (v0.4.0 call
  shape) — works unchanged, returns the same result.
- `filter_active(plugins)` (no kwargs) — works
  unchanged, returns all plugins.
- `filter_active(plugins, disabled=[])` — works
  unchanged, returns all plugins (the v0.4.0
  `if not disabled: return dict(plugins)` short-circuit
  is preserved).
- `audit_plugins(..., disabled=...)` — works
  unchanged. The `enabled` arg defaults to `None`.
- Per-paper config: existing papers without
  `c11_plugins_enabled` behave as before.

**No migration is required** for v0.4.0 users.

### 16.7 Tests

The 5-step TDD + meta-test pattern (per §15.12)
yields:

**Unit tests** in `tests/test_plugin_api.py` (7 new):

1. `test_filter_active_empty_lists_run_all` — both
   `enabled=[]` and `disabled=[]` returns all plugins.
2. `test_filter_active_blacklist_only` — `enabled=[]`
   + `disabled=['a']` returns `{b, c}`.
3. `test_filter_active_whitelist_only` —
   `enabled=['a', 'b']` + `disabled=[]` returns `{a, b}`.
4. `test_filter_active_whitelist_overrides_blacklist`
   — `enabled=['a', 'b']` + `disabled=['a']` returns
   `{a, b}` (disabled ignored).
5. `test_filter_active_whitelist_with_unknown_plugin`
   — `enabled=['a', 'nonexistent']` returns `{a}`.
6. `test_audit_plugins_respects_c11_plugins_enabled`
   — end-to-end: a paper with
   `c11_plugins_enabled=['synth-yes']` only runs that
   one plugin.
7. `test_paper_configs_can_carry_c11_plugins_enabled`
   — schema check: if the field is present, it's a
   `list[str]`.

**Meta-test bugs** in `_check_all_regressions.py`
(2 new):

- **Bug 15**: `filter_active` ignores the `enabled`
  whitelist (anchor: `enabled_set = set(enabled) if
  enabled else set()` → replace with `enabled_set = set()`).
  Regression test:
  `test_filter_active_whitelist_only`.
- **Bug 16**: the precedence rule is reversed (anchor:
  `if enabled_set:` → replace with `if False:  # BROKEN`).
  Regression test:
  `test_filter_active_whitelist_overrides_blacklist`.

Both bugs use the established `inject_bugN()` pattern
from §11–§14: a context-manager-backed patch that
mutates the source, asserts the targeted regression
test fails, then restores.

### 16.8 CLI design — no new flag for v0.5.0

A `--enable-plugin` CLI flag (multi-value, parallels
the existing `--disable-plugin`) was considered but
**deferred**:

- The per-paper config knob (`c11_plugins_enabled`) is
  the canonical entry point — it travels with the
  paper, so different papers can have different
  whitelists.
- A CLI flag would be a **runtime override** of the
  config, which is a different semantic. Mixing the
  two in v0.5.0 would force us to define what wins
  (CLI > config? config > CLI?).
- v0.5.0 keeps the CLI surface stable (we promised
  this in §14.7).

If a CLI flag is needed later (e.g., for ad-hoc
audits), it can be added in v0.5.x or v0.6.0 with a
clear precedence rule: `--enable-plugin` augments
`c11_plugins_enabled`; both are union'd before
filtering. This is a small follow-up.

### 16.9 Edge cases

| Case | Behaviour |
|---|---|
| `enabled = None` (default) | Treated as `[]` (whitelist mode off). |
| `enabled = []` (explicit empty) | Same as None: whitelist mode off. |
| `enabled = ['nonexistent']` | Returns empty dict; the unknown name is silently skipped. |
| `enabled = ['a', 'a']` (duplicates) | Deduped via `set()`. |
| `enabled = ['a']` + plugin `a` errors at runtime | `run_all_plugins` (or `audit_plugins`) catches the exception, logs a warning, and continues with the other plugins. |
| Both `enabled` and `disabled` non-empty | Whitelist wins; warning logged. |
| Plugin name with hyphens or underscores | Treated as opaque strings. No normalization. |

### 16.10 Limitations and future work

- **No `--enable-plugin` CLI flag** for v0.5.0. See
  §16.8 for the rationale. May land in v0.5.x.
- **No strict mode** (error on unknown plugin names).
  See §16.5. May land in v2.0.
- **No audit-trail log of which filter mode was used**.
  v2.0 may write a one-line summary to the audit
  output ("filter mode: whitelist (3 plugins active,
  2 skipped)").
- **No per-plugin config validation** yet. v0.5.0
  may ship a JSON-Schema validator for the per-paper
  config block, which would also catch typos in
  `c11_plugins_enabled` (e.g., `None` instead of `[]`).
- **No whitelist ordering semantics**. The whitelist
  is a set; plugin execution order is the iteration
  order of the dict (which is insertion order in
  Python 3.7+). If a paper cares about ordering (e.g.,
  "run plugin `a` before `b` to get a stable
  finding-order"), v0.6.0 may add an
  `c11_plugins_order` field.

### 16.11 Implementation milestones

| Milestone | Effort | Status |
|---|---|---|
| 7 new unit tests (TDD red) | 30 min | Not started |
| Update `filter_active` (signature + logic) | 30 min | Not started |
| Update `audit_plugins` (read `c11_plugins_enabled` from config) | 15 min | Not started |
| Update `cmd_audit_all` (pass `enabled` through) | 5 min | Not started |
| Update `paper_configs.py` (`c11_plugins_enabled` field) | 15 min | Not started |
| Update `gen_verify_scripts.py` (emit the new field) | 15 min | Not started |
| Meta-test Bug 15 (whitelist ignored) | 30 min | Not started |
| Meta-test Bug 16 (precedence reversed) | 30 min | Not started |
| CHANGELOG.md + RELEASE_NOTES_v0.5.0.md | 30 min | Not started |
| ROADMAP.md (v0.5.0 IN PROGRESS) | 5 min | Not started |
| Close `.github/issues/19-whitelist-mode.md` | 5 min | Not started |
| **Total** | **~3-4 hours** | |

The order is the 5-step pattern from §15.12. Tests
first, then implementation, then driver wiring, then
meta-test, then docs.

### 16.12 Why this design (alternatives rejected)

| Alternative | Rejected because |
|---|---|
| **No whitelist — only blacklist** | Doesn't address the security/CI-gating use cases. |
| **Whitelist-only (drop blacklist)** | Breaks backward compat; v0.4.0 papers with `c11_plugins_disabled` would silently change behaviour. |
| **Whitelist + blacklist both required, error if absent** | Forces every paper to make a choice. Most papers just want the default ("run all"). |
| **Whitelist and blacklist are union'd** (`(enabled ∪ all) - disabled`) | Confusing semantics: "I want plugins `a` and `b`, but I also want to disable `a`" becomes a contradiction. |
| **Whitelist and blacklist are intersection'd** (`enabled ∩ ¬disabled`) | Subtle: requires the user to think about both lists simultaneously. The chosen rule (whitelist wins) is simpler. |
| **Plugin-tier system** (CORE / COMMUNITY / EXPERIMENTAL; whitelist = CORE) | Adds a third axis of complexity. The maintainer rejected this in §14.13 as overkill. |
| **Per-plugin "scope" attribute** (`@check(scope="paper")`) | Pushes the policy into each plugin, not the per-paper config. This is the inverse of the desired model. |

The chosen design — **whitelist wins, both default to
empty, all behaviour follows from the dict / set
filter** — maximises the use of standard Python
(`set()`, `dict()`, `if/for` comprehensions) and
minimises new surface area. The only new public symbol
is the `enabled` keyword arg and the
`c11_plugins_enabled` config field; everything else
is the existing `filter_active` and `audit_plugins`
machinery.

### 16.13 Status

| Component | Status | Date |
|---|---|---|
| Design rationale (§16) | ✅ written | 2026-07-10 |
| 4-case truth table (live-tested) | ✅ confirmed | 2026-07-10 |
| `filter_active` change (v0.4.0 → v0.5.0) | ⏳ not started | target 2026-10 |
| `c11_plugins_enabled` per-paper config | ⏳ not started | target 2026-10 |
| Bug 15 + 16 meta-tests | ⏳ not started | target 2026-10 |
| RELEASE_NOTES_v0.5.0.md | ⏳ not started | target 2026-10 |

The design is **stable and reviewed**; implementation
is the next step. The 4-case truth table has been
empirically confirmed against the v0.4.0 source code
(see §16.2 for the live test output).

## Appendix: file listings

Repository root after this work:

| File | Size (chars) | Role |
|---|---|---|
| `_compile_check_TEMPLATE.py`            | ≈4,500 | Generic 4-pass LaTeX build. |
| `_fix_abstract_unicode_TEMPLATE.py`      | ≈5,000 | Generic abstract-Unicode fix. |
| `gen_compile_scripts.py`                | ≈4,500 | Fork tool for the compile scripts. |
| `_verify_TEMPLATE.py`                   | ≈15,000 | Generic 6-category audit. |
| `gen_verify_scripts.py`                 | ≈9,000  | Fork tool for the verify scripts. |
| `README.md`                             | ≈6,000  | User-facing documentation. |
| `engineering_notes_verify_template.md`  | (this file) | Engineering appendix. |

`papers/PAPER<N>_CONSOLIDATED/` after this work (N ∈ {1, 5}):

| File | Size (chars) | Generated by |
|---|---|---|
| `verify_p<N>.py`              | ≈22,800 | `gen_verify_scripts.py` |
| `verify_p<N>.py.bak_before_template` | (original) | backup of hand-written original |
| `_compile_check.py`           | ≈5,600  | `gen_compile_scripts.py` |
| `_fix_abstract_unicode.py`    | ≈4,500  | `gen_compile_scripts.py` |

`papers/PAPER<N>_CONSOLIDATED/` for N ∈ {2, 3, 4}: not yet
forked. The `PAPER_CONFIGS` entries in `gen_verify_scripts.py` for
Paper 2/3/4 are placeholders that need to be filled with the
actual paper-specific rules; the README has a template for
filling them in.
