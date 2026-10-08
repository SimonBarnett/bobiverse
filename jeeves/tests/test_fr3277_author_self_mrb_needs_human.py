"""FR #3277: author self-MRB must not strand MRBs via needs_human / missing author_seat.

Acceptance:
1. Stamp author_seat on MRB when FR DONE names the PR URL (webhook-first + non-bobiverse).
2. Self-MRB GIVEUP must not count toward GIVEUP_NEEDS_HUMAN_COUNT / stamp needs_human.
3. needs_human with giveup_seats set blocks only those seats on !bored and !assign.
"""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import shop_listen


ASEARCH = "SimonBarnett/a-search"
AUTHOR = "marchhare-40596"
OTHER = "marchhare-22372"


def _home(tmp_path, monkeypatch, seats=None):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    workers = seats or {
        "40596": {"state": "idle", "nick": AUTHOR},
        "22372": {"state": "idle", "nick": OTHER},
    }
    digest["machines"]["marchhare"]["workers"] = workers
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def test_row_needs_human_with_giveup_seats_only_blocks_those_seats_even_at_threshold():
    """FR #3277: giveup_count>=GIVEUP_NEEDS_HUMAN_COUNT must not override giveup_seats."""
    row = {
        "needs_human": True,
        "giveup_count": gitclaim.GIVEUP_NEEDS_HUMAN_COUNT,
        "giveup_seats": AUTHOR,
    }
    assert gitclaim.row_needs_human(row, AUTHOR) is True
    assert gitclaim.row_needs_human(row, OTHER) is False
    assert gitclaim.row_needs_human(row, "ionos-99") is False
    # Bare needs_human (no giveup_seats) stays a global gate.
    bare = {"needs_human": True, "giveup_count": gitclaim.GIVEUP_NEEDS_HUMAN_COUNT}
    assert gitclaim.row_needs_human(bare, OTHER) is True


def test_assign_refuses_needs_human_only_for_giveup_seats(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": ASEARCH,
                    "task": "MRB",
                    "id": "#501",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "url": f"https://github.com/{ASEARCH}/pull/501",
                    "title": "fix(fr-194)",
                    "needs_human": True,
                    "giveup_count": 2,
                    "giveup_seats": AUTHOR,
                    "author_seat": AUTHOR,
                    "implementer_seat": AUTHOR,
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st_a, why_a = gitclaim.assign_row(home, AUTHOR, ASEARCH, "MRB", "#501")
    assert st_a == "refused" and "needs-human" in str(why_a).lower()
    st_b, job_b = gitclaim.assign_row(home, OTHER, ASEARCH, "MRB", "#501")
    assert st_b == "ok" and job_b and job_b["id"] == "#501"


def test_self_mrb_giveup_does_not_increment_giveup_count_or_stamp_needs_human(
    tmp_path, monkeypatch
):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": ASEARCH,
        "task": "MRB",
        "id": "#501",
        "nick": AUTHOR,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{ASEARCH}/pull/501",
        "author_seat": AUTHOR,
        "implementer_seat": AUTHOR,
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    # Two self-MRB GIVEUPs (production a-search#501 pattern).
    for _ in range(2):
        doc = gitclaim._load_queue_unlocked(home)
        # Re-accept for the author if returned to unaccepted.
        un = [r for r in (doc.get("unaccepted") or []) if r.get("id") == "#501"]
        acc = [r for r in (doc.get("accepted") or []) if r.get("id") == "#501"]
        if un and not acc:
            j = dict(un[0])
            j["nick"] = AUTHOR
            doc["unaccepted"] = [r for r in doc["unaccepted"] if r.get("id") != "#501"]
            doc.setdefault("accepted", []).append(j)
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
        st, job = shop_listen.return_job_to_unaccepted(
            home, repo=ASEARCH, task="MRB", ident="#501", now=time.time()
        )
        assert st == "ok" and job is not None

    final = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#501"][0]
    assert int(final.get("giveup_count") or 0) == 0
    assert not final.get("needs_human")
    assert AUTHOR.lower() in str(final.get("giveup_seats") or "").lower()
    # Other seats remain offerable.
    assert gitclaim.row_needs_human(final, OTHER) is False
    st, offered = gitclaim.offer_focus_top(home, OTHER, "#marchhare", now=time.time() + 10_000)
    assert st == "ok" and offered["id"] == "#501"


def test_non_author_giveup_still_counts_toward_needs_human(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": ASEARCH,
        "task": "MRB",
        "id": "#501",
        "nick": OTHER,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{ASEARCH}/pull/501",
        "author_seat": AUTHOR,
        "implementer_seat": AUTHOR,
        "giveup_count": 1,
        "giveup_seats": "flamingo-9",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [row], "done": []},
    )
    st, job = shop_listen.return_job_to_unaccepted(
        home, repo=ASEARCH, task="MRB", ident="#501", now=time.time()
    )
    assert st == "ok"
    assert int(job.get("giveup_count") or 0) == 2
    assert job.get("needs_human") is True
    # giveup_seats set → only those seats blocked (flamingo-9 + OTHER), not AUTHOR.
    assert gitclaim.row_needs_human(job, OTHER) is True
    assert gitclaim.row_needs_human(job, AUTHOR) is False


