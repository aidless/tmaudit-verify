"""Tests for artifact-side verification in ``tmaudit.artifacts``.

Every assertion here is about the *contract*, not about bytes on disk: the
verdict must be one of three values, ``UNVERIFIABLE`` must never compare equal
to ``PASS``, and the reported evidence level must not exceed what the check
actually established. Where a fixture is needed it is built in the test, so a
failure points at one rule rather than at a shared binary blob.

The motivating cases are documented in each test: they are the two failure
modes found while auditing HKUDS/CLI-Anything on 2026-10-24 —
an export that returns exit 0 while producing no file, and a macro generator
that emits an unsubstituted ``{safe_path}`` placeholder.
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
import zipfile
import zlib

import pytest

from tmaudit import artifacts as A


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _png(width: int, height: int) -> bytes:
    """Minimal valid PNG header through IHDR. Not a decodable image."""
    ihdr = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
    crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk + crc + b"\x00" * 32


def _pdf(pages: int = 1, *, compress: bool = True) -> bytes:
    """A PDF whose page count and stream decodability are both controllable."""
    body = b"BT /F1 12 Tf 72 720 Td (hello) Tj ET"
    if compress:
        payload = zlib.compress(body)
        stream = b"stream\n" + payload + b"\nendstream"
    else:
        stream = b"stream\n" + body + b"\nendstream"
    objects = [b"%PDF-1.7\n"]
    for i in range(pages):
        objects.append(f"{i + 2} 0 obj\n<< /Type /Page /Parent 1 0 R >>\nendobj\n".encode())
    objects.append(b"3 0 obj\n<< /Length 44 >>\n" + stream + b"\nendobj\n")
    objects.append(b"trailer\n<< /Root 1 0 R >>\n%%EOF\n")
    return b"".join(objects)


def _zip(members: dict[str, bytes]) -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def workdir(tmp_path):
    return tmp_path


# ---------------------------------------------------------------------------
# Tri-state contract
# ---------------------------------------------------------------------------
def test_verdict_is_tri_state():
    members = {v.name for v in A.Verdict}
    assert members == {"PASS", "FAIL", "UNVERIFIABLE"}


def test_unverifiable_is_not_ok(tmp_path):
    """The single most important property: 'could not check' is not 'fine'.

    Harness suites that skip when a dependency is missing still report green;
    this module must not reproduce that.
    """
    p = tmp_path / "mystery.weirdext"
    p.write_bytes(b"some bytes that match no signature table")
    r = A.check_artifact(A.Spec(path=str(p)))
    assert r.verdict is A.Verdict.UNVERIFIABLE
    assert r.ok is False
    assert r.evidence is A.Evidence.NONTRIVIAL


def test_unverifiable_does_not_count_as_all_ok(tmp_path):
    p = tmp_path / "mystery.weirdext"
    p.write_bytes(b"x" * 64)
    results = A.check_all([A.Spec(path=str(p))])
    s = A.summarise(results)
    assert s["UNVERIFIABLE"] == 1
    assert s["all_ok"] is False


def test_empty_result_set_is_not_all_ok():
    """A run that checked nothing has not passed."""
    assert A.summarise([])["all_ok"] is False


# ---------------------------------------------------------------------------
# Existence and size
# ---------------------------------------------------------------------------
def test_missing_file_fails_at_evidence_none(tmp_path):
    """The draw.io case: export reported success, no file existed."""
    r = A.check_artifact(A.Spec(path=str(tmp_path / "out.png"), format="png"))
    assert r.verdict is A.Verdict.FAIL
    assert r.evidence is A.Evidence.NONE
    assert "does not exist" in r.reasons[0]


def test_directory_is_not_an_artifact(tmp_path):
    d = tmp_path / "adir"
    d.mkdir()
    r = A.check_artifact(A.Spec(path=str(d)))
    assert r.verdict is A.Verdict.FAIL
    assert "not a regular file" in r.reasons[0]


def test_zero_byte_file_fails(tmp_path):
    p = tmp_path / "empty.pdf"
    p.touch()
    r = A.check_artifact(A.Spec(path=str(p), format="pdf"))
    assert r.verdict is A.Verdict.FAIL
    assert "empty" in r.reasons[0]
    assert r.evidence is A.Evidence.EXISTS


def test_size_floor(tmp_path):
    p = tmp_path / "small.pdf"
    p.write_bytes(b"%PDF-1.7\n")
    r = A.check_artifact(A.Spec(path=str(p), format="pdf", min_bytes=1000))
    assert r.verdict is A.Verdict.FAIL
    assert "below the floor" in r.reasons[0]


def test_size_floor_off_by_default(tmp_path):
    p = tmp_path / "tiny.pdf"
    p.write_bytes(_pdf(pages=1))
    r = A.check_artifact(A.Spec(path=str(p), format="pdf"))
    assert r.verdict is A.Verdict.PASS


# ---------------------------------------------------------------------------
# Stale-artifact guard
# ---------------------------------------------------------------------------
def test_stale_artifact_rejected(tmp_path):
    """A leftover file from a previous run satisfies every other check."""
    p = tmp_path / "old.pdf"
    p.write_bytes(_pdf())
    r = A.check_artifact(A.Spec(path=str(p), format="pdf", min_mtime=1e18))
    assert r.verdict is A.Verdict.FAIL
    assert "predates the run" in r.reasons[0]


def test_fresh_artifact_accepted(tmp_path):
    p = tmp_path / "new.pdf"
    p.write_bytes(_pdf())
    r = A.check_artifact(A.Spec(path=str(p), format="pdf", min_mtime=0.0))
    assert r.verdict is A.Verdict.PASS


# ---------------------------------------------------------------------------
# Magic bytes
# ---------------------------------------------------------------------------
def test_wrong_magic_fails_at_evidence_magic_minus_one(tmp_path):
    p = tmp_path / "notreally.pdf"
    p.write_bytes(b"%PDX-1.7\n" + b"x" * 100)
    r = A.check_artifact(A.Spec(path=str(p), format="pdf"))
    assert r.verdict is A.Verdict.FAIL
    assert r.evidence is A.Evidence.NONTRIVIAL
    assert "magic mismatch" in r.reasons[0]


def test_extension_lie_is_caught(tmp_path):
    """A text file renamed to .png does not pass a PNG check."""
    p = tmp_path / "fake.png"
    p.write_text("this is not an image at all, just text")
    r = A.check_artifact(A.Spec(path=str(p)))
    assert r.verdict is A.Verdict.FAIL
    assert r.format == "png"


# ---------------------------------------------------------------------------
# PDF structure
# ---------------------------------------------------------------------------
def test_pdf_page_floor(tmp_path):
    p = tmp_path / "one.pdf"
    p.write_bytes(_pdf(pages=1))
    r = A.check_artifact(A.Spec(path=str(p), format="pdf", min_pages_pdf=3))
    assert r.verdict is A.Verdict.FAIL
    assert "below the floor of 3" in r.reasons[-1]


def test_pdf_header_only_shell_rejected(tmp_path):
    """Magic bytes alone are not a document."""
    p = tmp_path / "shell.pdf"
    p.write_bytes(b"%PDF-1.7\n%%EOF\n")
    r = A.check_artifact(A.Spec(path=str(p), format="pdf", min_pages_pdf=1))
    assert r.verdict is A.Verdict.FAIL


def test_pdf_undecodable_streams_fail(tmp_path):
    """A PDF whose only content stream is corrupt garbage must not pass."""
    p = tmp_path / "corrupt.pdf"
    p.write_bytes(
        b"%PDF-1.7\n1 0 obj\n<< /Type /Page >>\nendobj\n"
        b"2 0 obj\n<< /Length 8 >>\nstream\n\x00\xff\x00\xff\x00\xff\x00\xff\n"
        b"endstream\nendobj\n%%EOF\n"
    )
    r = A.check_artifact(A.Spec(path=str(p), format="pdf"))
    assert r.verdict is A.Verdict.FAIL
    assert "could be decoded" in r.reasons[0]


def test_pdf_valid_passes_at_parsed(tmp_path):
    p = tmp_path / "good.pdf"
    p.write_bytes(_pdf(pages=2))
    r = A.check_artifact(A.Spec(path=str(p), format="pdf", min_pages_pdf=2))
    assert r.verdict is A.Verdict.PASS
    assert r.evidence is A.Evidence.PARSED


# ---------------------------------------------------------------------------
# PNG dimensions
# ---------------------------------------------------------------------------
def test_png_dimensions_exact(tmp_path):
    p = tmp_path / "img.png"
    p.write_bytes(_png(640, 480))
    r = A.check_artifact(A.Spec(path=str(p), png_dimensions=(640, 480)))
    assert r.verdict is A.Verdict.PASS
    assert r.evidence is A.Evidence.PARSED


def test_png_dimensions_mismatch_by_one(tmp_path):
    """Off-by-one is exactly what a DPI conversion bug produces."""
    p = tmp_path / "img.png"
    p.write_bytes(_png(640, 480))
    r = A.check_artifact(A.Spec(path=str(p), png_dimensions=(640, 481)))
    assert r.verdict is A.Verdict.FAIL
    assert "!=" in r.reasons[-1]


# ---------------------------------------------------------------------------
# ZIP containers
# ---------------------------------------------------------------------------
def test_docx_missing_document_member(tmp_path):
    """A ZIP that lacks word/document.xml is not a .docx."""
    p = tmp_path / "fake.docx"
    p.write_bytes(_zip({"[Content_Types].xml": b"<Types/>"}))
    r = A.check_artifact(A.Spec(path=str(p)))
    assert r.verdict is A.Verdict.FAIL
    assert "missing member" in r.reasons[-1]


def test_docx_complete_passes(tmp_path):
    p = tmp_path / "real.docx"
    p.write_bytes(_zip({
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": b"<w:document/>",
    }))
    r = A.check_artifact(A.Spec(path=str(p)))
    assert r.verdict is A.Verdict.PASS
    assert r.evidence is A.Evidence.PARSED


def test_zip_required_member_from_spec(tmp_path):
    p = tmp_path / "bundle.zip"
    p.write_bytes(_zip({"a.txt": b"a"}))
    r = A.check_artifact(A.Spec(path=str(p), zip_members=("manifest.json",)))
    assert r.verdict is A.Verdict.FAIL
    assert "manifest.json" in r.reasons[-1]


def test_zip_corrupt_fails(tmp_path):
    p = tmp_path / "broken.zip"
    p.write_bytes(b"PK\x03\x04" + b"\xff" * 200)
    r = A.check_artifact(A.Spec(path=str(p)))
    assert r.verdict is A.Verdict.FAIL
    assert "ZIP" in r.reasons[-1]


# ---------------------------------------------------------------------------
# Semantic content
# ---------------------------------------------------------------------------
def test_unsubstituted_placeholder_is_caught(tmp_path):
    """The FreeCAD bug: ``os.path.abspath('{safe_path}')`` is not an f-string.

    The generated macro prints a literal placeholder. Checking for it is how a
    template bug becomes a test failure instead of a silent wrong answer.
    """
    p = tmp_path / "macro.pdf"
    p.write_bytes(_pdf() + b"Export complete: {safe_path}\n")
    r = A.check_artifact(A.Spec(
        path=str(p), format="pdf", must_not_contain=("{safe_path}",),
    ))
    assert r.verdict is A.Verdict.FAIL
    assert "forbidden content present" in r.reasons[-1]


def test_required_content_absent(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(_pdf())
    r = A.check_artifact(A.Spec(
        path=str(p), format="pdf", must_contain=("quarterly report",),
    ))
    assert r.verdict is A.Verdict.FAIL
    assert "required content absent" in r.reasons[-1]


def test_required_content_present_passes_at_semantic(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(_pdf() + b"quarterly report\n")
    r = A.check_artifact(A.Spec(
        path=str(p), format="pdf", must_contain=("quarterly report",),
    ))
    assert r.verdict is A.Verdict.PASS
    assert r.evidence is A.Evidence.SEMANTIC


def test_text_regex_applies_to_zip_text_members(tmp_path):
    """OOXML text lives inside compressed members; the check must look there."""
    p = tmp_path / "doc.docx"
    p.write_bytes(_zip({
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": b"<w:t>Revenue 42</w:t>",
    }))
    r = A.check_artifact(A.Spec(
        path=str(p), text_regex=r"Revenue \d+",
    ))
    assert r.verdict is A.Verdict.PASS


def test_text_regex_miss_fails(tmp_path):
    p = tmp_path / "doc.docx"
    p.write_bytes(_zip({
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": b"<w:t>nothing here</w:t>",
    }))
    r = A.check_artifact(A.Spec(path=str(p), text_regex=r"Revenue \d+"))
    assert r.verdict is A.Verdict.FAIL
    assert "did not match" in r.reasons[-1]


def test_bad_regex_is_unverifiable_not_pass(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(_pdf())
    r = A.check_artifact(A.Spec(path=str(p), format="pdf", text_regex="([unclosed"))
    assert r.verdict is A.Verdict.UNVERIFIABLE
    assert r.ok is False


# ---------------------------------------------------------------------------
# Evidence grading
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "body,expected",
    [
        (b"", A.Evidence.EXISTS),            # empty file stops at EXISTS
        (b"x" * 200, A.Evidence.NONTRIVIAL),  # unknown format caps here
    ],
)
def test_evidence_does_not_overstate(tmp_path, body, expected):
    p = tmp_path / "f.bin"
    p.write_bytes(body)
    r = A.check_artifact(A.Spec(path=str(p)))
    assert r.evidence is expected


def test_evidence_ordering_is_meaningful():
    order = [A.Evidence.NONE, A.Evidence.EXISTS, A.Evidence.NONTRIVIAL,
             A.Evidence.MAGIC, A.Evidence.PARSED, A.Evidence.SEMANTIC]
    assert [e.value for e in order] == sorted(e.value for e in order)


def test_format_without_parser_caps_evidence_at_magic(tmp_path):
    """Verifying a signature is not the same as parsing the container."""
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 200)
    r = A.check_artifact(A.Spec(path=str(p)))
    assert r.verdict is A.Verdict.PASS
    assert r.evidence is A.Evidence.MAGIC
    assert "no structural parser" in r.reasons[-1]


# ---------------------------------------------------------------------------
# Text payloads (generated scripts, g-code, config dumps)
# ---------------------------------------------------------------------------
def test_text_format_passes_at_parsed(tmp_path):
    p = tmp_path / "macro.py"
    p.write_text("import FreeCAD\nPart.export(objects, 'out.step')\n")
    r = A.check_artifact(A.Spec(path=str(p), text_regex=r"Part\.export"))
    assert r.verdict is A.Verdict.PASS
    assert r.evidence is A.Evidence.SEMANTIC
    assert r.format == "text"


def test_text_format_catches_silent_skip_marker(tmp_path):
    """The FreeCAD contract break: a WARNING comment means the emitter dropped
    a feature and carried on. The macro still runs; the model is wrong."""
    p = tmp_path / "macro.py"
    p.write_text(
        "doc = FreeCAD.newDocument('D')\n"
        "# WARNING: Unknown part type 'cut' for 'CutResult'\n"
        "Part.export(objs, 'out.step')\n"
    )
    r = A.check_artifact(A.Spec(
        path=str(p), must_not_contain=("WARNING", "{safe_path}"),
        text_regex=r"Part\.export",
    ))
    assert r.verdict is A.Verdict.FAIL
    assert "WARNING" in r.reasons[-1]


def test_text_format_rejects_binary(tmp_path):
    p = tmp_path / "notreally.txt"
    p.write_bytes(b"\x00\xff\xfe\x00binary junk" * 10)
    r = A.check_artifact(A.Spec(path=str(p), format="text"))
    assert r.verdict is A.Verdict.FAIL
    assert "not UTF-8" in r.reasons[0]


def test_text_without_content_rules_is_only_parsed(tmp_path):
    """Decoding text proves nothing about what is in it; the verdict says so."""
    p = tmp_path / "notes.md"
    p.write_text("# heading\n")
    r = A.check_artifact(A.Spec(path=str(p)))
    assert r.verdict is A.Verdict.PASS
    assert r.evidence is A.Evidence.PARSED


# ---------------------------------------------------------------------------
# Python syntax checking
# ---------------------------------------------------------------------------
def test_python_syntax_accepts_valid(tmp_path):
    p = tmp_path / "macro.py"
    p.write_text("def main():\n    return 0\n")
    r = A.check_artifact(A.Spec(path=str(p), python_syntax=True))
    assert r.verdict is A.Verdict.PASS
    assert "parses as Python" in r.reasons[-1]


def test_python_syntax_reports_line_number(tmp_path):
    """A generated script with a template bug must fail loudly, not silently."""
    p = tmp_path / "broken.py"
    p.write_text("doc = FreeCAD.newDocument('D')\ndef main(:\n    pass\n")
    r = A.check_artifact(A.Spec(path=str(p), python_syntax=True))
    assert r.verdict is A.Verdict.FAIL
    assert "line 2" in r.reasons[-1]
    assert "invalid syntax" in r.reasons[-1]


def test_python_syntax_on_binary_payload_is_unverifiable(tmp_path):
    """Asking for a parse on a non-text artifact must not be read as a pass."""
    p = tmp_path / "img.png"
    p.write_bytes(_png(64, 64))
    r = A.check_artifact(A.Spec(path=str(p), python_syntax=True))
    assert r.verdict is A.Verdict.UNVERIFIABLE
    assert r.ok is False


def test_python_syntax_failure_precedes_content_rules(tmp_path):
    """Ordering: a file that will not parse cannot be searched meaningfully."""
    p = tmp_path / "bad.py"
    p.write_text("x = (\n")
    r = A.check_artifact(A.Spec(
        path=str(p), python_syntax=True, must_contain=("x",),
    ))
    assert r.verdict is A.Verdict.FAIL
    assert "syntax error" in r.reasons[-1]


def test_python_syntax_does_not_promote_to_semantic(tmp_path):
    """Parsing proves the file is Python, not that it says the right thing."""
    p = tmp_path / "m.py"
    p.write_text("x = 1\n")
    r = A.check_artifact(A.Spec(path=str(p), python_syntax=True))
    assert r.verdict is A.Verdict.PASS
    assert r.evidence is A.Evidence.PARSED


def test_python_syntax_with_content_rules_reaches_semantic(tmp_path):
    p = tmp_path / "m.py"
    p.write_text("Part.export(objs, 'out.step')\n")
    r = A.check_artifact(A.Spec(
        path=str(p), python_syntax=True, text_regex=r"Part\.export",
    ))
    assert r.verdict is A.Verdict.PASS
    assert r.evidence is A.Evidence.SEMANTIC


def test_cli_python_syntax_flag(tmp_path):
    p = tmp_path / "m.py"
    p.write_text("def f(:\n")
    r = _run_cli("--python-syntax", str(p))
    assert r.returncode == 1


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------
def test_spec_rejects_unknown_key(tmp_path):
    """A typo'd key would otherwise silently disable the check it meant to add."""
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"path": "x", "min_byte": 10}]))
    with pytest.raises(ValueError, match="unknown key"):
        A.parse_spec(spec)


