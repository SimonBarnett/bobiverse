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
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=None,
        machine="marchhare",
        kind="grok",
        reason="opencode-frozen-progress",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    assert "stopped making progress" in posts[0]["title"]
    assert "fuel-exhausted" not in posts[0]["body"] or "Reason: opencode-frozen-progress" in posts[0]["body"]
