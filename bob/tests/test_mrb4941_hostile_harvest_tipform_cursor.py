"""docs/mrb-4941: pin harvest TipForm/Status Cursor spending-group lesson (FR #4938)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"

NEEDLE = (
    "TipForm/Status: after account unification omit Cursor spending-group section"
)


def test_harvest_skill_pins_tipform_cursor_spending_group_lesson():
    text = HARVEST.read_text(encoding="utf-8")
    assert text.startswith("---") or "name: harvest" in text[:200]
    # Contiguous playbook line from lesson(harvest) tip #4941 / FR #4938.
    assert NEEDLE in text
    i = text.index(NEEDLE)
    window = text[i : i + 180]
    assert "grok chat / high cost / Low cost" in window
    assert "Grok accounts only" in window
    assert "FR #4938" in window
    # UTF-8 no BOM
    raw = HARVEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
