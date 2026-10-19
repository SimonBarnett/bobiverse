"""FR #4881: out-of-fuel GIVEUPs must not stamp needs_human or burn giveup_count.

Seat-out-of-fuel (like self-MRB / ack-stale) is about the seat, not the job.
Two flamingo seats GIVEUP reason=out-of-fuel must leave the row offerable to a
fuelled seat; giveup_count stays 0, giveup_seats stays empty, needs_human unset.
"""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/a-search"
FUEL_A = "flamingo-37200"
FUEL_B = "flamingo-48824"
FRESH = "marchhare-18680"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {
        "37200": {"state": "idle", "nick": FUEL_A},
        "48824": {"state": "idle", "nick": FUEL_B},
    }
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "18680": {"state": "idle", "nick": FRESH},
    }
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _accept(doc, nick, ident="#4500"):
    un = [r for r in (doc.get("unaccepted") or []) if r.get("id") == ident]
    if not un:
        return doc
    job = dict(un[0])
    job["nick"] = nick
    doc["unaccepted"] = [r for r in doc["unaccepted"] if r.get("id") != ident]
    doc.setdefault("accepted", []).append(job)
    return doc


def test_two_out_of_fuel_giveups_leave_fresh_seat_offerable(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#4500",
        "nick": FUEL_A,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/pull/4500",
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    for seat in (FUEL_A, FUEL_B):
        doc = gitclaim._load_queue_unlocked(home)
        doc = _accept(doc, seat)
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        st, job = shop_listen.return_job_to_unaccepted(
            home,
            repo=REPO,
            task="MRB",
            ident="#4500",
            now=time.time(),
            reason="out-of-fuel",
        )
        assert st == "ok" and job is not None

    final = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#4500"][0]
    assert int(final.get("giveup_count") or 0) == 0
    assert not final.get("needs_human")
    assert not str(final.get("giveup_seats") or "").strip()
    assert not str(final.get("cooldown_until") or "").strip()
    assert gitclaim.row_needs_human(final, FRESH) is False
    st, offered = gitclaim.offer_focus_top(
        home, FRESH, "#marchhare", now=time.time() + 10_000
    )
    assert st == "ok" and offered["id"] == "#4500"


def test_job_caused_giveup_still_stamps_needs_human_at_threshold(tmp_path, monkeypatch):
    """Regression: real review GIVEUPs still burn the budget (FR #180)."""
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#4500",
        "nick": FUEL_A,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/pull/4500",
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    for seat, reason in ((FUEL_A, "cannot review"), (FUEL_B, "blocked")):
        doc = gitclaim._load_queue_unlocked(home)
        doc = _accept(doc, seat)
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        st, job = shop_listen.return_job_to_unaccepted(
            home,
            repo=REPO,
            task="MRB",
            ident="#4500",
            now=time.time(),
            reason=reason,
        )
        assert st == "ok" and job is not None

    final = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#4500"][0]
    assert int(final.get("giveup_count") or 0) == 2
    assert final.get("needs_human") is True
    assert gitclaim.row_needs_human(final, FRESH) is True
