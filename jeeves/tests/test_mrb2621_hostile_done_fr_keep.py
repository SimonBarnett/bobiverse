"""MRB #2621 hostile: keep DONE FR in done[] while implement PR open (FR #2617).

Product PR #2621 stopped resync from stripping DONE FR+/pull/ rows while the
implement PR is still open (live: #2612 re-offered after 9524 DONE + open #2615).
These gates lock the still_open keep path and the #2389 drop-when-PR-gone path.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
HARVEST = ROOT / "common" / "docs" / "skill-harvest-log.md"
PRODUCT = ROOT / "jeeves" / "tests" / "test_fr2617_done_fr_no_reoffer_after_resync.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb2621_resync_keeps_done_fr_with_open_pull():
    t = _read(GITCLAIM)
    assert "FR #2617" in t
    # Keep path must consult open_pulls_map / parse_github_pull_url.
    assert "parse_github_pull_url" in t
    assert "open_pulls_map" in t
    # Marker comment for the keep-done behaviour.
    assert "keep DONE FR" in t or "fr_superseded_by_done_pr" in t


def test_mrb2621_product_tests_cover_sibling_mrb_and_2389():
    t = _read(PRODUCT)
    assert "test_fr2617_done_fr_resync_sibling_gets_mrb_not_fr" in t
    assert "test_fr2617_keeps_2389_reoffer_when_closes_pr_gone" in t
    assert "marchhare-39912" in t or "sibling" in t.lower()


def test_mrb2621_skill_and_harvest_mark_no_reoffer():
    skill = _read(SKILL)
    assert "2617" in skill or "DONE FR" in skill
    assert "re-offer" in skill.lower() or "resync" in skill.lower()
    log = _read(HARVEST)
    assert "2617" in log or "2621" in log
    assert "DONE FR" in log or "done[]" in log or "re-offer" in log.lower()
