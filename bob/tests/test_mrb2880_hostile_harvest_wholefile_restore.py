"""MRB #2880 hostile pins for harvest whole-file SKILL restore playbook lesson."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb2880_harvest_wholefile_restore_playbook_contiguous():
    raw = HARVEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "harvest SKILL.md must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    # Contiguous playbook from harvest-lesson #2880 (FR #2835 session)
    needle = (
        "When a whole-file SKILL.md overwrite drops rules, restore from git show reverse of the wipe commit; "
        "widen Measure-BobTrayWorkerSeats pin windows when comments grow; "
        "drop nested skill-dba\\.grok from Sync-BobiverseAgentFolders staging."
    )
    assert needle in text
    # Still keep product restore pins from docs/mrb-2878 adjacent in the same book
    assert "Skill-intake consolidation:" in text
    assert "One issue per issue:" in text
