"""MRB #5131: FR #5129 CursorTurnWatcher mtime lesson lives in bobiverse-bob-worker."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb5131_worker_skill_pins_fr5129_mtime_fallback():
    raw = SKILL.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", "skill must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    assert "FR #4754" in text
    assert "FR #5129" in text or "#5129" in text
    assert "re-utime" in text
    assert "directory mtime" in text
    assert "file mtimes read as 0" in text


def test_mrb5131_harvest_does_not_repeat_fr5129_bullet():
    text = HARVEST.read_text(encoding="utf-8")
    assert "FR #5129" not in text
    assert "file mtimes read as 0" not in text
