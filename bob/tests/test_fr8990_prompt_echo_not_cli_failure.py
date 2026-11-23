"""FR #8990: exit 0xffffffff plus the seat prompt on stderr is an external kill."""
from __future__ import annotations

import bob_worker as bw

PROMPT = (
    "ons inside this job worktree or the worker run folder --- never under %TEMP%. "
    "Use .bob\\tmp (TEMP/TMP already point there). "
    "The turn is not over until DONE is written. Do not check the outbox first.\n"
)


def test_fr8990_prompt_echo_is_external_kill():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        job_key="FR SimonBarnett/bobiverse#8798",
        machine="redqueen",
        nick="redqueen-12012",
        kind="opencode",
        agent_pid=1820,
        stderr_tail=PROMPT,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    body = posts[0]["body"]
    assert "end=external-kill" in body
    assert "end=cli-failure" not in body
    assert posts[0]["title"].startswith("bug: seat ended")
    assert "FR #8990" in body


def test_fr8990_prompt_plus_traceback_stays_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        machine="redqueen",
        kind="opencode",
        stderr_tail=PROMPT + "Traceback (most recent call last):\n",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "end=cli-failure" in posts[0]["body"]


def test_fr8990_exit_one_prompt_stays_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        machine="redqueen",
        kind="opencode",
        stderr_tail=PROMPT,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "end=cli-failure" in posts[0]["body"]
