"""FR #9025: fuel-exhausted recycle while process running skips progress intake."""
from __future__ import annotations

import bob_worker as bw


def test_fr9025_fuel_exhausted_recycle_skips_intake():
    posts = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        job_key="",
        machine="marchhare",
        nick="marchhare-11692",
        kind="grok",
        agent_pid=55,
        reason="fuel-exhausted",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "fuel-exhausted-recycle"
    assert posts == []


def test_fr9025_fuel_exhausted_opencode_free_prefix_skips():
    posts = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        machine="redqueen",
        kind="opencode",
        reason="fuel-exhausted:opencode-free",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("skipped") is True
    assert posts == []


def test_fr9025_hang_recycle_still_files():
    # Generic hang reasons still file; OpenCode freeze reasons are skipped by FR #9279.
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        machine="marchhare",
        kind="grok",
        reason="not-responding",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    assert "stopped making progress" in posts[0]["title"]
    assert "Reason: not-responding" in posts[0]["body"]
