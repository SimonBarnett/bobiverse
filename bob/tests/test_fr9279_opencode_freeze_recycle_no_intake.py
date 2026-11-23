# -*- coding: utf-8 -*-
"""FR #9279: OpenCode freeze recycles while process running skip progress intake."""
from __future__ import annotations

import bob_worker as bw


def test_fr9279_lost_ack_stale_recycle_skips_intake():
    """redqueen-6148: after external-dir-loop GIVEUP, lost-ack-stale recycle must not file."""
    posts = []
    logs = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        job_key="MRB SimonBarnett/bobiverse#9093",
        machine="redqueen",
        nick="redqueen-6148",
        kind="opencode",
        agent_pid=14008,
        reason="opencode-lost-ack-stale",
        stderr_tail=(
            "failed-turn: external-directory: exit 0: external_directory auto-reject\n"
            "giveup: external-dir-loop"
        ),
        filer_post=lambda p: posts.append(p) or {"ok": True},
        log=logs.append,
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "opencode-freeze-recycle"
    assert posts == []
    assert any("FR #9279" in m and "opencode-lost-ack-stale" in m for m in logs)


def test_fr9279_frozen_progress_recycle_skips_intake():
    posts = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        machine="redqueen",
        kind="opencode",
        reason="opencode-frozen-progress",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "opencode-freeze-recycle"
    assert posts == []


def test_fr9279_other_hang_reason_still_files():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        machine="redqueen",
        kind="opencode",
        reason="not-responding",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    assert posts[0]["title"] == "bug: seat stopped making progress"
    assert "Reason: not-responding" in posts[0]["body"]


def test_fr9279_lost_ack_with_real_exit_still_files():
    """Skip only applies while process still running (exit_code is None)."""
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        machine="redqueen",
        kind="opencode",
        reason="opencode-lost-ack-stale",
        stderr_tail="boom",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    assert "boom" in posts[0]["body"]
