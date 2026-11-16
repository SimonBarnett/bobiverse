"""FR #7594: jobs-watcher and stall-alerts run under Invoke-BobTrayEngineStep."""
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


def _watch() -> str:
    return WATCH.read_text(encoding="utf-8")


def test_fr7594_poll_wraps_jobs_watcher_and_stall_alerts():
    w = _watch()
    assert "FR #7594" in w
    i_cycle = w.index("cycle-start name=poll")
    i_jw = w.index("Invoke-BobTrayEngineStep -Name 'jobs-watcher'", i_cycle)
    i_sa = w.index("Invoke-BobTrayWarmEngineStep -Name 'stall-alerts'", i_cycle)
    i_hover = w.index("update-hover", i_jw)
    assert i_cycle < i_jw < i_sa < i_hover
    # Direct try/catch Start-JobsWatcher / Get-BobStallAlerts must not remain in the poll body.
    poll = w[i_cycle : w.index("cycle-end name=poll", i_cycle)]
    assert "try { Start-JobsWatcher }" not in poll
    assert "Get-BobStallAlerts -Seen $seen" not in poll or "Invoke-BobTrayWarmEngineStep -Name 'stall-alerts'" in poll
    # Stall alerts body still calls Get-BobStallAlerts inside the timed job.
    assert "Get-BobStallAlerts" in w[i_sa : i_sa + 1200]


def test_fr7594_engine_step_returns_output():
    w = _watch()
    start = w.index("function Invoke-BobTrayEngineStep")
    end = w.index("function Invoke-BobTrayEngineSelfTest", start)
    body = w[start:end]
    assert "output = Receive-Job" in body or "$output = Receive-Job" in body
    assert "output = $output" in body


def test_fr7594_no_machine_names():
    w = _watch().lower()
    start = w.index("fr #7594: jobs-watcher")
    chunk = w[start : start + 2500]
    for banned in ("red" + "queen", "flam" + "ingo", "march" + "hare", "wal" + "rus"):
        assert banned not in chunk


@WIN
def test_fr7594_selftest_still_ok(tmp_path):
    """FR #7579 selftest remains green after #7594 output capture change."""
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
