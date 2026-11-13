"""MRB #6797 hostile pin: harvest lesson pins jeeves/docs Groups table path."""
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


def test_mrb6797_harvested_lessons_groups_table_jeeves_docs_path():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    needle = (
        "Jeeves appliance UI FR-04 Groups table lives at jeeves/docs/feature-request-jeeves-appliance-ui-*.md"
    )
    lines = [ln for ln in section.splitlines() if needle in ln]
    assert lines, "harvest lesson missing from Harvested lessons"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "do not invent the table" in lines[0]
    assert "git info/exclude" in lines[0]
    assert "SettingSpec" in lines[0]
