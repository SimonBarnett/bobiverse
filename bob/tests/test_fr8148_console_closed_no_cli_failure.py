# -*- coding: utf-8 -*-
"""FR #8148: console-closed shutdown must not also file cli-failure for exit_code=1."""
from __future__ import annotations

import bob_worker as bw


def test_fr8148_report_reason_console_closed_is_console_close_not_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        reason="console-closed",
        machine="flamingo",
        nick="flamingo-18800",
        kind="grok",
        agent_pid=17068,
        stderr_tail="",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    assert posts[0]["title"].startswith("bug: agent console closed")
    assert "end=console-close" in posts[0]["body"]
    assert "Reason: console-closed" in posts[0]["body"]
    assert "agent CLI nonzero exit" not in posts[0]["title"]
    assert "stopped making progress" not in posts[0]["title"]


def test_fr8148_wait_exit_skips_report_when_shutdown_already_recorded(monkeypatch, tmp_path):
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
    proc = FakeProc()
    sup.proc = proc
    # Simulate CTRL/console handler winning the race: shutdown records first.
    assert sup._record_exit(proc, "console-closed", 1, report=False) is True
    assert (sup.last_exit or {}).get("reason") == "console-closed"

    # Wait thread still sees unexpected exit (expected set only inside shutdown()).
    # Without FR #8148 it would file cli-failure after the no-op _record_exit.
    sup._wait_exit(proc)

    assert posts == [], f"must not report after console-closed record; got {posts!r}"
    assert any("skip cli-failure report (FR #8148)" in line for line in logs)
    assert (sup.last_exit or {}).get("reason") == "console-closed"


def test_fr8148_record_exit_returns_false_on_second_call(tmp_path):
    class FakeProc:
        pid = 42

        def stderr_tail(self):
            return ""

    class FakeRelay:
        def close(self):
            pass

    class FakeIrc:
        shop = "#t"
        alive = True

        def close(self, *a, **k):
            pass

    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=str(tmp_path),
        machine="t",
        nick="t-1",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=lambda *_a, **_k: None,
        startup_grace_s=0.0,
        backoff=(0.0,),
        kill=lambda pid: True,
        spawn=lambda spec, env: FakeProc(),
    )
    proc = FakeProc()
    assert sup._record_exit(proc, "console-closed", 1) is True
    assert sup._record_exit(proc, "agent-cli-nonzero-exit", 1) is False
