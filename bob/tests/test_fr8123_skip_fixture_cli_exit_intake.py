"""FR #8123: do not file live intake for unit-test seat fingerprints / BOB_INTAKE_DISABLE."""
from __future__ import annotations

import bob_worker as bw


def test_fr8123_unit_test_seat_fingerprint_skips_intake(monkeypatch):
    # Offline repros have no PYTEST_CURRENT_TEST — that is how #8123 was filed.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("BOB_INTAKE_DISABLE", raising=False)
    monkeypatch.delenv("BOBIVERSE_NO_INTAKE", raising=False)
    posts: list[dict] = []

    out = bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        machine="marchhare",
        nick="marchhare-42052",
        kind="grok",
        agent_pid=9001,
        stderr_tail="Never request external_directory and never PASS",
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "unit-test-seat"
    assert posts == []


def test_fr8123_intake_disable_env(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("BOB_INTAKE_DISABLE", "1")
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        machine="livebox",
        nick="livebox-1",
        agent_pid=4242,
        stderr_tail="real failure",
    )
    assert out.get("skipped") is True


def test_fr8123_live_seat_still_files_with_filer():
    posts: list[dict] = []
    out = bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        machine="livebox",
        nick="livebox-99",
        kind="grok",
        agent_pid=4242,
        stderr_tail="agent crashed",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("ok") is True
    assert len(posts) == 1
    assert "agent CLI nonzero exit" in posts[0]["title"]
