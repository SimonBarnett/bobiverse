"""MRB #6973 hostile pin: harvest lesson captures native stdout before Stage/heat."""
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


def test_mrb6973_harvested_lessons_pins_ps_stdout_heat0001():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    needle = "capture native stdout (npm ci) or it becomes extra return values"
    lines = [ln for ln in section.splitlines() if needle in ln]
    assert lines, "harvest lesson missing from Harvested lessons"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "HEAT0001" in lines[0]
    assert "[string]$Stage" in lines[0] or "[string]`$Stage" in lines[0] or "string]$Stage" in lines[0]
    assert "heat.exe" in lines[0]
