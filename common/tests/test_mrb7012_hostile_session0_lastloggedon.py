"""MRB #7012 hostile pin: harvest lesson for Session 0 LastLoggedOn / stamp."""
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


def test_mrb7012_harvested_lessons_pins_session0_lastloggedon():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    needle = "LastLoggedOnUser"
    lines = [ln for ln in section.splitlines() if needle in ln and "CIM" in ln]
    assert lines, "harvest lesson missing from Harvested lessons"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "system-profile-skipped" in lines[0]
    assert "interactive-user-home" in lines[0]
    assert "Users" in lines[0]
