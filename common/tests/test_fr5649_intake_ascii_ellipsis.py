"""FR #5649: common/scripts/intake.py must stay BOM-less ASCII (no U+2026)."""
from __future__ import annotations

from repo_layout import ROOT

INTAKE = ROOT / "common/scripts/intake.py"


def test_fr5649_intake_py_bomless_ascii():
    raw = INTAKE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\xe2\x80\xa6" not in raw  # U+2026 ellipsis
    text = raw.decode("ascii")  # raises if non-ASCII remains
    assert "parent..." in text or "..." in text
