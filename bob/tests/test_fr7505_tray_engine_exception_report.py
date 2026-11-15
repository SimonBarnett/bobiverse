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


def test_fr7505_fix7519_ensure_treats_stale_snap_as_dead_while_process_present():
    """FIX #7519: frozen TipForm (process present, tray-status.json >= 120s) must report + relaunch."""
    e = ENSURE.read_text(encoding="utf-8")
    assert "TrayStatusStaleSeconds" in e or "120" in e
    assert "Get-BobTrayStatusAgeSeconds" in e
    assert "watchdog-status-stale" in e
    assert "Stop-BobTrayProcesses" in e
    assert "FIX #7519" in e or "frozen TipForm" in e
    assert "statusAge" in e or "statusAgeS" in e
    # Frozen path reports status-stale and still relaunches (not early watchdog-ok only).
    assert "Invoke-BobTrayEngineReport" in e
    assert "-Kind 'status-stale'" in e or '-Kind "status-stale"' in e or "Kind 'status-stale'" in e
    assert "$frozen" in e
    assert "why={1}" in e or "why =" in e or "relaunchWhy" in e


def test_mrb7519_ensure_bob_tray_running_is_bomless_ascii():
    """MRB #7519 hostile: WinPS 5.1 watched scripts must be BOM-less ASCII (pytest-ascii-bom / FR #3975)."""
    raw = ENSURE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM forbidden"
    assert all(b < 128 for b in raw), "non-ASCII in Ensure-BobTrayRunning.ps1"
