"""MRB #5215 hostile pins: ircBob self-update heal after abort (FR #5195)."""
from __future__ import annotations
from pathlib import Path
from repo_layout import ROOT

UPD = ROOT / "common/scripts/Update-BobiverseService.ps1"
TRAY = ROOT / "bob/tray/dialogs/BobTray.cs"

def test_mrb5215_apply_finally_heal_and_watchdog_order():
    t = UPD.read_text(encoding="utf-8-sig")
    apply_ = t[t.index("function Invoke-Apply"):]
    assert "Start-ApplyTimeoutWatchdog" in apply_
    assert apply_.index("service-stopped") < apply_.index("Start-ApplyTimeoutWatchdog")
    assert "apply-finally-heal" in apply_
    assert "pending-stale-clock" in t
    assert "self-update.log" in t

def test_mrb5215_tray_heals_ircbob_not_workers():
    tray = TRAY.read_text(encoding="utf-8-sig")
    assert "HealIrcBobIfIdle" in tray
    assert "start ircBob" in tray
    wd = tray[tray.find("void Watchdog()"): tray.find("void Watchdog()") + 2500]
    assert "HealIrcBobIfIdle()" in wd
    assert "WorkerLauncher.Launch" not in wd