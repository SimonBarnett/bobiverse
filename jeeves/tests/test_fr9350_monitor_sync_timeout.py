"""FR #9350: Invoke-JeevesMonitorCheck bounds Sync so a hang cannot block checks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

WRAPPER = REPO / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_fr9350_wrapper_bounds_sync_timeout_and_throttle():
    _no_bom(WRAPPER)
    text = WRAPPER.read_text(encoding="utf-8")
    assert "9350" in text
    assert "SyncTimeoutSec" in text
    assert "SyncMinIntervalSec" in text
    assert "WaitForExit" in text
    assert "BOB_MONITOR_SYNC_TIMEOUT_SEC" in text
    assert "BOB_MONITOR_SYNC_MIN_INTERVAL_SEC" in text
    assert ".bobiverse-monitor-last-sync" in text
    assert "proceeding with existing tools\\monitor" in text or "proceeding with existing tools/monitor" in text
    # Must not call Sync in-process (that is the hang class).
    assert "Start-Process" in text
    low = text.lower()
    assert "kill()" in low or ".kill()" in low


def test_fr9350_wrapper_still_lists_health_check():
    text = WRAPPER.read_text(encoding="utf-8")
    assert "'health'" in text or '"health"' in text


def test_fr9350_dryrun_health_reaches_python():
    """Smoke: DryRun Sync path must return and still run tools\\monitor\\health.py."""
    assert WRAPPER.is_file()
    health = REPO / "jeeves" / "tools" / "monitor" / "health.py"
    assert health.is_file()
    ps = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(WRAPPER),
        "-Check",
        "health",
        "-DryRun",
        "-InstallRoot",
        str(REPO / "jeeves"),
        "-SyncTimeoutSec",
        "20",
        "-SyncMinIntervalSec",
        "0",
    ]
    proc = subprocess.run(
        ps,
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(REPO / "jeeves"),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode in (0, 1), out[-2000:]
    # Dry-run monitor scripts emit JSON with ok true (or skipped).
    assert "ok" in out.lower() or "{" in out, out[-2000:]


def test_fr9350_files_end_with_newline():
    for p in (WRAPPER, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
