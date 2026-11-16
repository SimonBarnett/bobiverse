# -*- coding: utf-8 -*-
"""FR #7978: no-ack recycle of a live agent is not a progress-bug intake."""
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
