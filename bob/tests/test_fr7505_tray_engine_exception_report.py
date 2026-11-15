"""FR #7505: bob-tray HealEngine / StartEngine report dead engine + log relaunches."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobTrayRunning.ps1"
REPORT = ROOT / "common" / "scripts" / "tray_engine_report.py"


def _cs() -> str:
    return CS.read_text(encoding="utf-8-sig")


def test_fr7505_tray_engine_report_module_exists():
    assert REPORT.is_file()
    t = REPORT.read_text(encoding="utf-8")
    assert "FR #7505" in t
    assert "stable_sig" in t
    assert "LIFECYCLE_TAIL_LINES" in t
    assert "recovery" in t


def test_fr7505_start_engine_logs_and_reports_fail():
    t = _cs()
    start = t[t.find("void StartEngine()") : t.find("void StartEngine()") + 2800]
    assert "engine-launch" in start
    assert "TrayEngineFailure.Report" in start
    assert "relaunch-fail" in start
    assert "engine-launch-miss" in start or "engine-launch-error" in start


def test_fr7505_heal_reports_dead_and_status_stale():
    t = _cs()
    heal = t[t.find("void HealEngine()") : t.find("void HealEngine()") + 3500]
    assert "FR #7505" in heal or "TrayEngineFailure" in heal
    assert "TrayEngineFailure.Report" in heal
    assert "status-stale" in heal or "StatusStaleSeconds" in t
    assert "engine-relaunch" in heal
    assert "recovery" in heal
    assert "StatusStaleSeconds = 120" in t or "StatusStaleSeconds=120" in t.replace(" ", "")


def test_fr7505_ensure_watchdog_logs_relaunch_result():
    e = ENSURE.read_text(encoding="utf-8")
    assert "FR #7505" in e
    assert "result" in e
    assert "tray_engine_report" in e
    assert "relaunch-fail" in e
