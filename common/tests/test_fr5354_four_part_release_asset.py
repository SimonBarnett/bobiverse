"""FR #5354: four-part release tags/assets must not yield no-matching-asset for bob."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_layout import ROOT

S = ROOT / "scripts"
UPD = S / "Update-BobiverseService.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")
REPO = "SimonBarnett/bobiverse"


def _release(ver: str, product: str = "bob", sha: bool = True) -> dict:
    base = f"https://github.com/{REPO}/releases/download/v{ver}"
    assets = [{"name": f"{product}-{ver}.msi", "browser_download_url": f"{base}/{product}-{ver}.msi"}]
    if sha:
        assets.append(
            {
                "name": f"{product}-{ver}.msi.sha256",
                "browser_download_url": f"{base}/{product}-{ver}.msi.sha256",
            }
        )
    return {"tag_name": f"v{ver}", "assets": assets}


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "bob"
    root.mkdir()
    (root / "VERSION").write_text("0.1.16\n")
    state = tmp_path / "state"

    def run(*extra, release=None, mode="Check"):
        args = [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(UPD),
            "-Product",
            "bob",
            "-InstallRoot",
            str(root),
            "-StateDir",
            str(state),
            "-Mode",
            mode,
        ]
        if release is not None:
            rj = tmp_path / "release.json"
            rj.write_text(json.dumps(release), encoding="utf-8")
            args += ["-ReleaseJson", str(rj)]
        args += list(extra)
        e = {k: v for k, v in os.environ.items() if k not in ("BOB_AUTOUPDATE", "BOBIVERSE_NO_UPDATE")}
        p = subprocess.run(args, capture_output=True, text=True, env=e, timeout=120)
        log = (state / "update.log").read_text(encoding="utf-8") if (state / "update.log").exists() else ""
        return p, log

    return run


@win
def test_fr5354_four_part_bob_msi_matches(env):
    p, log = env("-DryRun", release=_release("1.0.0.1"))
    assert p.returncode == 0
    assert "no-matching-asset" not in log
    assert "would-update local=0.1.16 latest=1.0.0.1" in log


@win
def test_fr5354_four_part_patch_style_matches(env):
    p, log = env("-DryRun", release=_release("0.1.32.2"))
    assert p.returncode == 0
    assert "no-matching-asset" not in log
    assert "would-update" in log and "0.1.32.2" in log


@win
def test_fr5354_three_part_still_matches(env):
    p, log = env("-DryRun", release=_release("0.1.17"))
    assert p.returncode == 0
    assert "no-matching-asset" not in log
    assert "would-update local=0.1.16 latest=0.1.17" in log


def test_fr5354_convertto_ver_and_msi_regex_source():
    text = UPD.read_text(encoding="utf-8-sig")
    assert "FR #5354" in text
    assert r"\d+\.\d+\.\d+(?:\.\d+)?" in text
    assert "Write-CheckFailIntake -Result 'no-matching-asset' -Tag" in text
