"""Hostile pins for MRB #2940 / FR #2939 repo UAT self-UAT prefilter + escalate.

Product already on main via #2940. Pins code + docs phrases so a later wipe
cannot restore the all-blocked escape that offered a seat which then GIVEUP'd.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"
DOCS = ROOT / "jeeves" / "docs" / "jeeves-commands.md"
PRODUCT = ROOT / "jeeves" / "tests" / "test_fr2939_repo_uat_self_uat_prefilter.py"


def test_mrb2940_gitclaim_pins_self_uat_helpers():
    text = GITCLAIM.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "FR #2939" in text
    assert "maybe_escalate_repo_uat_all_self_uat" in text
    assert "repo_uat_no_eligible_live_seat" in text
    assert "ledger_why_is_self_uat" in text
    assert "self_uat_escalated" in text
    assert '"self_uat"' in text or "self_uat =" in text
    # Escape removed: ledger_blocks must not lift all-blocked self-UAT.
    assert "repo UAT self-UAT (FR or MRB cycle touch) is never escaped" in text


def test_mrb2940_docs_uat_paragraph():
    text = DOCS.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "FR #2939" in text
    assert "self_uat" in text or "self-UAT" in text
    assert "needs_human" in text or "needs-human" in text
    assert "fewer cycle FR touches" not in text


def test_mrb2940_product_test_module_present():
    text = PRODUCT.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "test_escalate_stamps_needs_human_and_announces" in text
    assert "test_summarize_empty_offer_reports_self_uat" in text
    assert "test_no_escape_when_all_self_uat" in text
