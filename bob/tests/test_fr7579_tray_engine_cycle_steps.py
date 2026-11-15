"""FR #7579: tray engine alive-first cycle, step log, timed-out blocking steps."""
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


def test_fr7579_watch_pins_alive_before_blocking_steps():
    w = WATCH.read_text(encoding="utf-8")
    assert "FR #7579" in w
    assert "Write-BobTrayEngineAliveStamp" in w
    assert "tray-engine-cycle.log" in w
    assert "Invoke-BobTrayEngineStep" in w
    i_cycle = w.index("cycle-start name=poll")
    i_alive = w.index("Write-BobTrayEngineAliveStamp -Dir $script:startWorkerDir", i_cycle)
    i_hover = w.index("update-hover", i_alive)
    assert i_cycle < i_alive < i_hover
    # ThreadPool heartbeat also advances engine.alive
    assert "advance engine.alive on ThreadPool" in w


@WIN
def test_fr7579_selftest_hung_step_and_normal_cycle(tmp_path):
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
    log = tmp_path / "logs" / "tray-engine-cycle.log"
    assert log.is_file()
    text = log.read_text(encoding="ascii", errors="replace")
    assert "step-start name=alpha" in text
    assert "step-end name=alpha" in text
    assert "step-start name=bravo" in text
    assert "step-timeout name=hung" in text
    alive = tmp_path / "run" / "startworker" / "engine.alive"
    assert alive.is_file()
