"""MRB #3047: Plan-seat xlsx→CSV playbook lives in plan AGENTS (not harvest)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN_AGENTS = ROOT / "bob" / "agents" / "plan" / "AGENTS.md"
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_plan_agents_documents_xlsx_copy_then_openpyxl():
    text = PLAN_AGENTS.read_text(encoding="utf-8-sig")
    assert "openpyxl" in text.lower()
    assert "xlsx" in text.lower() or "workbook" in text.lower()
    assert "work\\plan-" in text or "work/plan-" in text or r"work\plan-" in text


def test_harvest_skill_does_not_park_plan_xlsx_anecdote():
    """Wrong-book tip #3047 must not land under harvest honesty-box."""
    text = HARVEST.read_text(encoding="utf-8-sig")
    # Allow mentioning Plan seats in process text; forbid the specific network-drive scrap.
    assert "Excel COM against M:" not in text
    assert "copy workbook off the network drive into work\\plan-*" not in text
