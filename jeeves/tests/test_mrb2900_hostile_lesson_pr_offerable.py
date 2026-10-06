"""Hostile pins for MRB #2900 / FR #2899 lesson-PR offerability.

Product + fix already on main via #2900 / #2903. This docs/mrb module pins
contiguous skill + code phrases so a later wipe cannot drop the playbook.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-troubleshooting" / "SKILL.md"
GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"


def test_mrb2900_skill_pins_fr2899_playbook():
    text = SKILL.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "FR #2899" in text
    assert "github-resync dropped" in text
    assert "git-claim idle offered" in text
    assert "OFFER_TIMEOUT_S" in text
    assert "harvest-lesson" in text or "harvest-lesson MRBs" in text


def test_mrb2900_gitclaim_pins_survive_and_default_log():
    text = GITCLAIM.read_text(encoding="utf-8")
    assert "skipped_open_pulls" in text
    assert "dropped_detail" in text
    assert "_heal_mrb_pull_url" in text
    assert "_default_log" in text
    assert "git-claim idle offered" in text
    # Survive open pull that missed want (unless draft/receipt skip).
    assert "still-open pull that missed desired" in text or "not in skipped_open_pulls" in text
    assert "dead_pin" in text or "offered_to nick is not live" in text
