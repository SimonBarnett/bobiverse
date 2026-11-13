"""MRB #7044 hostile pin: harvest lesson for OpenCode FUEL_FIXTURE delenv hygiene."""
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


def test_mrb7044_harvested_lessons_pins_fuel_fixture_delenv():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    needle = "FUEL_FIXTURE"
    lines = [ln for ln in section.splitlines() if needle in ln and "delenv" in ln]
    assert lines, "harvest lesson missing from Harvested lessons"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "zen" in lines[0].lower() or "GO_USAGE" in lines[0] or "usage" in lines[0]
    assert "NSSM" in lines[0] or "!build" in lines[0]
