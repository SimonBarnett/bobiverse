"""FR #5346: tray.alive share miss must not intake; OpenOrCreate + no throw."""
from __future__ import annotations

from repo_layout import ROOT

START = ROOT / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"


def test_fr5346_write_uses_openorcreate_not_create():
    fn = START.read_text(encoding="utf-8")
    chunk = fn[fn.index("function Write-BobTrayAlive") : fn.index("function Invoke-BobTrayStartWorkerQueue")]
    assert "OpenOrCreate" in chunk
    assert "FileMode]::Create" not in chunk
    assert "FR #5346" in chunk


def test_fr5346_timer_does_not_must_report_share_miss():
    w = WATCH.read_text(encoding="utf-8")
    i = w.index("$script:trayAliveSub = Register-ObjectEvent")
    chunk = w[i : i + 2200]
    assert "Write-BobTrayAlive" in chunk
    assert "Invoke-BobMustReportFailure -Component" not in chunk
    assert "FR #5346" in chunk


def test_fr5346_cs_openorcreate_swallows_io():
    t = CS.read_text(encoding="utf-8-sig")
    i = t.index("void WriteTrayAlive()")
    chunk = t[i : i + 1400]
    assert "FileMode.OpenOrCreate" in chunk
    assert "FileMode.Create," not in chunk
    assert "FR #5346" in chunk
