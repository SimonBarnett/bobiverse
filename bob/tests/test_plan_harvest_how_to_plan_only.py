"""Plan seats harvest only how-to-plan lessons, never plan content (owner rule 2026-10-08, #3097).

FR #8833: in-tree plan AGENTS/skills removed; bob_worker.plan_prompt + MRB/intake pins remain.
"""
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


def test_plan_prompt_says_how_to_plan_only():
    p = bob_worker.plan_prompt(r"C:\ai\bob\plan")
    assert "HARVEST HOW-TO-PLAN ONLY" in p
    assert "SimonBarnett/skills-visionary" in p
    assert "NEVER harvest the plan itself" in p
    for word in ("requirements", "designs", "FR/issue lists"):
        assert word in p


def test_plan_pointer_readme_forbids_readding_source():
    text = _read("bob/agents/plan/README.md")
    assert "skills-visionary" in text
    assert "Do not re-add" in text or "removed" in text.lower()


def test_mrb_closes_plan_content_and_moves_planning_lesson():
    text = _read("bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md")
    assert "plan content, not a lesson" in text
    assert "MRB CLOSED - plan-content" in text
    assert "SimonBarnett/skills-visionary" in text
    assert "unless** it is plan content" in text


def test_intake_lesson_pr_instruction_mentions_plan_content():
    t = intake.LESSON_PR_MRB_INSTRUCTION
    assert "plan content, not a lesson" in t
    assert "skills-visionary" in t
    assert "OPEN" in t  # FR #3299 pin still holds
