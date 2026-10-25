#!/usr/bin/env python3
"""Audit arXiv:2502.14074 with the shipped tmaudit checks and two plugins.

Why this exists
---------------
`tmaudit`'s built-in categories are a per-paper rulepack; its README tells
a reader to audit an arbitrary manuscript with
`tmaudit verify --paper-dir DIR` (generic checks, empty config) and, for
checks the generic categories do not cover, with a plugin run through
`tmaudit plugins run NAME --paper-dir DIR`.

This script does exactly that against one real paper: *Investigating
Non-Transitivity in LLM-as-a-Judge* (arXiv:2502.14074, ICML 2025
Spotlight), whose LaTeX source the authors publish. It runs:

  1. `tmaudit verify --paper-dir DIR` — the generic categories;
  2. `tmaudit plugins run claims-significance-no-test --paper-dir DIR` —
     significance wording with no hypothesis-test standard;
  3. `tmaudit plugins run claims-percent-table-no-uncertainty --paper-dir DIR` —
     a percentage-bearing results table with no uncertainty marker.

Both plugins are `requires_config=False`, so the empty config the
`--paper-dir` path supplies is not a limitation: the checks read only the
manuscript, and they are general (they name no line numbers, symbols, or
tables of this paper).

What the audit finds is a **reporting-standards** observation, not a claim
that the paper's results are wrong. The companion `README.md` states that
boundary explicitly, together with three candidate weaknesses that were
checked and withdrawn.

Inputs and reproducibility
--------------------------
Every input this script reads is listed in `inputs.txt` with its SHA-256.
A missing file or a hash mismatch aborts with exit 2 (the same code
tmaudit reserves for "the audit could not run"). The extracted sources are
copied to a temporary directory before any tmaudit command runs, so the
pristine download is never mutated by the fork that `verify` writes.

The plugin must be installed first::

    pip install -e ./case-studies/arxiv-2502.14074/tmaudit_claims_plugin

Usage
-----
    python3 audit_paper.py --paper-dir _paper
    python3 audit_paper.py --paper-dir _paper --archive src.tar.gz
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ARCHIVE_NAME = "src.tar.gz"
DEFAULT_PAPER = HERE / "_paper"
DEFAULT_MANIFEST = HERE / "inputs.txt"
DEFAULT_OUT = HERE / "results.json"

PLUGIN_CHECKS = (
    "claims-significance-no-test",
    "claims-percent-table-no-uncertainty",
)


# ---------------------------------------------------------------------------
# Input verification
# ---------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: Path) -> list[tuple[str, str]]:
    """Parse `<sha256>  <name>` lines; blanks and `#` comments are skipped."""
    entries: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(None, 1)
        entries.append((name.strip(), digest.strip()))
    return entries


def verify_inputs(entries, paper_dir: Path, archive: Path | None) -> dict[str, str]:
    """Verify every manifest entry; exit 2 on anything missing or changed.

    The archive entry is verified only when `--archive` is given (it is a
    download, not part of the extracted source); otherwise it is recorded
    as unverified so the reader can see the distinction.
    """
    verified: dict[str, str] = {}
    problems: list[str] = []
    for name, digest in entries:
        if name == ARCHIVE_NAME:
            if archive is None:
                continue
            target = archive
        else:
            target = paper_dir / name
        if not target.exists():
            problems.append(f"missing: {name}")
            continue
        got = sha256_of(target)
        if got != digest:
            problems.append(
                f"hash mismatch: {name} (expected {digest[:16]}…, got {got[:16]}…)"
            )
            continue
        verified[name] = got
    if problems:
        print("INPUT VERIFICATION FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        raise SystemExit(2)
    return verified


# ---------------------------------------------------------------------------
# Running tmaudit
# ---------------------------------------------------------------------------

def run_tmaudit(*cli_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tmaudit", *cli_args],
        cwd=str(REPO), capture_output=True, text=True,
    )


_CAT_LINE_RE = re.compile(
    r"^\s{2}(C\d+)\s+\[(OK|HIGH|MEDIUM|LOW|ERROR)\]\s+(\d+) finding\(s\)(.*)$"
)
_DETAIL_HDR_RE = re.compile(
    r"^\[(HIGH|MEDIUM|LOW)\]\s+(C\d+)\s+\((line \d+|global)\)\s*$"
)
_PLUGIN_LINE_RE = re.compile(
    r"^\[(HIGH|MEDIUM|LOW)\]\s+(\S+)\s+L(\d+):\s*(.*)$"
)


def parse_verify_output(stdout: str) -> dict:
    """Split the generic verify stdout into per-category status + findings."""
    categories: dict[str, dict] = {}
    for line in stdout.splitlines():
        m = _CAT_LINE_RE.match(line)
        if m:
            note = m.group(4).strip()
            categories[m.group(1)] = {
                "marker": m.group(2),
                "n": int(m.group(3)),
                "note": note.strip("[]") if note else "",
            }
    findings: list[dict] = []
    lines = stdout.splitlines()
    for i, line in enumerate(lines):
        m = _DETAIL_HDR_RE.match(line)
        if not m:
            continue
        msg: list[str] = []
        j = i + 1
        while j < len(lines) and lines[j].startswith("    "):
            msg.append(lines[j].strip())
            j += 1
        findings.append({
            "severity": m.group(1),
            "category": m.group(2),
            "location": m.group(3),
            "message": " ".join(msg),
        })
    return {"categories": categories, "findings": findings}


def parse_plugin_output(stdout: str) -> list[dict]:
    out: list[dict] = []
    for line in stdout.splitlines():
        m = _PLUGIN_LINE_RE.match(line)
        if m:
            out.append({
                "severity": m.group(1),
                "category": m.group(2),
                "line": int(m.group(3)),
                "message": m.group(4),
            })
    return out


def tmaudit_version() -> str:
    proc = subprocess.run(
        [sys.executable, "-c", "import tmaudit; print(tmaudit.__version__)"],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() or "unknown"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paper-dir", type=Path, default=DEFAULT_PAPER,
                    help="extracted arXiv source (default: ./_paper)")
    ap.add_argument("--archive", type=Path, default=None,
                    help="the e-print tarball, to verify against inputs.txt")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    entries = load_manifest(args.manifest)
    source_entries = [(n, d) for n, d in entries if n != ARCHIVE_NAME]
    verified = verify_inputs(entries, args.paper_dir, args.archive)

    # Audit a copy: `verify` forks verify_generic.py into the directory it
    # is pointed at, and the pristine extraction must not be touched.
    work = Path(tempfile.mkdtemp(prefix="tmaudit-2502.14074-"))
    try:
        for name, _ in source_entries:
            shutil.copy2(args.paper_dir / name, work / name)

        ver_proc = run_tmaudit("verify", "--paper-dir", str(work))
        generic = parse_verify_output(ver_proc.stdout)
        generic["exit_code"] = ver_proc.returncode
        generic["stdout"] = ver_proc.stdout

        plugins: dict[str, dict] = {}
        for name in PLUGIN_CHECKS:
            p = run_tmaudit("plugins", "run", name, "--paper-dir", str(work))
            plugins[name] = {
                "exit_code": p.returncode,
                "findings": parse_plugin_output(p.stdout),
                "stdout": p.stdout,
            }
    finally:
        shutil.rmtree(work, ignore_errors=True)

    payload = {
        "generated_by": "case-studies/arxiv-2502.14074/audit_paper.py",
        "arxiv_id": "2502.14074",
        "title": "Investigating Non-Transitivity in LLM-as-a-Judge",
        "tmaudit_version": tmaudit_version(),
        "inputs": verified,
        "archive_verified": ARCHIVE_NAME in verified,
        "generic_verify": generic,
        "plugin_findings": plugins,
    }
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )

    # Human-readable summary.
    print(f"generic verify: exit {generic['exit_code']}")
    for cat, info in sorted(generic["categories"].items()):
        note = f"  [{info['note']}]" if info["note"] else ""
        print(f"  {cat}  {info['marker']:7s}  n={info['n']}{note}")
    for name, info in plugins.items():
        print(f"{name}: {len(info['findings'])} finding(s)")
        for f in info["findings"]:
            print(f"  [{f['severity']}] {f['category']} L{f['line']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
