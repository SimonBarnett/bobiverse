"""MRB #5487: optional intake.py skip must not weaken required harvest .ps1 overlays."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("git"),
    reason="windows + git",
)

COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"


def test_mrb5487_missing_required_harvest_ps1_still_fails(tmp_path: Path):
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

    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    write(seed / "common/VERSION", "0.1.24\n")
    write(
        seed / "common/scripts/Report-BobiverseIntakeIssue.ps1",
        "# Report-BobiverseIntakeIssue posts /bob/v1/intake\n",
    )
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "no-harvest-ps1")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
    install = tmp_path / "install-bob"
    git(tmp_path, "clone", "-q", str(bare), str(install))
    git(install, "remote", "set-url", "origin", str(bare))
    git(install, "fetch", "-q", "origin")

    common_ps1 = COMMON.as_posix()
    install_ps = str(install).replace("'", "''")
    ps = f"""
    . '{common_ps1}'
    $r = Sync-BobiverseHarvestScriptsFromOrigin -InstallRoot '{install_ps}' -Branch main
    if ($r.Ok) {{ Write-Output ("OK:" + $r.Reason); exit 0 }}
    Write-Output ("FAIL:" + $r.Reason)
    exit 2
    """
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "FAIL:" in (r.stdout or "")
    assert "Invoke-BobiverseHarvest" in (r.stdout or "") or "does not exist" in (r.stdout or "").lower()
