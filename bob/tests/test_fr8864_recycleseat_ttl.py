"""FR #8864: recycleseat TTL 300s and launch output keeps the last numeric pid."""
from __future__ import annotations

import subprocess
from pathlib import Path

import recycleseat as rs

ROOT = Path(__file__).resolve().parents[2]


def test_fr8864_request_ttl_is_300s():
    assert rs.REQUEST_TTL_S == 300.0


def test_fr8864_launch_pid_ignores_write_output_noise():
    start = ROOT / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1"
    recycle = ROOT / "bob" / "tray" / "tools" / "BobTrayRecycleSeat.ps1"
    watch = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
    doc = (ROOT / "bob" / "docs" / "bob-ear.md").read_text(encoding="utf-8")
    assert "Get-BobTrayLaunchPidFromOutput" in start.read_text(encoding="utf-8")
    assert "Get-BobTrayLaunchPidFromOutput" in recycle.read_text(encoding="utf-8")
    assert "Get-BobTrayLaunchPidFromOutput" in watch.read_text(encoding="utf-8")
    assert "BobTrayStartWorker.ps1" in doc and "300s" in doc
    script = (
        "$ErrorActionPreference='Stop'; "
        f". '{start}'; "
        "$out = Get-BobTrayLaunchPidFromOutput -Output @('agent: started pid=9', 4242, 'noise'); "
        "if ([int]$out -ne 4242) { throw \"got $out\" }; "
        "$zero = Get-BobTrayLaunchPidFromOutput -Output @(4242, 'log', 0); "
        "if ([int]$zero -ne 0) { throw \"zero got $zero\" }"
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
