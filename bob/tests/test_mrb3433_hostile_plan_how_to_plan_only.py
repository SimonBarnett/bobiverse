"""Hostile pins for MRB #3433: Plan harvest how-to-plan only (owner rule / #3097)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker  # noqa: E402
import intake  # noqa: E402


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_plan_prompt_contiguous_how_to_plan_cast_iron():
    p = bob_worker.plan_prompt(r"C:\ai\bob\plan")
    assert "HARVEST HOW-TO-PLAN ONLY:" in p
    assert "NEVER harvest the plan itself" in p
    assert "-Repo SimonBarnett/skills-visionary" in p
    assert "requirements, designs, architecture or product decisions, FR/issue lists" in p


def test_mrb_checklist_item_5_and_plan_content_exit_contiguous():
    text = _read("bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md")
    assert "5. **Plan content?** Only how-to-plan lessons are harvests" in text
    assert "**Plan-content exit (owner rule 2026-10-08, test case #3097):**" in text
    assert "plan content, not a lesson" in text
    assert "MRB CLOSED - plan-content" in text
    assert "unless** it is plan content (checklist 5)" in text


def test_harvest_skills_visionary_different_product_test():
    text = _read("bob/agents/plan/.grok/skills/harvest-skills-visionary/SKILL.md")
    assert "## What belongs here (how-to-plan only)" in text
    assert "would this line help a Plan seat plan a DIFFERENT product?" in text
    assert "bobiverse#3097" in text


def test_intake_lesson_instruction_plan_content_never_hold_open():
    t = intake.LESSON_PR_MRB_INSTRUCTION
    assert "Plan content only" in t
    assert "plan content, not a lesson" in t
    assert "never hold it OPEN" in t
    assert "SimonBarnett/skills-visionary" in t
    assert "leave OPEN if the owner repo does not exist yet" in t
