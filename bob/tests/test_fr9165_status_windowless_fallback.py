"""FR #9165: windowless bob-status must not block TipForm left-click.

Single-instance mutex held with MainWindowHandle=0 made further Status starts
look successful while nothing painted. Start-BobTrayDialog must fall back when
hwnd stays 0; park TipForm skips bob-status; C# abandons mutex if HWND missing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

DIALOGS = ROOT / "third_party" / "bob-tray" / "tools" / "BobTrayDialogs.ps1"
WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
COMMON_CS = ROOT / "third_party" / "bob-tray" / "dialogs" / "BobDialogsCommon.cs"
STATUS_CS = ROOT / "third_party" / "bob-tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "docs" / "bob-9165-status-windowless-fallback.md"
WIN = pytest.mark.skipif(sys.platform != "win32", reason="tray PowerShell")


def test_fr9165_source_pins():
    d = DIALOGS.read_text(encoding="utf-8")
    w = WATCH.read_text(encoding="utf-8")
    assert "FR #9165" in d
    assert "function Test-BobTrayClickFixParkPresent" in d
    assert "MainWindowHandle" in d
    assert "function Start-BobTrayDialog" in d
    start = d[d.index("function Start-BobTrayDialog") : d.index("function Start-BobTrayDialog") + 1800]
    assert "Test-BobTrayStatusWindowVisible" in start
    assert "Stop-BobTrayWindowlessStatus" in start
    assert "MainWindowHandle" in d
    assert "Stop-Process" in d
    status = w[w.index("function Invoke-BobTrayStatus") : w.index("function Invoke-BobTrayStatus") + 2200]
    assert "Test-BobTrayClickFixParkPresent" in status
    assert "Show-BobTrayCard" in status
    # param() must be first statement in Show-BobTrayCard
    show = w[w.index("function Show-BobTrayCard") :]
    body_start = show.index("{") + 1
    head = show[body_start : body_start + 120].lstrip()
    assert head.startswith("param(")
    cs = COMMON_CS.read_text(encoding="utf-8")
    assert "AbandonSingle" in cs or "ReleaseSingle" in cs
    assert "FR #9165" in cs
    st = STATUS_CS.read_text(encoding="utf-8")
    assert "FR #9165" in st
    assert "AbandonSingle" in st or "ReleaseSingle" in st


def test_fr9165_evidence_doc():
    assert DOCS.is_file()
    t = DOCS.read_text(encoding="utf-8")
    assert "FR #9165" in t
    assert "MainWindowHandle" in t
    assert "park" in t.lower()


@WIN
def test_fr9165_park_detect_and_dialog_hwnd_gate(tmp_path: Path):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "bob-tray.exe.clickfalse-park").write_bytes(b"park")
    script = tmp_path / "t.ps1"
    script.write_text(
        "\n".join(
            [
                f". '{DIALOGS}'",
                f"$p = Test-BobTrayClickFixParkPresent -Root '{tmp_path}'",
                'Write-Output ("park={0}" -f $p)',
                # No bob-status.exe → Start returns false
                f"$s = Start-BobTrayDialog -Root '{tmp_path}' -Name 'status'",
                'Write-Output ("start={0}" -f $s)',
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = ((r.stdout or "") + (r.stderr or "")).replace("\r", "")
    assert r.returncode == 0, out
    assert "park=True" in out
    assert "start=False" in out
