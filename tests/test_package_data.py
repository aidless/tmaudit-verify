"""Package-data parity: what the source tree has, an install must have too.

These tests exist because the 0.7.0 candidate wheel shipped without
``detector_config/detector.yaml``. ``package-data`` listed ``templates/*`` and
``configs/*`` but not the yaml, so a non-editable install -- the path every
``pip install tmaudit`` user takes -- silently fell back to the built-in
defaults. The full test suite stayed green because it runs against ``src/``
via ``PYTHONPATH``, where the file is present. Editable installs hide it for
the same reason.

The check therefore reads the **built wheel**, not the source tree. The
structural test below always runs and catches a ``package-data`` omission.
The wheel test skips when ``dist/`` has no wheel. CI runs ``python -m build``
first, so that skip does not happen in CI. A skip is not a pass of the
wheel check. The wheel test is not marked ``slow``: opening a zip is cheap,
and marking it slow deselected it from the same CI job that had just built
the wheel.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "tmaudit"
DIST = ROOT / "dist"


def _declared_package_data() -> list[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(
        r"\[tool\.setuptools\.package-data\][^\[]*?tmaudit\s*=\s*\[(.*?)\]",
        text, re.S,
    )
    assert block, "package-data for tmaudit not found in pyproject.toml"
    return re.findall(r'"([^"]+)"', block.group(1))


def _yaml_files() -> list[Path]:
    return sorted(SRC.rglob("*.yaml"))


class TestPackageDataDeclaration:
    """Structural: the declaration must cover every runtime data file."""

    def test_yaml_files_exist(self):
        # Guard against the test passing vacuously if the file is renamed.
        assert _yaml_files(), "no .yaml under src/tmaudit; update this test"

    @pytest.mark.parametrize(
        "yaml_path",
        _yaml_files(),
        ids=lambda p: p.relative_to(SRC).as_posix(),
    )
    def test_every_yaml_is_declared(self, yaml_path: Path):
        rel = yaml_path.relative_to(SRC)
        patterns = _declared_package_data()
        # A pattern matches if it equals the parent glob for this file's dir.
        wanted = f"{rel.parent.as_posix()}/*{rel.suffix}"
        assert wanted in patterns, (
            f"{rel.as_posix()} is read at runtime but package-data does not "
            f"declare {wanted!r}; patterns are {patterns}. An installed wheel "
            f"would fall back to the built-in defaults."
        )

    def test_templates_still_declared(self):
        # Regression guard on the patterns that were already there.
        patterns = _declared_package_data()
        assert "templates/*.py" in patterns
        assert "configs/*.py" in patterns


class TestBuiltWheelContents:
    """For real: open the newest wheel and look inside it."""

    @staticmethod
    def _wheel() -> Path:
        wheels = sorted(DIST.glob("*.whl"))
        if not wheels:
            pytest.skip("no wheel in dist/; run `python -m build` first")
        return wheels[-1]

    def test_wheel_is_importable_shape(self):
        wheel = self._wheel()
        with zipfile.ZipFile(wheel) as zf:
            names = zf.namelist()
        assert any(n.endswith("tmaudit/__init__.py") for n in names)
        assert any(n.endswith("tmaudit/templates/verify_TEMPLATE.py") for n in names)

    def test_wheel_carries_every_runtime_yaml(self):
        wheel = self._wheel()
        with zipfile.ZipFile(wheel) as zf:
            names = set(zf.namelist())
        missing = [
            rel
            for rel in (p.relative_to(SRC).as_posix() for p in _yaml_files())
            if f"tmaudit/{rel}" not in names
        ]
        assert not missing, (
            f"{wheel.name} is missing {missing}. A pip install of this wheel "
            f"cannot read its own config."
        )
