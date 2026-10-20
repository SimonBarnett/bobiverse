"""docs/mrb-4930 hostile pins for FR #4929 / PR #4930.

Prior MRB PASS in done[] + mrb_done must not strand a FIX head without re-MRB.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import mrb_merge_on_green


REPO = "SimonBarnett/a-search"
PR = "#4717"
URL = f"https://github.com/{REPO}/pull/4717"


def test_pop_done_mrb_rows_removes_only_matching_mrb():
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [],
        "done": [
            {"repo": REPO, "task": "MRB", "id": PR, "result": "PASS"},
            {"repo": REPO, "task": "FR", "id": "#99", "result": "PASS"},
            {"repo": "Other/repo", "task": "MRB", "id": PR, "result": "FAIL"},
        ],
    }
    removed = gitclaim.pop_done_mrb_rows(doc, REPO, PR)
    assert len(removed) == 1
    assert removed[0]["result"] == "PASS"
    assert len(doc["done"]) == 2
    assert all(
        not (
            str(r.get("task") or "").upper() == "MRB"
            and str(r.get("id") or "") == PR
            and gitclaim.canonical_queue_repo(str(r.get("repo") or ""))
            == gitclaim.canonical_queue_repo(REPO)
        )
        for r in doc["done"]
    )


def test_ensure_mrb_requeued_after_head_move_clears_ledger_and_queues(tmp_path):
    home = tmp_path
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [],
        "done": [{"repo": REPO, "task": "MRB", "id": PR, "result": "PASS"}],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    gitclaim.stamp_mrb_done(home, REPO, PR)
    assert gitclaim.mrb_ledger_done_hold(home, REPO, PR)

    loaded = gitclaim._load_queue_unlocked(home)
    st = gitclaim.ensure_mrb_requeued_after_head_move(
        loaded,
        home,
        repo=REPO,
        pr=PR,
        url=URL,
        reason="hostile-pin",
    )
    assert st in ("added", "duplicate", "updated")
    gitclaim._write_queue(gitclaim.queue_path(home), loaded)

    q = gitclaim.load_queue(home)
    assert not gitclaim.mrb_ledger_done_hold(home, REPO, PR)
    assert not any(
        str(r.get("task") or "").upper() == "MRB" and str(r.get("id") or "") == PR
        for r in (q.get("done") or [])
        if isinstance(r, dict)
    )
    mrb = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
        and str(r.get("task") or "").upper() == "MRB"
        and str(r.get("id") or "") == PR
    ]
    assert len(mrb) == 1
    assert "requeue after" in str(mrb[0].get("title") or "")


def test_requeue_mrb_helper_uses_ensure_and_pops_done(tmp_path, monkeypatch):
    home = tmp_path
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [],
        "done": [{"repo": REPO, "task": "MRB", "id": PR, "result": "PASS"}],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    gitclaim.stamp_mrb_done(home, REPO, PR)

    mrb_merge_on_green.requeue_mrb(home, repo=REPO, pr=PR, url=URL, reason="ci-red")

    q = gitclaim.load_queue(home)
    assert not gitclaim.mrb_ledger_done_hold(home, REPO, PR)
    assert any(
        str(r.get("task") or "").upper() == "MRB" and str(r.get("id") or "") == PR
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
    )


def test_source_pins_fr4929_helpers_contiguous():
    root = Path(__file__).resolve().parents[2]
    gc = (root / "common" / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    shop = (root / "common" / "scripts" / "shop_listen.py").read_text(encoding="utf-8")
    mog = (root / "common" / "scripts" / "mrb_merge_on_green.py").read_text(
        encoding="utf-8"
    )
    assert "def pop_done_mrb_rows(" in gc
    assert "def ensure_mrb_requeued_after_head_move(" in gc
    assert "reason=\"done-fix\"" in shop.replace("'", '"') or 'reason="done-fix"' in shop
    assert "ensure_mrb_requeued_after_head_move" in mog
    assert "FR #4929" in gc and "FR #4929" in shop
