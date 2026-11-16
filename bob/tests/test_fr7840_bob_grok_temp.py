# -*- coding: utf-8 -*-
"""FR #7840: Invoke-Grok must not leave bob-grok-* directories in TEMP."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

PS1 = Path(__file__).resolve().parents[1] / "tray" / "src" / "Private" / "Invoke-Grok.ps1"


def _run(tmp: Path, body: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", body],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_fr7840_success_and_exception_leave_no_bob_grok_dirs(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    script = f"""
    . '{PS1}'
    function Get-GrokExe {{ 'C:\\Windows\\System32\\cmd.exe' }}
    1..3 | ForEach-Object {{
        Invoke-Grok -Args @('/c','exit','0') -WorkingDirectory '{work}' -TimeoutSec 20 | Out-Null
    }}
    function Get-GrokExe {{ 'C:\\no\\such\\grok-fr7840.exe' }}
    try {{
        Invoke-Grok -Args @('version') -WorkingDirectory '{work}' -TimeoutSec 10 | Out-Null
    }} catch {{}}
    $left = @(Get-ChildItem -LiteralPath '{tmp_path}' -Directory -Filter 'bob-grok-*' -ErrorAction SilentlyContinue)
    Write-Output ("LEFT=" + $left.Count)
    """
    proc = _run(tmp_path, script)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "LEFT=0" in proc.stdout
    assert not list(tmp_path.glob("bob-grok-*"))


def test_fr7840_startup_prunes_empty_dirs_older_than_one_hour(tmp_path: Path):
    old = tmp_path / ("bob-grok-" + "a" * 32)
    young = tmp_path / ("bob-grok-" + "b" * 32)
    full = tmp_path / ("bob-grok-" + "c" * 32)
    session = tmp_path / "bob-grok-session"
    for path in (old, young, full, session):
        path.mkdir()
    (full / "keep.txt").write_text("x", encoding="ascii")
    script = f"""
    . '{PS1}'
    (Get-Item -LiteralPath '{old}').LastWriteTime = (Get-Date).AddHours(-2)
    (Get-Item -LiteralPath '{full}').LastWriteTime = (Get-Date).AddHours(-2)
    (Get-Item -LiteralPath '{session}').LastWriteTime = (Get-Date).AddHours(-2)
    Clear-BobGrokStaleTempDirs
    Write-Output ("OLD=" + (Test-Path -LiteralPath '{old}'))
    Write-Output ("YOUNG=" + (Test-Path -LiteralPath '{young}'))
    Write-Output ("FULL=" + (Test-Path -LiteralPath '{full}'))
    Write-Output ("SESSION=" + (Test-Path -LiteralPath '{session}'))
    """
    proc = _run(tmp_path, script)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "OLD=False" in proc.stdout
    assert "YOUNG=True" in proc.stdout
    assert "FULL=True" in proc.stdout
    assert "SESSION=True" in proc.stdout
