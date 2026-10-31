"""FR #1018: Sync-BobiverseFromRepo must not overwrite a newer installed VERSION with an older clone."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from repo_layout import REPO

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell") or not shutil.which("git"),
    reason="windows powershell+git",
)

SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")


def test_sync_skips_when_install_version_newer_than_clone(tmp_path):
    """MSI stamped InstallRoot\\VERSION=0.1.21; split-repo common\\VERSION still 0.1.20 — must refuse robocopy."""
    install = tmp_path / "ai" / "jeeves"
    (install / "jeeves" / "scripts").mkdir(parents=True)
    (install / "common" / "scripts").mkdir(parents=True)
    (install / "VERSION").write_text("0.1.21\n", encoding="utf-8")  # MSI stamp
    (install / "common" / "VERSION").write_text("0.1.20\n", encoding="utf-8")  # dirty clone
    (install / "jeeves" / "scripts" / "j1.ps1").write_text("# j\n", encoding="utf-8")
    (install / "common" / "scripts" / "c1.ps1").write_text("# c\n", encoding="utf-8")
    (install / "scripts").mkdir(exist_ok=True)
    (install / "scripts" / "keep.ps1").write_text("# keep\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(install), check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
        cwd=str(install),
        check=True,
        capture_output=True,
    )

    env = {**os.environ}
    env.pop("BOBIVERSE_NO_UPDATE", None)
    # FR #5479: live HKLM ARP / BOBIVERSE_REPO must not stamp this fixture (0.1.31 heal).
    env["BOB_AI_ROOT"] = str(tmp_path)
    env["BOBIVERSE_REPO"] = str(install)
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
            "-ArpVersionOverride",
            "none",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out
    assert "sync-skip-newer-install" in out, out
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "0.1.21"
    assert (install / "scripts" / "keep.ps1").read_text(encoding="utf-8").startswith("# keep")


def test_fr5479_1018_isolates_arp_and_repo():
    src = Path(__file__).read_text(encoding="utf-8")
    assert "-ArpVersionOverride" in src
    assert '"none"' in src
    assert "BOBIVERSE_REPO" in src
    assert "FR #5479" in src