def test_spec_allows_underscore_annotations(tmp_path):
    """``_why`` documents a check without weakening the typo guard."""
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{
        "path": "x", "min_bytes": 10, "_why": "floor chosen from 3 samples",
    }]))
    parsed = A.parse_spec(spec)
    assert parsed[0].min_bytes == 10


def test_spec_rejects_typo_even_next_to_annotation(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"path": "x", "_ok": 1, "minbyte": 5}]))
    with pytest.raises(ValueError, match="unknown key"):
        A.parse_spec(spec)


def test_spec_rejects_missing_path(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"format": "pdf"}]))
    with pytest.raises(ValueError, match="missing 'path'"):
        A.parse_spec(spec)


def test_spec_rejects_wrong_format_marker(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"format": "some-other/9", "artifacts": []}))
    with pytest.raises(ValueError, match="expected"):
        A.parse_spec(spec)


def test_spec_accepts_both_shapes(tmp_path):
    bare = tmp_path / "a.json"
    bare.write_text(json.dumps([{"path": "x"}]))
    wrapped = tmp_path / "b.json"
    wrapped.write_text(json.dumps(
        {"format": A.SPEC_FORMAT, "artifacts": [{"path": "x"}]}
    ))
    assert A.parse_spec(bare)[0].path == "x"
    assert A.parse_spec(wrapped)[0].path == "x"


