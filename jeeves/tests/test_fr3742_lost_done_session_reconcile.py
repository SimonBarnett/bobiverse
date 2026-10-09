"""FR #3742: lost DONE across chair restart — !bored heals pre-session accepted rows."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim

NICK = "marchhare-34384"


def _setup(home: Path, monkeypatch, work: str = "a-search FR #977") -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare","win-mpre8vi4u6u"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": work,
        "worker_list": [
            {
                "nick": NICK,
                "state": "doing",
                "work": work,
                "updated": "2026-10-09T14:30:56Z",
            }
        ],
        "workers": {
            "34384": {
                "pid": "34384",
                "nick": NICK,
                "state": "doing",
                "working_on": work,
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue(home: Path, accepted: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": accepted},
    )


def test_fr3742_pre_session_accepted_healed_on_bored(tmp_path, monkeypatch):
    """Incident shape: ACK before chair restart, !bored minutes later -> ok not nak busy."""
    _setup(tmp_path, monkeypatch)
    now = time.time()
    session_started = now - 60.0
    ack_ts = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(session_started - 300)
    )
    row = {
        "repo": "SimonBarnett/a-search",
        "task": "FR",
        "id": "#977",
        "nick": NICK,
        "accepted_ts": ack_ts,
        "ts": ack_ts,
    }
    _queue(tmp_path, [row])
    gitclaim.note_worker_activity(tmp_path, NICK, now - 10_000)
    logs: list[str] = []
    assert gitclaim.release_stale_busy(
        tmp_path, NICK, now, session_started=session_started, log=logs.append
    )
    assert gitclaim.load_queue(tmp_path)["accepted"] == []
    done = gitclaim.load_queue(tmp_path).get("done") or []
    assert any(
        str(r.get("id")) == "#977"
        and (
            str(r.get("result") or "") == "LOST_DONE_RESTART"
            or str(r.get("reconcile") or "") == "LOST_DONE_RESTART"
        )
        for r in done
    )
    assert any("seat-reconcile" in line and "LOST_DONE_RESTART" in line for line in logs)
    # Gate sees idle after heal (re-seed doing digest; accepted already cleared).
    _setup(tmp_path, monkeypatch)
    assert (
        gitclaim.bored_gate(
            tmp_path, NICK, "#marchhare", now, session_started=session_started
        )
        == "ok"
    )


def test_fr3742_post_session_fresh_ack_still_busy(tmp_path, monkeypatch):
    """ACK after this session started and age < BUSY_STALE_S stays busy."""
    _setup(tmp_path, monkeypatch, work="bobiverse FR #7")
    now = time.time()
    session_started = now - 600.0
    ack_ts = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(session_started + 60)
    )
    _queue(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#7",
                "nick": NICK,
                "accepted_ts": ack_ts,
                "ts": ack_ts,
            }
        ],
    )
    gitclaim.note_worker_activity(tmp_path, NICK, now - 10_000)
    assert (
        gitclaim.bored_gate(
            tmp_path, NICK, "#marchhare", now, session_started=session_started
        )
        == "busy"
    )
    assert len(gitclaim.load_queue(tmp_path)["accepted"]) == 1


def test_fr3742_age_stale_still_heals_without_session(tmp_path, monkeypatch):
    """FR #2369 path unchanged when session_started is omitted."""
    _setup(tmp_path, monkeypatch, work="bobiverse FR #2340")
    now = time.time()
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 8 * 3600))
    _queue(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#2340",
                "nick": NICK,
                "accepted_ts": old,
                "ts": old,
            }
        ],
    )
    gitclaim.note_worker_activity(tmp_path, NICK, now - 10_000)
    assert gitclaim.bored_gate(tmp_path, NICK, "#marchhare", now) == "ok"
    assert gitclaim.load_queue(tmp_path)["accepted"] == []


def test_fr3742_pull_url_in_digest_used_as_result(tmp_path, monkeypatch):
    pull = "https://github.com/SimonBarnett/a-search/pull/1157"
    _setup(tmp_path, monkeypatch, work=f"a-search FR #977 {pull}")
    now = time.time()
    session_started = now - 30.0
    ack_ts = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(session_started - 120)
    )
    _queue(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/a-search",
                "task": "FR",
                "id": "#977",
                "nick": NICK,
                "accepted_ts": ack_ts,
                "ts": ack_ts,
            }
        ],
    )
    assert gitclaim.release_stale_busy(
        tmp_path, NICK, now, session_started=session_started
    )
    done = gitclaim.load_queue(tmp_path).get("done") or []
    assert any(str(r.get("result") or "") == pull for r in done)


def test_fr3742_irc_agent_wires_session_started():
    agent = Path(__file__).resolve().parents[2] / "common/scripts/irc_agent.py"
    text = agent.read_text(encoding="utf-8")
    assert "_irc_session_started" in text
    assert "session_started=session_started" in text
    assert "FR #3742" in text
    # session() refreshes the boundary on each (re)connect
    assert "self._irc_session_started = time.time()" in text
