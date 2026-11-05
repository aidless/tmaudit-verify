# Failure modes

Three holes this repository has already shipped, and what still is not proved.
A green run of the suite did not catch the first two until a check was aimed
at the bytes that actually get installed, not at the source tree the tests
import.

## False witness accept

`tmaudit witness` answers "is this fix still in the tree?" A previous version
could answer yes for the wrong tree, or for a marker that was no longer the
fix.

- `regen` stored `repo_root` as the absolute checkout path. `verify` with no
  `--root` opened that path. A manifest written on one machine could accept
  the tree that still had the marker while the tree under inspection had lost
  it.
- The marker test was `marker in text`. In Python the empty string is a
  substring of every file, so a blank marker verified. A marker that survived
  only inside a longer line (a string literal, a comment, a rewritten
  statement) verified too.
- Fix paths were copied into the manifest as given, including an absolute path.

What is guarded now, by `tests/test_witness.py::TestFalseAccept`:

- manifests do not record a checkout path, and `verify` ignores a stored
  `repo_root`. The tree is `--root`, or the current directory.
- a marker counts only when it is a non-empty whole line
- an absolute path or a `..` segment is not stored and does not verify

What exit 0 still does not mean:

- the file bytes match the recorded digest. Hash drift is printed as `DRIFT`
  and does not change the exit code. Exit 0 means every marker line is present.
- the marker line is executable code. A comment whose entire text is the
  marker still verifies. This ledger does not parse the language.
- anyone in particular produced the snapshot. The ledger is unsigned on
  purpose. A signature derived from the public commit would prove integrity,
  which the hash already records, and would not prove authorship.

## Packaging missing yaml

`detector_config/detector.yaml` is read at runtime. A candidate wheel listed
`templates/*` and `configs/*` and not the yaml. A non-editable install then
fell back to the built-in defaults and behaved differently from the tree it
was built from. The suite stayed green because it imports `src/`, and an
editable install reads `src/` too.

`tests/test_package_data.py` has two layers. The declaration test always runs
and fails if a `.yaml` under `src/tmaudit/` is missing from
`[tool.setuptools.package-data]`. `TestBuiltWheelContents` opens the newest
`dist/*.whl` and checks the yaml is inside it. That class used to be marked
`slow`, which deselected it from the CI job that had just run `python -m build`.
It is in the fast suite now. With no wheel in `dist/` it skips. A skip is not
a pass of the wheel check. CI builds the wheel first, so the CI job does not
skip it.

## Stale pyz

`tmaudit.pyz` is committed, and it is the offline way to run the tool. It once
lagged `src/`: modules the package had grown were absent, and the archive
carried `.pyc`. Nothing in CI compared the committed archive to the tree,
because the old job rebuilt a fresh archive and smoked that copy.

`python _check_pyz_fresh.py` compares source bytes for every `.py` and `.yaml`
under `src/tmaudit/`, rejects bytecode, and rejects extra members. CI runs it
on the committed archive. `python _build_pyz.py` overwrites the archive, so
the freshness check has to run before a rebuild, not after. `tests/test_check_pyz_fresh.py`
builds a short archive that is missing a module, one that contains bytecode,
and one whose bytes differ, and requires each to be rejected.
