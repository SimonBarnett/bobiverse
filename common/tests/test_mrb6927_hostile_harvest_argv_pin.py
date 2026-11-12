"""MRB #6927 hostile pin: harvest lesson pins args[0] when launch argv grows."""
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


def test_mrb6927_harvested_lessons_pins_args0_when_argv_grows():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    needle = "When launch argv grows (--root packs), pin only args[0] exists; leave extra flags to the FR that added them."
    lines = [ln for ln in section.splitlines() if needle in ln]
    assert lines, "argv-grows harvest lesson missing"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "args[0]" in lines[0]
    assert "Keep the stamped BOB_OUTBOX path" in section
