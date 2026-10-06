"""MRB #2607 hostile: DONE FR pull URL + MRB exact-seat self-exclusion (FR #2604).

Product PR #2607 landed shop_listen URL stamp, review_blocked MRB exact-seat,
and resync skipped_draft. These gates lock source markers so a future chair tip
cannot drop the offerable URL or re-strand same-machine siblings.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"
SHOP = ROOT / "common" / "scripts" / "shop_listen.py"
SKILL_MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
HARVEST = ROOT / "common" / "docs" / "skill-harvest-log.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb2607_done_fr_stamps_pull_url_in_shop_listen():
    t = _read(SHOP)
    assert "FR #2604" in t
    assert 'extra["url"]' in t or "extra['url']" in t
    assert "/pull/" in t
    # Must build github pull URL when DONE carries repo+id without full URL.
    assert "github.com" in t and "pull" in t


def test_mrb2607_review_blocked_mrb_exact_seat_only():
    t = _read(GITCLAIM)
    body = t[t.find("def review_blocked_for_author") :]
    body = body[: body.find("\ndef ", 1)]
    assert "FR #2604" in body
    assert 'task == "MRB"' in body
    assert "continue" in body
    # UAT sibling block must remain in the same function.
    assert "UAT" in body and "sibling" in body.lower()


def test_mrb2607_resync_skips_draft_returns_skipped_draft():
    t = _read(GITCLAIM)
    assert "skipped_draft" in t
    assert 'pr.get("draft") is True' in t or "pr.get('draft') is True" in t
    assert "resync skip draft PR" in t


def test_mrb2607_skill_and_harvest_mark_exact_seat():
    skill = _read(SKILL_MRB)
    assert "FR #2604" in skill or "exact-seat" in skill or "exact seat" in skill
    log = _read(HARVEST)
    assert "2604" in log or "2607" in log
    assert "exact" in log.lower() and "MRB" in log
