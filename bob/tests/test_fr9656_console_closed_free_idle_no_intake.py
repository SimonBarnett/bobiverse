"""FR #9656: console-closed after free-idle GIVEUP must not file crash intake."""
from __future__ import annotations

import bob_worker as bw


def test_fr9656_console_closed_no_job_skips_intake():
    posts = []

    def filer(payload):
        posts.append(payload)
        return {"ok": True}

    out = bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        reason="console-closed",
        job_key="",
        machine="redqueen",
        nick="redqueen-10704",
        kind="grok",
        agent_pid=10704,
        filer_post=filer,
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "console-closed-free-idle"
    assert posts == []


def test_fr9656_console_closed_with_ack_job_still_files():
    posts = []

    def filer(payload):
        posts.append(payload)
        return {"ok": True}

    out = bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        reason="console-closed",
        job_key="FR SimonBarnett/bobiverse#9628",
        machine="redqueen",
        nick="redqueen-10704",
        kind="grok",
        agent_pid=10704,
        filer_post=filer,
    )
    assert not out.get("skipped")
    assert len(posts) == 1
    assert "console closed" in posts[0]["title"].lower() or "console-close" in posts[0]["body"]
    assert "end=console-close" in posts[0]["body"]


def test_fr9656_source_cites_rule():
    src = (bw.__file__ and open(bw.__file__, encoding="utf-8").read()) or ""
    assert "FR #9656" in src
    assert "console-closed-free-idle" in src
