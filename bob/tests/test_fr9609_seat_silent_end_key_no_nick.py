# -*- coding: utf-8 -*-
"""FR #9609: seat-silent-end / seat-no-progress keys are machine+end (nick in body only)."""
from __future__ import annotations

import bob_worker as bw


def test_fr9609_two_nicks_same_machine_external_kill_share_key():
    keys = []
    bodies = []

    def capture(p):
        keys.append(p["idempotency_key"])
        bodies.append(p["body"])
        assert p["dedupe_key"] == p["idempotency_key"]
        return {"ok": True}

    bw.report_agent_cli_nonzero_exit(
        exit_code=0xFFFFFFFF,
        job_key="MRB SimonBarnett/priority-mcp#803",
        machine="redqueen",
        nick="redqueen-668",
        kind="grok",
        agent_pid=9904,
        stderr_tail="",
        filer_post=capture,
    )
    bw.report_agent_cli_nonzero_exit(
        exit_code=0xFFFFFFFF,
        job_key="MRB SimonBarnett/priority-mcp#802",
        machine="redqueen",
        nick="redqueen-6564",
        kind="grok",
        agent_pid=3324,
        stderr_tail="",
        filer_post=capture,
    )
    assert len(keys) == 2
    assert keys[0] == keys[1] == "seat-silent-end|redqueen|external-kill"
    assert "nick=redqueen-668" in bodies[0]
    assert "nick=redqueen-6564" in bodies[1]
    assert "job=MRB SimonBarnett/priority-mcp#803" in bodies[0]
    assert "agent_pid=3324" in bodies[1]


def test_fr9609_console_close_key_omits_nick():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=3221225786,
        machine="redqueen",
        nick="redqueen-2528",
        kind="opencode",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert posts[0]["idempotency_key"] == "seat-silent-end|redqueen|console-close"
    assert "nick=redqueen-2528" in posts[0]["body"]


def test_fr9609_seat_no_progress_recycle_key_omits_nick():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        reason="hang",
        machine="flamingo",
        nick="flamingo-17160",
        kind="grok",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert posts[0]["idempotency_key"] == "seat-no-progress|flamingo|recycle"
    assert "nick=flamingo-17160" in posts[0]["body"]
