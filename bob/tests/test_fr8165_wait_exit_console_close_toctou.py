# -*- coding: utf-8 -*-
"""FR #8165: when _wait_exit wins _record_exit before console-closed shutdown, do not file cli-failure."""
from __future__ import annotations

import bob_worker as bw


def test_fr8165_wait_won_record_then_shutting_reconciles(monkeypatch, tmp_path):
    """Inverse of FR #8148: wait recorded agent-cli-nonzero; then console shutdown."""
    posts: list[dict] = []
    logs: list[str] = []

    class FakeProc:
        pid = 17068

        def wait(self):
            return 1

        def poll(self):
            return 1

        def stderr_tail(self):
            return ""

    class FakeRelay:
        last_unacked = ""

        def close(self):
            pass

    class FakeIrc:
        shop = "#flamingo"
        alive = True

        def close(self, *a, **k):
            pass

        def say(self, *a, **k):
            return True

    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    monkeypatch.setattr(
        bw,
        "report_agent_cli_nonzero_exit",
        lambda **kw: posts.append(kw) or {"ok": True},
    )

    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=str(tmp_path),
        machine="flamingo",
        nick="flamingo-18800",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=logs.append,
        startup_grace_s=0.0,
        backoff=(0.0,),
        kill=lambda pid: True,
        spawn=lambda spec, env: FakeProc(),
    )
    monkeypatch.setattr(sup, "_giveup_on_console_closed_shutdown", lambda reason: None)
    restarts: list[str] = []
    monkeypatch.setattr(sup, "restart_agent", lambda reason: restarts.append(reason))

    proc = FakeProc()
    sup.proc = proc
    # Wait thread wins the record.
    assert sup._record_exit(proc, "agent-cli-nonzero-exit", 1) is True
    assert (sup.last_exit or {}).get("reason") == "agent-cli-nonzero-exit"
    # Ctrl handler then starts shutdown (record no-ops).
    bw.Supervisor.shutdown(sup, "console-closed", bw.EXIT_OK)
    assert (sup.last_exit or {}).get("reason") == "agent-cli-nonzero-exit"  # not yet reconciled
    # Wait thread continues past record=True and reconciles.
    assert (
        bw.Supervisor._reconcile_wait_exit_with_shutdown(
            sup, proc, 1, kill_line="kill=test"
        )
        is True
    )
    assert (sup.last_exit or {}).get("reason") == "console-closed"
    assert posts == []
    assert restarts == []
    assert any("8165" in line for line in logs)


def test_fr8165_console_close_exit_code_records_console_closed(monkeypatch, tmp_path):
    posts: list[dict] = []
    logs: list[str] = []
    restarts: list[str] = []

    class FakeProc:
        pid = 99

        def wait(self):
            return bw.CONSOLE_CLOSE_EXIT

        def poll(self):
            return bw.CONSOLE_CLOSE_EXIT

        def stderr_tail(self):
            return ""

    class FakeRelay:
        last_unacked = ""

        def close(self):
            pass

    class FakeIrc:
        shop = "#t"
        alive = True

        def close(self, *a, **k):
            pass

        def say(self, *a, **k):
            return True

    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    monkeypatch.setattr(
        bw,
        "report_agent_cli_nonzero_exit",
        lambda **kw: posts.append(kw) or {"ok": True},
    )

    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=str(tmp_path),
        machine="t",
        nick="t-1",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=logs.append,
        startup_grace_s=0.0,
        backoff=(0.0,),
        kill=lambda pid: True,
        spawn=lambda spec, env: FakeProc(),
    )
    monkeypatch.setattr(sup, "restart_agent", lambda reason: restarts.append(reason))
    proc = FakeProc()
    sup.proc = proc
    bw.Supervisor._wait_exit(sup, proc)
    assert (sup.last_exit or {}).get("reason") == "console-closed"
    assert posts == []
    assert restarts == []


def test_fr8165_full_wait_exit_skips_report_when_shutting_after_record(
    monkeypatch, tmp_path
):
    """End-to-end: after wait records nonzero, mark shutting before report path."""
    posts: list[dict] = []
    logs: list[str] = []
    restarts: list[str] = []

    class FakeProc:
        pid = 55

        def wait(self):
            return 1

        def poll(self):
            return 1

        def stderr_tail(self):
            return ""

    class FakeRelay:
        last_unacked = ""

        def close(self):
            pass

    class FakeIrc:
        shop = "#t"
        alive = True

        def close(self, *a, **k):
            pass

        def say(self, *a, **k):
            return True

    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    monkeypatch.setattr(
        bw,
        "report_agent_cli_nonzero_exit",
        lambda **kw: posts.append(kw) or {"ok": True},
    )

    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=str(tmp_path),
        machine="t",
        nick="t-1",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=logs.append,
        startup_grace_s=0.0,
        backoff=(0.0,),
        kill=lambda pid: True,
        spawn=lambda spec, env: FakeProc(),
    )
    monkeypatch.setattr(sup, "restart_agent", lambda reason: restarts.append(reason))
    monkeypatch.setattr(sup, "_giveup_on_console_closed_shutdown", lambda reason: None)

    proc = FakeProc()
    sup.proc = proc
    real_record = sup._record_exit

    def record_then_mark_shutting(p, reason, code=None, *, report=False, job_key=""):
        out = real_record(p, reason, code, report=report, job_key=job_key)
        # Simulate Ctrl handler setting shutdown immediately after wait won the record.
        if out and reason == "agent-cli-nonzero-exit":
            with sup._lock:
                sup._shutting = True
                sup._shutdown_reason = "console-closed"
                if p is not None:
                    sup._expected_exit.add(p.pid)
        return out

    monkeypatch.setattr(sup, "_record_exit", record_then_mark_shutting)
    bw.Supervisor._wait_exit(sup, proc)
    assert posts == []
    assert restarts == []
    assert (sup.last_exit or {}).get("reason") == "console-closed"