<!--
Thanks for contributing to tmaudit!

Please fill in this template. Sections marked with `<!-- -->` are
visible only in the source file; GitHub does not render them in
the PR view. The placeholder text (after each `### Heading`) is
rendered into the PR body so you can see what to replace.
-->

## What

<!--
A clear, one-sentence summary of the change.

GOOD: "Add regression test for Bug 4 (C1 narrow window)"
GOOD: "Add Paper 6 audit config"
BAD:  "fix stuff"
BAD:  "update code"
-->

## Why

<!--
Motivation. What problem does this PR solve? Link any related
issues, paper sections, or engineering notes.

Examples:
  - Fixes #42
  - Addresses the audit false-negative reported in
    engineering_notes_verify_template.md §4
  - Implements the workflow described in
    https://github.com/.../issues/123
-->

## Type of change

<!--
Check ALL that apply. Delete any that do not.
-->

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (existing functionality changes behavior)
- [ ] Refactor (no functional change, just code cleanup)
- [ ] Documentation only
- [ ] Test only (no production code change)
- [ ] Build / CI only (no production code change)

## Affected components

<!--
Check ALL files / modules that this PR touches.
-->

- [ ] `src/tmaudit/forge.py`
- [ ] `src/tmaudit/cli.py`
- [ ] `src/tmaudit/templates/verify_TEMPLATE.py`
- [ ] `src/tmaudit/templates/compile_check_TEMPLATE.py`
- [ ] `src/tmaudit/templates/fix_abstract_unicode_TEMPLATE.py`
- [ ] `src/tmaudit/configs/paper_configs.py`
- [ ] `src/tmaudit/configs/compile_configs.py`
- [ ] `tests/`
- [ ] `hooks/`
- [ ] `.github/workflows/ci.yml`
- [ ] Documentation (`README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `engineering_notes_verify_template.md`, `act_summary.md`)
- [ ] Other: <!-- describe below -->

## Pre-merge checklist

<!--
Every box MUST be checked before the PR is merged.
The CI (`.github/workflows/ci.yml`) and the pre-commit hook
(`hooks/pre-commit`) check many of these automatically, but
the human author must still verify the rest.
-->

### Automated checks (CI runs these)

- [ ] `python -m pytest -m "not slow"` passes (the count is the sentence in `README.md`)
- [ ] `python _check_all_regressions.py` reports every injected bug caught
- [ ] `python _build_pyz.py` produces a working `tmaudit.pyz`
- [ ] `python tmaudit.pyz list` lists the correct papers
- [ ] `python _check_yaml.py` reports `ci.yml` is valid
- [ ] GitHub Actions CI is green on this branch
- [ ] Pre-commit hook passed (or `--no-verify` was justified in PR description)

### Manual checks (the author must verify)

- [ ] I have read [`CONTRIBUTING.md`](../blob/main/CONTRIBUTING.md) and followed its guidance
- [ ] If this PR adds a new audit category, a sample paper (Paper 1 or 5) still passes
- [ ] If this PR changes `verify_TEMPLATE.py`, the audit output is identical on a known paper
- [ ] If this PR changes `paper_configs.py`, the per-paper audit still produces 0 findings
- [ ] If this PR adds a regression test for a bug, I have verified the test **fails** when the bug is injected (using `_check_all_regressions.py`)
- [ ] If this PR fixes a bug, the new test is referenced from `engineering_notes_verify_template.md`
- [ ] If this PR adds a paper (Paper 6+), the `TestEndToEndAudit` test for it is added
- [ ] If this PR changes public API, the CLI still works (`tmaudit --help`, `tmaudit list`, `tmaudit verify --paper N`)
- [ ] If this PR changes the audit logic, I have manually re-run the audit on Paper 1 and confirmed 0 findings
- [ ] `CHANGELOG.md` has an entry for this change under the next version

### Documentation

- [ ] `README.md` is updated (if user-facing behavior changes)
- [ ] `CONTRIBUTING.md` is updated (if dev workflow changes)
- [ ] `CHANGELOG.md` is updated
- [ ] `engineering_notes_verify_template.md` is updated (if a bug is fixed or a new bug is discovered)

## Test plan

<!--
How did you verify the change works? Paste command output, test
logs, audit results, or screenshots.

GOOD: "Added test_forge.py::TestBug6X. Ran
       `python -m pytest -m \"not slow\"` and pasted the summary.
       The new test fails when the strict regex is substituted
       back into the template (verified via
       _check_all_regressions.py)."
GOOD: "Ran tmaudit verify --paper 1 -> 0 finding(s).
       Before this PR: 1 finding. After: 0 findings."
BAD:  "I tested it and it works."
-->

```
# Paste command output here
```

## Screenshots / output

<!--
Optional. If the change is user-visible (CLI, audit report,
PDF), paste a screenshot or the output of `tmaudit verify
--paper N`. If the change is purely internal, delete this
section.
-->

## Breaking changes

<!--
If you checked "Breaking change" above, describe:
  - What breaks?
  - Who is affected?
  - What is the migration path?

If not a breaking change, write "None" and delete this section.
-->

## Related issues / PRs

<!--
Link any related issues, PRs, or external references.
-->

- Fixes #
- Related to #
- See also #

## Reviewer notes

<!--
Anything specific you want the reviewer to focus on. Examples:
  - "I'm unsure about the regex in check_c5; please verify it
    against the test cases in §5 of engineering_notes."
  - "I considered X but went with Y because Z. Happy to
    discuss if you disagree."
  - "This is the first time I've touched the templates; please
    be extra careful about the string-literal state machine."
-->
