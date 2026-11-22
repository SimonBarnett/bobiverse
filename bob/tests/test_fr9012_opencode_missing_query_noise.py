"""FR #9012: OpenCode unsigned exit with missing-query console noise is external-kill."""
from __future__ import annotations

import bob_worker as bw

NOISE = (
    "console: ?? .bobiverse-seat\n"
    "console: ?? opencode.json\n"
    "console: ---outbox---\n"
    "console: ---pr---\n"
    'console: missing query (try ".")\n'
)


def test_fr9012_missing_query_is_external_kill():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        job_key="",
        machine="redqueen",
        nick="redqueen-13608",
        kind="opencode",
        agent_pid=2280,
        stderr_tail=NOISE,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    body = posts[0]["body"]
    assert "end=external-kill" in body
    assert "end=cli-failure" not in body
    assert posts[0]["title"].startswith("bug: seat ended")
    assert "FR #9012" in body


def test_fr9012_missing_query_plus_traceback_stays_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        machine="redqueen",
        kind="opencode",
        stderr_tail=NOISE + "Traceback (most recent call last):\n",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "end=cli-failure" in posts[0]["body"]


def test_fr9012_exit_one_missing_query_stays_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        machine="redqueen",
        kind="opencode",
        stderr_tail=NOISE,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "end=cli-failure" in posts[0]["body"]
