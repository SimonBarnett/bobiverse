# -*- coding: utf-8 -*-
"""FR #7978: a no-ack recycle of a live agent is not a progress-bug intake, and a
still-running hang/ack-miss recycle is classified as a recycle (not a CLI failure)."""
from __future__ import annotations

import bob_worker as bw


def test_fr7978_no_ack_while_running_does_not_file():
    posts = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        raw_code=None,
        reason="no-ack-after-assign",
        job_key="",
        machine="flamingo",
        nick="flamingo-18988",
        kind="opencode",
        agent_pid=14736,
        stderr_tail="Immediately append DONE for FR SimonBarnett/bobiverse#7965",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "no-ack-still-running"
    assert posts == []


def test_fr7978_real_nonzero_still_files():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        reason="no-ack-after-assign",
        machine="flamingo",
        nick="flamingo-18988",
        kind="opencode",
        stderr_tail="boom",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    assert "boom" in posts[0]["body"]


def test_fr7978_still_running_hang_is_recycle_not_cli_failure():
    """A hang recycle (reason != no-ack-after-assign) while the process is still
    running is a recycle, not a CLI failure, and the job is not dropped from the body."""
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        raw_code=None,
        job_key="FR owner/repo#7965",
        machine="box",
        nick="box-1",
        kind="opencode",
        agent_pid=14736,
        stderr_tail="do not PASS 6) Immediately append DONE for FR #7965",
        reason="not-responding",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    body = posts[0]["body"]
    assert posts[0]["title"] == "bug: seat stopped making progress"
    assert "end=recycle" in body
    assert "end=cli-failure" not in body
    assert "process still running" in body
    assert "Reason: not-responding" in body
    assert "FR owner/repo#7965" in body
    assert "job=(none)" not in body
    assert "accepted jobs are GIVEUP'd" in body


def test_fr7978_restart_agent_carries_pending_assign_job(monkeypatch, tmp_path):
    logs: list[str] = []
    posts: list[dict] = []

    class FakeProc:
        pid = 7001

        def poll(self):
            return None

        def stderr_tail(self):
            return ""

    class FakeRelay:
        last_unacked = "FROM Jeeves #box box-1: FR owner/repo#7965 https://example/7965"
        on_inject = None

        def set_target(self, _t):
            pass

        def hold(self, _line):
            pass

        def release_held_assigns(self):
            return 0

        def close(self):
            pass

    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    monkeypatch.setattr(
        bw,
        "report_agent_cli_nonzero_exit",
        lambda **kw: posts.append(kw) or {"ok": True},
    )

    bored = bw.BoredEmitter(lambda: True, logs.append, harvest_hold_s=0.0)
    sup = bw.Supervisor(
        kind="opencode",
        exe="x",
        cwd=str(tmp_path),
        machine="box",
        nick="box-1",
        run_dir=tmp_path,
        irc=None,
        relay=FakeRelay(),
        log=logs.append,
        bored=bored,
        kill=lambda pid: True,
        spawn=lambda spec, env: FakeProc(),
        backoff=(0.0,),
        restart_max=3,
        restart_window_s=1800.0,
    )
    sup.proc = FakeProc()
    sup.start_agent = lambda note="": True  # type: ignore[method-assign]
    sup.restart_agent("no-ack-after-assign")

    assert len(posts) == 1
    assert posts[0]["reason"] == "no-ack-after-assign"
    assert posts[0]["exit_code"] is None
    assert posts[0]["job_key"] == "FR owner/repo#7965"
