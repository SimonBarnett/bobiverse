"""Hostile pins for MRB #2929 / FR #2927 dead-pin + fake-MRB heal.

Product already on main via #2929. This docs/mrb module pins contiguous skill
+ code phrases so a later wipe cannot drop the one-offer / prune playbook.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-troubleshooting" / "SKILL.md"
GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"
PRODUCT_TEST = ROOT / "jeeves" / "tests" / "test_fr2927_offer_pin_and_prune.py"


def test_mrb2929_skill_pins_fr2927_playbook():
    text = SKILL.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "FR #2927" in text
    assert "non-empty" in text
    assert "one-offer-per-job" in text
    assert "pull provenance" in text or "force" in text
    assert "bare fake MRB" in text or "fake MRB" in text


def test_mrb2929_gitclaim_pins_dead_pin_and_provenance():
    text = GITCLAIM.read_text(encoding="utf-8")
    assert "_mrb_row_has_pull_provenance" in text
    assert "bool(live_l) and to_c not in live_l" in text
    assert "force=True" in text or "_heal_mrb_pull_url(row, force=True)" in text
    assert "never invent a pull URL for fake/bare MRB" in text or "FR #2927" in text


def test_mrb2929_product_test_module_present():
    text = PRODUCT_TEST.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "test_fr2927_empty_live_keeps_one_offer_per_job" in text
    assert "test_fr2927_heal_skips_bare_fake_mrb" in text
    assert "test_fr2927_heal_lesson_missing_url" in text
