"""FR #7601: engine.alive + tray-status.json before first hover; alive while fetch hangs."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
PS = shutil.which("powershell") or "powershell.exe"
WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell"
)


def test_fr7601_seed_before_startup_hover():
    w = WATCH.read_text(encoding="utf-8")
    assert "FR #7601" in w
    assert "Write-BobTrayStartupWatchdogSeed" in w
    i_seed = w.index("Write-BobTrayStartupWatchdogSeed -Dir $script:startWorkerDir")
    i_hover = w.index("startup-update-hover", i_seed)
    assert i_seed < i_hover
    # No bare Update-Hover between seed and tray-up (that hung under PS 5.1).
    between = w[i_seed:w.index("Write-TrayLog 'tray up'", i_seed)]
    assert "\nUpdate-Hover\n" not in between.replace("\r\n", "\n")
    assert "startup-update-hover" in between


def test_fr7601_threadpool_writes_engine_alive_inline():
    w = WATCH.read_text(encoding="utf-8")
    i_timer = w.index("Register-ObjectEvent -InputObject $script:trayAliveTimer")
    chunk = w[i_timer : i_timer + 2200]
    assert "engine.alive" in chunk
    assert "File]::Open" in chunk or "[IO.File]::Open" in chunk
    assert "FR #7601" in chunk


def test_fr7601_no_machine_names_in_watch_helpers():
    w = WATCH.read_text(encoding="utf-8")
    start = w.index("function Write-BobTrayStartupWatchdogSeed")
    end = w.index("\nfunction ", start + 10)
    chunk = w[start:end].lower()
    for banned in ("red" + "queen", "white" + "queen", "march" + "hare", "flam" + "ingo"):
        assert banned not in chunk


@WIN
def test_fr7601_selftest_hung_startup_hover_alive_advances(tmp_path):
    env = os.environ.copy()
    env["BOB_TRAY_ENGINE_SELFTEST"] = "1"
    env["BOB_TRAY_ENGINE_SELFTEST_ROOT"] = str(tmp_path)
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WATCH),
            "-RepoRoot",
            str(ROOT / "bob" / "tray"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "FR7579_SELFTEST_OK" in out
    assert (tmp_path / "run" / "startworker" / "engine.alive").is_file()
    assert (tmp_path / "run" / "tray-status.json").is_file()
    log = (tmp_path / "logs" / "tray-engine-cycle.log").read_text(encoding="ascii", errors="replace")
    assert "step-timeout name=startup-update-hover" in log
