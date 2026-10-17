"""FR #4336: needs_human blocks all auto-offers; recycle nick inherits giveup/author; LOST_ACK skips needs_human."""
from __future__ import annotations

import gitclaim
import bobreport
import registered_machines


def test_fr4336_needs_human_blocks_every_seat_for_auto_offer():
    """Once needs_human is stamped, bored/done-offer skip every seat (FR #4336 Expected #1)."""
    row = {
        "needs_human": True,
        "giveup_seats": "marchhare-12524,marchhare-9068",
        "giveup_count": 3,
    }
    assert gitclaim.row_needs_human(row, "marchhare-8824") is True
    assert gitclaim.row_needs_human(row, "marchhare-12524") is True
    assert gitclaim.row_needs_human(row, "flamingo-9") is True
    assert gitclaim.row_needs_human(row, "") is True
    assert gitclaim.row_needs_human({"needs_human": False}, "marchhare-8824") is False


def test_fr4336_nick_in_giveup_seats_inherits_dead_same_machine(tmp_path, monkeypatch):
    """Recycled seat: old nick in giveup_seats, new nick on same machine inherits (Expected #2)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-8824", "state": "idle"}
    ]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": "flamingo-9", "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert "marchhare-8824" in live
    row = {"giveup_seats": "marchhare-12524,marchhare-9068"}
    assert gitclaim.nick_in_giveup_seats(row, "marchhare-8824", live=live) is True
    assert gitclaim.nick_in_giveup_seats(row, "flamingo-9", live=live) is False
    # When old nick still live, sibling on same machine does not inherit (FR #2604).
    row_live_pred = {"giveup_seats": "marchhare-12524"}
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-12524", "state": "idle"},
        {"nick": "marchhare-8824", "state": "idle"},
    ]
    bobreport.save_digest(tmp_path, digest)
    live2 = gitclaim.live_seat_nicks(tmp_path)
    assert "marchhare-12524" in live2 and "marchhare-8824" in live2
    assert gitclaim.nick_in_giveup_seats(row_live_pred, "marchhare-8824", live=live2) is False
    assert gitclaim.nick_in_giveup_seats(row_live_pred, "marchhare-12524", live=live2) is True


def test_fr4336_review_blocked_inherits_dead_author_seat(tmp_path, monkeypatch):
    """UAT inherits dead author (FR #4336); MRB does not (FR #4606 / #2604 exact seat)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-8824", "state": "idle"}
    ]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": "flamingo-9", "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    live = gitclaim.live_seat_nicks(tmp_path)
    mrb = {
        "task": "MRB",
        "author_seat": "marchhare-12524",
        "implementer_seat": "marchhare-12524",
        "url": "https://github.com/SimonBarnett/a-search/pull/2195",
    }
    # Fresh recycled seat may MRB-review (exact seat only).
    assert gitclaim.review_blocked_for_author(mrb, "marchhare-8824", live) is False
    assert gitclaim.review_blocked_for_author(mrb, "flamingo-9", live) is False
    uat = {
        "task": "UAT",
        "author_seat": "marchhare-12524",
        "implementer_seat": "marchhare-12524",
        "repo": "SimonBarnett/a-search",
        "id": "SimonBarnett/a-search",
    }
    assert gitclaim.review_blocked_for_author(uat, "marchhare-8824", live) is True
    assert gitclaim.review_blocked_for_author(uat, "flamingo-9", live) is False


def test_fr4336_lost_ack_skips_needs_human_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "8824": {
            "state": "doing",
            "working_on": "MRB SimonBarnett/a-search#2250",
        }
    }
    # worker_list shape used by reconcile
    digest["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-8824",
            "state": "doing",
            "work": "MRB SimonBarnett/a-search#2250",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/a-search",
                "task": "MRB",
                "id": "#2250",
                "seq": 1,
                "needs_human": True,
                "giveup_seats": "marchhare-12524",
                "line": "MRB",
                "url": "https://github.com/SimonBarnett/a-search/pull/2250",
                "ts": "t",
            }
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    n = gitclaim.reconcile_lost_ack_from_digest(tmp_path)
    assert n == 0
    q = gitclaim._load_queue_unlocked(tmp_path)
    assert len(q["unaccepted"]) == 1
    assert len(q["accepted"]) == 0
    assert q["unaccepted"][0].get("needs_human") is True


def test_fr4336_assign_row_allows_needs_human(tmp_path, monkeypatch):
    """Explicit !assign may hand out needs_human (Expected #1)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {"8824": {"state": "idle"}}
    bobreport.save_digest(tmp_path, digest)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/a-search",
                "task": "MRB",
                "id": "#2250",
                "seq": 1,
                "needs_human": True,
                "giveup_seats": "marchhare-12524",
                "line": "MRB SimonBarnett/a-search#2250",
                "url": "https://github.com/SimonBarnett/a-search/pull/2250",
                "ts": "t",
                "event": "pull_request",
                "action": "opened",
            }
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    st, job = gitclaim.assign_row(
        tmp_path,
        "marchhare-8824",
        "SimonBarnett/a-search",
        "MRB",
        "#2250",
    )
    assert st == "ok", job
    assert job.get("offered_to") == "marchhare-8824"



def test_fr4336_offer_focus_top_inherits_dead_giveup(tmp_path, monkeypatch):
    """!bored / done-offer must not hand a giveup_seats row to a recycled successor."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-8824", "state": "idle"}
    ]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": "flamingo-9", "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/a-search",
                "task": "MRB",
                "id": "#2250",
                "seq": 1,
                "needs_human": False,
                "giveup_seats": "marchhare-12524",
                "line": "MRB SimonBarnett/a-search#2250",
                "url": "https://github.com/SimonBarnett/a-search/pull/2250",
                "ts": "t",
                "event": "pull_request",
                "action": "opened",
            }
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    st, job = gitclaim.offer_focus_top(
        tmp_path, "marchhare-8824", "#marchhare", pr_exists=lambda *a, **k: True
    )
    assert st == "empty", (st, job)
    st2, job2 = gitclaim.offer_focus_top(
        tmp_path, "flamingo-9", "#flamingo", pr_exists=lambda *a, **k: True
    )
    assert st2 == "ok", (st2, job2)
    assert job2.get("offered_to") == "flamingo-9"


def test_fr4336_needs_human_blocks_offer_focus_top(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-8824", "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/a-search",
                "task": "MRB",
                "id": "#2250",
                "seq": 1,
                "needs_human": True,
                "giveup_seats": "marchhare-12524",
                "line": "MRB SimonBarnett/a-search#2250",
                "url": "https://github.com/SimonBarnett/a-search/pull/2250",
                "ts": "t",
                "event": "pull_request",
                "action": "opened",
            }
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    st, job = gitclaim.offer_focus_top(
        tmp_path, "marchhare-8824", "#marchhare", pr_exists=lambda *a, **k: True
    )
    assert st == "empty", (st, job)
