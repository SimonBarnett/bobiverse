# -*- coding: utf-8 -*-
"""FR #9435: skip tip-fresh Sync; tree-kill on timeout; force-copy invoke wrapper."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import REPO

INVOKE = REPO / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_fr9435_invoke_has_skip_tip_fresh_and_tree_kill():
    _no_bom(INVOKE)
    text = INVOKE.read_text(encoding="utf-8")
    assert "9435" in text
    assert "SkipSync" in text
    assert "BOB_MONITOR_SKIP_SYNC" in text
    assert "Test-BobMonitorTipFresh" in text
    assert "tools\\monitor already tip-fresh" in text or "tip-fresh" in text
    assert "taskkill" in text.lower()
    assert "/T" in text
    # Keep FR #9350 bound Sync path.
    assert "SyncTimeoutSec" in text
    assert "WaitForExit" in text
    assert "Start-Process" in text


def test_fr9435_sync_force_copies_invoke_wrapper():
    text = SYNC.read_text(encoding="utf-8")
    assert "9435" in text
    assert "sync-invoke-monitor-check-force" in text
    assert "Invoke-JeevesMonitorCheck.ps1" in text


def test_fr9435_dryrun_skip_sync_reaches_python():
    """Smoke: -SkipSync DryRun must return and still run tools\\monitor\\health.py."""
    assert INVOKE.is_file()
    health = REPO / "jeeves" / "tools" / "monitor" / "health.py"
    assert health.is_file()
    ps = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(INVOKE),
        "-Check",
        "health",
        "-DryRun",
        "-SkipSync",
        "-InstallRoot",
        str(REPO / "jeeves"),
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
    assert "ok" in out.lower() or "{" in out, out[-2000:]
    assert "skip sync" in out.lower() or "9435" in out or "ok" in out.lower()


def test_fr9435_files_end_with_newline():
    for p in (INVOKE, SYNC, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
