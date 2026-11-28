"""FR #10337: digest state=idle releases a young accepted row (nak-busy stall)."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim

NICK = "redqueen-11760"


def _setup(home: Path, monkeypatch, state: str) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["redqueen"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["redqueen"] = {
        "id": "redqueen",
        "online": True,
        "working_on": "",
        "worker_list": [
            {
                "nick": NICK,
                "state": state,
                "work": "",
                "updated": "2026-11-28T14:00:00Z",
            }
        ],
        "workers": {
            "11760": {
                "pid": "11760",
                "nick": NICK,
                "state": state,
                "working_on": "",
            }
        },
    }
    bobreport.save_digest(home, doc)


def _acc(home: Path, age_s: float, now: float) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - age_s))
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10327",
                    "nick": NICK,
                    "accepted_ts": ts,
                    "ts": ts,
                }
            ],
        },
    )


def test_idle_digest_releases_accepted_after_90s(tmp_path, monkeypatch):
    now = time.time()
    _setup(tmp_path, monkeypatch, "idle")
    _acc(tmp_path, 120.0, now)
    logs: list[str] = []
    assert gitclaim.release_stale_busy(tmp_path, NICK, now, log=logs.append)
    q = gitclaim.load_queue(tmp_path)
    assert q["accepted"] == []
    assert not any(str(r.get("id")) == "#10327" for r in (q.get("done") or []))
    unacc = q.get("unaccepted") or []
    hit = [r for r in unacc if str(r.get("id")) == "#10327"]
    assert len(hit) == 1
    assert hit[0].get("reconcile") == "requeue:IDLE_DIGEST"
    assert "prior_holder" not in hit[0]
    assert any("IDLE_DIGEST" in line for line in logs)


def test_idle_digest_under_90s_stays_accepted(tmp_path, monkeypatch):
    now = time.time()
    _setup(tmp_path, monkeypatch, "idle")
    _acc(tmp_path, 30.0, now)
    assert not gitclaim.release_stale_busy(tmp_path, NICK, now)
    assert len(gitclaim.load_queue(tmp_path)["accepted"]) == 1
    assert (
        gitclaim.bored_gate(tmp_path, NICK, "#redqueen", now) == "busy"
    )


def test_doing_digest_young_row_stays_accepted(tmp_path, monkeypatch):
    now = time.time()
    _setup(tmp_path, monkeypatch, "doing")
    _acc(tmp_path, 120.0, now)
    assert not gitclaim.release_stale_busy(tmp_path, NICK, now)
    assert len(gitclaim.load_queue(tmp_path)["accepted"]) == 1
