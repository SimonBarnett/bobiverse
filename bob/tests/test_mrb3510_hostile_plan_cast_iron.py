"""docs/mrb-3510: hostile pins for FR #3506 Plan CAST IRON + Sync/ff note."""
from __future__ import annotations

from repo_layout import ROOT

AGENTS = ROOT / "bob/agents/plan/AGENTS.md"


def test_mrb3510_agents_sync_ff_note_and_utf8_xlsx():
    t = AGENTS.read_text(encoding="utf-8")
    assert "FR #3506" in t
    assert "Sync/ff" in t or "Sync/ff or MSI" in t
    assert "skills-visionary" in t
    # UTF-8 arrows (no mojibake) on xlsx bullet
    assert "\u2192" in t  # →
    assert "\u2014" in t  # —
    assert "â" not in t


def test_mrb3510_fr3506_product_tests_present():
    path = ROOT / "bob/tests/test_fr3506_plan_cast_iron_skills_visionary.py"
    assert path.is_file()
    body = path.read_text(encoding="utf-8")
    assert "skills-visionary" in body
    assert "CAST IRON" in body
