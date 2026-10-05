"""FR #2581: Sync overlays Update-BobiverseService.ps1 from origin tip when ff blocked.

Dirty install worktrees (hotpatched bob_worker / airc_console) leave Sync on a
stale HEAD; robocopy then composes a pre-#2563 updater that still burns MaxAttempts
on robocopy>=8. Overlay tip blob into flat scripts\\ and common\\scripts\\.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import REPO

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("git"),
    reason="windows + git",
)

COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"


def _fn_body(text: str, name: str) -> str:
    m = re.search(r"function\s+" + re.escape(name) + r"\b", text)
    assert m, name
    rest = text[m.start() :]
    m2 = re.search(r"\nfunction\s+\w+", rest[1:])
    return rest if not m2 else rest[: m2.start() + 1]


def test_fr2581_common_defines_updater_overlay():
    body = _fn_body(COMMON.read_text(encoding="utf-8"), "Sync-BobiverseUpdaterFromOrigin")
    assert "Update-BobiverseService.ps1" in body
    assert "origin/" in body
    assert "FR #2581" in body or "FR #2563" in body
    assert "common\\scripts" in body or "common/scripts" in body


def test_fr2581_sync_calls_updater_overlay_after_scripts_robocopy():
    t = SYNC.read_text(encoding="utf-8")
    assert "Sync-BobiverseUpdaterFromOrigin" in t
    # Must run after scripts compose so tip wins over stale robocopy.
    robocopy_idx = t.find("foreach ($d in @('scripts', 'third_party'))")
    call_idx = t.find("Sync-BobiverseUpdaterFromOrigin")
    assert robocopy_idx >= 0 and call_idx > robocopy_idx


def test_fr2581_overlay_writes_tip_when_local_updater_stale(tmp_path: Path):
    """Local common/scripts lacks FR #2563; origin/main tip has it — overlay restores tip."""
    seed = tmp_path / "seed"
    seed.mkdir()
    ident = ["-c", "user.name=t", "-c", "user.email=t@t"]

    def git(cwd, *a, check=True):
        r = subprocess.run(
            ["git", *ident, "-c", "core.autocrlf=false", "-C", str(cwd), *a],
            capture_output=True,
            text=True,
        )
        if check:
            assert r.returncode == 0, (a, r.stdout, r.stderr)
        return r

    def write(p: Path, text: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    git(seed, "init", "-q", "-b", "main")
    write(seed / "common/VERSION", "0.1.24\n")
    write(
        seed / "common/scripts/Update-BobiverseService.ps1",
        "# stale updater\n# no soft-fail\n",
    )
    write(seed / "bob/scripts/b1.ps1", "# b\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "stale")

    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))

    tip = tmp_path / "tip"
    git(tmp_path, "clone", "-q", str(bare), str(tip))
    write(
        tip / "common/scripts/Update-BobiverseService.ps1",
        "# tip updater\n# FR #2563: backup-only Apply failures\nparam([switch]$NoCount)\n",
    )
    git(tip, "add", "-A")
    git(tip, "commit", "-q", "-m", "tip-2563")
    git(tip, "push", "-q", "origin", "main")

    install = tmp_path / "install-bob"
    git(tmp_path, "clone", "-q", str(bare), str(install))
    # Stay on stale HEAD; fetch so origin/main advances (ff blocked by dirty file).
    git(install, "remote", "set-url", "origin", str(bare))
    git(install, "fetch", "-q", "origin")
    write(install / "bob/scripts/bob_worker.py", "# dirty hotpatch\n")
    # flat scripts composed stale
    write(
        install / "scripts/Update-BobiverseService.ps1",
        "# stale flat\n",
    )
    write(
        install / "common/scripts/Update-BobiverseService.ps1",
        "# stale common\n",
    )

    # Dot-source Common from REPO and invoke overlay against install.
    common_ps1 = COMMON.as_posix()
    install_ps = str(install).replace("'", "''")
    ps = f"""
    . '{common_ps1}'
    $r = Sync-BobiverseUpdaterFromOrigin -InstallRoot '{install_ps}' -Branch main
    if (-not $r.Ok) {{ Write-Output ("FAIL:" + $r.Reason); exit 2 }}
    Write-Output ("OK:" + $r.Reason)
    """
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "OK:" in (r.stdout or "")
    flat = (install / "scripts/Update-BobiverseService.ps1").read_text(encoding="utf-8")
    common = (install / "common/scripts/Update-BobiverseService.ps1").read_text(
        encoding="utf-8"
    )
    assert "FR #2563" in flat
    assert "FR #2563" in common
    assert "stale" not in flat.lower() or "tip" in flat.lower()
