"""MRB #2819 hostile: chair-outbox say False must not clear idle / count as delivered."""
from __future__ import annotations

import time

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines as rm
import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(
        tmp_path, ["#bobiverse", "#marchhare", "#flamingo", "#win-mpre8vi4u6u"]
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    fi.handle_focus_cmd(tmp_path, "bobiverse")
    return tmp_path


def _put_idle(home, nick="marchhare-1"):
    doc = bobreport.load_digest(home)
    machines = doc.setdefault("machines", {})
    machines["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "worker_list": [
            {
                "nick": nick,
                "state": "idle",
                "work": "",
                "updated": "2026-10-06T10:00:00Z",
            }
        ],
        "working_on": "",
    }
    bobreport.save_digest(home, doc)


def test_mrb2819_say_false_keeps_idle_and_retries(home, monkeypatch):
    """enqueue_chair_fleet_privmsg returning False must not clear idle-after-empty."""
    nick = "marchhare-1"
    _put_idle(home, nick)
    gitclaim.note_idle_after_empty(home, nick, "#marchhare", now=1000.0)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "seq": 1,
                    "ts": "2026-10-06T10:00:01Z",
                    "line": "x",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/10",
                    "title": "t",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    monkeypatch.setattr(
        bobreport, "enqueue_chair_fleet_privmsg", lambda *a, **k: False
    )
    n = gitclaim.push_idle_offers_via_chair_outbox(home, now=1001.0)
    assert n == 0
    idle = gitclaim.list_idle_after_empty(home, now=1001.0)
    assert any(e["nick"].lower().startswith("marchhare") for e in idle)
    # Rate-limited until IDLE_PUSH_MIN_INTERVAL_S
    n2 = gitclaim.push_idle_offers_via_chair_outbox(home, now=1002.0)
    assert n2 == 0
    # After interval + successful enqueue, deliver once and clear idle
    monkeypatch.setattr(
        bobreport, "enqueue_chair_fleet_privmsg", lambda *a, **k: True
    )
    n3 = gitclaim.push_idle_offers_via_chair_outbox(
        home, now=1001.0 + gitclaim.IDLE_PUSH_MIN_INTERVAL_S + 0.1
    )
    assert n3 == 1
    assert gitclaim.list_idle_after_empty(
        home, now=1001.0 + gitclaim.IDLE_PUSH_MIN_INTERVAL_S + 0.1
    ) == []


def test_mrb2819_say_exception_keeps_idle(home):
    nick = "marchhare-1"
    _put_idle(home, nick)
    gitclaim.note_idle_after_empty(home, nick, "#marchhare", now=1000.0)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#11",
                    "seq": 1,
                    "ts": "2026-10-06T10:00:02Z",
                    "line": "x",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/11",
                    "title": "t",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )

    def boom(ch, t):
        raise RuntimeError("irc down")

    n = gitclaim.offer_to_idle_seats(home, say=boom, now=1001.0)
    assert n == 0
    assert gitclaim.list_idle_after_empty(home, now=1001.0)
