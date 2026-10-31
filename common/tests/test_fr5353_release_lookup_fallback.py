"""FR #5353: Get-LatestRelease must survive /releases/latest 404 (prerelease-only catalog).

Fleet !build uses --prerelease --latest=false. When no non-prerelease exists,
GitHub /releases/latest returns 404 and Check logged release-lookup-failed
(flamingo intake). Fall back to listing releases and picking the newest
semver tag that has the product MSI.
"""
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


def _rel(ver: str, product: str = "bob", *, prerelease: bool = True) -> dict:
    base = f"https://github.com/{REPO}/releases/download/v{ver}"
    return {
        "tag_name": f"v{ver}",
        "prerelease": prerelease,
        "draft": False,
        "assets": [
            {
                "name": f"{product}-{ver}.msi",
                "browser_download_url": f"{base}/{product}-{ver}.msi",
            },
            {
                "name": f"{product}-{ver}.msi.sha256",
                "browser_download_url": f"{base}/{product}-{ver}.msi.sha256",
            },
        ],
    }


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "bob"
    root.mkdir()
    (root / "VERSION").write_text("0.1.16\n")
    state = tmp_path / "state"

    def run(*extra, release_list=None, mode="Check", product="bob"):
        args = [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(UPD),
            "-Product",
            product,
            "-InstallRoot",
            str(root),
            "-StateDir",
            str(state),
            "-Mode",
            mode,
            "-DryRun",
            "-ForceCheck",
        ]
        if release_list is not None:
            rj = tmp_path / "release-list.json"
            rj.write_text(json.dumps(release_list), encoding="utf-8")
            args += ["-ReleaseListJson", str(rj)]
        args += list(extra)
        e = {
            k: v
            for k, v in os.environ.items()
            if k not in ("BOB_AUTOUPDATE", "BOBIVERSE_NO_UPDATE")
        }
        p = subprocess.run(args, capture_output=True, text=True, env=e, timeout=120)
        log = (state / "update.log").read_text() if (state / "update.log").exists() else ""
        return p, log

    run.root, run.state, run.tmp = root, state, tmp_path
    return run


def test_fr5353_script_pins_latest_404_fallback():
    text = UPD.read_text(encoding="utf-8-sig")
    assert "FR #5353" in text
    assert "ReleaseListJson" in text
    assert "releases?per_page=" in text or "releases?per_page" in text
    assert "latest-endpoint-404" in text or "Select-BestReleaseFromList" in text
    assert "\u2014" not in text


@win
def test_fr5353_release_list_picks_newest_prerelease_with_product_msi(env):
    """Prerelease-only catalog (no /latest): pick highest bob MSI semver."""
    catalog = [
        _rel("1.0.5", prerelease=True),
        _rel("1.0.6", prerelease=True),
        _rel("1.0.4", product="airc", prerelease=True),
    ]
    p, log = env(release_list=catalog)
    assert p.returncode == 0, log + p.stdout + p.stderr
    assert "would-update local=0.1.16 latest=1.0.6" in log, log
    assert "release-lookup-failed" not in log


@win
def test_fr5353_release_list_prefers_non_prerelease(env):
    catalog = [
        _rel("1.0.9", prerelease=True),
        _rel("1.0.7", prerelease=False),
        _rel("1.0.8", prerelease=True),
    ]
    p, log = env(release_list=catalog)
    assert p.returncode == 0, log
    assert "would-update local=0.1.16 latest=1.0.7" in log, log


@win
def test_fr5353_release_list_empty_of_product_is_no_match(env):
    catalog = [_rel("1.0.6", product="jeeves", prerelease=True)]
    p, log = env(release_list=catalog)
    assert p.returncode == 0, log
    assert "release-lookup-failed" in log or "no-release-data" in log or "no-matching" in log
