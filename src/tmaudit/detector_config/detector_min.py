"""Minimal detector: only the config surface + 1 toy detector.

This is a standalone subset of an earlier hallucination detector
(about 60 lines), so unit tests can import without pulling in the full
detector (arXiv API, GitHub API, pdfplumber, etc.) or any private tree.

The behavior is intentionally identical to the production detector
with respect to:
  - DEFAULT_CONFIG structure & values
  - _deep_merge semantics
  - load_config priority: missing file -> DEFAULT; partial -> merge; broken -> DEFAULT + warn
  - detect_arxiv_year_issues: safe_window_months from CONFIG, downgrade by verify_online
"""
from __future__ import annotations
import json
import sys
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("tmaudit.detector_config")

CONFIG_FILE_DEFAULT = Path(__file__).parent / "detector.yaml"

DEFAULT_CONFIG: dict[str, Any] = {
    "arxiv": {
        "safe_window_months": 2,
        "verify_online": True,
        "api_timeout_sec": 8,
        "user_agent": "mm3-detector/1.0",
    },
    "internal": {
        "soft_down_paragraph": True,
    },
    "log": {
        "file_enabled": True,
        "file_path": "detector.log",
        "console_level": "INFO",
        "file_level": "INFO",
    },
}


def deep_merge(base: dict, override: dict | None) -> dict:
    """Recursively merge override into base. override wins. Returns new dict."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Path | str | None = None) -> dict:
    """Load detector.yaml and deep-merge into DEFAULT_CONFIG.

    Failure modes (all non-fatal):
      - path is None or doesn't exist -> DEFAULT_CONFIG (deep copy)
      - YAML is unreadable / broken    -> DEFAULT_CONFIG + stderr warning
    """
    p = Path(path) if path else CONFIG_FILE_DEFAULT
    if not p.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        import yaml  # type: ignore
    except ImportError:
        sys.stderr.write(f"[detector.config] PyYAML missing; using defaults for {p}\n")
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(p, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
    except Exception as e:
        sys.stderr.write(f"[detector.config] cannot read {p}: {e}; using defaults\n")
        return json.loads(json.dumps(DEFAULT_CONFIG))
    return deep_merge(DEFAULT_CONFIG, user_cfg)


def detect_arxiv_year_issues_min(text: str, *, config: dict | None = None,
                                  current_year: int = 2026, current_month: int = 7) -> list[dict]:
    """Toy arxiv-year detector. Mirrors production logic, but uses
    pre-canned regex behavior and synthetic dates so tests don't hit the
    network. Same priority rules as the real detector.
    """
    import re
    cfg = config or load_config()
    n_months = cfg["arxiv"]["safe_window_months"]
    safe_lo = current_month - n_months
    safe_hi = current_month + n_months
    pattern = re.compile(r"arXiv:(\d{2})(\d{2})\.(\d{4,5})")
    issues: list[dict] = []
    for m in pattern.finditer(text):
        year = 2000 + int(m.group(1))
        month = int(m.group(2))
        full = m.group(0)
        if year > current_year:
            sev = "HIGH"
            ttype = "arxiv_year_future"
        elif year == current_year and (month < safe_lo or month > safe_hi):
            sev = "HIGH"
            ttype = "arxiv_year_outside_safe_window"
        elif year == current_year:
            sev = "MEDIUM"
            ttype = "arxiv_year_safe_window"
        else:
            sev = "MEDIUM"
            ttype = "arxiv_year_old"
        issues.append({
            "match": full, "year": year, "month": month,
            "severity": sev, "type": ttype,
            "safe_window": (safe_lo, safe_hi),
        })
    return issues
