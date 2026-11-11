"""MRB #6582 hostile: FR #6566 FR595 stale-pull pin opts into live budget."""
from __future__ import annotations

from pathlib import Path

import gitclaim

ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / "jeeves" / "tests" / "test_fr595_mrb_fr_routing.py"
GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"


def test_mrb6582_production_bored_budget_still_zero():
    """Product default must stay zero-call (FR #3212); only the pin opts in."""
    assert gitclaim.BORED_GITHUB_CALL_BUDGET == 0
    src = GITCLAIM.read_text(encoding="utf-8")
    assert "BORED_GITHUB_CALL_BUDGET = 0" in src
    assert not GITCLAIM.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6582_stale_pull_pin_opts_into_budget():
    pin = PIN.read_text(encoding="utf-8")
    i = pin.find("def test_offer_skips_stale_pull_when_pr_exists_false")
    assert i >= 0
    window = pin[i : i + 2200]
    assert 'setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 2)' in window
    assert "FR #3212" in window or "zero-call" in window
    assert "offer-precompute.json" in window
    assert 'assert "227" in seen' in window
    assert "offered_to" in window and "marchhare-1" in window
    assert "load_unaccepted" in window
    assert not PIN.read_bytes().startswith(b"\xef\xbb\xbf")
