"""FR #8310: harvest SKILL.md must stay under the skill-dag 64KiB cap."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
LESSONS = ROOT / "common" / ".grok" / "skills" / "harvest" / "lessons.md"
CAP = 65536


def test_fr8310_harvest_skill_under_resolve_cap():
    raw = SKILL.read_bytes()
    item = {
        "id": "harvest",
        "description": "honesty box",
        "depends_on": [],
        "path": str(SKILL),
        "bytes": len(raw),
    }
    cost = 64 + len(json.dumps(item).encode("utf-8")) + len(raw)
    assert cost <= CAP
    assert len(raw) <= CAP
    text = raw.decode("utf-8")
    assert "lessons.md" in text
    assert "do not land a second copy" in text.lower()


def test_fr8310_lesson_archive_kept():
    archive = LESSONS.read_text(encoding="utf-8")
    assert "## Harvested lessons (intake)" in archive
    assert "sha_line" in archive
