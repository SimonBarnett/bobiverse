"""FR #7681: Windows 0xffffffff with empty stderr is an external kill, not an intake."""
from __future__ import annotations

import bob_worker as bw


def test_fr7681_ffffffff_without_stderr_does_not_file():
    posts = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=0xFFFFFFFF,
        raw_code=-1,
        job_key="MRB SimonBarnett/bobiverse#7678",
        machine="marchhare",
        nick="marchhare-24160",
        kind="grok",
        agent_pid=31488,
        stderr_tail="",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "external-kill"
    assert posts == []


def test_fr7681_exit_one_without_stderr_still_files():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        job_key="FR owner/repo#1",
        machine="box",
        stderr_tail="",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1


def test_fr7681_mrb_ffffffff_with_stderr_still_files():
    """Hostile: external-kill skip only when stderr evidence is empty."""
    posts = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=-1,
        raw_code=-1,
        job_key="FR owner/repo#9",
        machine="box",
        stderr_tail="failed to start the acp-agent-worker runtime\n",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("skipped") is not True
    assert len(posts) == 1
    assert "acp-agent-worker" in posts[0]["body"]


def test_fr7681_mrb_signed_minus_one_empty_is_external_kill():
    """Hostile: signed -1 masks to 0xffffffff and skips when stderr empty."""
    posts = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=-1,
        job_key="MRB owner/repo#1",
        machine="box",
        stderr_tail="   \n",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("reason") == "external-kill"
    assert posts == []

