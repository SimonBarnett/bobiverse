"""FR #1565: Sync must not clobber MSI ARP VERSION with a newer git clone VERSION."""
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


def test_fr1565_sync_script_has_arp_heal_and_skip():
    t = SYNC.read_text(encoding="utf-8-sig")
    assert "FR #1565" in t
    assert "sync-heal-version-from-arp" in t
    assert "sync-skip-arp-version" in t
    assert "ArpVersionOverride" in t
    assert "Get-BobiverseArpDisplayVersion" in t


def _seed_airc_install(tmp_path: Path, *, file_ver: str, clone_ver: str) -> Path:
    install = tmp_path / "ai" / "airc"
    (install / "airc" / "scripts").mkdir(parents=True)
    (install / "common" / "scripts").mkdir(parents=True)
    (install / "VERSION").write_text(file_ver + "\n", encoding="utf-8")
    (install / "common" / "VERSION").write_text(clone_ver + "\n", encoding="utf-8")
    (install / "airc" / "scripts" / "a1.ps1").write_text("# a\n", encoding="utf-8")
    (install / "common" / "scripts" / "c1.ps1").write_text("# c\n", encoding="utf-8")
    (install / "scripts").mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(install), check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
        cwd=str(install),
        check=True,
        capture_output=True,
    )
    return install


def test_fr1565_arp_blocks_newer_clone_version_and_heals_file(tmp_path):
    """ARP=0.1.21, file wrongly 0.1.22, clone 0.1.22 → heal to 0.1.21 and skip clone copy."""
    install = _seed_airc_install(tmp_path, file_ver="0.1.22", clone_ver="0.1.22")
    env = {**os.environ}
    env.pop("BOBIVERSE_NO_UPDATE", None)
    env["BOBIVERSE_SYNC_FROM_REPO"] = "1"  # FR #3289: sync-off default
    p = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SYNC),
            "-Product",
            "airc",
            "-InstallRoot",
            str(install),
            "-ComposeOnly",
            "-ArpVersionOverride",
            "0.1.21",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out
    assert "sync-heal-version-from-arp" in out, out
    assert "sync-skip-arp-version" in out or "sync-keep-arp-version" in out, out
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "0.1.21"


def test_fr1565_matching_arp_and_clone_still_copies(tmp_path):
    install = _seed_airc_install(tmp_path, file_ver="0.1.21", clone_ver="0.1.21")
    env = {**os.environ}
    env.pop("BOBIVERSE_NO_UPDATE", None)
    env["BOBIVERSE_SYNC_FROM_REPO"] = "1"  # FR #3289: sync-off default
    p = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SYNC),
            "-Product",
            "airc",
            "-InstallRoot",
            str(install),
            "-ComposeOnly",
            "-ArpVersionOverride",
            "0.1.21",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out
    assert "sync-skip-arp-version" not in out
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "0.1.21"


def test_fr1565_no_arp_allows_clone_version_copy(tmp_path):
    """MRB #1577: without ARP (dev / override empty), clone VERSION may refresh the file."""
    install = _seed_airc_install(tmp_path, file_ver="0.1.20", clone_ver="0.1.21")
    env = {**os.environ}
    env.pop("BOBIVERSE_NO_UPDATE", None)
    env["BOBIVERSE_SYNC_FROM_REPO"] = "1"  # FR #3289: sync-off default
    p = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SYNC),
            "-Product",
            "airc",
            "-InstallRoot",
            str(install),
            "-ComposeOnly",
            "-ArpVersionOverride",
            "none",  # sentinel: ignore live ARP on the test host
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out
    assert "sync-skip-arp-version" not in out
    assert "sync-heal-version-from-arp" not in out
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "0.1.21"


def test_fr1565_display_name_compare_is_case_insensitive():
    t = SYNC.read_text(encoding="utf-8-sig")
    assert "ToLowerInvariant()" in t
    assert "DisplayName" in t
