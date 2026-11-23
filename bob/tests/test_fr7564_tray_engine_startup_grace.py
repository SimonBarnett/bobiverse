"""FR #7564: tray engine start-up grace >= stale window; storm reports; pools independent."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

WIN = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell")
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
BUILD = ROOT / "bob" / "scripts" / "Build-BobDialogs.ps1"
PS = shutil.which("powershell") or "powershell.exe"


def _cs() -> str:
    return CS.read_text(encoding="utf-8-sig")


def test_fr7564_cold_start_grace_at_least_max_age():
    t = _cs()
    stamp = t[t.find("internal static class EngineAliveStamp") : t.find("internal static class EngineAliveStamp") + 2800]
    assert "ColdStartGraceSeconds" in stamp
    assert "MaxAgeSeconds" in stamp
    # Grace must be at least the normal stale window (120), measured from launch (FR #7564).
    assert "ColdStartGraceSeconds = MaxAgeSeconds" in stamp or "ColdStartGraceSeconds = 120" in stamp
    assert "ColdStartGraceSeconds = 60" not in stamp
    assert "FR #7564" in t


def test_fr7564_heal_storm_reports_exception():
    t = _cs()
    heal = t[t.find("void HealEngine()") : t.find("void HealEngine()") + 6000]
    assert "engine-restart-storm" in heal
    assert "CrashHook.Report" in heal or "TrayEngineFailure" in heal
    assert "StartEngine()" in heal
    # Storm must not keep calling StartEngine after the threshold.
    i = heal.find("engineStarts > 3")
    assert i > 0
    storm = heal[i : i + 1200]
    assert "return" in storm
    assert "CrashHook.Report" in storm or "TrayEngineFailure" in storm
    # First StartEngine after the storm gate must be after return (relaunch only when under cap).
    ret = storm.find("return")
    start_in_storm = storm.find("StartEngine()")
    assert start_in_storm < 0 or ret < start_in_storm


def test_fr7564_digest_pools_timer_independent_of_engine():
    t = _cs()
    assert "StopDigestPoolsTimer" in t or "digestPools" in t or "DigestPools" in t
    assert "Update-BobTrayDigestPools" in t or "tray-digest-pools" in t
    # Pool paint must not require a live engine (FR #7510 / #7564).
    assert "FR #7510" in t or "tray-digest-pools" in t


@WIN
def test_fr7564_watchdog_eval_first_heartbeat_window_90s(tmp_path):
    """Simulated engine: no post-start stamp yet at 90s after launch must not be stale."""
    out_dir = tmp_path / "dialogs"
    out_dir.mkdir()
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BUILD), "-RepoRoot", str(ROOT), "-OutDir", str(out_dir)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    exe = out_dir / "bob-tray.exe"
    assert exe.is_file()
    root = tmp_path / "root"
    swdir = root / "run" / "startworker"
    swdir.mkdir(parents=True)
    # Leftover pre-start stamp (old mtime) — new engine launched 90s ago.
    leftover = swdir / "engine.alive"
    leftover.write_text("pre-start leftover", encoding="ascii")
    past = time.time() - 36000
    os.utime(leftover, (past, past))
    text_out = tmp_path / "eval90.txt"
    p = subprocess.run(
        [
            str(exe),
            "--root",
            str(root),
            "--watchdog-eval",
            "--engine-started-ago-s",
            "90",
            "--text-out",
            str(text_out),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body = text_out.read_text(encoding="utf-8")
    assert "stale=0" in body, body
    assert p.returncode == 0

    # After grace (>=120) with still only leftover: stale so HealEngine can restart once.
    text_out2 = tmp_path / "eval200.txt"
    p2 = subprocess.run(
        [
            str(exe),
            "--root",
            str(root),
            "--watchdog-eval",
            "--engine-started-ago-s",
            "200",
            "--text-out",
            str(text_out2),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body2 = text_out2.read_text(encoding="utf-8")
    assert "stale=1" in body2, body2
    assert p2.returncode == 2

    # Post-start heartbeat then hung >120s: still stale.
    now = time.time()
    leftover.write_text("hung", encoding="ascii")
    os.utime(leftover, (now - 500, now - 500))
    text_out3 = tmp_path / "evalhung.txt"
    p3 = subprocess.run(
        [
            str(exe),
            "--root",
            str(root),
            "--watchdog-eval",
            "--engine-started-ago-s",
            "600",
            "--text-out",
            str(text_out3),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body3 = text_out3.read_text(encoding="utf-8")
    assert "stale=1" in body3, body3
    assert p3.returncode == 2
