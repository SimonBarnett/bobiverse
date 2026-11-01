"""FR #5720: conflict-FIX must skip closed harvest FAIL-supersede tips (FR #4800 gap)."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import mrb_merge_on_green

REPO = "SimonBarnett/bobiverse"
PR = "5716"
SHA = "7593036aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
URL = f"https://github.com/{REPO}/pull/{PR}"
NICK = "flamingo-64124"


def test_fr5720_enqueue_conflict_fix_skips_closed_harvest(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )

    def fake_state(repo, num, **_k):
        return {
            "sha": SHA,
            "closed": True,
            "merged": False,
            "title": "lesson(harvest): EXTENSION CredMan IPC$",
            "labels": ["harvest-lesson", "via-intake"],
            "comments": [
                {
                    "body": (
                        "## MRB board\n"
                        "**Verdict:** FAIL-supersede (closed unmerged)\n"
                        "Keeper: #5715"
                    )
                }
            ],
        }

    monkeypatch.setattr(mrb_merge_on_green, "fetch_pr_state", fake_state)
    out = mrb_merge_on_green.enqueue_conflict_fix(
        home, repo=REPO, pr=PR, pass_sha=SHA, url=URL, reason="conflicting"
    )
    assert out == "skipped"
    assert gitclaim.load_unaccepted(home) == []


def test_fr5720_offer_dirty_skips_closed_harvest(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    monkeypatch.setattr(
        mrb_merge_on_green,
        "fetch_pr_state",
        lambda *_a, **_k: {
            "sha": SHA,
            "closed": True,
            "merged": False,
            "title": "lesson(harvest): x",
            "labels": ["harvest-lesson"],
        },
    )
    out = mrb_merge_on_green.offer_dirty_conflict_fix(
        home, repo=REPO, pr=PR, sha=SHA, url=URL, reason="conflicting"
    )
    assert out == "skipped"
    assert not any(
        str(r.get("task") or "").upper() == "FIX"
        for r in gitclaim.load_unaccepted(home)
    )


def test_fr5720_done_pass_conflicting_closed_harvest_skips_fix(tmp_path: Path):
    """FR #5581 DONE CONFLICTING path must not FIX a closed harvest disposition tip."""
    home = tmp_path / "home"
    home.mkdir()

    def fetch_pr(repo, pr, **_k):
        return {
            "sha": SHA,
            "labels": ["harvest-lesson", "via-intake"],
            "title": "lesson(harvest): EXTENSION CredMan IPC$",
            "body": "",
            "html_url": URL,
            "mergeable": "CONFLICTING",
            "merge_state_status": "DIRTY",
            "merged": False,
            "closed": True,
            "checks": "success",
            "comments": [{"body": "**Verdict:** FAIL-supersede"}],
        }

    row = mrb_merge_on_green.enqueue_from_done(
        home,
        repo=REPO,
        pr_url=URL,
        result="PASS",
        nick=NICK,
        fetch_pr=fetch_pr,
        fetch_comments=lambda *_a, **_k: [],
    )
    assert row is not None
    assert row.get("conflict_fix") == "skipped"
    assert row.get("status") == "skipped_harvest_disposition"
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert fixes == []
    pending = mrb_merge_on_green.load_ledger(home).get("pending") or []
    assert pending == [] or not any(
        isinstance(p, dict) and str(p.get("pr") or "") == PR for p in pending
    )


def test_fr5720_open_product_conflicting_still_offers_fix(tmp_path: Path, monkeypatch):
    """Open product CONFLICTING tips still get conflict-FIX (FR #5581 unchanged)."""
    home = tmp_path / "home"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    monkeypatch.setattr(
        mrb_merge_on_green,
        "fetch_pr_state",
        lambda *_a, **_k: {
            "sha": SHA,
            "closed": False,
            "merged": False,
            "title": "FR #9999: product tip",
            "labels": ["via-intake"],
        },
    )
    out = mrb_merge_on_green.enqueue_conflict_fix(
        home, repo=REPO, pr="9999", pass_sha=SHA, url=URL, reason="conflicting"
    )
    assert out == "added"
    rows = gitclaim.load_unaccepted(home)
    assert any(str(r.get("task") or "").upper() == "FIX" for r in rows)
