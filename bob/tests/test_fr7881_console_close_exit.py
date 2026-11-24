# -*- coding: utf-8 -*-
"""FR #7881: 3221225786 is a closed console, not an agent CLI crash."""
from __future__ import annotations

import bob_worker as bw


def test_fr7881_control_c_exit_is_console_close_not_cli_bug():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=3221225786,
        # FR #9656: empty job_key skips free-idle console-close intake; ACK-open still files.
        job_key="FR SimonBarnett/bobiverse#7881",
        machine="redqueen",
        nick="redqueen-2528",
        kind="opencode",
        agent_pid=4120,
        stderr_tail="",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    body = posts[0]["body"]
    assert posts[0]["title"].startswith("bug: agent console closed")
    assert "end=console-close" in body
    assert "0xc000013a" in body
    assert "nick=redqueen-2528" in body
    assert "kind=opencode" in body
    assert "agent CLI nonzero exit" not in posts[0]["title"]
    assert "GIVEUP" in body


def test_fr7881_signed_control_c_matches():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=-1073741510,
        job_key="FR SimonBarnett/bobiverse#7881",
        machine="redqueen",
        nick="redqueen-2528",
        kind="opencode",
        stderr_tail="some line",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "end=console-close" in posts[0]["body"]
    assert "some line" in posts[0]["body"]


def test_fr7881_ordinary_nonzero_stays_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        machine="redqueen",
        nick="redqueen-2528",
        kind="opencode",
        stderr_tail="boom",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert posts[0]["title"].startswith("bug: agent CLI nonzero exit")
    assert "end=cli-failure" in posts[0]["body"]


def test_fr8148_signal_reason_is_console_close():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        reason="signal",
        job_key="FR SimonBarnett/bobiverse#8148",
        machine="flamingo",
        nick="flamingo-1",
        kind="grok",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert posts[0]["title"].startswith("bug: agent console closed")
    assert "end=console-close" in posts[0]["body"]
