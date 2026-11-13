"""FR #7167: MSI VERSION newer than clone must not block tip-ok / ComposeOnly compose.

FR #1018 still full-skips when the tip is not trustworthy (stale external clone).
When tip is OK, Sync composes flat scripts and keeps MSI VERSION (no clone VERSION copy).
"""
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


def test_fr7167_sync_documents_tip_ok_compose():
    t = SYNC.read_text(encoding="utf-8-sig")
    assert "FR #7167" in t
    assert "sync-newer-install-compose-tip-ok" in t
    assert "tipOkForNewerInstallCompose" in t
    # Still keeps the FR #1018 full-skip path for stale tips.
    assert "sync-skip-newer-install" in t


def _seed_bob_install(tmp_path: Path, *, file_ver: str, clone_ver: str) -> Path:
    install = tmp_path / "ai" / "bob"
    (install / "bob" / "scripts").mkdir(parents=True)
    (install / "common" / "scripts").mkdir(parents=True)
    (install / "VERSION").write_text(file_ver + "\n", encoding="utf-8")
    (install / "common" / "VERSION").write_text(clone_ver + "\n", encoding="utf-8")
    (install / "bob" / "scripts" / "b1.ps1").write_text("# tip-bob\n", encoding="utf-8")
    (install / "common" / "scripts" / "c_tip.ps1").write_text("# tip-common\n", encoding="utf-8")
    (install / "scripts").mkdir(exist_ok=True)
    (install / "scripts" / "stale.ps1").write_text("# stale-flat\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(install), check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
        cwd=str(install),
        check=True,
        capture_output=True,
    )
    return install


def test_fr7167_compose_only_composes_when_msi_version_newer(tmp_path):
    """ComposeOnly + install 2.0.0 > clone 1.0.8 must robocopy scripts and keep MSI VERSION."""
    install = _seed_bob_install(tmp_path, file_ver="2.0.0", clone_ver="1.0.8")
    env = {**os.environ}
    env.pop("BOBIVERSE_NO_UPDATE", None)
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
            "bob",
            "-InstallRoot",
            str(install),
            "-ComposeOnly",
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
    assert "sync-newer-install-compose-tip-ok" in out, out
    assert "sync-skip-newer-install" not in out, out
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0"
    assert (install / "scripts" / "c_tip.ps1").read_text(encoding="utf-8").startswith("# tip-common")
    # SkipVersionCopyFromClone: MSI stamp kept (message reuses sync-keep-arp-version label).
    assert "sync-keep-arp-version" in out, out


def test_fr7167_stale_external_clone_still_full_skips(tmp_path):
    """FR #1018 path: non-ComposeOnly + BOBIVERSE_REPO (viaWorkTree false) still full-skips."""
    install = _seed_bob_install(tmp_path, file_ver="2.0.0", clone_ver="1.0.8")
    env = {**os.environ}
    env.pop("BOBIVERSE_NO_UPDATE", None)
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
            "bob",
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
    assert "sync-newer-install-compose-tip-ok" not in out, out
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0"
    assert (install / "scripts" / "stale.ps1").read_text(encoding="utf-8").startswith("# stale-flat")
    assert not (install / "scripts" / "c_tip.ps1").exists()
