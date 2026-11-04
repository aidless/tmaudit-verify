"""tmaudit.artifacts — artifact-side verification for agent tool calls.

Motivation
----------
A tool call that exits 0 has not necessarily done anything. In the audit of
HKUDS/CLI-Anything (2026-10-24) the draw.io harness returned

    {"action": "export_fallback", "note": "draw.io CLI not found..."}

with **exit code 0** when the backend was missing: the caller was told the
export succeeded, and no PNG existed on disk. The same audit found FreeCAD's
macro generator silently collapsing ``pad(length=42)`` to ``Length = 10.0``
and dropping boolean results entirely, while ``export`` still reported success.
Both are *process signals* masquerading as *results*.

The rule this module encodes:

    The only admissible evidence that a side effect occurred is a property of
    the artifact, measured independently of the tool's return value.

Design constraints
------------------
* **Stdlib only.** ``pyproject.toml`` declares ``dependencies = []`` and that
  stays true: magic-byte, ZIP, PDF, PNG, and text checks are implemented here
  directly. Anything requiring a third-party parser degrades to
  ``UNVERIFIABLE`` rather than importing it.
* **Three verdicts, not two.** ``PASS`` / ``FAIL`` / ``UNVERIFIABLE``. The most
  common failure in harness code is treating "could not check" as "checked and
  fine" — test suites that skip when a dependency is missing still go green.
  ``UNVERIFIABLE`` is a first-class outcome and never compares equal to
  ``PASS``.
* **Evidence is graded.** A run that only established existence is not the same
  as one that parsed the file and matched its content. ``Evidence`` records the
  strongest level actually reached so a report cannot overstate itself.
* **No silent fallbacks.** An unknown format is not assumed valid; it is
  ``UNVERIFIABLE`` with the reason recorded.

Caveats that belong to the method, not the implementation
---------------------------------------------------------
* ``PASS`` bounds *format conformance and declared-content presence*. It never
  establishes that the artifact is the one the user wanted.
* A stale artifact from a previous run satisfies every check below unless
  ``min_mtime`` is supplied. Callers that can capture a start timestamp should
  always pass it.
* Semantic checks are only as strong as the expectation supplied. Comparing a
  rendered frame against the source is the only way to catch a filter that was
  written to the project file and then dropped by the renderer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
import zipfile
import zlib
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "Verdict",
    "Evidence",
    "Spec",
    "CheckResult",
    "check_artifact",
    "check_all",
    "parse_spec",
    "SPEC_FORMAT",
    "MAGIC",
    "detect_format",
    "cmd_artifacts",
]

#: Bumped when the spec schema changes shape. Specs carrying a different value
#: are rejected rather than silently reinterpreted.
SPEC_FORMAT = "tmaudit-artifact-spec/1"


# ---------------------------------------------------------------------------
# Verdict tri-state
# ---------------------------------------------------------------------------
class Verdict(IntEnum):
    """Outcome of one artifact check.

    ``UNVERIFIABLE`` is deliberately distinct from both other members. It means
    the check could not be carried out — missing file, missing capability,
    format not recognised — and must never be counted as a success.
    """

    PASS = 0
    FAIL = 1
    UNVERIFIABLE = 2

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.name


class Evidence(IntEnum):
    """Strongest evidence level a check actually established.

    Ordered: a higher level implies the lower ones were also established. The
    levels exist so that a report states *how* something was verified instead of
    collapsing every outcome into "ok".
    """

    NONE = 0
    """Nothing was established."""

    EXISTS = 1
    """Path exists and can be stat'ed."""

    NONTRIVIAL = 2
    """Size is above the configured floor."""

    MAGIC = 3
    """Leading bytes match a known container signature."""

    PARSED = 4
    """The file was parsed with the standard library (ZIP/PDF/PNG/text)."""

    SEMANTIC = 5
    """Content was matched against a declared expectation."""


