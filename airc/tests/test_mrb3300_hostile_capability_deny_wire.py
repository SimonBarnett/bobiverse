"""MRB #3300 hostile: capability_deny must be wired to PRIVMSG (DONE exit=126)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import airc_console as ac
from repo_layout import ROOT

SVC = ROOT / "airc" / "scripts" / "airc_console_service.py"


def test_service_dispatches_capability_deny_to_privmsg():
    text = SVC.read_text(encoding="utf-8")
    assert 'hr.action == "capability_deny"' in text
    assert "send_privmsg(hr.nick, hr.reply)" in text
    # capability_deny block must sit near deny handling (not dead code later).
    deny_at = text.find('hr.action == "deny"')
    cap_at = text.find('hr.action == "capability_deny"')
    assert deny_at > 0 and cap_at > deny_at
    assert "INFO capability-deny" in text


def test_shell_off_stranger_still_auth_denied_not_capability():
    """Auth gate runs before capability; strangers never see shell-disabled."""
    runner = MagicMock()
    auth = ac.AuthPolicy(operators={"op"}, machine="tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        shell_runner=runner,
        capabilities=ac.ConsoleCapabilities(shell_mode="off"),
    )
    hr = core.handle_raw(":evil!u@h PRIVMSG tm_console :Write-Output 1")
    assert hr is not None
    assert hr.action == "deny"
    assert "authenticate" in (hr.reply or "").lower()
    runner.start.assert_not_called()


def test_jobs_off_allows_status_only():
    job = MagicMock()
    auth = ac.AuthPolicy(operators={"op"}, machine="tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        job_protocol=job,
        capabilities=ac.ConsoleCapabilities(shell_mode="operators", jobs="off"),
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :STATUS")
    assert hr is not None and hr.action == "job"
    job.handle_async.assert_called_once()
    hr2 = core.handle_raw(":op!u@h PRIVMSG tm_console :RUN cmd=x")
    assert hr2 is not None and hr2.action == "capability_deny"
    assert "jobs-disabled" in (hr2.reply or "")
