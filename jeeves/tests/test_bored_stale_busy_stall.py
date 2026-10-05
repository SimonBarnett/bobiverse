"""FR #2369: !bored must not nak-busy forever on stale digest doing after lost DONE."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim


def _roster(home: Path, machine: str = "marchhare") -> None:
    (home / "registered-machines.json").write_text(
        f'{{"v":1,"machines":["{machine}"]}}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _seed_doing(home: Path, nick: str, work: str) -> None:
    mid = nick.rsplit("-", 1)[0]
    pid = nick.rsplit("-", 1)[-1]
    doc = bobreport.empty_digest()
    doc["machines"][mid] = {
        "id": mid,
        "online": True,
        "working_on": work,
        "worker_list": [
            {
                "nick": nick,
                "state": "doing",
                "work": work,
                "updated": "2026-10-04T22:11:00Z",
            }
        ],
        "workers": {
            pid: {
                "pid": pid,
                "nick": nick,
                "state": "running",
                "working_on": work,
            }
        },
    }
    bobreport.save_digest(home, doc)


def _write_acc(home: Path, rows: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": rows, "done": []},
    )


def test_fr2369_stale_acc_releases_busy(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_BUSY_STALE_S", "3600")
    _roster(tmp_path)
    nick = "marchhare-40208"
    work = "bobiverse FR #2340"
    _seed_doing(tmp_path, nick, work)
    stale_ts = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 10_000)
    )
    _write_acc(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#2340",
                "nick": nick,
                "accepted_ts": stale_ts,
                "line": work,
            }
        ],
    )
    now = time.time()
    gitclaim.note_worker_activity(tmp_path, nick, now - 10_000)
    assert gitclaim.worker_working_on(tmp_path, nick)
    assert gitclaim.bored_gate(tmp_path, nick, "#marchhare", now) == "ok"
    assert gitclaim.worker_working_on(tmp_path, nick) == ""
    assert gitclaim.load_accepted(tmp_path) == []
    done = gitclaim.load_queue(tmp_path).get("done") or []
    assert any(str(r.get("result") or "") == "STALE_BUSY" for r in done)


def test_fr2369_absent_acc_clears_digest_doing(tmp_path, monkeypatch):
    """Lost DONE: digest still doing, ACC already gone → clear and offer."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    nick = "marchhare-35016"
    _seed_doing(tmp_path, nick, "bobiverse MRB #2349")
    _write_acc(tmp_path, [])
    now = time.time()
    gitclaim.note_worker_activity(tmp_path, nick, now - 10_000)
    assert gitclaim.worker_working_on(tmp_path, nick)
    assert gitclaim.release_stale_busy(tmp_path, nick, now) is True
    assert gitclaim.bored_gate(tmp_path, nick, "#marchhare", now) == "ok"
    assert gitclaim.worker_working_on(tmp_path, nick) == ""


def test_fr2369_recent_acc_keeps_nak_busy(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_BUSY_STALE_S", "3600")
    _roster(tmp_path)
    nick = "marchhare-40208"
    work = "bobiverse FR #9999"
    _seed_doing(tmp_path, nick, work)
    recent_ts = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60)
    )
    _write_acc(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9999",
                "nick": nick,
                "accepted_ts": recent_ts,
                "line": work,
            }
        ],
    )
    now = time.time()
    gitclaim.note_worker_activity(tmp_path, nick, now - 10_000)
    assert gitclaim.bored_gate(tmp_path, nick, "#marchhare", now) == "busy"
    assert len(gitclaim.load_accepted(tmp_path)) == 1
