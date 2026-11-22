"""FR #8969 / #8970: 0xffffffff with pager info or TUI chrome is an external kill."""
from __future__ import annotations

import bob_worker as bw

PAGER = (
    '{"ts":"2026-11-22T10:37:48.481Z","src":"grok-pager","lvl":"info",'
    '"msg":"turn.first_activity"}\n'
    '{"src":"grok-pager","lvl":"debug","msg":"turn.phase_transition"}'
)
TUI = "3m0s [stop]\nGrok 4.7 (low)  Shift+Tab:mode  Ctrl+c:cancel"


def _end(stderr: str, code: int = 0xFFFFFFFF) -> str:
    posts: list[dict] = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=code,
        raw_code=-1 if code == 0xFFFFFFFF else code,
        job_key="",
        machine="box",
        nick="box-1",
        kind="grok",
        agent_pid=50,
        stderr_tail=stderr,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    body = posts[0]["body"]
    return body.split("end=", 1)[1].split(" ", 1)[0]


def test_pager_info_is_external_kill():
    assert bw.unsigned_exit_stderr_is_noise(PAGER) is True
    assert _end(PAGER) == "external-kill"


def test_live_tui_is_external_kill():
    assert bw.unsigned_exit_stderr_is_noise(TUI) is True
    assert _end(TUI) == "external-kill"


def test_real_failure_stays_cli_failure():
    tail = "agent cli failed to start\n"
    assert bw.unsigned_exit_stderr_is_noise(tail) is False
    assert _end(tail) == "cli-failure"


def test_nonzero_with_pager_info_stays_cli_failure():
    assert _end(PAGER, code=1) == "cli-failure"
