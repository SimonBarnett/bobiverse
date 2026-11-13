"""FR #7123: watchers follow per-worker GROK_HOME, not stale ~/.grok unified.jsonl."""
from __future__ import annotations

import json
import time
from pathlib import Path

import bob_worker as bw


def test_fr7123_agent_grok_home_prefers_run_dir_over_user(tmp_path, monkeypatch):
    run = tmp_path / "run"
    seat = run / "grok-home"
    seat.mkdir(parents=True)
    user = tmp_path / "user-grok"
    user.mkdir()
    monkeypatch.setenv("GROK_HOME", str(user))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "not-used"))
    got = bw.agent_grok_home(run_dir=run)
    assert got == seat
    assert bw.default_unified_log_path(run_dir=run) == seat / "logs" / "unified.jsonl"
    assert bw.grok_sessions_root(run_dir=run) == seat / "sessions"


def test_fr7123_stale_global_unified_ignored(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "grok-home" / "logs").mkdir(parents=True)
    seat_log = run / "grok-home" / "logs" / "unified.jsonl"
    global_log = tmp_path / "user" / ".grok" / "logs" / "unified.jsonl"
    global_log.parent.mkdir(parents=True)
    global_log.write_text('{"msg":"prompt.enqueue","pid":1}\n', encoding="utf-8")
    monkeypatch.setenv("GROK_HOME", str(tmp_path / "user" / ".grok"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "user"))
    path = bw.default_unified_log_path(run_dir=run)
    assert path == seat_log
    assert path != global_log
    assert not path.is_file()


def test_fr7123_session_dir_finds_uuid_under_seat_home(tmp_path):
    run = tmp_path / "run"
    sid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    d = run / "grok-home" / "sessions" / "quoted-bound-cwd" / sid
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text(
        json.dumps({"type": "turn_ended", "ts": "2026-11-13T17:12:00Z", "turn_number": 0}) + "\n",
        encoding="utf-8",
    )
    found = bw.grok_session_dir(str(tmp_path / "install-cwd"), sid, run_dir=run)
    assert found == d


def test_fr7123_turn_ended_from_seat_events(tmp_path):
    run = tmp_path / "run"
    sid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    d = run / "grok-home" / "sessions" / "x" / sid
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text(
        '{"type":"turn_ended","ts":"2026-11-13T17:20:00Z","turn_number":0}\n',
        encoding="utf-8",
    )
    sdir = bw.grok_session_dir("cwd", sid, run_dir=run)
    assert bw.probe_grok_session_submit(sdir, since_wall=0) is False  # turn_started only
    # activity helper sees turn_ended
    assert bw.grok_log_has_turn_activity(sdir / "events.jsonl", since_wall=0) is True


def test_fr7123_hang_recycle_skipped_when_ack_or_activity(tmp_path):
    log = tmp_path / "unified.jsonl"
    log.write_text('{"type":"turn_started","ts":"2026-11-13T17:20:00Z"}\n', encoding="utf-8")
    assert (
        bw.should_startup_hang_recycle(ack_open=True, activity_paths=[], since_wall=0) is False
    )
    assert (
        bw.should_startup_hang_recycle(ack_open=False, activity_paths=[log], since_wall=0)
        is False
    )
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert (
        bw.should_startup_hang_recycle(ack_open=False, activity_paths=[empty], since_wall=time.time())
        is True
    )


def test_fr7123_mid_job_giveup_line():
    assert bw.seat_release_giveup_line("FR owner/repo#1", "hang-recycle") == (
        "GIVEUP FR owner/repo#1 hang-recycle"
    )