# ---------------------------------------------------------------------------
# Format signatures
# ---------------------------------------------------------------------------
#: ``offset -> (signature, human name)``. Offsets above zero exist because some
#: containers place a length or box header before the type tag.
MAGIC: dict[str, list[tuple[int, bytes, str]]] = {
    "pdf": [(0, b"%PDF-", "PDF document")],
    "zip": [(0, b"PK\x03\x04", "ZIP container")],
    "png": [(0, b"\x89PNG\r\n\x1a\n", "PNG image")],
    "jpeg": [(0, b"\xff\xd8\xff", "JPEG image")],
    "gif": [(0, b"GIF8", "GIF image")],
    "webp": [(0, b"RIFF", "RIFF container")],
    "mp4": [(4, b"ftyp", "ISO base media (MP4/MOV)")],
    "wav": [(0, b"RIFF", "RIFF container")],
    "ogg": [(0, b"OggS", "Ogg stream")],
    "flac": [(0, b"fLaC", "FLAC audio")],
    "elf": [(0, b"\x7fELF", "ELF binary")],
    "gzip": [(0, b"\x1f\x8b", "gzip stream")],
    "sqlite": [(0, b"SQLite format 3\x00", "SQLite database")],
}

#: Formats whose payload is text with no container signature. Generated scripts,
#: g-code, and config dumps fall here: there is nothing to match on, so the
#: check is "decodes as text, then satisfies the declared content rules".
TEXT_FORMATS = frozenset({"text", "txt", "py", "gcode", "json", "yaml", "csv", "md"})

#: Extension aliases that share a container. ``.docx`` is a ZIP; the ZIP check
#: cannot tell you it is a Word file, so ``check_zip_members`` carries the
#: format-specific part.
_EXT_TO_FORMAT = {
    ".pdf": "pdf",
    ".zip": "zip", ".docx": "zip", ".xlsx": "zip", ".pptx": "zip",
    ".odt": "zip", ".ods": "zip", ".odp": "zip", ".3mf": "zip",
    ".epub": "zip", ".whl": "zip", ".jar": "zip", ".pyz": "zip",
    ".png": "png",
    ".jpg": "jpeg", ".jpeg": "jpeg",
    ".gif": "gif",
    ".webp": "webp",
    ".mp4": "mp4", ".mov": "mp4", ".m4v": "mp4",
    ".wav": "wav",
    ".ogg": "ogg",
    ".flac": "flac",
    ".so": "elf", ".o": "elf",
    ".gz": "gzip", ".tgz": "gzip",
    ".sqlite": "sqlite", ".db": "sqlite",
    # Text payloads — verified by decoding and content rules, not by signature.
    ".py": "text", ".txt": "text", ".gcode": "text", ".nc": "text",
    ".json": "text", ".yaml": "text", ".yml": "text", ".csv": "text",
    ".md": "text", ".toml": "text", ".ini": "text", ".cfg": "text",
}

#: OOXML / ODF members that must be present and non-empty for the container to
#: be the document type its extension claims.
_DOC_MEMBERS: dict[str, tuple[str, ...]] = {
    "docx": ("[Content_Types].xml", "word/document.xml"),
    "xlsx": ("[Content_Types].xml", "xl/workbook.xml"),
    "pptx": ("[Content_Types].xml", "ppt/presentation.xml"),
    "odt": ("mimetype", "content.xml"),
    "ods": ("mimetype", "content.xml"),
    "odp": ("mimetype", "content.xml"),
}


def detect_format(path: Path, declared: str | None = None) -> str | None:
    """Resolve the expected container format.

    A declared format always wins (it is what the caller asserts the file is).
    Otherwise the extension is consulted. Returns ``None`` when nothing is
    known, which makes the check ``UNVERIFIABLE`` rather than assumed-valid.
    """
    if declared:
        return declared.lower().lstrip(".")
    return _EXT_TO_FORMAT.get(path.suffix.lower())


