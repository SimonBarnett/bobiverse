"""FR #8235: a live job process with a current heartbeat is not LOST_ACK_RESTART."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import bobreport
import gitclaim

NICK = "redqueen-7968"
WORK = "bobiverse MRB #8224"
REPO = "SimonBarnett/bobiverse"


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _home(tmp_path: Path, monkeypatch, *, last_progress: str, pid: str = "8360") -> Path:
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    home.mkdir(parents=True, exist_ok=True)
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["redqueen"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["redqueen"] = {
        "id": "redqueen",
        "online": True,
        "worker_list": [
            {
                "nick": NICK,
                "state": "doing",
                "work": WORK,
                "pid": pid,
                "last_progress": last_progress,
                "updated": last_progress,
            }
        ],
        "workers": {
            "8360": {
                "pid": pid,
                "nick": NICK,
                "state": "running",
                "working_on": WORK,
                "last_progress": last_progress,
            }
        },
    }
    bobreport.save_digest(home, doc)
    return home


def _queue(home: Path) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#8224",
                    "seq": 8224,
                    "url": f"https://github.com/{REPO}/pull/8224",
                }
            ],
            "accepted": [],
        },
    )


def test_fr8235_fresh_heartbeat_accepts_without_lost_ack(tmp_path, monkeypatch):
    now = time.time()
    home = _home(tmp_path, monkeypatch, last_progress=_iso(now - 30.0))
    _queue(home)
    logs: list[str] = []
    n = gitclaim.reconcile_lost_ack_from_digest(home, log=logs.append)
    assert n == 1
    acc = gitclaim.load_queue(home)["accepted"][0]
    assert str(acc.get("reconcile") or "") != "LOST_ACK_RESTART"
    assert acc["nick"] == NICK
    assert any("accepted-live-heartbeat" in line for line in logs)
    assert not any("result=LOST_ACK_RESTART" in line for line in logs)


def test_fr8235_stale_heartbeat_still_lost_ack(tmp_path, monkeypatch):
    now = time.time()
    home = _home(tmp_path, monkeypatch, last_progress=_iso(now - 4000.0))
    _queue(home)
    logs: list[str] = []
    n = gitclaim.reconcile_lost_ack_from_digest(home, log=logs.append)
    assert n == 1
    acc = gitclaim.load_queue(home)["accepted"][0]
    assert str(acc.get("reconcile") or "") == "LOST_ACK_RESTART"
    assert any("result=LOST_ACK_RESTART" in line for line in logs)
