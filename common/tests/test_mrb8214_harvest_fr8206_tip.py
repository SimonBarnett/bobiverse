"""MRB #8214 hostile pin: harvest tip for FR #8156/#8206 fr7991 fleet .ps1 fixtures."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb8214_harvest_tip_pins_fr8206_fleet_ps1_fixture_lesson():
    text = HARVEST.read_text(encoding="utf-8")
    assert "shipped_script_names always includes fleet .ps1" in text
    assert "FR #8156" in text
    assert "fr7991" in text
    assert "FR #8206" in text
