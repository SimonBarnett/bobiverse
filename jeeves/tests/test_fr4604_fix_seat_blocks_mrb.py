"""FR #4604: FIX (CI) seat must not be offered the re-queued MRB for the same PR."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines
import shop_listen


REPO = "SimonBarnett/a-search"
PR = "#1796"
FIX_SEAT = "flamingo-70260"
OTHER_SEAT = "flamingo-63220"
IMPL_SEAT = "marchhare-12524"
URL = f"https://github.com/{REPO}/pull/1796"


def _digest_two_flamingo(home):
    """Populate worker_list so live_seat_nicks (FR #4211) sees remote seats."""
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": FIX_SEAT, "state": "idle"},
        {"nick": OTHER_SEAT, "state": "idle"},
    ]
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": IMPL_SEAT, "state": "idle"},
    ]
    bobreport.save_digest(home, digest)


def _mrb_row(**extra):
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": PR,
        "seq": 2,
        "ts": "t",
        "line": "x",
        "url": URL,
        "event": "pull_request",
        "action": "synchronize",
    }
    row.update(extra)
    return row


def test_fix_ci_seats_from_doc_done_and_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare"})
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "nick": FIX_SEAT,
                "url": URL,
            }
        ],
        "done": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#2179",
                "done_by": OTHER_SEAT,
                "url": f"https://github.com/{REPO}/pull/2179",
                "result": "PASS",
            }
        ],
    }
    assert gitclaim.fix_ci_seats_from_doc(doc, REPO, PR) == [FIX_SEAT]
    assert gitclaim.fix_ci_seats_from_doc(doc, REPO, "#2179") == [OTHER_SEAT]


def test_enrich_mrb_merges_fix_seat_into_author_seats(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare"})
    doc = {
        "v": 1,
        "unaccepted": [_mrb_row()],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "done_by": FIX_SEAT,
                "url": URL,
                "result": "PASS",
            }
        ],
    }
    enriched = gitclaim.enrich_mrb_author_fields(doc, doc["unaccepted"][0])
    seats = gitclaim.row_author_seats(enriched)
    assert FIX_SEAT in seats


def test_offer_skips_fix_done_seat_unstamped_mrb(tmp_path, monkeypatch):
    """Done FIX by flamingo-70260; synchronize MRB with no stamps → not offered to that seat."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo", "marchhare"})
    _digest_two_flamingo(home)
    doc = {
        "v": 1,
        "unaccepted": [_mrb_row()],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "done_by": FIX_SEAT,
                "nick": FIX_SEAT,
                "url": URL,
                "result": "PASS",
                "done_ts": "t",
            }
        ],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)

    st, job = gitclaim.offer_focus_top(home, FIX_SEAT, "#flamingo")
    assert st == "empty" or job is None or str((job or {}).get("id") or "") != PR

    st2, job2 = gitclaim.offer_focus_top(home, OTHER_SEAT, "#flamingo")
    assert st2 == "ok"
    assert job2 is not None
    assert job2.get("id") == PR
    assert job2.get("offered_to") == OTHER_SEAT


def test_offer_skips_fix_still_accepted(tmp_path, monkeypatch):
    """Synchronize arrives before FIX DONE — accepted FIX seat still blocked at review gate."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo", "marchhare"})
    _digest_two_flamingo(home)
    doc = {
        "v": 1,
        "unaccepted": [_mrb_row()],
        "accepted": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "nick": FIX_SEAT,
                "url": URL,
                "accepted_ts": "t",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    live = {"flamingo-70260", "flamingo-63220", "marchhare-12524"}
    enriched = gitclaim.enrich_mrb_author_fields(doc, doc["unaccepted"][0])
    assert gitclaim.review_blocked_for_author(enriched, FIX_SEAT, live) is True
    assert gitclaim.review_blocked_for_author(enriched, OTHER_SEAT, live) is False

    # Other idle seat still gets the offer while FIX seat holds the accepted FIX.
    st2, job2 = gitclaim.offer_focus_top(home, OTHER_SEAT, "#flamingo")
    assert st2 == "ok"
    assert job2.get("id") == PR


def test_offer_blocks_implementer_and_fix_seat(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo", "marchhare"})
    _digest_two_flamingo(home)
    doc = {
        "v": 1,
        "unaccepted": [_mrb_row(author_seat=IMPL_SEAT, implementer_seat=IMPL_SEAT)],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "done_by": OTHER_SEAT,
                "url": URL,
                "result": "PASS",
            }
        ],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)

    st_a, _ = gitclaim.offer_focus_top(home, IMPL_SEAT, "#marchhare")
    assert st_a == "empty" or _ is None or str((_ or {}).get("id") or "") != PR

    st_b, _ = gitclaim.offer_focus_top(home, OTHER_SEAT, "#flamingo")
    assert st_b == "empty" or _ is None or str((_ or {}).get("id") or "") != PR

    st_c, job_c = gitclaim.offer_focus_top(home, FIX_SEAT, "#flamingo")
    assert st_c == "ok"
    assert job_c.get("id") == PR


def test_nick_inherits_dead_fix_seat_on_recycle(tmp_path, monkeypatch):
    """FR #4606: recycled sole seat does NOT inherit dead FIX author for MRB.

    nick_inherits_dead_seat remains True (UAT / giveup paths), but review_blocked_for_author
    for MRB is exact-seat only — fresh flamingo-99999 with no PR touch may review.
    Live FIX nick still blocked (exact stamp, FR #4604).
    """
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo", "marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    # Only the recycled seat is live; FIX was done by dead flamingo-70260.
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": "flamingo-99999", "state": "idle"},
    ]
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": IMPL_SEAT, "state": "idle"},
    ]
    bobreport.save_digest(home, digest)

    doc = {
        "v": 1,
        "unaccepted": [_mrb_row()],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "done_by": FIX_SEAT,
                "url": URL,
                "result": "PASS",
            }
        ],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)

    recycled = "flamingo-99999"
    live = {"flamingo-99999", "marchhare-12524"}
    assert gitclaim.nick_inherits_dead_seat(recycled, FIX_SEAT, live) is True
    enriched = gitclaim.enrich_mrb_author_fields(doc, doc["unaccepted"][0])
    # MRB: exact seat only — recycled successor is NOT blocked (FR #4606).
    assert gitclaim.review_blocked_for_author(enriched, recycled, live) is False
    # Exact FIX nick still blocked when live.
    assert gitclaim.review_blocked_for_author(enriched, FIX_SEAT, live | {FIX_SEAT}) is True

    st, job = gitclaim.offer_focus_top(home, recycled, "#flamingo")
    assert st == "ok"
    assert job is not None and str(job.get("id") or "") == PR
    assert job.get("offered_to") == recycled
    # offer_focus_top stamps offered_to — other seats see sticky offer, not a second copy.


def test_done_fix_stamps_existing_mrb_author_seats(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo", "marchhare"})
    doc = {
        "v": 1,
        "unaccepted": [_mrb_row()],
        "accepted": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "nick": FIX_SEAT,
                "url": URL,
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    st, job = shop_listen.complete_job_by_ref(
        home, nick=FIX_SEAT, repo=REPO, task="FIX", ident=PR, result="PASS", url=URL
    )
    assert st == "ok"
    assert job is not None
    rows = gitclaim.load_unaccepted(home)
    mrb = next(r for r in rows if r.get("task") == "MRB" and r.get("id") == PR)
    assert FIX_SEAT in gitclaim.row_author_seats(mrb)
