"""MRB #7023 hostile pin: harvest lesson for SYSTEM python resolve (FR #7020)."""
from __future__ import annotations

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[2]
    / "common"
    / ".grok"
    / "skills"
    / "harvest"
    / "SKILL.md"
)


def test_mrb7023_harvested_lessons_pins_fr7020_python_resolve():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    needle = "FR #7020"
    lines = [ln for ln in section.splitlines() if needle in ln and "BOBIVERSE_PYTHON" in ln]
    assert lines, "harvest lesson missing from Harvested lessons"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "config/python.path" in lines[0]
    assert "WindowsApps" in lines[0]
    assert "BUILD fail" in lines[0] or "releases the machine lock" in lines[0]
    assert "python-status.json" in lines[0]
