"""FR #5195: execute the independent watchdog with mocked Windows services."""

import base64
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "common/scripts/Watch-BobiverseService.ps1"
PWSH = shutil.which("pwsh") or shutil.which("powershell.exe")


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_watchdog(marker="missing", status="Stopped", failure="", bob_home=False,
                 windows=False):
    with tempfile.TemporaryDirectory(prefix="watchdog-test-") as folder:
        root = Path(folder)
        state = root / "state"
        install = root / "install"
        home = root / "custom home" if bob_home else install / "home"
        state.mkdir()
        home.mkdir(parents=True)
        harness = r"""
$ErrorActionPreference = 'Stop'
$global:starts = 0
$global:gets = 0
$global:waitSeconds = 0
$global:waitTarget = ''
$global:aclCalls = @()
$env:OS = WINDOWS
function icacls.exe {
    $global:aclCalls += ,@($args)
}
$global:failure = FAILURE
$global:initialStatus = STATUS
$global:service = [pscustomobject]@{ Status = $global:initialStatus }
$global:service | Add-Member ScriptMethod WaitForStatus {
    param($target, $timeout)
    $global:waitSeconds = $timeout.TotalSeconds
    $global:waitTarget = [string]$target
    if ($global:failure -eq 'wait') { throw 'SECRET wait error /private/path' }
    $this.Status = 'Running'
}
$global:service | Add-Member ScriptMethod Refresh { }
function Get-Service {
    param($Name, $ErrorAction)
    $global:gets++
    if ($global:failure -eq 'get') { throw 'SECRET lookup /private/path' }
    return $global:service
}
function Start-Service {
    param($Name, $ErrorAction)
    $global:starts++
    if ($global:failure -eq 'start') { throw 'SECRET start /private/path' }
}
function Get-ItemProperty {
    param($LiteralPath, $Name, $ErrorAction)
    return [pscustomobject]@{ AppParameters = APPPARAMS }
}
$state = STATE
$marker = MARKER
if ($marker -ne 'missing') {
    $text = switch ($marker) {
        'fresh' { @{ atUtc = [DateTime]::UtcNow.AddMinutes(-1).ToString('o') } | ConvertTo-Json }
        'stale' { @{ atUtc = [DateTime]::UtcNow.AddMinutes(-11).ToString('o') } | ConvertTo-Json }
        'boundary' { @{ atUtc = [DateTime]::UtcNow.AddMinutes(-10).ToString('o') } | ConvertTo-Json }
        'future' { @{ atUtc = [DateTime]::UtcNow.AddHours(1).ToString('o') } | ConvertTo-Json }
        'invalid' { '{"atUtc":"SECRET invalid /private/path"}' }
        'malformed' { '{SECRET' }
        'absent-field' { '{}' }
        'non-utc' { '{"atUtc":"2026-10-29T12:00:00-04:00"}' }
        'oversized' { 'x' * 4097 }
        default { '' }
    }
    if ($marker -eq 'unreadable') {
        $null = New-Item -ItemType Directory -Path (Join-Path $state 'downtime.json')
    } else {
        [IO.File]::WriteAllText((Join-Path $state 'downtime.json'), $text)
    }
}
& SCRIPT -InstallRoot INSTALL -StateDir $state -ServiceName ircBob
[pscustomobject]@{
    starts = $global:starts
    gets = $global:gets
    waitSeconds = $global:waitSeconds
    waitTarget = $global:waitTarget
    aclCalls = @($global:aclCalls)
} | ConvertTo-Json -Compress
"""
        replacements = {
            "FAILURE": ps_quote(failure),
            "STATUS": ps_quote(status),
            "APPPARAMS": ps_quote(
                f'-BobHome "{home}" -PasswordFile "SECRET /private/path"'
                if bob_home else '-PasswordFile "SECRET /private/path"'
            ),
            "STATE": ps_quote(state),
            "MARKER": ps_quote(marker),
            "SCRIPT": ps_quote(SCRIPT),
            "INSTALL": ps_quote(install),
            "WINDOWS": ps_quote("Windows_NT" if windows else "Linux"),
        }
        for token, value in replacements.items():
            harness = harness.replace(token, value)
        encoded = base64.b64encode(harness.encode("utf-16-le")).decode("ascii")
        result = subprocess.run(
            [PWSH, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, text=True, timeout=20, check=True,
        )
        assert not result.stderr
        data = json.loads(result.stdout)
        log_path = state / "update.log"
        outbox_path = home / "outbox.txt"
        data["log"] = log_path.read_text() if log_path.exists() else ""
        data["outbox"] = outbox_path.read_bytes() if outbox_path.exists() else b""
        data["log_path"] = str(log_path)
        for output in (data["log"], data["outbox"].decode()):
            assert "SECRET" not in output
            assert "/private/path" not in output
            assert str(root) not in output
        return data


@unittest.skipUnless(PWSH, "PowerShell is required")
class ServiceWatchdogTests(unittest.TestCase):
    def test_fresh_marker_suppresses_recovery(self):
        result = run_watchdog("fresh")
        self.assertEqual(result["gets"], 0)
        self.assertEqual(result["starts"], 0)
        self.assertIn("update-active", result["log"])
        self.assertEqual(result["outbox"], b"")

    def test_no_unbounded_marker_suppression(self):
        for marker in [
            "missing", "stale", "boundary", "future", "invalid", "malformed",
            "absent-field", "non-utc", "oversized", "unreadable",
        ]:
            with self.subTest(marker=marker):
                result = run_watchdog(marker)
                self.assertEqual(result["gets"], 1)
                self.assertEqual(result["starts"], 1)
                self.assertEqual(result["waitSeconds"], 60)
                self.assertEqual(result["waitTarget"], "Running")
                self.assertIn(" recovered", result["log"])
                self.assertEqual(result["outbox"], (
                    b"PRIVMSG #bobiverse :watchdog: service ircBob recovered (Running)\n"
                ))
                self.assertFalse(result["outbox"].startswith(b"\xef\xbb\xbf"))

    def test_running_is_noop(self):
        result = run_watchdog(status="Running")
        self.assertEqual(result["gets"], 1)
        self.assertEqual(result["starts"], 0)
        self.assertEqual(result["log"], "")
        self.assertEqual(result["outbox"], b"")

    def test_only_stopped_service_is_started(self):
        for status in ["StartPending", "StopPending", "Paused"]:
            with self.subTest(status=status):
                result = run_watchdog(status=status)
                self.assertEqual(result["starts"], 0)
                self.assertIn("service-not-stopped", result["log"])

    def test_failure_is_safe_and_reported(self):
        for failure in ["start", "wait", "get"]:
            with self.subTest(failure=failure):
                result = run_watchdog(failure=failure)
                self.assertIn("recovery-failed", result["log"])
                self.assertNotIn(" recovered", result["log"])
                self.assertEqual(result["outbox"], (
                    b"PRIVMSG #bobiverse :watchdog: service ircBob recovery failed\n"
                ))

    def test_registry_bob_home_receives_announcement(self):
        result = run_watchdog(bob_home=True)
        self.assertIn(b"recovered (Running)", result["outbox"])

    def test_new_log_gets_only_explicit_users_read_permission(self):
        result = run_watchdog(windows=True)
        self.assertEqual(result["aclCalls"], [
            [result["log_path"], "/grant:r", "*S-1-5-32-545:R"],
        ])


if __name__ == "__main__":
    unittest.main()
