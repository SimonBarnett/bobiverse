"""FR #2623: DONE FR that only cites another seat's open PR must not stamp that citer as implementer.

Fallout of #2617: seat A opens PR P and DONE FR; FR wrongly re-offered to seat B; B DONE FR
pointing at the same P. Before this fix, B overwrote implementer_seat on the MRB row and
stranded the hostile review on a two-seat machine (A blocked as author, B blocked as
\"implementer\").
"""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines
import shop_listen


REPO = "SimonBarnett/bobiverse"
PULL = "https://github.com/SimonBarnett/bobiverse/pull/2615"
SEAT_A = "marchhare-9524"
SEAT_B = "marchhare-39912"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "9524": {"state": "idle", "nick": SEAT_A},
        "39912": {"state": "idle", "nick": SEAT_B},
    }
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _accept_fr(home, nick: str, issue: str = "#2612") -> None:
    doc = gitclaim._load_queue_unlocked(home)
    # Drop any prior accepted FR for this issue so the new seat owns it.
    doc["accepted"] = [
        r
        for r in (doc.get("accepted") or [])
        if not (
            str(r.get("repo")) == REPO
            and str(r.get("task") or "").upper() == "FR"
            and str(r.get("id")) == issue
        )
    ]
    doc.setdefault("unaccepted", [])
    doc["unaccepted"] = [
        r
        for r in doc["unaccepted"]
        if not (
            str(r.get("repo")) == REPO
            and str(r.get("task") or "").upper() == "FR"
            and str(r.get("id")) == issue
        )
    ]
    doc["accepted"].append(
        {
            "repo": REPO,
            "task": "FR",
            "id": issue,
            "seq": 1,
            "nick": nick,
            "ts": "t",
            "line": "x",
            "channel": "#marchhare",
            "accepted_ts": "t",
        }
    )
    gitclaim._write_queue(gitclaim.queue_path(home), doc)


def test_citing_done_fr_keeps_prior_implementer_and_offers_mrb_to_citer(tmp_path, monkeypatch):
    """A DONE FR P → wrong re-offer → B DONE same P → B gets MRB P; A stays implementer."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )

    # Seat A implements and DONE FR with PR P.
    _accept_fr(home, SEAT_A)
    st, _ = shop_listen.complete_job_by_ref(
        home,
        nick=SEAT_A,
        repo=REPO,
        task="FR",
        ident="#2612",
        result="",
        url=PULL,
    )
    assert st == "ok"
    mrbs = [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert mrbs[0]["id"] == "#2615"
    assert mrbs[0].get("implementer_seat") == SEAT_A
    assert mrbs[0].get("author_seat") == SEAT_A

    # Simulate #2617-class re-offer: FR returns to the queue and seat B ACKs it.
    _accept_fr(home, SEAT_B)
    st, _ = shop_listen.complete_job_by_ref(
        home,
        nick=SEAT_B,
        repo=REPO,
        task="FR",
        ident="#2612",
        result="",
        url=PULL,
    )
    assert st == "ok"

    mrbs = [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert mrbs[0].get("implementer_seat") == SEAT_A, mrbs[0]
    assert mrbs[0].get("author_seat") == SEAT_A, mrbs[0]

    # B must be offerable for the hostile MRB; A remains blocked as implementer.
    st_b, job_b = gitclaim.offer_focus_top(home, SEAT_B, "#marchhare")
    assert st_b == "ok"
    assert (job_b.get("task"), job_b.get("id")) == ("MRB", "#2615")

    # Reset offer pin so we can probe A independently.
    doc = gitclaim._load_queue_unlocked(home)
    for r in doc.get("unaccepted") or []:
        if str(r.get("task")) == "MRB" and str(r.get("id")) == "#2615":
            r.pop("offered_to", None)
            r.pop("offered_ts", None)
    gitclaim._write_queue(gitclaim.queue_path(home), doc)

    st_a, job_a = gitclaim.offer_focus_top(home, SEAT_A, "#marchhare")
    # A is the implementer: either refused/empty or some other row — never MRB #2615.
    if st_a == "ok":
        assert not (job_a.get("task") == "MRB" and job_a.get("id") == "#2615")


def test_resolve_done_fr_implementer_prefers_earlier_done_over_citer(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FR",
                "id": "#2612",
                "nick": SEAT_A,
                "done_by": SEAT_A,
                "url": PULL,
            },
            {
                "repo": REPO,
                "task": "FR",
                "id": "#2612",
                "nick": SEAT_B,
                "done_by": SEAT_B,
                "url": PULL,
            },
        ],
    }
    seat = gitclaim.resolve_done_fr_implementer_seat(
        doc,
        pr_repo=REPO,
        pr_id="#2615",
        issue_repo=REPO,
        issue_id="#2612",
        done_nick=SEAT_B,
    )
    assert seat == SEAT_A


def test_append_unaccepted_keeps_existing_implementer_on_duplicate(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#2615",
                "seq": 1,
                "ts": "t",
                "line": "x",
                "implementer_seat": SEAT_A,
                "author_seat": SEAT_A,
                "url": PULL,
            }
        ],
        "accepted": [],
        "done": [],
    }
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#2615",
        event="pull_request",
        action="opened",
        line="x",
        refs=("#2612",),
    )
    st = gitclaim._append_unaccepted(
        doc,
        claim,
        author_seat=SEAT_B,
        implementer_seat=SEAT_B,
        url=PULL,
        supersedes=f"{REPO}#2612",
    )
    assert st == "duplicate"
    row = doc["unaccepted"][0]
    assert row["implementer_seat"] == SEAT_A
    assert row["author_seat"] == SEAT_A
    assert row.get("supersedes") == f"{REPO}#2612"
