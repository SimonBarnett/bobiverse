"""FR #4658: pusher-seat self-MRB GIVEUPs must not stamp needs_human."""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import shop_listen

ASEARCH = "SimonBarnett/a-search"
PUSHER_A = "flamingo-33384"
PUSHER_B = "flamingo-30252"
FRESH = "marchhare-13128"
AUTHOR = "marchhare-21524"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {
        "33384": {"state": "idle", "nick": PUSHER_A},
        "30252": {"state": "idle", "nick": PUSHER_B},
    }
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "13128": {"state": "idle", "nick": FRESH},
    }
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _accept(doc, nick):
    un = [r for r in (doc.get("unaccepted") or []) if r.get("id") == "#2389"]
    if not un:
        return doc
    job = dict(un[0])
    job["nick"] = nick
    doc["unaccepted"] = [r for r in doc["unaccepted"] if r.get("id") != "#2389"]
    doc.setdefault("accepted", []).append(job)
    return doc


def test_two_pusher_self_mrb_giveups_leave_fresh_seat_offerable(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": ASEARCH,
        "task": "MRB",
        "id": "#2389",
        "nick": PUSHER_A,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{ASEARCH}/pull/2389",
        "author_seat": AUTHOR,
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    for seat in (PUSHER_A, PUSHER_B):
        doc = gitclaim._load_queue_unlocked(home)
        doc = _accept(doc, seat)
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        st, job = shop_listen.return_job_to_unaccepted(
            home,
            repo=ASEARCH,
            task="MRB",
            ident="#2389",
            now=time.time(),
            reason="self-MRB",
        )
        assert st == "ok" and job is not None

    final = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#2389"][0]
    assert int(final.get("giveup_count") or 0) == 0
    assert not final.get("needs_human")
    authors = " ".join(gitclaim.row_author_seats(final)).lower()
    assert PUSHER_A.lower() in authors
    assert PUSHER_B.lower() in authors
    assert gitclaim.row_needs_human(final, FRESH) is False
    st_a, _why = gitclaim.offer_focus_top(
        home, PUSHER_A, "#flamingo", now=time.time() + 10_000
    )
    assert st_a != "ok"
    st, offered = gitclaim.offer_focus_top(
        home, FRESH, "#marchhare", now=time.time() + 20_000
    )
    assert st == "ok" and offered["id"] == "#2389"
