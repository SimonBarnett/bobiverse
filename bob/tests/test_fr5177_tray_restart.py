"""FR #5177: restart survives a slow IRC drain and commands cannot replay."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

PS = shutil.which("powershell.exe") or shutil.which("pwsh") or shutil.which("powershell")
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
HELPER = ROOT / "bob" / "tray" / "tools" / "BobTrayDialogs.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def _ps(root: Path, script: str) -> None:
    if not PS:
        pytest.skip("needs PowerShell")
    setup = f"""
$ErrorActionPreference = 'Stop'
$env:BOB_TRAY_EXE_PID = ''
. '{str(HELPER).replace("'", "''")}'
$root = '{str(root).replace("'", "''")}'
$commandPath = Join-Path (Join-Path $root 'run') 'tray-cmd.txt'
"""
    result = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", setup + script],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("command", ["ack", "exit", "restart"])
def test_commands_are_consumed_before_callbacks(tmp_path: Path, command: str):
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "tray-cmd.txt").write_text(command + "\n", encoding="ascii")
    _ps(tmp_path, """
$callback = {
    if (Test-Path -LiteralPath $commandPath) { throw 'command was not consumed' }
    $replayed = @(Invoke-BobTrayExeCommands -Root $root -OnRestart { throw 'replayed' })
    if ($replayed.Count) { throw 'command replayed during callback' }
    Add-Content -LiteralPath $commandPath -Value 'ack' -Encoding ascii
}
$done = @(Invoke-BobTrayExeCommands -Root $root -OnAck $callback -OnExit $callback -OnRestart $callback)
if ($done.Count -ne 1) { throw 'callback did not run' }
if ((Get-Content -LiteralPath $commandPath -Raw).Trim() -ne 'ack') { throw 'new command lost' }
""")


def test_throwing_restart_does_not_leave_replay_and_preserves_reload(tmp_path: Path):
    (tmp_path / "run").mkdir()
    cmd = tmp_path / "run" / "tray-cmd.txt"
    cmd.write_text("restart\nreload\n", encoding="ascii")
    _ps(tmp_path, """
try {
    Invoke-BobTrayExeCommands -Root $root -OnRestart { throw 'interrupted restart' }
    throw 'restart did not run'
} catch {
    if ($_.Exception.Message -ne 'interrupted restart') { throw }
}
$done = @(Invoke-BobTrayExeCommands -Root $root -OnRestart { throw 'replayed restart' })
if ($done.Count) { throw 'restart replayed' }
if ((Get-Content -LiteralPath $commandPath -Raw).Trim() -ne 'reload') { throw 'reload lost' }
""")


def test_command_arriving_during_claim_is_not_deleted(tmp_path: Path):
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "tray-cmd.txt").write_text("restart\n", encoding="ascii")
    _ps(tmp_path, """
function Move-Item {
    [CmdletBinding()]
    param([string]$LiteralPath, [string]$Destination)
    Microsoft.PowerShell.Management\\Move-Item @PSBoundParameters
    Add-Content -LiteralPath $commandPath -Value 'ack' -Encoding ascii
}
$done = @(Invoke-BobTrayExeCommands -Root $root -OnRestart { })
if ($done.Count -ne 1 -or $done[0] -ne 'restart') { throw 'restart not handled' }
if ((Get-Content -LiteralPath $commandPath -Raw).Trim() -ne 'ack') { throw 'new command lost' }
""")


def test_failed_claim_does_not_execute_restart(tmp_path: Path):
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "tray-cmd.txt").write_text("restart\n", encoding="ascii")
    _ps(tmp_path, """
function Move-Item { throw 'file busy' }
$done = @(Invoke-BobTrayExeCommands -Root $root -OnRestart { throw 'unclaimed restart ran' })
if ($done.Count) { throw 'unclaimed command reported as handled' }
if ((Get-Content -LiteralPath $commandPath -Raw).Trim() -ne 'restart') { throw 'command lost' }
""")


def test_restart_wait_covers_drain_shutdown_and_poll():
    source = CS.read_text(encoding="utf-8-sig")
    restart = source.split("void Restart()", 1)[1].split("void FinishAfterEngine", 1)[0]
    wait_ms = int(re.search(r"FinishAfterEngine\((\d+)\)", restart).group(1))
    assert wait_ms > (30 + 10 + 2) * 1000


def test_engine_start_discards_leftover_restart(tmp_path: Path):
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "tray-cmd.txt").write_text("restart\n", encoding="ascii")
    source = CS.read_text(encoding="utf-8-sig")
    start = source[source.index("void StartEngine()"):source.index("// FR #3180: public")]
    assert start.index("File.Delete(cmdFile)") < start.index("Process.Start(psi)")
    _ps(tmp_path, """
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Diagnostics;
public class EngineStartupProbe {
    public string root, cmdFile, machine = "";
    public Process engine;
    public DateTime engineStartedUtc;
    public EngineStartupProbe(string path) {
        root = path;
        cmdFile = Path.Combine(root, "run", "tray-cmd.txt");
        StartEngine();
    }
""" + start + """
}
'@
[void][EngineStartupProbe]::new($root)
if (Test-Path -LiteralPath $commandPath) { throw 'stale command survived engine startup' }
Invoke-BobTrayExeCommands -Root $root -OnRestart { throw 'stale restart replayed' }
""")


def test_restart_relaunches_after_slow_irc_logout(tmp_path: Path):
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "tray-cmd.txt").write_text("restart\n", encoding="ascii")
    _ps(tmp_path, f"""
$watch = '{str(WATCH).replace("'", "''")}'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($watch, [ref]$tokens, [ref]$errors)
$fn = $ast.Find({{ param($n)
    $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $n.Name -eq 'Restart-BobTrayWatcher'
}}, $true)
. ([scriptblock]::Create($fn.Extent.Text))
$RepoRoot = Split-Path (Split-Path $watch)
$ctx = [pscustomobject]@{{}}
$ctx | Add-Member ScriptMethod ExitThread {{ $script:exited = $true }}
function Write-TrayLog {{ param($Message) }}
function powershell.exe {{ }}
function Request-BobTrayIrcLogout {{
    param($Reason)
    if (Test-Path -LiteralPath $commandPath) {{ throw 'restart not consumed before drain' }}
    Start-Sleep -Seconds 7
    $script:drained = $true
}}
function Start-Process {{
    param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle)
    if (-not $script:drained) {{ throw 'logout did not complete' }}
    if ($ArgumentList -notcontains '-ForceNew' -or
        $ArgumentList -notcontains '-SkipServiceRestart') {{ throw 'wrong bootstrap' }}
    $script:launched = $true
}}
Invoke-BobTrayExeCommands -Root $root -OnRestart {{ Restart-BobTrayWatcher }}
if (-not $script:launched -or -not $script:exited) {{ throw 'restart did not relaunch' }}
Invoke-BobTrayExeCommands -Root $root -OnRestart {{ throw 'restart replayed after relaunch' }}
""")
