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
    """Done FIX by flamingo-70260; synchronize MRB â†’ flamingo machine blocked; marchhare offered."""
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

    # FR #9574: same-machine sibling of FIX seat is eligible (exact FIX nick only).
    st2, job2 = gitclaim.offer_focus_top(home, OTHER_SEAT, "#flamingo")
    assert st2 == "ok"
    assert job2 is not None
    assert job2.get("id") == PR
    assert job2.get("offered_to") == OTHER_SEAT


def test_offer_skips_fix_still_accepted(tmp_path, monkeypatch):
    """Synchronize arrives before FIX DONE â€” FIX machine blocked; other machine offered."""
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
    # FR #9574: sibling of FIX seat eligible (exact FIX nick only).
    assert gitclaim.review_blocked_for_author(enriched, OTHER_SEAT, live) is False
    assert gitclaim.review_blocked_for_author(enriched, IMPL_SEAT, live) is False

    st2, job2 = gitclaim.offer_focus_top(home, OTHER_SEAT, "#flamingo")
    assert st2 == "ok"
    assert job2 is not None and job2.get("id") == PR


def test_offer_blocks_implementer_and_fix_seat(tmp_path, monkeypatch):
    """Exact IMPL + FIX done_by blocked; FR #9480 allows flamingo sibling."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    third = "redqueen-42"
    registered_machines.save_registered(home, {"flamingo", "marchhare", "redqueen"})
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
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {"nick": third, "state": "idle"},
    ]
    bobreport.save_digest(home, digest)
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

    # FR #9480: author_seats span marchhare + flamingo (IMPL + FIX done_by) â†’
    # exact-seat only; flamingo sibling FIX_SEAT is eligible (not machine-blocked).
    st_c, job_c = gitclaim.offer_focus_top(home, FIX_SEAT, "#flamingo")
    assert st_c == "ok"
    assert job_c.get("id") == PR

    # Third machine remains eligible under review_blocked (offer already stamped).
    live = gitclaim.live_seat_nicks(home)
    doc2 = gitclaim.load_queue(home)
    # After FIX_SEAT accepted the offer, row may be in accepted; check eligibility directly.
    row = None
    for bucket in ("unaccepted", "accepted"):
        for r in doc2.get(bucket) or []:
            if str(r.get("id") or "") == PR:
                row = r
                break
        if row is not None:
            break
    assert row is not None
    enriched = gitclaim.enrich_mrb_author_fields(doc2, row)
    assert gitclaim.review_blocked_for_author(enriched, third, live) is False


def test_nick_inherits_dead_fix_seat_on_recycle(tmp_path, monkeypatch):
    """FR #9574 / #4606: recycled same-machine as dead FIX may MRB (exact stamp only).

    nick_inherits_dead_seat remains True (UAT paths). Live FIX nick still blocked
    (exact stamp, FR #4604). Recycled flamingo nick is eligible for MRB.
    """
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    third = "redqueen-42"
    registered_machines.save_registered(home, {"flamingo", "marchhare", "redqueen"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": "flamingo-99999", "state": "idle"},
    ]
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": IMPL_SEAT, "state": "idle"},
    ]
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {"nick": third, "state": "idle"},
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
    live = {"flamingo-99999", "marchhare-12524", third}
    assert gitclaim.nick_inherits_dead_seat(recycled, FIX_SEAT, live) is True
    enriched = gitclaim.enrich_mrb_author_fields(doc, doc["unaccepted"][0])
    assert gitclaim.review_blocked_for_author(enriched, recycled, live) is False
    assert gitclaim.review_blocked_for_author(enriched, FIX_SEAT, live | {FIX_SEAT}) is True
    assert gitclaim.review_blocked_for_author(enriched, third, live) is False

    st, job = gitclaim.offer_focus_top(home, recycled, "#flamingo")
    assert st == "ok"
    assert job is not None and str(job.get("id") or "") == PR
    assert job.get("offered_to") == recycled


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
