"""FR #9634: !assign clears nick+row giveup (queue + ledger) instead of refusing.

Live pain: seats in giveup_seats got ``already gave this row up`` on !assign until
ops ran !cleargiveup. Explicit !assign (FR #4336 path) implies clear for that seat.
Non-goal: auto-clear credential needs_human without ops (a-search #5058 class).
"""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines

REPO = "SimonBarnett/bobiverse"
SEAT_A = "flamingo-17068"
SEAT_B = "flamingo-17160"


def _idle_digest(home, *nicks: str) -> None:
    registered_machines.save_registered(home, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": n, "state": "idle"} for n in nicks
    ]
    digest["machines"]["flamingo"]["workers"] = {
        n.rsplit("-", 1)[-1]: {"state": "idle"} for n in nicks
    }
    bobreport.save_digest(home, digest)


def test_fr9634_assign_clears_exact_nick_giveup(tmp_path, monkeypatch):
    """Seat already in giveup_seats + ledger: !assign clears and offers (not refuse)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _idle_digest(tmp_path, SEAT_A, SEAT_B)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": REPO,
                "task": "FR",
                "id": "#9622",
                "seq": 1,
                "needs_human": True,
                "giveup_seats": f"{SEAT_A},{SEAT_B}",
                "giveup_count": 2,
                "line": f"FR {REPO}#9622",
                "url": f"https://github.com/{REPO}/issues/9622",
                "ts": "t",
                "event": "issues",
                "action": "opened",
            }
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    gitclaim.ledger_giveup(tmp_path, SEAT_A, REPO, "FR", "#9622")
    gitclaim.ledger_giveup(tmp_path, SEAT_B, REPO, "FR", "#9622")

    # Precondition: both paths would have blocked before FR #9634.
    assert gitclaim.row_gave_up_by(doc["unaccepted"][0], SEAT_A) is True
    led = gitclaim.ledger_load(tmp_path)
    why = gitclaim.ledger_blocks(led, doc["unaccepted"][0], SEAT_A)
    assert "gave up" in why

    st, job = gitclaim.assign_row(
        tmp_path,
        SEAT_A,
        REPO,
        "FR",
        "#9622",
        issue_open=lambda *_a, **_k: True,
    )
    assert st == "ok", job
    assert job.get("offered_to") == SEAT_A
    # Exact nick cleared from queue; sibling giveup remains.
    seats = str(job.get("giveup_seats") or "")
    assert SEAT_A not in seats
    assert SEAT_B in seats
    # Ledger entry for A cleared so a later re-check does not block.
    # Ledger keys are lower-case repo (``_lkey`` / ``_repo_key``).
    led2 = gitclaim.ledger_load(tmp_path)
    lkey = gitclaim._lkey(REPO, "#9622")
    bucket = (led2.get("giveup") or {}).get(lkey) or {}
    assert SEAT_A not in bucket
    assert SEAT_B in bucket
    assert not gitclaim.ledger_blocks(led2, job, SEAT_A)


def test_fr9634_assign_still_ok_when_only_queue_giveup(tmp_path, monkeypatch):
    """Queue giveup_seats alone (no ledger) also clears on !assign."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _idle_digest(tmp_path, SEAT_A)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": REPO,
                "task": "FR",
                "id": "#9634",
                "seq": 1,
                "giveup_seats": SEAT_A,
                "line": f"FR {REPO}#9634",
                "url": f"https://github.com/{REPO}/issues/9634",
                "ts": "t",
                "event": "issues",
                "action": "opened",
            }
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    st, job = gitclaim.assign_row(
        tmp_path,
        SEAT_A,
        REPO,
        "FR",
        "#9634",
        issue_open=lambda *_a, **_k: True,
    )
    assert st == "ok", job
    assert job.get("offered_to") == SEAT_A
    assert not job.get("giveup_seats")
