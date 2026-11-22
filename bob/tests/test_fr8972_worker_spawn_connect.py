"""FR #8972: grok worker_spawn connect does not open a CLI-failure intake issue."""
from __future__ import annotations

import bob_worker as bw

SPAWN = (
    '"resolve_config_ms": 4, "error_kind": "connect", '
    '"failed_phase": "worker_spawn", "previous_exit": "clean"'
)


def test_spawn_connect_signature():
    assert bw.grok_worker_spawn_connect_failure(SPAWN) is True
    assert bw.grok_worker_spawn_connect_failure("error_kind connect only") is False
    assert bw.grok_worker_spawn_connect_failure("agent cli failed to start") is False


def test_spawn_connect_skips_intake():
    posts: list[dict] = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        job_key="FR owner/repo#8734",
        machine="box",
        nick="box-1",
        kind="grok",
        agent_pid=5328,
        stderr_tail=SPAWN,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "grok-worker-spawn-connect"
    assert posts == []


def test_other_exit_one_still_files():
    posts: list[dict] = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        job_key="FR owner/repo#1",
        machine="box",
        nick="box-1",
        kind="grok",
        agent_pid=11,
        stderr_tail="agent cli failed to start\n",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    assert "cli-failure" in posts[0]["body"]
