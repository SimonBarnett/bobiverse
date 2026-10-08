"""Hostile MRB #3342 / FR #3317 + #3299: owning-repo harvest + light triage pins."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import intake

ROOT = Path(__file__).resolve().parents[2]
JOB_MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"


def test_mrb3342_short_triage_contiguous_phrases():
    text = JOB_MRB.read_text(encoding="utf-8")
    assert "FR #3317" in text
    assert "**Short triage checklist (FR #3317):**" in text
    assert "1. **Useful?**" in text
    assert "2. **Generalised?**" in text
    assert "3. **Non-duplicate?**" in text
    assert "4. **Vision / AGENTS fit?**" in text
    assert "MRB CLOSED - not-useful:" in text
    assert "no full test suite" in text.lower() or "Cost cap" in text
    assert text.startswith("\ufeff") is False


def test_mrb3342_step0_owning_repo_contiguous():
    text = JOB_MRB.read_text(encoding="utf-8")
    assert "0. **Who owns this lesson (owning repo)?**" in text
    assert "re-file" in text
    assert "Moved to owner/repo#N" in text or "Moved to" in text
    assert "leave the original **OPEN**" in text or "leave the original OPEN" in text
    assert "owner-missing" in text
    assert "Never** FAIL" in text or "**Never** FAIL" in text
    # Wrong-repo exits must point at step 0 (not silent FAIL-close).
    assert "step 0" in text.lower() or "Step 0" in text or "step **0**" in text


def test_mrb3342_lesson_instruction_mentions_repo():
    assert "repo" in intake.LESSON_PR_MRB_INSTRUCTION.lower()
    assert "light triage" in intake.LESSON_PR_MRB_INSTRUCTION.lower() or (
        "useful" in intake.LESSON_PR_MRB_INSTRUCTION.lower()
    )


def test_mrb3342_owner_missing_and_moved_verdicts():
    assert intake.OWNER_MISSING_LABEL == "owner-missing"
    assert (
        gitclaim.issue_skip_fr_reason(
            title="held: owner-missing SimonBarnett/iphone-text-bridge",
            labels=(intake.OWNER_MISSING_LABEL,),
        )
        == f"label:{intake.OWNER_MISSING_LABEL}"
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB MOVED - SimonBarnett/a-search#610",
            labels=(),
        )
        == "mrb_verdict_title"
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB CLOSED - not-useful: one-box anecdote",
            labels=(),
        )
        == "mrb_verdict_title"
    )


def test_mrb3342_product_default_skills_visionary():
    entry = intake.PRODUCT_DEFAULT_SKILL_BOOK.get("simonbarnett/skills-visionary")
    assert entry is not None
    book, path = entry
    assert book == "harvest-skills-visionary"
    assert path == ".grok/skills/harvest-skills-visionary/SKILL.md"
