"""FR #5088: recycled seat nick must NOT inherit dead giveup on auto-offer.

Give-up / NACK exclusions are exact-seat only (like !assign). needs_human stays
global (FR #4336). UAT dead-author inherit is unchanged (review_blocked_for_author).
"""
from __future__ import annotations

import gitclaim
import bobreport
import registered_machines


def test_fr5088_nick_in_giveup_seats_exact_only_no_dead_inherit(tmp_path, monkeypatch):
    """Dead predecessor in giveup_seats must not block the recycled sole live nick."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-8328", "state": "idle"}
    ]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": "flamingo-9", "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    live = gitclaim.live_seat_nicks(tmp_path)
    row = {"giveup_seats": "marchhare-6700"}
    # Exact dead nick is not live; recycled successor must NOT inherit (FR #5088).
    assert gitclaim.nick_inherits_dead_seat("marchhare-8328", "marchhare-6700", live) is True
    assert gitclaim.nick_in_giveup_seats(row, "marchhare-8328", live=live) is False
    assert gitclaim.row_gave_up_by(row, "marchhare-8328", live=live) is False
    # Exact listed nick still blocked when present as the asking nick.
    assert gitclaim.nick_in_giveup_seats(row, "marchhare-6700", live=live) is True


def test_fr5088_offer_focus_top_allows_recycled_after_dead_giveup(tmp_path, monkeypatch):
    """!bored must offer a non-needs_human row the dead predecessor NACKed."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-8328", "state": "idle"}
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
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#5076",
                "seq": 1,
                "needs_human": False,
                "giveup_seats": "marchhare-6700",
                "giveup_count": 1,
                "line": "MRB SimonBarnett/bobiverse#5076",
                "url": "https://github.com/SimonBarnett/bobiverse/pull/5076",
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
        tmp_path, "marchhare-8328", "#marchhare", pr_exists=lambda *a, **k: True
    )
    assert st == "ok", (st, job)
    assert job.get("offered_to") == "marchhare-8328"


def test_fr5088_needs_human_still_blocks_recycled(tmp_path, monkeypatch):
    """FR #4336 global needs_human gate unchanged for recycled nick."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-8328", "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    row = {
        "needs_human": True,
        "giveup_seats": "marchhare-6700",
        "giveup_count": 3,
    }
    assert gitclaim.row_needs_human(row, "marchhare-8328") is True
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#5076",
                "seq": 1,
                "needs_human": True,
                "giveup_seats": "marchhare-6700",
                "line": "MRB SimonBarnett/bobiverse#5076",
                "url": "https://github.com/SimonBarnett/bobiverse/pull/5076",
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
        tmp_path, "marchhare-8328", "#marchhare", pr_exists=lambda *a, **k: True
    )
    assert st == "empty", (st, job)


def test_fr5088_cooldown_exact_only(tmp_path, monkeypatch):
    """Per-seat cooldown_until does not transfer to recycled successor."""
    import time

    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-8328", "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    live = gitclaim.live_seat_nicks(tmp_path)
    future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    row = {"giveup_seats": "marchhare-6700", "cooldown_until": future}
    assert gitclaim.row_on_cooldown(row, time.time(), "marchhare-8328", live=live) is False
    assert gitclaim.row_on_cooldown(row, time.time(), "marchhare-6700", live=live) is True
