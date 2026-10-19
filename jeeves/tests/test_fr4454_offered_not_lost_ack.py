"""FR #4454: Jeeves worker_list state=offered is not a lost-ACK work claim."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim

NICK = "marchhare-11360"
WORK = "a-search MRB #2389"
REPO = "SimonBarnett/a-search"
PULL = "https://github.com/SimonBarnett/a-search/pull/2389"


def _digest(home: Path, monkeypatch, *, list_state: str, list_work: str, map_work: str) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": "",
        "worker_list": [
            {
                "nick": NICK,
                "state": list_state,
                "work": list_work,
                "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        ],
        "workers": {
            "11360": {
                "pid": "11360",
                "nick": NICK,
                "state": "idle" if not map_work else "running",
                "working_on": map_work,
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue(home: Path, *, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": list(unaccepted), "accepted": list(accepted or [])},
    )


def _row(**extra) -> dict:
    base = {
        "repo": REPO,
        "task": "MRB",
        "id": "#2389",
        "seq": 2389,
        "url": PULL,
    }
    base.update(extra)
    return base


def test_fr4454_offered_worker_list_does_not_promote(tmp_path, monkeypatch):
    """Digest state=offered is Jeeves's own offer. Reconcile must leave offered_* stamps."""
    _digest(tmp_path, monkeypatch, list_state="offered", list_work=WORK, map_work="")
    offer_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30))
    offered = _row(offered_to=NICK, offered_ts=offer_ts, offered_channel="#marchhare")
    _queue(tmp_path, unaccepted=[offered])
    n = gitclaim.reconcile_lost_ack_from_digest(tmp_path, log=lambda _line: None)
    assert n == 0
    q = gitclaim.load_queue(tmp_path)
    assert len(q["unaccepted"]) == 1
    row = q["unaccepted"][0]
    assert row.get("offered_to") == NICK
    assert row.get("offered_ts") == offer_ts
    assert row.get("offered_channel") == "#marchhare"
    assert q["accepted"] == []


def test_fr4454_seat_working_on_still_promotes(tmp_path, monkeypatch):
    """FR #3867: workers[*].working_on (seat-reported) still promotes after a restart."""
    _digest(tmp_path, monkeypatch, list_state="idle", list_work="", map_work=WORK)
    offer_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
    _queue(
        tmp_path,
        unaccepted=[_row(offered_to=NICK, offered_ts=offer_ts, offered_channel="#marchhare")],
    )
    n = gitclaim.reconcile_lost_ack_from_digest(tmp_path, log=lambda _line: None)
    assert n == 1
    q = gitclaim.load_queue(tmp_path)
    assert q["unaccepted"] == []
    acc = q["accepted"][0]
    assert str(acc.get("reconcile") or "") == "LOST_ACK_RESTART"
    assert acc.get("nick") == NICK


def test_fr4454_bored_reoffers_unacked_lost_ack(tmp_path, monkeypatch):
    """!bored on a LOST_ACK_RESTART row with no seat-reported work is not NAK busy."""
    _digest(tmp_path, monkeypatch, list_state="idle", list_work="", map_work="")
    accepted_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
    _queue(
        tmp_path,
        unaccepted=[],
        accepted=[_row(nick=NICK, accepted_ts=accepted_ts, reconcile="LOST_ACK_RESTART")],
    )
    gate = gitclaim.bored_gate(tmp_path, NICK, "#marchhare", time.time())
    assert gate == "ok"
    st, job = gitclaim.offer_focus_top(tmp_path, NICK, "#marchhare")
    assert st == "ok"
    assert job is not None
    assert str(job.get("id")) == "#2389"
    assert str(job.get("offered_to") or "") == NICK


def test_fr4454_assign_redelivers_unacked_lost_ack(tmp_path, monkeypatch):
    """!assign of the same row to the same seat re-delivers a false LOST_ACK_RESTART."""
    _digest(tmp_path, monkeypatch, list_state="idle", list_work="", map_work="")
    accepted_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
    _queue(
        tmp_path,
        unaccepted=[],
        accepted=[_row(nick=NICK, accepted_ts=accepted_ts, reconcile="LOST_ACK_RESTART")],
    )
    st, job = gitclaim.assign_row(tmp_path, NICK, REPO, "MRB", "2389")
    assert st == "ok", job
    assert isinstance(job, dict)
    assert str(job.get("id")) == "#2389"
    assert str(job.get("offered_to") or "") == NICK
    q = gitclaim.load_queue(tmp_path)
    assert q["accepted"] == []
    assert any(str(r.get("id")) == "#2389" for r in q["unaccepted"])
