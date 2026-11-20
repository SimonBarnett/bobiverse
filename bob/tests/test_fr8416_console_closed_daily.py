"""FR #8416: child console-close GIVEUPs an ACKed job and counts the day."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import bob_worker as bw


def test_note_console_closed_exit_counts_utc_days(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_BRIDGE_HOME", str(tmp_path / "bridge"))
    when = bw._dt.datetime(2026, 11, 19, 3, 59, 58, tzinfo=bw._dt.timezone.utc)
    one = bw.note_console_closed_exit("RedQueen", when=when)
    two = bw.note_console_closed_exit("RedQueen", when=when)
    assert one["days"]["2026-11-19"] == 1
    assert two["days"]["2026-11-19"] == 2
    raw = bw.console_closed_daily_path("redqueen").read_text(encoding="utf-8")
    assert "token" not in raw.lower()
    assert "GIVEUP" not in raw
    assert json.loads(raw)["machine"] == "redqueen"


def test_wait_exit_console_close_giveup_when_acked(tmp_path, monkeypatch):
    said: list[str] = []

    class FakeProc:
        pid = 8028

        def wait(self):
            return bw.CONSOLE_CLOSE_EXIT

        def poll(self):
            return bw.CONSOLE_CLOSE_EXIT

        def stderr_tail(self):
            return ""

    class FakeIrc:
        shop = "#redqueen"
        alive = True

        def say(self, _target, text):
            said.append(text)
            return True

        def close(self, *_a, **_k):
            pass

    class FakeRelay:
        last_unacked = ""

        def close(self):
            pass

    monkeypatch.setenv("BOB_BRIDGE_HOME", str(tmp_path / "bridge"))
    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    monkeypatch.setattr(bw, "report_agent_cli_nonzero_exit", lambda **kw: {"ok": True})
    monkeypatch.setattr(bw, "resolve_console_closed_worktree", lambda key: None)

    sup = bw.Supervisor(
        kind="opencode",
        exe="x",
        cwd=str(tmp_path),
        machine="redqueen",
        nick="redqueen-1",
        run_dir=tmp_path / "run",
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=lambda _m: None,
        startup_grace_s=0.0,
        backoff=(0.0,),
        kill=lambda pid: True,
        spawn=lambda spec, env: FakeProc(),
    )
    bored = bw.BoredEmitter(lambda: True, lambda _m: None)
    bored.run_dir = tmp_path / "run"
    bored._ack_open = True
    bored._ack_job_key = "FR SimonBarnett/bobiverse#8416"
    bored._cv = threading.Condition()
    sup.bored = bored
    proc = FakeProc()
    sup.proc = proc
    bw.Supervisor._wait_exit(sup, proc)
    assert (sup.last_exit or {}).get("reason") == "console-closed"
    assert any(line.startswith("GIVEUP ") and "console-closed" in line for line in said)
    assert bored._ack_open is False
    doc = json.loads(bw.console_closed_daily_path("redqueen").read_text(encoding="utf-8"))
    assert sum(doc["days"].values()) == 1
