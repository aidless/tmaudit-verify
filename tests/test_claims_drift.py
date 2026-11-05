"""The README and CI must describe this tree.

Collection counts, the CI matrix, and the three failure-mode headings are
read back from the files a reviewer sees and compared to the tree. A frozen
pass total is rejected: "N passed" goes stale the moment a test is added,
and this file exists so that staleness fails the suite.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COUNT_RE = re.compile(
    r'Fast suite \(`python3 -m pytest -m "not slow"`\): '
    r"(\d+) selected, (\d+) deselected\."
)
CI_LINE_RE = re.compile(
    r"CI runs that selection on Python (\d+\.\d+), (\d+\.\d+), and (\d+\.\d+)\."
)
# The summary is "N/M tests collected (K deselected)" or "N tests collected".
# A trailing word-boundary fails on the first form: ")" and the following
# space are both non-word, so the alternation fell through and captured M.
DESELECTED_RE = re.compile(r"(\d+)/(\d+) tests collected \((\d+) deselected\)")
BARE_RE = re.compile(r"^(\d+) tests collected\b")


def _readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def _collect() -> tuple[int, int]:
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest", "--collect-only", "-q",
            "-m", "not slow", "-p", "no:cacheprovider",
            "--override-ini", "addopts=",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    selected = deselected = None
    for line in proc.stdout.splitlines():
        found = DESELECTED_RE.search(line)
        if found:
            selected, deselected = int(found.group(1)), int(found.group(3))
            continue
        bare = BARE_RE.search(line.strip())
        if bare and selected is None:
            selected, deselected = int(bare.group(1)), 0
    assert selected is not None, proc.stdout
    return selected, deselected


def _problem_lines(text: str) -> list[str]:
    lines = text.splitlines()
    body: list[str] = []
    started = False
    for line in lines:
        if line.startswith("# "):
            started = True
            continue
        if not started:
            continue
        if line.strip() == "":
            if body:
                break
            continue
        if line.startswith("#"):
            break
        body.append(line)
    return body


def test_problem_statement_is_at_most_three_lines():
    body = _problem_lines(_readme())
    assert body, "README is missing a problem statement"
    assert len(body) <= 3, body


def test_readme_names_upstream_as_complement():
    text = _readme()
    assert "aidless/tmaudit" in text
    assert "complement" in text
    assert "not published to PyPI" in text
    assert "tmaudit.pyz" in text
    assert "_check_pyz_fresh.py" in text


def test_readme_selection_matches_collection():
    match = COUNT_RE.search(_readme())
    assert match, "README is missing the fast-suite count sentence"
    claimed = (int(match.group(1)), int(match.group(2)))
    assert claimed == _collect()


def test_readme_ci_pythons_match_workflow():
    text = _readme()
    match = CI_LINE_RE.search(text)
    assert match, "README is missing the CI Python sentence"
    claimed = [match.group(1), match.group(2), match.group(3)]
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    matrix = re.search(r"python-version:\s*\[([^\]]+)\]", workflow)
    assert matrix, workflow
    configured = re.findall(r"\d+\.\d+", matrix.group(1))
    assert claimed == configured
    # Declared in metadata, not executed by this fork's CI.
    assert "3.9" not in claimed


def test_readme_has_no_pass_count_badge_or_pypi_project_url():
    text = _readme()
    assert re.search(r"\b\d+\s+passed\b", text) is None
    assert "shields.io" not in text
    assert "badge" not in text.lower()
    assert "pypi.org/project" not in text
    assert "stars" not in text.lower()


def test_failure_modes_names_the_three_holes():
    text = (ROOT / "FAILURE_MODES.md").read_text(encoding="utf-8")
    assert "## False witness accept" in text
    assert "## Packaging missing yaml" in text
    assert "## Stale pyz" in text


def test_ci_builds_wheel_and_checks_pyz():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m build" in workflow
    assert "python _check_pyz_fresh.py" in workflow
    assert 'pytest -m "not slow"' in workflow


def test_templates_use_portable_root_sentinel():
    from tmaudit.forge import TEMPLATE_ROOT_ASSIGNMENT

    assert "F:" not in TEMPLATE_ROOT_ASSIGNMENT
    templates = ROOT / "src" / "tmaudit" / "templates"
    for name in (
        "verify_TEMPLATE.py",
        "compile_check_TEMPLATE.py",
        "fix_abstract_unicode_TEMPLATE.py",
    ):
        text = (templates / name).read_text(encoding="utf-8")
        assert TEMPLATE_ROOT_ASSIGNMENT in text, name
    minimal = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert TEMPLATE_ROOT_ASSIGNMENT in minimal


def test_meta_test_count_matches_its_case_list():
    text = (ROOT / "_check_all_regressions.py").read_text(encoding="utf-8")
    ids = re.findall(r"\('\d+', inject_bug\d+\)", text)
    claimed = re.findall(r"The case list has (\d+) bugs\.", text)
    assert ids, "case list not found"
    assert claimed, "docstring count not found"
    assert len(set(claimed)) == 1
    assert int(claimed[0]) == len(ids)


def test_current_instructions_do_not_freeze_46_tests():
    for rel in (
        "README.md",
        "CONTRIBUTING.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "hooks/pre-commit",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "46 tests" not in text, rel
        assert re.search(r"\b\d+\s+passed\b", text) is None, rel


def _line_violations(line: str) -> list[str]:
    """Author-machine paths. Needles are split so this file does not contain them."""
    found: list[str] = []
    drive_fwd = "F:" + "/"
    drive_back = "F:" + "\\"
    users = "/" + "Users/"
    home = "/" + "home/"
    allowed_home = home + "user"
    if drive_fwd in line or drive_back in line:
        found.append("F: drive path")
    if users in line and "Public" not in line:
        found.append("/Users path")
    # Collapse doubled backslashes so a Python literal and a prose path match
    # the same way. The Windows public-profile fallback in cache.py is allowed.
    folded = line.replace("\\\\", "\\")
    users_back = "Users" + "\\"
    if users_back in folded and (users_back + "Public") not in folded:
        found.append("Users path")
    if home in line:
        stripped = line.replace(allowed_home, "")
        if home in stripped or allowed_home not in line:
            found.append("home path")
    return found


def test_no_author_absolute_paths():
    skip_dirs = {
        ".git", ".venv", "venv", "dist", "build", "build_pyz",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".eggs",
    }
    suffixes = {".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".json", ".sh", ".ps1"}
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix not in suffixes:
            continue
        # This file builds the needles by concatenation. Scanning it would
        # only prove the concatenation compiled, not that the tree is clean.
        if path.name == "test_claims_drift.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            problems = _line_violations(line)
            if problems:
                rel = path.relative_to(ROOT).as_posix()
                offenders.append(f"{rel}:{number}: {problems}: {line.strip()[:160]}")
    pyz = ROOT / "tmaudit.pyz"
    if pyz.is_file():
        blob = pyz.read_bytes()
        for needle in (b"F:" + b"/" + b"Research", b"F:" + b"\\" + b"Research"):
            if needle in blob:
                offenders.append(f"tmaudit.pyz contains {needle!r}")
    assert not offenders, "author paths still in the tree:\n" + "\n".join(offenders[:40])
