# -*- coding: utf-8 -*-
"""FR #3623: ask_user_question pending hang detection + agent disallowed-tools."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import bob_worker as bw


def _write_events(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows),
        encoding="utf-8",
    )


def test_probe_ask_user_pending_age_none_when_missing(tmp_path: Path):
    assert bw.probe_ask_user_pending_age(tmp_path) is None


def test_probe_ask_user_pending_age_tracks_started_until_completed(tmp_path: Path):
    ev = tmp_path / "events.jsonl"
    t0 = "2026-10-08T18:19:12.328Z"
    t1 = "2026-10-08T18:20:12.328Z"
    _write_events(
        ev,
        [
            {"ts": t0, "type": "tool_started", "tool_name": "ask_user_question"},
            {"ts": t0, "type": "permission_requested", "tool_name": "ask_user_question"},
        ],
    )
    now = bw._parse_iso_ts(t0) + 90.0
    age = bw.probe_ask_user_pending_age(tmp_path, now_wall=now)
    assert age is not None
    assert 89.0 <= age <= 91.0
    _write_events(
        ev,
        [
            {"ts": t0, "type": "tool_started", "tool_name": "ask_user_question"},
            {"ts": t1, "type": "tool_completed", "tool_name": "ask_user_question", "outcome": "success"},
        ],
    )
    assert bw.probe_ask_user_pending_age(tmp_path, now_wall=now) is None


def test_ask_user_watch_enter_then_recycle():
    w = bw.AskUserPendingWatch(pending_s=10.0, enter_grace_s=5.0)
    assert w.tick(None, 0.0) is None
    assert w.tick(5.0, 1.0) is None
    assert w.tick(10.0, 2.0) == "enter"
    assert w.tick(11.0, 3.0) is None
    assert w.tick(12.0, 8.0) == "recycle"
    w.clear()
    assert w.tick(20.0, 9.0) == "enter"


def test_build_launch_agent_disallows_ask_user(tmp_path: Path):
    rd = tmp_path / "run"
    rd.mkdir()
    spec = bw.build_launch(
        "grok",
        "agent",
        str(tmp_path / "cwd"),
        "prompt",
        r"C:\fake\grok.exe",
        rd,
        session_id="11111111-1111-1111-1111-111111111111",
    )
    assert "--disallowed-tools" in spec.argv
    i = spec.argv.index("--disallowed-tools")
    assert spec.argv[i + 1] == "ask_user_question"
    assert "ask_user_question" in bw.rules_text(str(tmp_path), "agent")


def test_build_launch_plan_keeps_ask_user(tmp_path: Path):
    rd = tmp_path / "run"
    rd.mkdir()
    spec = bw.build_launch(
        "grok",
        "plan",
        str(tmp_path / "cwd"),
        "prompt",
        r"C:\fake\grok.exe",
        rd,
        session_id="22222222-2222-2222-2222-222222222222",
    )
    assert "--disallowed-tools" not in spec.argv


def test_check_ask_user_pending_enter_then_recycle(tmp_path: Path, monkeypatch):
    """Detector acts within threshold: Enter once, then restart with ask-user-pending."""
    cwd = tmp_path / "worker"
    cwd.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    sessions = tmp_path / "sessions"
    sid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    key = quote(str(cwd), safe="")
    sdir = sessions / key / sid
    sdir.mkdir(parents=True)
    t0 = "2026-10-08T18:19:12.000Z"
    start_wall = bw._parse_iso_ts(t0)
    assert start_wall is not None
    _write_events(
        sdir / "events.jsonl",
        [{"ts": t0, "type": "tool_started", "tool_name": "ask_user_question"}],
    )

    class FakeProc:
        pid = 4242

        def poll(self):
            return None

    class FakeRelay:
        last_unacked = None
        on_inject = None
        hold_assigns_while = None
        on_hold_assign = None

        def set_target(self, _t):
            pass

        def hold(self, _m):
            pass

        def release_held_assigns(self):
            return 0

    enters = []
    logs = []
    restarts = []
    clock = {"t": 100.0}

    monkeypatch.setattr(bw.time, "time", lambda: start_wall + 120.0)

    watch = bw.AskUserPendingWatch(pending_s=60.0, enter_grace_s=5.0)
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\fake\grok.exe",
        cwd=str(cwd),
        machine="marchhare",
        nick="marchhare-1",
        run_dir=run,
        irc=None,
        relay=FakeRelay(),
        log=logs.append,
        spawn=lambda spec, env: FakeProc(),
        kill=lambda pid: True,
        probe=lambda pid: bw.Sample(True, True, 1),
        detector=bw.HangDetector(not_responding_s=9999, silent_s=9999),
        health_interval_s=5.0,
        startup_grace_s=0.0,
        clock=lambda: clock["t"],
        backoff=(0.0,),
        restart_max=3,
        ask_user_watch=watch,
        send_enter=lambda pid: enters.append(pid) or True,
        sessions_root=sessions,
    )
    sup.proc = FakeProc()
    sup.sessions.append(sid)
    monkeypatch.setattr(sup, "restart_agent", lambda reason: restarts.append(reason))

    assert sup._check_ask_user_pending(sup.proc) is True
    assert enters == [4242]
    assert any("stuck: ask_user pending" in m and "sending Enter" in m for m in logs)
    assert restarts == []

    # Still pending during grace
    clock["t"] = 102.0
    assert sup._check_ask_user_pending(sup.proc) is False
    assert restarts == []

    # After grace → recycle
    clock["t"] = 106.0
    assert sup._check_ask_user_pending(sup.proc) is True
    assert restarts == ["ask-user-pending"]
    assert any("stuck: ask_user pending" in m and "recycling" in m for m in logs)
