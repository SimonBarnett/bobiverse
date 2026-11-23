"""FR #9013: OpenCode unsigned exit with stdout OSError 22 is external-kill."""
from __future__ import annotations

import bob_worker as bw

NOISE = (
    "Exception ignored in: <_io.TextIOWrapper name='<stdout>' mode='w' encoding='cp1252'>\n"
    "OSError: [Errno 22] Invalid argument\n"
)


def test_fr9013_oserror22_is_external_kill():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        job_key="",
        machine="redqueen",
        nick="redqueen-4120",
        kind="opencode",
        agent_pid=7584,
        stderr_tail=NOISE,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    body = posts[0]["body"]
    assert "end=external-kill" in body
    assert "end=cli-failure" not in body
    assert posts[0]["title"].startswith("bug: seat ended")
    assert "FR #9013" in body


def test_fr9013_oserror22_plus_traceback_stays_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        machine="redqueen",
        kind="opencode",
        stderr_tail=NOISE + "Traceback (most recent call last):\n",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "end=cli-failure" in posts[0]["body"]


def test_fr9013_exit_one_oserror22_stays_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        machine="redqueen",
        kind="opencode",
        stderr_tail=NOISE,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "end=cli-failure" in posts[0]["body"]
