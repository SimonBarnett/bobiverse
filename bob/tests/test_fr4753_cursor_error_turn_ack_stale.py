"""FR #4753: cursor turn_ended status=error arms done-miss; ack_stale releases stuck ACK."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import bob_worker as bw
from test_cursor_turn_watcher import _arm_transcript, _chat, _touch, _user_line
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def _turn_ended_error_line(msg: str = "Connection stalled repeatedly") -> str:
    return json.dumps({"type": "turn_ended", "status": "error", "error": msg})


def test_cursor_turn_ended_status_error_arms_done_miss(tmp_path: Path):
    """Fail-when 1: ACK open + transcript turn_ended status=error → done-miss armed."""
    clock = FakeClock(time.time())
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=5.0, ack_stale_s=2700.0)
    reminds: list[str] = []
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#4746")

    t0 = clock()
    d = _chat(tmp_path, born=t0)
    projects = tmp_path / "projects"
    path = _arm_transcript(d, projects, [_user_line("FROM Jeeves")])
    os.utime(path, (t0, t0))
    w = bw.CursorTurnWatcher(
        since_wall=t0 - 1,
        chats_root=tmp_path,
        projects_root=projects,
        quiet_s=20.0,
        clock=clock,
        on_turn_started=lambda n, t: e.turn_started(at=t, turn=n),
        on_turn_ended=lambda n, t: e.turn_ended(at=t, turn=n),
    )
    assert w.tick() == "started"

    # Agent stalled: user inject still newest role-line, then turn_ended error.
    path.write_text(
        _user_line("FROM Jeeves") + "\n" + _turn_ended_error_line() + "\n",
        encoding="utf-8",
    )
    clock.advance(1.0)
    os.utime(path, (clock(), clock()))
    _touch(d, clock())
    assert w.tick() == "ended", "error turn_ended must end the cursor turn"
    assert any("done-miss armed" in m for m in logs), logs
    assert e.ack_open is True
    clock.advance(6.0)
    assert _wait(lambda: len(reminds) == 1, clock), reminds
    e.turn_ended(at=clock())  # second end after reminder → release
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent), clock), e.sent
    e.stop()


def test_ack_stale_releases_with_one_bored_despite_open_turn_gen():
    """Open turn holds past ack_stale_s (FR #4827). With the turn closed, one ack-stale."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(
        clock,
        harvest_hold_s=90.0,
        idle_s=1.0,
        repeat_s=9999.0,
        ack_stale_s=30.0,
        done_miss_grace_s=20.0,
    )
    e.on_outbox("ACK MRB o/r#1")
    e.turn_ended(at=clock())
    clock.advance(1.0)
    e.turn_started(at=clock())
    n0 = len(sent)
    clock.advance(35.0)
    time.sleep(0.05)
    assert not any(r == "ack-stale" for _, r in e.sent[n0:]), e.sent[n0:]
    assert e.ack_open is True
    e.stop()

    clock2 = FakeClock(0.0)
    e2, sent2, logs2 = _emitter(
        clock2,
        harvest_hold_s=90.0,
        idle_s=1.0,
        repeat_s=9999.0,
        ack_stale_s=30.0,
        done_miss_grace_s=20.0,
    )
    e2.on_outbox("ACK MRB o/r#1")
    n1 = len(sent2)
    clock2.advance(31.0)
    assert _wait(lambda: any(r == "ack-stale" for _, r in e2.sent[n1:]), clock2), (
        e2.sent[n1:],
        logs2,
    )
    assert sum(1 for _, r in e2.sent[n1:] if r == "ack-stale") == 1
    assert e2.ack_open is False
    assert any("ACK stale" in m and "ack-stale" in m for m in logs2), logs2
    e2.stop()


def test_giveup_then_replayed_ack_does_not_reopen_busy():
    """Fail-when 3: GIVEUP K then replayed ACK K must not reopen busy hold."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=5.0, ack_stale_s=2700.0)
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#4746")
    e.on_outbox("GIVEUP MRB SimonBarnett/bobiverse#4746 submit-verify failed")
    assert e.ack_open is False
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#4746")
    assert e.ack_open is False, "stale ACK after GIVEUP must not reopen"
    assert any("ignore stale ACK" in m for m in logs), logs
    assert e.should_forward_outbox("ACK MRB SimonBarnett/bobiverse#4746") is False
    e.stop()


def test_cursor_transcript_still_open_false_after_turn_ended_error(tmp_path: Path):
    tp = tmp_path / "t.jsonl"
    tp.write_text(
        json.dumps({"role": "user", "message": {"content": [{"type": "text", "text": "x"}]}})
        + "\n"
        + json.dumps({"type": "turn_ended", "status": "error", "error": "Connection stalled"})
        + "\n",
        encoding="utf-8",
    )
    assert bw.cursor_transcript_still_open(tp) is False
    te = bw.cursor_transcript_last_turn_ended(tp)
    assert te is not None and te.get("status") == "error"