# ---------------------------------------------------------------------------
# Check result
# ---------------------------------------------------------------------------
@dataclass
class CheckResult:
    """One artifact, one verdict, with the evidence that produced it."""

    path: str
    verdict: Verdict
    evidence: Evidence
    format: str | None = None
    size: int | None = None
    sha256: str | None = None
    reasons: list[str] = field(default_factory=list)
    """Every finding, in order. Failures and blockers both land here."""

    @property
    def ok(self) -> bool:
        """True only for ``PASS``. ``UNVERIFIABLE`` is not ok."""
        return self.verdict is Verdict.PASS

    def as_row(self) -> str:
        tag = self.verdict.name
        lvl = self.evidence.name
        size = f"{self.size:,}B" if self.size is not None else "-"
        return (
            f"[{tag:<12}] E{self.evidence.value} {lvl:<9} "
            f"{size:>12}  {self.path}"
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = self.verdict.name
        d["evidence"] = self.evidence.name
        d["ok"] = self.ok
        return d


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------
@dataclass
class Spec:
    """Declarative expectation for one artifact.

    Every field is optional except ``path``; whatever is omitted is simply not
    checked, and the resulting ``evidence`` level reflects that honestly.
    """

    path: str
    format: str | None = None
    min_bytes: int = 0
    """Floor on file size. ``0`` disables the check (existence only)."""

    min_mtime: float | None = None
    """Epoch seconds. Rejects artifacts older than this — the stale-artifact
    guard. Callers should pass the time the producing command started."""

    zip_members: tuple[str, ...] = ()
    """Members that must exist inside the archive. Empty means none required."""

    must_contain: tuple[str, ...] = ()
    """Literal byte sequences that must appear in the file."""

    must_not_contain: tuple[str, ...] = ()
    """Literal byte sequences that must NOT appear (e.g. ``{safe_path}``)."""

    text_regex: str | None = None
    """Regex that must match the decoded text payload."""

    min_pages_pdf: int | None = None
    """Lower bound on ``/Type /Page`` occurrences in a PDF."""

    python_syntax: bool = False
    """Parse the payload as Python. Catches generated scripts that a template
    bug has left syntactically invalid — the cheapest failure to cause and the
    easiest to miss, because the file still exists and still has the right
    extension."""

    png_dimensions: tuple[int, int] | None = None
    """Exact ``(width, height)`` for PNG. Requires no third-party library."""

    label: str = ""
    """Human label used in reports; defaults to the basename."""

    @property
    def name(self) -> str:
        return self.label or os.path.basename(self.path)


_SPEC_KEYS = {
    "path", "format", "min_bytes", "min_mtime", "zip_members", "must_contain",
    "must_not_contain", "text_regex", "min_pages_pdf", "python_syntax",
    "png_dimensions", "label",
}


def _coerce_spec(item: dict[str, Any], index: int) -> Spec:
    unknown = {k for k in item if k not in _SPEC_KEYS and not k.startswith("_")}
    if unknown:
        raise ValueError(
            f"spec #{index} has unknown key(s) {sorted(unknown)}; "
            f"allowed: {sorted(_SPEC_KEYS)} (or any key starting with '_' for "
            f"free-form annotation)"
        )
    if "path" not in item:
        raise ValueError(f"spec #{index} is missing 'path'")

    dims = item.get("png_dimensions")
    if dims is not None:
        if (not isinstance(dims, (list, tuple)) or len(dims) != 2
                or not all(isinstance(v, int) for v in dims)):
            raise ValueError(
                f"spec #{index} field 'png_dimensions' must be [width, height] ints"
            )
        dims = (int(dims[0]), int(dims[1]))

    return Spec(
        path=str(item["path"]),
        format=item.get("format"),
        min_bytes=int(item.get("min_bytes", 0)),
        min_mtime=(None if item.get("min_mtime") is None
                   else float(item["min_mtime"])),
        zip_members=tuple(item.get("zip_members") or ()),
        must_contain=tuple(item.get("must_contain") or ()),
        must_not_contain=tuple(item.get("must_not_contain") or ()),
        text_regex=item.get("text_regex"),
        min_pages_pdf=(None if item.get("min_pages_pdf") is None
                       else int(item["min_pages_pdf"])),
        python_syntax=bool(item.get("python_syntax", False)),
        png_dimensions=dims,
        label=str(item.get("label") or ""),
    )


def parse_spec(path: Path) -> list[Spec]:
    """Load a spec file: either a list of specs or ``{"artifacts": [...]}``.

    Raises
    ------
    ValueError
        On a wrong container shape, a missing ``path``, an unknown key, or a
        mismatched ``format`` marker. Unknown keys are rejected because a
        typo'd key would otherwise silently disable the check it was meant to
        add — the same class of bug as an unsupported CLI flag being ignored.

    Keys beginning with ``_`` are treated as annotations and ignored. The
    convention is unambiguous because no real key starts with an underscore,
    and it lets a spec explain *why* a check exists next to the check.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        marker = raw.get("format")
        if marker is not None and marker != SPEC_FORMAT:
            raise ValueError(
                f"spec format is {marker!r}, expected {SPEC_FORMAT!r}"
            )
        if "artifacts" not in raw:
            raise ValueError(
                "spec object must contain 'artifacts' (a list of "
                "{path, ...} objects)"
            )
        raw = raw["artifacts"]
    if not isinstance(raw, list):
        raise ValueError("spec file must contain a list of spec objects")
    return [_coerce_spec(item, i) for i, item in enumerate(raw)]


# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------
def _read_head(path: Path, n: int = 512) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(n)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _png_dimensions(head: bytes) -> tuple[int, int] | None:
    """Read IHDR width/height without Pillow.

    PNG layout: 8-byte signature, 4-byte length, b'IHDR', then width and height
    as big-endian uint32.
    """
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if head[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", head[16:24])
    return int(width), int(height)


def _pdf_page_count(path: Path) -> int | None:
    """Count ``/Type /Page`` occurrences in the raw PDF bytes.

    This over-counts when a page object is referenced from a cross-reference
    stream as well as defined, and under-counts on object streams that compress
    the page dictionaries. It is a *floor* check — enough to distinguish a real
    multi-page render from an empty shell — not a parser. Returns ``None`` when
    the header is not a PDF at all.
    """
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        return None
    # Both "/Type /Page" and "/Type/Page" appear in the wild; "/Pages" must not
    # be counted, so require a non-letter right after "Page".
    hits = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))
    return hits


def _decompressible_streams(path: Path) -> tuple[int, int]:
    """Return ``(streams_found, streams_that_look_valid)`` for a PDF.

    A PDF whose content streams are neither inflatable nor plausible plain
    PDF operators is structurally broken even though it carries the right
    magic bytes. Counting a non-empty undecodable blob as "good" would let a
    corrupt file pass, so the plaintext acceptance is narrow: the bytes must
    decode as ASCII and contain at least one real PDF content operator.
    """
    data = path.read_bytes()
    found = 0
    good = 0
    operator = re.compile(
        rb"(?:^|[\s\]\)>/])(?:BT|ET|Tj|TJ|Td|TD|Tm|Tf|re|S|s|f|W|n|q|Q|Do|BI)(?=[\s\[(<]|$)"
    )
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        found += 1
        body = match.group(1).rstrip(b"\r\n")
        if not body.strip():
            good += 1          # an empty stream is legal
            continue
        try:
            inflated = zlib.decompress(body)
        except zlib.error:
            inflated = None
        if inflated is not None:
            good += 1
            continue
        # Not deflate: accept only if it reads as plain PDF content operators.
        try:
            body.decode("ascii")
        except UnicodeDecodeError:
            continue
        if operator.search(body):
            good += 1
    return found, good


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------
def check_artifact(spec: Spec, *, compute_hash: bool = False) -> CheckResult:
    """Verify one artifact against its spec.

    Ordering matters: cheap structural facts are established first, so the
    ``evidence`` level reported is the strongest one actually reached. The
    first hard failure short-circuits with ``FAIL``; a missing capability
    yields ``UNVERIFIABLE`` and is never upgraded to ``PASS``.
    """
    path = Path(spec.path)
    reasons: list[str] = []

    # ---- EXISTS -----------------------------------------------------------
    if not path.exists():
        return CheckResult(
            path=str(path), verdict=Verdict.FAIL, evidence=Evidence.NONE,
            reasons=["file does not exist"],
        )
    if not path.is_file():
        return CheckResult(
            path=str(path), verdict=Verdict.FAIL, evidence=Evidence.NONE,
            reasons=["path exists but is not a regular file"],
        )
    try:
        st = path.stat()
    except OSError as exc:  # pragma: no cover - races only
        return CheckResult(
            path=str(path), verdict=Verdict.UNVERIFIABLE, evidence=Evidence.NONE,
            reasons=[f"stat failed: {exc}"],
        )

    level = Evidence.EXISTS
    size = st.st_size
    fmt = detect_format(path, spec.format)

    # ---- NONTRIVIAL -------------------------------------------------------
    if size == 0:
        return CheckResult(
            path=str(path), verdict=Verdict.FAIL, evidence=level,
            format=fmt, size=size,
            reasons=["file is empty (0 bytes)"],
        )
    if spec.min_bytes and size < spec.min_bytes:
        return CheckResult(
            path=str(path), verdict=Verdict.FAIL, evidence=level,
            format=fmt, size=size,
            reasons=[f"size {size:,}B is below the floor of {spec.min_bytes:,}B"],
        )
    level = Evidence.NONTRIVIAL

    # ---- STALE GUARD ------------------------------------------------------
    if spec.min_mtime is not None and st.st_mtime < spec.min_mtime:
        age = spec.min_mtime - st.st_mtime
        return CheckResult(
            path=str(path), verdict=Verdict.FAIL, evidence=level,
            format=fmt, size=size,
            reasons=[
                f"artifact predates the run by {age:.1f}s "
                f"(mtime={st.st_mtime:.0f}, earliest accepted="
                f"{spec.min_mtime:.0f}); likely left over from a previous run"
            ],
        )

    head = _read_head(path)

    # ---- MAGIC ------------------------------------------------------------
    if fmt is None:
        # No declared format and no extension mapping. Everything below needs a
        # container assumption, so stop here rather than guess.
        digest = _sha256(path) if compute_hash else None
        return CheckResult(
            path=str(path), verdict=Verdict.UNVERIFIABLE, evidence=level,
            format=None, size=size, sha256=digest,
            reasons=[
                "format unknown (no 'format' in spec and extension not mapped); "
                "existence and size only — this is not a format validation"
            ],
        )

    signatures = MAGIC.get(fmt)
    text_payload: bytes | None = None

    if fmt in TEXT_FORMATS:
        # No signature to assert. The strongest honest claim is "decodes as
        # text", which is PARSED — a generated script or g-code dump is only
        # checkable at the content level, so the content rules below carry the
        # weight.
        try:
            head.decode("utf-8")
        except UnicodeDecodeError as exc:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=[f"declared text but the first bytes are not UTF-8: {exc}"],
            )
        level = Evidence.PARSED
        text_payload = path.read_bytes()

    elif signatures is None:
        return CheckResult(
            path=str(path), verdict=Verdict.UNVERIFIABLE, evidence=level,
            format=fmt, size=size,
            reasons=[f"no signature table for format {fmt!r}"],
        )

    else:
        for offset, signature, _label in signatures:
            if head[offset:offset + len(signature)] != signature:
                return CheckResult(
                    path=str(path), verdict=Verdict.FAIL, evidence=level,
                    format=fmt, size=size,
                    reasons=[
                        f"magic mismatch for {fmt}: expected {signature!r} at "
                        f"offset {offset}, found "
                        f"{head[offset:offset + len(signature)]!r}"
                    ],
                )
        level = Evidence.MAGIC

    # ---- PARSED -----------------------------------------------------------
    if fmt == "zip":
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
                if zf.testzip() is not None:
                    return CheckResult(
                        path=str(path), verdict=Verdict.FAIL, evidence=level,
                        format=fmt, size=size,
                        reasons=["ZIP CRC check failed on a member"],
                    )
        except zipfile.BadZipFile as exc:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=[f"not a readable ZIP container: {exc}"],
            )

        # Document-type members, when the extension names one.
        want = _DOC_MEMBERS.get(path.suffix.lower().lstrip("."), ())
        missing = [m for m in want if m not in names]
        if missing:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=[f"{path.suffix} container is missing member(s) {missing}"],
            )

        # Explicitly required members.
        missing = [m for m in spec.zip_members if m not in names]
        if missing:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=[f"required ZIP member(s) absent: {missing}"],
            )
        level = Evidence.PARSED

        # Concatenate text-ish members so must_contain/text_regex can apply.
        chunks: list[bytes] = []
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.endswith((".xml", ".txt", ".csv", ".json", ".rels",
                                  ".mimetype", ".html", ".svg")):
                    try:
                        chunks.append(zf.read(name))
                    except (KeyError, RuntimeError, zipfile.BadZipFile):
                        continue
        text_payload = b"\n".join(chunks) if chunks else None

    elif fmt == "pdf":
        pages = _pdf_page_count(path)
        if pages is None:  # pragma: no cover - magic already checked
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size, reasons=["PDF header unreadable"],
            )
        found, good = _decompressible_streams(path)
        if found and good == 0:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=[f"none of {found} content stream(s) could be decoded"],
            )
        reasons.append(f"{pages} page object(s), {good}/{found} stream(s) decodable")
        if spec.min_pages_pdf is not None and pages < spec.min_pages_pdf:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=reasons + [
                    f"page count {pages} is below the floor of "
                    f"{spec.min_pages_pdf}"
                ],
            )
        level = Evidence.PARSED
        text_payload = path.read_bytes()

    elif fmt == "png":
        dims = _png_dimensions(head)
        if dims is None:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=["PNG header present but IHDR is unreadable"],
            )
        reasons.append(f"dimensions {dims[0]}x{dims[1]}")
        if spec.png_dimensions is not None and dims != spec.png_dimensions:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=reasons + [
                    f"dimensions {dims[0]}x{dims[1]} != expected "
                    f"{spec.png_dimensions[0]}x{spec.png_dimensions[1]}"
                ],
            )
        level = Evidence.PARSED

    elif fmt == "sqlite":
        # Header is enough to assert the container; schema checks belong to a
        # caller that knows the expected tables.
        level = Evidence.PARSED

    elif fmt in TEXT_FORMATS:
        # Already decoded above; PARSED was set there. Nothing more to add.
        reasons.append("decoded as UTF-8 text")

    else:
        # Magic verified, but this module has no parser for the container, so
        # it cannot claim PARSED.
        reasons.append(
            f"{fmt}: container signature verified, no structural parser in "
            f"this module (evidence capped at MAGIC)"
        )

    # ---- SYNTAX -----------------------------------------------------------
    # Checked before content rules: a file that will not parse cannot be
    # searched meaningfully, and the parse error carries the line number that
    # the content checks would otherwise have to guess at.
    if spec.python_syntax:
        if text_payload is None:
            return CheckResult(
                path=str(path), verdict=Verdict.UNVERIFIABLE, evidence=level,
                format=fmt, size=size,
                reasons=reasons + [
                    "python_syntax requested but the payload is binary; "
                    "declare format 'text' (or a .py extension) to enable it"
                ],
            )
        import ast
        try:
            source = text_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=reasons + [f"declared python but not UTF-8: {exc}"],
            )
        try:
            ast.parse(source)
        except SyntaxError as exc:
            return CheckResult(
                path=str(path), verdict=Verdict.FAIL, evidence=level,
                format=fmt, size=size,
                reasons=reasons + [
                    f"python syntax error at line {exc.lineno}"
                    f"{f' col {exc.offset}' if exc.offset else ''}: {exc.msg}"
                ],
            )
        reasons.append("parses as Python")
        if level < Evidence.PARSED:
            level = Evidence.PARSED

    # ---- SEMANTIC ---------------------------------------------------------
    semantic_checks = bool(
        spec.must_contain or spec.must_not_contain or spec.text_regex
    )
    if semantic_checks:
        haystack = text_payload if text_payload is not None else path.read_bytes()

        for needle in spec.must_contain:
            if needle.encode() not in haystack:
                return CheckResult(
                    path=str(path), verdict=Verdict.FAIL, evidence=level,
                    format=fmt, size=size,
                    reasons=reasons + [f"required content absent: {needle!r}"],
                )
        for needle in spec.must_not_contain:
            if needle.encode() in haystack:
                return CheckResult(
                    path=str(path), verdict=Verdict.FAIL, evidence=level,
                    format=fmt, size=size,
                    reasons=reasons + [
                        f"forbidden content present: {needle!r} "
                        f"(this is the unrendered-placeholder pattern)"
                    ],
                )
        if spec.text_regex:
            try:
                pattern = re.compile(spec.text_regex)
            except re.error as exc:
                return CheckResult(
                    path=str(path), verdict=Verdict.UNVERIFIABLE, evidence=level,
                    format=fmt, size=size,
                    reasons=reasons + [f"text_regex does not compile: {exc}"],
                )
            try:
                decoded = haystack.decode("utf-8", errors="replace")
            except Exception:  # pragma: no cover - replace never raises
                decoded = ""
            if not pattern.search(decoded):
                return CheckResult(
                    path=str(path), verdict=Verdict.FAIL, evidence=level,
                    format=fmt, size=size,
                    reasons=reasons + [
                        f"text_regex {spec.text_regex!r} did not match"
                    ],
                )
        level = Evidence.SEMANTIC

    digest = _sha256(path) if compute_hash else None

    # A file whose format was recognised but never structurally parsed cannot
    # be reported as fully verified; it is still a PASS for what was asserted,
    # with evidence capped honestly at MAGIC.
    return CheckResult(
        path=str(path), verdict=Verdict.PASS, evidence=level,
        format=fmt, size=size, sha256=digest,
        reasons=reasons or ["existence and size verified"],
    )


def check_all(
    specs: Sequence[Spec],
    *,
    compute_hash: bool = False,
) -> list[CheckResult]:
    """Check every spec; order is preserved so reports line up with the spec file."""
    return [check_artifact(s, compute_hash=compute_hash) for s in specs]


# ---------------------------------------------------------------------------
# Aggregate reporting
# ---------------------------------------------------------------------------
def summarise(results: Sequence[CheckResult]) -> dict[str, Any]:
    """Count verdicts and report the weakest evidence level seen.

    ``all_ok`` is True only when every result is ``PASS``. An
    ``UNVERIFIABLE`` entry makes it False, which is the whole point: a run that
    could not check something has not passed.
    """
    counts = {v.name: 0 for v in Verdict}
    for r in results:
        counts[r.verdict.name] += 1
    weakest = min((r.evidence for r in results), default=Evidence.NONE)
    return {
        "total": len(results),
        **counts,
        "weakest_evidence": weakest.name,
        "all_ok": bool(results) and counts["PASS"] == len(results),
    }


def _render_table(results: Sequence[CheckResult]) -> None:
    if not results:
        print("no artifacts checked")
        return
    width = min(max(len(r.path) for r in results), 60)
    print(f"{'verdict':<14} {'evidence':<12} {'size':>14}  artifact")
    print("-" * (width + 46))
    for r in results:
        tag = r.verdict.name
        size = f"{r.size:,}B" if r.size is not None else "-"
        print(f"{tag:<14} E{r.evidence.value} {r.evidence.name:<9} "
              f"{size:>14}  {r.path}")
    print("-" * (width + 46))
    s = summarise(results)
    print(
        f"{s['total']} artifact(s): {s['PASS']} pass, {s['FAIL']} fail, "
        f"{s['UNVERIFIABLE']} unverifiable; weakest evidence "
        f"{s['weakest_evidence']}"
    )
    if s["UNVERIFIABLE"]:
        print(
            "note: unverifiable is not a pass — those artifacts were not "
            "validated at the level their format allows"
        )


# ---------------------------------------------------------------------------
# CLI handler (wired into tmaudit.cli)
# ---------------------------------------------------------------------------
def cmd_artifacts(args) -> int:
    """``tmaudit artifacts ...`` — see :mod:`tmaudit.cli` for the flags.

    Exit codes
    ----------
    0  every artifact passed
    1  at least one artifact failed
    2  operational error (bad spec, unreadable file) *or* every artifact was
       unverifiable — indistinguishable from success in a log, so it gets its
       own non-zero code
    """
    try:
        if getattr(args, "spec", None):
            specs = parse_spec(Path(args.spec))
        elif getattr(args, "paths", None):
            specs = [
                Spec(path=p, format=args.format,
                     min_bytes=args.min_bytes,
                     min_pages_pdf=getattr(args, "min_pages_pdf", None),
                     python_syntax=getattr(args, "python_syntax", False))
                for p in args.paths
            ]
        else:
            print(
                "tmaudit artifacts: need either --spec FILE or one or more "
                "paths",
                file=sys.stderr,
            )
            return 2

        if not specs:
            print("tmaudit artifacts: spec file contains no artifacts",
                  file=sys.stderr)
            return 2

        if getattr(args, "min_mtime", None) is not None:
            # Applied to specs that did not pin their own, so a run-wide start
            # time can reject stale artifacts without editing the spec.
            cutoff = float(args.min_mtime)
            for s in specs:
                if s.min_mtime is None:
                    s.min_mtime = cutoff

        results = check_all(specs, compute_hash=getattr(args, "hash", False))
        _render_table(results)

        if getattr(args, "json", False):
            print()
            print(json.dumps(
                {
                    "summary": summarise(results),
                    "artifacts": [r.to_dict() for r in results],
                },
                ensure_ascii=False, indent=2,
            ))

        s = summarise(results)
        if s["FAIL"]:
            return 1
        if s["PASS"] == 0:
            return 2
        return 0
    except (ValueError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"tmaudit artifacts: {exc}", file=sys.stderr)
        return 2