def test_webhook_first_then_done_fr_stamps_author_on_asearch(tmp_path, monkeypatch):
    """Webhook opens MRB before DONE FR; DONE must still leave author_seat stamped."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": ASEARCH,
                    "task": "FR",
                    "id": "#194",
                    "seq": 1,
                    "nick": AUTHOR,
                    "ts": "t",
                    "line": "x",
                    "channel": "#marchhare",
                    "accepted_ts": "t",
                }
            ],
            "done": [],
        },
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": ASEARCH},
            "pull_request": {
                "number": 501,
                "title": "fix(fr-194)",
                "body": "Closes SimonBarnett/a-search#194",
                "html_url": f"https://github.com/{ASEARCH}/pull/501",
            },
        },
    )
    assert claim is not None
    assert gitclaim.apply_queue_event(home, claim) in ("added", "updated", "duplicate")
    mrbs = [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert mrbs[0].get("author_seat") == AUTHOR

    # DONE FR after webhook (production order).
    # Re-accept FR if webhook removed it from accepted.
    doc = gitclaim._load_queue_unlocked(home)
    if not any(
        str(r.get("task") or "").upper() == "FR" and r.get("id") == "#194"
        for r in (doc.get("accepted") or [])
    ):
        doc.setdefault("accepted", []).append(
            {
                "repo": ASEARCH,
                "task": "FR",
                "id": "#194",
                "seq": 1,
                "nick": AUTHOR,
                "ts": "t",
                "line": "x",
                "channel": "#marchhare",
                "accepted_ts": "t",
            }
        )
        gitclaim._write_queue(gitclaim.queue_path(home), doc)

    st, _ = shop_listen.complete_job_by_ref(
        home,
        nick=AUTHOR,
        repo=ASEARCH,
        task="FR",
        ident="#194",
        result="",
        url=f"https://github.com/{ASEARCH}/pull/501",
    )
    assert st == "ok"
    mrbs = [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert mrbs[0].get("author_seat") == AUTHOR
    assert mrbs[0].get("implementer_seat") == AUTHOR
    # Author blocked as self_mrb; other seat offered.
    assert gitclaim.offer_focus_top(home, AUTHOR, "#marchhare")[0] == "empty"
    st2, job2 = gitclaim.offer_focus_top(home, OTHER, "#marchhare")
    assert st2 == "ok" and job2["id"] == "#501"


def test_resync_readd_stamps_author_from_done_fr(tmp_path, monkeypatch):
    """Resync that re-queues an open MRB must stamp author from prior DONE FR."""
    home = _home(tmp_path, monkeypatch)
    pull = f"https://github.com/{ASEARCH}/pull/501"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": ASEARCH,
                    "task": "FR",
                    "id": "#194",
                    "nick": AUTHOR,
                    "done_by": AUTHOR,
                    "url": pull,
                    "result": "",
                }
            ],
        },
    )
    claim = gitclaim.GitClaim(
        repo=ASEARCH,
        task="MRB",
        id="#501",
        event="pull_request",
        action="opened",
        line="MRB",
        refs=("#194",),
        title="fix(fr-194)",
        body="Closes SimonBarnett/a-search#194",
    )
    # Simulate resync desired-append path (url only historically — must also stamp author).
    doc = gitclaim._load_queue_unlocked(home)
    mrb_url = pull
    assert (
        gitclaim._append_unaccepted(
            doc,
            claim,
            url=mrb_url,
            **gitclaim.mrb_author_extra_from_doc(doc, claim),
        )
        == "added"
    )
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    mrbs = [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert mrbs[0].get("author_seat") == AUTHOR
    assert mrbs[0].get("implementer_seat") == AUTHOR