def test_spec_png_dimensions_must_be_pair_of_ints(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"path": "x", "png_dimensions": [1, 2, 3]}]))
    with pytest.raises(ValueError, match="png_dimensions"):
        A.parse_spec(spec)


# ---------------------------------------------------------------------------
# CLI wiring and exit-code contract
# ---------------------------------------------------------------------------
def _run_cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tmaudit", "artifacts", *argv],
        capture_output=True, text=True,
    )


def test_cli_pass_exits_zero(tmp_path):
    p = tmp_path / "ok.pdf"
    p.write_bytes(_pdf())
    r = _run_cli(str(p))
    assert r.returncode == 0, r.stderr


def test_cli_fail_exits_one(tmp_path):
    r = _run_cli("--format", "png", str(tmp_path / "nope.png"))
    assert r.returncode == 1


def test_cli_unverifiable_exits_two(tmp_path):
    """Exit 2 keeps 'could not check' out of the success band in a shell log."""
    p = tmp_path / "x.weirdext"
    p.write_bytes(b"opaque" * 20)
    r = _run_cli(str(p))
    assert r.returncode == 2
    assert "unverifiable" in r.stdout


def test_cli_json_shape(tmp_path):
    p = tmp_path / "ok.pdf"
    p.write_bytes(_pdf())
    r = _run_cli("--json", "--hash", str(p))
    # The table precedes the JSON payload; take from the first top-level brace.
    payload = json.loads(r.stdout[r.stdout.index("\n{"):])
    assert payload["summary"]["PASS"] == 1
    assert payload["artifacts"][0]["verdict"] == "PASS"
    assert len(payload["artifacts"][0]["sha256"]) == 64


def test_cli_spec_file(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(_pdf() + b"{safe_path}\n")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(
        {"format": A.SPEC_FORMAT, "artifacts": [
            {"path": str(p), "format": "pdf",
             "must_not_contain": ["{safe_path}"]},
        ]}
    ))
    r = _run_cli("--spec", str(spec))
    assert r.returncode == 1


def test_cli_min_mtime_applies_to_bare_paths(tmp_path):
    p = tmp_path / "old.pdf"
    p.write_bytes(_pdf())
    r = _run_cli("--min-mtime", "1e18", str(p))
    assert r.returncode == 1


def test_cli_requires_input(tmp_path):
    r = _run_cli()
    assert r.returncode == 2
    assert "need either" in r.stderr


def test_cli_empty_spec_is_operational_error(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([]))
    r = _run_cli("--spec", str(spec))
    assert r.returncode == 2
