"""FR #8525: LOST_ACK_RESTART UAT #0 must not NAK-busy an idle seat forever."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bobreport
import gitclaim

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "monitor"))
import stuck_accepted  # noqa: E402

NICK = "flamingo-19720"
REPO = "SimonBarnett/wetherby"


def _seed(home: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["flamingo"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _digest_idle_with_stale_map_work(home: Path) -> None:
    doc = bobreport.empty_digest()
    doc["machines"]["flamingo"] = {
        "id": "flamingo",
        "online": True,
        "working_on": "",
        "worker_list": [
            {
                "nick": NICK,
                "state": "idle",
                "work": "",
                "working_on": "",
                "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        ],
        "workers": {
            "19720": {
                "pid": "19720",
                "nick": NICK,
                "state": "idle",
                # Stale paint must not block LOST_ACK demote (FR #8525).
                "working_on": f"UAT {REPO}#0",
            }
        },
    }
    bobreport.save_digest(home, doc)


def _uat0(**extra) -> dict:
    base = {
        "repo": REPO,
        "task": "UAT",
        "id": "#0",
        "repo_uat": True,
        "nick": NICK,
        "accepted_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 120)),
        "reconcile": "LOST_ACK_RESTART",
        "title": "repo UAT",
    }
    base.update(extra)
    return base


def test_fr8525_bored_demotes_uat0_despite_stale_workers_map(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _digest_idle_with_stale_map_work(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [_uat0()], "done": []},
    )
    gate = gitclaim.bored_gate(tmp_path, NICK, "#flamingo", time.time())
    assert gate == "ok"
    q = gitclaim.load_queue(tmp_path)
    assert q["accepted"] == []
    assert any(str(r.get("reconcile")) == "requeue:LOST_ACK_NO_ACK" for r in q["unaccepted"])
    assert any(str(r.get("task")).upper() == "UAT" and str(r.get("id")) == "#0" for r in q["unaccepted"])


def test_fr8525_bored_clears_hold_before_nak_held(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _digest_idle_with_stale_map_work(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [_uat0()], "done": []},
    )
    # Seat hold for the same UAT used to NAK why=held before demote ran.
    holds = {
        NICK.lower(): {
            "repo": REPO,
            "task": "UAT",
            "id": "#0",
            "via": "offer",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    }
    gitclaim._save_seat_holds_unlocked(tmp_path, holds)
    gate = gitclaim.bored_gate(tmp_path, NICK, "#flamingo", time.time())
    assert gate == "ok"
    open_job = gitclaim.seat_open_job(tmp_path, NICK, time.time())
    assert open_job == ""
    q = gitclaim.load_queue(tmp_path)
    assert q["accepted"] == []


def test_fr8525_monitor_flags_lost_ack_uat0_idle(tmp_path):
    rows = [_uat0()]
    shop = [{"nick": NICK, "state": "idle", "work": "", "working_on": ""}]
    text = stuck_accepted._lost_ack_uat0_finding(rows, shop)
    assert "UAT #0 LOST_ACK_RESTART" in text
    assert NICK in text
    doing = [{"nick": NICK, "state": "doing", "work": f"UAT {REPO}#0", "working_on": f"UAT {REPO}#0"}]
    assert stuck_accepted._lost_ack_uat0_finding(rows, doing) == ""


def test_fr8525_monitor_check_includes_finding(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _digest_idle_with_stale_map_work(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [_uat0()], "done": []},
    )
    # Monitor resolves chair/digest from args; use simple namespace.
    class Args:
        chair_home = str(tmp_path)
        digest_home = str(tmp_path)
        queue = ""

    payload, code = stuck_accepted.check(Args())
    assert code == stuck_accepted.EXIT_FINDING
    assert any("LOST_ACK_RESTART" in f for f in payload["findings"])
