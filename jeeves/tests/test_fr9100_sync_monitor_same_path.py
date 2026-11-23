"""FR #9100: Sync same-path skip for jeeves tools/monitor (Windows behavioural)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

PS = os.environ.get("BOB_PWSH") or "pwsh"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"


@pytest.mark.skipif(sys.platform != "win32", reason="Sync is Windows PowerShell")
def test_fr9100_sync_monitor_force_skips_same_path(tmp_path: Path):
    if os.environ.get("BOBIVERSE_NO_UPDATE", "").strip() == "1":
        pytest.skip("BOBIVERSE_NO_UPDATE=1")
    # Flat compose-only install: clone == InstallRoot so monFrom == monDst.
    install = tmp_path / "jeeves"
    mon = install / "tools" / "monitor"
    mon.mkdir(parents=True)
    (mon / "health.py").write_text("# tip-health\n", encoding="utf-8")
    (install / "scripts").mkdir()
    (install / "scripts" / "noop.ps1").write_text("# noop\n", encoding="utf-8")
    (install / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=str(install),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "i",
        ],
        cwd=str(install),
        check=True,
        capture_output=True,
    )
    env = {**os.environ}
    env.pop("BOBIVERSE_NO_UPDATE", None)
    env.pop("BOBIVERSE_REPO", None)
    env["BOB_AI_ROOT"] = str(tmp_path)
    p = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SYNC),
            "-Product",
            "jeeves",
            "-InstallRoot",
            str(install),
            "-ComposeOnly",
            "-ArpVersionOverride",
            "none",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    out = (p.stdout or "") + (p.stderr or "")
    # FR pin: force-copy skips when monFrom == monDst. Later ComposeOnly may still
    # warn on VERSION self-copy on a disposable flat tree; that is out of scope.
    assert "skipped (source == destination)" in out, out
