"""FR #8969: 0xffffffff plus grok-pager info/debug is an external kill, not a CLI crash."""
from __future__ import annotations

import bob_worker as bw

PAGER = (
    '{"ts": "2026-11-22T10:37:48.481Z", "src": "grok-pager", "lvl": "info", '
    '"msg": "turn.first_activity"}\n'
    '{"ts": "2026-11-22T10:37:48.684Z", "src": "grok-pager", "lvl": "debug", '
    '"msg": "turn.phase_transition"}\n'
)


def test_fr8969_pager_info_is_external_kill():
    posts = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        job_key="",
        machine="marchhare",
        nick="marchhare-23492",
        kind="grok",
        agent_pid=5040,
        stderr_tail=PAGER,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("skipped") is not True
    assert len(posts) == 1
    body = posts[0]["body"]
    assert "end=external-kill" in body
    assert "end=cli-failure" not in body
    assert "grok-pager" in body
    assert posts[0]["title"].startswith("bug: seat ended")
    assert "agent CLI nonzero exit" not in posts[0]["title"]


def test_fr8969_pager_error_still_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        machine="marchhare",
        kind="grok",
        stderr_tail='{"src": "grok-pager", "lvl": "error", "msg": "boom"}\n',
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    assert "end=cli-failure" in posts[0]["body"]
