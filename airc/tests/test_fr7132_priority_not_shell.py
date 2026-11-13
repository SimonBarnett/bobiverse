"""FR #7132: PRIORITY never falls through to PowerShell; not-configured is err+DONE exit=2."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_priority as ap
from airc_auth_helpers import ops_auth

ROOT = Path(__file__).resolve().parents[2]
REMOTE = ROOT / "airc" / "scripts" / "Invoke-AircRemote.ps1"


def _core(tmp_path: Path | None = None, **kw):
    auth = ops_auth("op", channel="#tm")
    extra = {}
    if tmp_path is not None:
        root = tmp_path / "airc-install"
        (root / "config").mkdir(parents=True)
        extra["install_root"] = str(root)
    return ac.AircConsoleCore(
        machine="tm", auth=auth, nick="tm_console", **extra, **kw
    )


def test_fr7132_status_not_powershell_when_unconfigured(tmp_path):
    core = _core(tmp_path)
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd PRIORITY status")
    assert hr is not None
    assert hr.action == "priority"
    text = hr.reply or ""
    assert "CommandNotFound" not in text
    assert "term 'PRIORITY'" not in text
    assert "code=not-configured" in text
    assert "priority_not_installed" in text
    assert "DONE id=aabbccdd exit=2" in text


def test_fr7132_priority_works_when_shell_off(tmp_path):
    core = _core(tmp_path, capabilities=ac.ConsoleCapabilities(shell_mode="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=11223344 PRIORITY status")
    assert hr and hr.action == "priority"
    assert "shell-disabled" not in (hr.reply or "")
    assert "DONE id=11223344 exit=2" in (hr.reply or "")


def test_fr7132_format_not_configured():
    blob = ap.format_priority_not_configured("deadbeef")
    assert blob.startswith("err id=deadbeef seq=1 code=not-configured")
    assert "DONE id=deadbeef exit=2" in blob


def test_fr7132_is_priority_line():
    assert ap.is_priority_line("PRIORITY status")
    assert ap.is_priority_line("id=aabbccdd PRIORITY prepare FOO")
    assert not ap.is_priority_line("STATUS")
    assert not ap.is_priority_line("Write-Output PRIORITY")


def test_fr7132_invoke_airc_remote_priority_action():
    text = REMOTE.read_text(encoding="utf-8")
    assert "'Priority'" in text or '"Priority"' in text
    assert "PRIORITY" in text
    # ValidateSet includes Priority on both param blocks.
    assert text.count("Priority") >= 3


def test_fr7132_safety_net_before_shell(tmp_path):
    """Unknown future PRIORITY sub-verb still must not hit PowerShell."""
    core = _core(tmp_path)

    class _Runner:
        def start(self, nick, cmd):
            raise AssertionError(f"shell start {cmd!r}")

        def discard_dcclisten(self, *a, **k):
            return None

    core.shell_runner = _Runner()
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :PRIORITY frobnicate")
    assert hr and hr.action == "priority"
    assert "code=usage" in (hr.reply or "")
