"""FR #3287: airc capability gates (shell/jobs/update) + MSI/install persistence."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import airc_console as ac
from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL_AIRC = ROOT / "airc/scripts/Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "airc/scripts/Install-AircConsole.ps1"
START = ROOT / "airc/scripts/Start-AircConsole.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
POST = ROOT / "common/docs/post-install.md"
SVC = ROOT / "airc/scripts/airc_console_service.py"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def _core(*, shell_mode="operators", jobs="on", update="on", runner=None, job_protocol=None):
    auth = ac.AuthPolicy(operators={"op"}, machine="tm")
    return ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        shell_runner=runner,
        job_protocol=job_protocol,
        capabilities=ac.ConsoleCapabilities(
            shell_mode=shell_mode, jobs=jobs, update=update
        ),
    )


def test_shell_off_refuses_operator_command_without_subprocess():
    runner = MagicMock()
    core = _core(shell_mode="off", runner=runner)
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :Write-Output 1")
    assert hr is not None
    assert hr.action == "capability_deny"
    assert hr.reply == "DONE exit=126 shell-disabled"
    runner.start.assert_not_called()


def test_shell_off_allows_status_and_ping():
    job = MagicMock()
    core = _core(shell_mode="off", job_protocol=job)
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :STATUS")
    assert hr is not None and hr.action == "job"
    job.handle_async.assert_called_once()
    verb = job.handle_async.call_args[0][1]
    assert verb == "STATUS"

    hr2 = core.handle_raw(":anyone!u@h PRIVMSG tm_console :ping")
    assert hr2 is not None and hr2.action == "pong"


def test_jobs_off_refuses_put_run_allows_shell_when_operators():
    runner = MagicMock()
    job = MagicMock()
    core = _core(shell_mode="operators", jobs="off", runner=runner, job_protocol=job)
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :PUT path=x bytes=1")
    assert hr is not None
    assert hr.action == "capability_deny"
    assert "jobs-disabled" in (hr.reply or "")
    job.handle_async.assert_not_called()

    hr2 = core.handle_raw(":op!u@h PRIVMSG tm_console :Write-Output hi")
    assert hr2 is not None and hr2.action == "shell"
    runner.start.assert_called_once()


def test_update_off_refuses_update_verb():
    sched = MagicMock()
    auth = ac.AuthPolicy(operators={"op"}, machine="tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        update_scheduler=sched,
        capabilities=ac.ConsoleCapabilities(shell_mode="operators", update="off"),
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :UPDATE airc")
    assert hr is not None
    assert hr.action == "capability_deny"
    assert "update-disabled" in (hr.reply or "")
    sched.assert_not_called()


def test_normalize_shell_cli_off_token_is_mode_not_path():
    mode, path = ac.normalize_shell_cli("off")
    assert mode == "off" and path is None
    mode2, path2 = ac.normalize_shell_cli(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    assert mode2 is None and path2 and path2.lower().endswith("powershell.exe")


def test_load_capabilities_from_airc_json(tmp_path: Path):
    cfg = tmp_path / "config" / "airc.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '{"shell":"off","jobs":"off","update":"on","require_account":true,"accounts":["simon"]}\n',
        encoding="utf-8",
    )
    caps = ac.load_capabilities(install_root=tmp_path, cli_shell=None, cli_jobs=None, cli_update=None)
    assert caps.shell_mode == "off"
    assert caps.jobs == "off"
    assert caps.update == "on"
    assert caps.require_account is True
    assert caps.accounts == ("simon",)


def test_resolve_shell_mode_fresh_default_off_upgrade_operators():
    assert ac.resolve_shell_mode_for_install(prior_shell=None, explicit=None, had_prior_service=False) == "off"
    assert ac.resolve_shell_mode_for_install(prior_shell=None, explicit=None, had_prior_service=True) == "operators"
    assert ac.resolve_shell_mode_for_install(prior_shell="off", explicit=None, had_prior_service=True) == "off"
    assert ac.resolve_shell_mode_for_install(prior_shell="operators", explicit="off", had_prior_service=True) == "off"


def test_install_and_pack_wire_msi_properties_and_persistence():
    pack = PACK.read_text(encoding="utf-8")
    _no_bom(PACK)
    assert 'Property Id="AIRC_SHELL"' in pack
    assert 'Property Id="AIRC_JOBS"' in pack
    assert 'Property Id="AIRC_UPDATE"' in pack
    assert 'Property Id="AIRC_REQUIRE_ACCOUNT"' in pack
    assert 'Property Id="AIRC_ACCOUNTS"' in pack
    assert "-ShellMode &quot;[AIRC_SHELL]&quot;" in pack
    assert "-Jobs &quot;[AIRC_JOBS]&quot;" in pack
    assert "-UpdateCap &quot;[AIRC_UPDATE]&quot;" in pack
    assert "-RequireAccount &quot;[AIRC_REQUIRE_ACCOUNT]&quot;" in pack
    assert "-Accounts &quot;[AIRC_ACCOUNTS]&quot;" in pack

    inst = INSTALL_AIRC.read_text(encoding="utf-8-sig")
    assert "[string]$ShellMode" in inst
    assert "airc.json" in inst
    assert "resolve" in inst.lower() or "ShellMode" in inst
    assert "FR #3287" in inst

    cons = INSTALL_CONSOLE.read_text(encoding="utf-8-sig")
    assert "ShellMode" in cons
    assert "--shell-mode" in cons or "shell-mode" in cons
    assert "--require-account" in cons
    assert "--accounts" in cons
    assert "airc.json" in cons

    common = COMMON.read_text(encoding="utf-8-sig")
    assert "ShellMode" in common or "shell-mode" in common
    assert "Get-BobiverseAircIdentityFromAppParameters" in common

    post = POST.read_text(encoding="utf-8")
    assert "AIRC_SHELL" in post
    assert "AIRC_REQUIRE_ACCOUNT" in post

    start = START.read_text(encoding="utf-8-sig")
    assert "ShellMode" in start
    assert "--shell-mode" in start

    svc = SVC.read_text(encoding="utf-8")
    assert "--shell-mode" in svc
    assert "--jobs" in svc
    assert "load_capabilities" in svc
    assert "caps.log_line()" in svc or "log_line()" in svc
    assert "INFO capabilities shell=" in ac.ConsoleCapabilities().log_line()


def test_fr3287_files_end_with_newline():
    for p in (
        PACK,
        INSTALL_AIRC,
        INSTALL_CONSOLE,
        START,
        COMMON,
        POST,
        SVC,
        Path(__file__),
    ):
        assert p.read_bytes().endswith(b"\n"), p
