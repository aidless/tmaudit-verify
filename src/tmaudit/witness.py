"""tmaudit.witness — temporal regression ledger for audit fixes.

Ported from ruflo's witness toolkit
(``plugins/ruflo-core/scripts/witness/``, ADR-103), verified there
end-to-end before porting: a fix whose marker line is deleted
flips ``marker_verified`` to False, ``verify`` exits 1, and the
history locates the commit that introduced the regression.

The problem it solves: a regression test suite proves the *test*
fails when a bug is re-injected. It does not record, over time,
which change removed a load-bearing line. This ledger does: every
regen appends a JSONL snapshot with the git commit, so
``find_regression`` can answer "last pass -> first fail".

Scope note (deliberate): this module computes SHA-256 and records
git commits, but does **not** sign. ruflo signs with Ed25519 keyed
off the commit hash, and its own verify output flags that as
``authenticity: self-attested`` — the seed is derivable by anyone
holding the commit, so it proves integrity, not authorship. Adding
an equally-derivable signature here would advertise a guarantee it
does not give, so the guarantee is not claimed at all. If release
authenticity is needed, pin a public key at regen time and record
the fingerprint alongside the snapshot.

Public API:
    regen(repo_root, fixes, history_path)  -> manifest dict
    verify(manifest, repo_root)            -> result dict (exit-code shaped)
    find_regression(history, fix_id)       -> (last_pass, first_fail) or None
    cli(argv)                              -> entry point for `tmaudit witness`
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

__all__ = ['regen', 'verify', 'append_history', 'find_regression',
           'file_sha256', 'file_contains', 'git_commit', 'cli']

SCHEMA = 'tmaudit-witness/v1'


def git_commit(repo_root: str | Path) -> str | None:
    """HEAD commit of ``repo_root``, or None when not a git repo."""
    try:
        out = subprocess.run(['git', 'rev-parse', 'HEAD'],
                             cwd=str(repo_root), capture_output=True,
                             text=True, timeout=30)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_contains(path: str | Path, marker: str) -> bool:
    try:
        return marker in Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False


def _refresh_fix(repo_root: Path, fix: dict) -> dict:
    """Recompute sha256 + marker presence for one fix."""
    abs_path = repo_root / fix['file']
    if not abs_path.exists():
        return {**fix, 'sha256': '', 'marker_verified': False, '_missing': True}
    return {
        'id': fix['id'],
        'desc': fix.get('desc', ''),
        'file': fix['file'],
        'sha256': file_sha256(abs_path),
        'marker': fix['marker'],
        'marker_verified': file_contains(abs_path, fix['marker']),
    }


def regen(repo_root: str | Path,
          fixes: list[dict],
          history_path: str | Path | None = None) -> dict:
    """Refresh every fix and write a manifest snapshot.

    ``fixes`` entries need ``id``, ``file``, ``marker``; ``desc`` is
    optional. Returns the manifest dict (also the JSON written).
    """
    root = Path(repo_root).resolve()
    refreshed = [_refresh_fix(root, f) for f in fixes]
    manifest = {
        'schema': SCHEMA,
        'issued_at': datetime.now(timezone.utc).isoformat(),
        'git_commit': git_commit(root),
        'repo_root': str(root),
        'total_fixes': len(refreshed),
        'verified': sum(1 for f in refreshed if f['marker_verified']),
        'fixes': refreshed,
    }
    if history_path:
        append_history(history_path, manifest)
    return manifest


def append_history(history_path: str | Path, manifest: dict) -> None:
    """Append one JSONL snapshot (git-diff friendly, append-cheap)."""
    path = Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        'issued_at': manifest['issued_at'],
        'commit': manifest['git_commit'],
        'verified': manifest['verified'],
        'total': manifest['total_fixes'],
        'fixes': {f['id']: {'sha256': f['sha256'],
                            'marker_verified': f['marker_verified']}
                  for f in manifest['fixes']},
    }
    with path.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + '\n')


def load_history(history_path: str | Path) -> list[dict]:
    path = Path(history_path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def verify(manifest: dict, repo_root: str | Path | None = None) -> dict:
    """Check a manifest against the live tree.

    Returns counts and a ``regressed`` list; ``exit_code`` mirrors the CLI
    contract: 0 = every fix present, 1 = at least one regressed or missing.
    """
    root = Path(repo_root).resolve() if repo_root else \
        Path(manifest.get('repo_root', '.')).resolve()
    results = []
    for fix in manifest.get('fixes', []):
        live = _refresh_fix(root, fix)
        results.append(live)
    regressed = [f['id'] for f in results
                 if not f['marker_verified'] and not f.get('_missing')]
    missing = [f['id'] for f in results if f.get('_missing')]
    drifted = [f['id'] for f, fix in zip(results, manifest.get('fixes', []))
               if f['marker_verified'] and f['sha256'] != fix.get('sha256')]
    return {
        'pass': sum(1 for f in results if f['marker_verified']),
        'regressed': regressed,
        'missing': missing,
        'drifted': drifted,
        'exit_code': 1 if (regressed or missing) else 0,
    }


def find_regression(history: list[dict], fix_id: str) -> tuple[dict, dict] | None:
    """Locate where a fix regressed: (last passing snapshot, first failing).

    Mirrors ruflo's ``findRegressionIntroductions``. Returns None when the
    fix never passed, or never regressed.
    """
    last_pass: dict | None = None
    for entry in history:
        state = entry.get('fixes', {}).get(fix_id)
        if state is None:
            continue
        if state.get('marker_verified'):
            last_pass = entry
        elif last_pass is not None:
            return last_pass, entry
    return None


def fix_timeline(history: list[dict], fix_id: str) -> list[tuple[str, str, str]]:
    """(issued_at, commit, state) rows for one fix, oldest first."""
    rows = []
    for entry in history:
        state = entry.get('fixes', {}).get(fix_id)
        if state is None:
            continue
        rows.append((entry.get('issued_at', ''),
                     (entry.get('commit') or '')[:12],
                     'pass' if state.get('marker_verified') else 'regressed'))
    return rows


def _load_fixes_file(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return data.get('fixes', data) if isinstance(data, dict) else data


def cli(argv: list[str] | None = None) -> int:
    """`tmaudit witness regen|verify|history` — see module docstring."""
    import argparse

    parser = argparse.ArgumentParser(prog='tmaudit witness',
                                     description='Temporal regression ledger for audit fixes.')
    sub = parser.add_subparsers(dest='action', required=True)

    p_regen = sub.add_parser('regen', help='refresh fixes and append a snapshot')
    p_regen.add_argument('--root', default='.')
    p_regen.add_argument('--manifest', required=True)
    p_regen.add_argument('--history', default=None)
    p_regen.add_argument('--fixes', default=None)

    p_verify = sub.add_parser('verify', help='check a manifest against the live tree')
    p_verify.add_argument('--manifest', required=True)
    p_verify.add_argument('--root', default=None)

    p_hist = sub.add_parser('history', help='query the temporal history')
    p_hist.add_argument('--history', required=True)
    p_hist.add_argument('--id', dest='fix_id', default=None)

    args = parser.parse_args(argv)

    if args.action == 'regen':
        fixes = _load_fixes_file(args.fixes) if args.fixes else []
        manifest = regen(args.root, fixes, args.history)
        if args.manifest:
            Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
            Path(args.manifest).write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"witness regen: {manifest['verified']}/{manifest['total_fixes']} verified "
              f"@ {(manifest['git_commit'] or 'no-git')[:12]}")
        return 0

    if args.action == 'verify':
        manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
        result = verify(manifest, args.root)
        print(f"witness verify: pass={result['pass']} "
              f"regressed={len(result['regressed'])} missing={len(result['missing'])} "
              f"drifted={len(result['drifted'])}")
        for fix_id in result['regressed']:
            print(f"  REGRESSED  {fix_id}")
        for fix_id in result['missing']:
            print(f"  MISSING    {fix_id}")
        for fix_id in result['drifted']:
            print(f"  DRIFT      {fix_id} (content changed, marker still present)")
        print("note: integrity check only — this ledger is unsigned, so it cannot "
              "prove authorship of the recorded state.")
        return result['exit_code']

    if args.action == 'history':
        history = load_history(args.history)
        if args.fix_id:
            found = find_regression(history, args.fix_id)
            if found:
                last_pass, first_fail = found
                print(f"{args.fix_id}: last pass {last_pass.get('commit', '')[:12]} "
                      f"({last_pass.get('issued_at', '')}) -> regressed at "
                      f"{first_fail.get('commit', '')[:12]} "
                      f"({first_fail.get('issued_at', '')})")
                return 1
            print(f"{args.fix_id}: no regression found in {len(history)} snapshots")
            return 0
        for row in fix_timeline(history, args.fix_id or ''):
            print('  '.join(row))
        print(f"{len(history)} snapshots")
        return 0

    return 2


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(cli())
