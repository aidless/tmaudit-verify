"""Tests for the temporal regression ledger (tmaudit.witness).

The end-to-end test builds a real throwaway git repository, records a
fix, deletes its load-bearing line, and asserts that (a) verify
reports the regression with a non-zero exit code and (b) the
history names the commit that introduced it. That is the behaviour
ruflo's JS toolkit was verified against before this port, so these
tests are the port's acceptance criteria rather than unit tests.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tmaudit import witness

MARKER = 'if (self._refreshing) return self._refreshing'
GOOD = (
    'class TokenRefresher:\n'
    '    def refresh(self, token):\n'
    f'        # FIX: early return on in-flight refresh\n'
    f'        {MARKER}\n'
    '        return None\n'
)
BAD = GOOD.replace(MARKER, 'if (self._refreshing) return None')


def _git(repo: Path, *args: str) -> str:
    subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True,
                   check=True)


@pytest.fixture()
def repo(tmp_path):
    """A minimal git repo holding src/auth.py with the fix in place."""
    root = tmp_path / 'repo'
    (root / 'src').mkdir(parents=True)
    target = root / 'src' / 'auth.py'
    target.write_text(GOOD, encoding='utf-8')
    _git(root, 'init', '-q')
    _git(root, 'config', 'user.email', 'test@example.com')
    _git(root, 'config', 'user.name', 'test')
    _git(root, 'add', '-A')
    _git(root, 'commit', '-qm', 'initial: fix present')
    return root


def _fixes():
    return [{'id': 'AUTH-001',
             'desc': 'Race condition in token refresh — early return on in-flight refresh',
             'file': 'src/auth.py',
             'marker': MARKER}]


class TestFixRefresh:
    def test_sha256_matches_openssl_style_digest(self, repo):
        import hashlib
        raw = (repo / 'src' / 'auth.py').read_bytes()
        assert witness.file_sha256(repo / 'src' / 'auth.py') == \
            hashlib.sha256(raw).hexdigest()

    def test_marker_detection(self, repo):
        assert witness.file_contains(repo / 'src' / 'auth.py', MARKER)
        assert not witness.file_contains(repo / 'src' / 'auth.py', 'definitely-absent')

    def test_missing_file_is_flagged_not_raised(self, repo):
        manifest = witness.regen(repo, [{'id': 'X', 'file': 'src/nope.py',
                                         'marker': 'anything'}])
        assert manifest['fixes'][0]['_missing'] is True
        assert manifest['verified'] == 0


class TestRegenAndVerify:
    def test_pass_when_marker_present(self, repo):
        manifest = witness.regen(repo, _fixes())
        result = witness.verify(manifest, repo)
        assert result['pass'] == 1
        assert result['exit_code'] == 0

    def test_regression_detected_and_exit_code_one(self, repo):
        manifest = witness.regen(repo, _fixes())
        (repo / 'src' / 'auth.py').write_text(BAD, encoding='utf-8')
        result = witness.verify(manifest, repo)
        assert result['regressed'] == ['AUTH-001']
        assert result['exit_code'] == 1

    def test_drift_detected_when_content_changes_but_marker_survives(self, repo):
        manifest = witness.regen(repo, _fixes())
        (repo / 'src' / 'auth.py').write_text(
            GOOD + '\n# an unrelated comment\n', encoding='utf-8')
        result = witness.verify(manifest, repo)
        assert result['drifted'] == ['AUTH-001']
        assert result['exit_code'] == 0  # marker still present -> not a regression

    def test_manifest_records_commit_and_schema(self, repo):
        manifest = witness.regen(repo, _fixes())
        assert manifest['schema'] == witness.SCHEMA
        assert manifest['git_commit']
        assert manifest['total_fixes'] == 1


class TestTemporalHistory:
    def test_regression_is_localised_to_a_commit(self, repo):
        history = repo / 'history.jsonl'
        witness.regen(repo, _fixes(), history)

        # commit the regression so the two snapshots differ by commit
        (repo / 'src' / 'auth.py').write_text(BAD, encoding='utf-8')
        _git(repo, 'commit', '-qam', 'regress: drop the fix')
        witness.regen(repo, _fixes(), history)

        entries = witness.load_history(history)
        assert len(entries) == 2
        found = witness.find_regression(entries, 'AUTH-001')
        assert found is not None
        last_pass, first_fail = found
        assert last_pass['fixes']['AUTH-001']['marker_verified'] is True
        assert first_fail['fixes']['AUTH-001']['marker_verified'] is False
        assert last_pass['commit'] != first_fail['commit']

    def test_no_regression_when_never_broken(self, repo):
        history = repo / 'history.jsonl'
        witness.regen(repo, _fixes(), history)
        witness.regen(repo, _fixes(), history)
        assert witness.find_regression(witness.load_history(history), 'AUTH-001') is None

    def test_fix_that_never_passed_has_no_regression(self, repo):
        history = repo / 'history.jsonl'
        (repo / 'src' / 'auth.py').write_text(BAD, encoding='utf-8')
        witness.regen(repo, _fixes(), history)
        assert witness.find_regression(witness.load_history(history), 'AUTH-001') is None

    def test_history_is_jsonl_and_diff_friendly(self, repo):
        history = repo / 'history.jsonl'
        witness.regen(repo, _fixes(), history)
        lines = history.read_text(encoding='utf-8').splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert set(entry) >= {'issued_at', 'commit', 'fixes'}
        assert entry['fixes']['AUTH-001']['marker_verified'] is True

    def test_corrupt_line_is_skipped_not_raised(self, tmp_path):
        path = tmp_path / 'h.jsonl'
        path.write_text('{"commit": "a"}\nnot json\n{"commit": "b"}\n',
                        encoding='utf-8')
        assert len(witness.load_history(path)) == 2


class TestCli:
    def test_regen_verify_history_roundtrip(self, repo):
        manifest_path = repo / 'verification.json'
        history_path = repo / 'history.jsonl'
        fixes_path = repo / 'fixes.json'
        fixes_path.write_text(json.dumps({'fixes': _fixes()}), encoding='utf-8')

        rc = witness.cli(['regen', '--root', str(repo), '--manifest',
                          str(manifest_path), '--history', str(history_path),
                          '--fixes', str(fixes_path)])
        assert rc == 0

        rc = witness.cli(['verify', '--manifest', str(manifest_path),
                          '--root', str(repo)])
        assert rc == 0

        (repo / 'src' / 'auth.py').write_text(BAD, encoding='utf-8')
        rc = witness.cli(['verify', '--manifest', str(manifest_path),
                          '--root', str(repo)])
        assert rc == 1

        rc = witness.cli(['history', '--history', str(history_path),
                          '--id', 'AUTH-001'])
        # no second snapshot recorded, so no regression to report
        assert rc == 0
