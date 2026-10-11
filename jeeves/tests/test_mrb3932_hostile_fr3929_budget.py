"""MRB #3932 hostile pins for FR #3929 fr740 budget-aware offer tests."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")


def test_mrb3932_fr740_file_raises_budget_for_pr_exists_skip():
    text = (ROOT / "jeeves" / "tests" / "test_fr740_skip_merged_mrb.py").read_text(encoding="utf-8")
    assert "FR #3929" in text
    assert 'monkeypatch.setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 2)' in text
    assert "test_offer_focus_top_budget0_fail_opens_when_pr_exists_exhausted" in text
    assert 'monkeypatch.setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 0)' in text
    assert "assert calls[\"n\"] == 0" in text


def test_mrb3932_production_bored_budget_still_zero():
    # Production policy unchanged by FR #3929 (tests only raise budget).
    assert int(gitclaim.BORED_GITHUB_CALL_BUDGET) == 0
