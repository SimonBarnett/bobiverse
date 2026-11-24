# -*- coding: utf-8 -*-
"""FR #9860: Jeeves skills pin nested/cross-repo Depends-on + no auto-unhold."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPENDS = ROOT / ".grok" / "skills" / "bobiverse-jeeves-agent-depends-on" / "SKILL.md"
DIGEST = ROOT / ".grok" / "skills" / "bobiverse-jeeves-agent-fr-digest" / "SKILL.md"


def test_fr9860_depends_on_skill_pins_cross_repo_and_walk():
    text = DEPENDS.read_text(encoding="utf-8")
    assert "FR #9857" in text or "9857" in text
    assert "FR #9858" in text or "9858" in text
    assert "owner/repo#N" in text
    assert "walk_depends_on_offer_reason" in text or "depends_gate_reason" in text
    assert "No auto-unhold" in text or "no auto-unhold" in text.lower()
    # Fail-when: must not teach auto-unhold next phase as required chair behavior.
    banned = (
        "auto-unhold next phase",
        "auto unhold next phase",
        "chair must unhold the next",
        "automatically unhold the next digest",
    )
    low = text.lower()
    for phrase in banned:
        assert phrase not in low, phrase


def test_fr9860_fr_digest_skill_pins_nested_parallel_no_auto_unhold():
    text = DIGEST.read_text(encoding="utf-8")
    assert "No auto-unhold" in text or "no auto-unhold" in text.lower()
    assert "Cross-repo" in text or "owner/repo#digest" in text
    assert "Parallel default" in text or "parallel" in text.lower()
    assert "operator" in text.lower() or "Plan" in text
    low = text.lower()
    # Fail-when: must forbid teaching auto-unhold as required chair behavior
    # (the ban phrase may appear inside the forbid sentence itself).
    assert "must not" in low or "never" in low
    assert "auto-unhold" in low
    # Positive required-behavior wording must not appear without a ban.
    assert "chair must auto-unhold" not in low
    assert "required: auto-unhold next phase" not in low
