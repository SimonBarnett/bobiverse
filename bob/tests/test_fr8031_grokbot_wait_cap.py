"""FR #8031: Invoke-GrokBotApi must honor TimeoutSec below the old 30s floor."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

SRC = ROOT / "bob" / "tray" / "src" / "Private" / "Invoke-GrokBot.ps1"


def test_fr8031_source_does_not_floor_wait_at_30s():
    text = SRC.read_text(encoding="utf-8")
    assert "[Math]::Max(30, $TimeoutSec + 30)" not in text
    assert "FR #8031" in text
    assert re.search(r"\$graceSec\s*=\s*\d+", text)


def test_fr8031_non_exiting_child_stops_near_timeout(tmp_path: Path):
    sleeper = tmp_path / "sleep_forever.py"
    sleeper.write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
    src = str(SRC).replace("'", "''")
    py = str(Path(sys.executable)).replace("'", "''")
    sleep_ps = str(sleeper).replace("'", "''")
    script = tmp_path / "run.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{src}'
function Get-PythonExe {{ return '{py}' }}
function Get-GrokBotApiScript {{ return '{sleep_ps}' }}
function Stop-ProcessTree {{
    param([int]$ProcessId)
    try {{
        Get-CimInstance Win32_Process -Filter \"ParentProcessId=$ProcessId\" -ErrorAction SilentlyContinue |
            ForEach-Object {{ Stop-ProcessTree -ProcessId $_.ProcessId }}
    }} catch {{ }}
    try {{ Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue }} catch {{ }}
}}
$r = Invoke-GrokBotApi -Action list -TimeoutSec 5
if ($r.ExitCode -ne 124) {{ throw ('exit ' + $r.ExitCode) }}
if ($r.Stderr -notmatch 'timeout after 7s') {{ throw $r.Stderr }}
if ($r.DurationMs -ge 15000) {{ throw ('waited ' + $r.DurationMs) }}
if ($r.DurationMs -lt 4000) {{ throw ('too fast ' + $r.DurationMs) }}
Write-Output 'ok'
""",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout
