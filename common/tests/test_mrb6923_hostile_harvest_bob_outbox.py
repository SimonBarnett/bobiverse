"""MRB #6923 hostile pin: harvest lesson keeps stamped BOB_OUTBOX, no newest-folder glob."""
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


def test_mrb6923_harvested_lessons_keeps_stamped_bob_outbox_path():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    needle = "Keep the stamped BOB_OUTBOX path: recreate that run dir on inject/drain; never glob the newest worker-* folder."
    lines = [ln for ln in section.splitlines() if needle in ln]
    assert lines, "harvest lesson missing from Harvested lessons"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "newest worker-*" in lines[0]
    assert "Path(www / '/jeeves')" in section
