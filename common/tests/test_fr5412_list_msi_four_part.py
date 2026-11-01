"""FR #5412 / #5429: list fallback must use the same 3- or 4-part MSI regex as Check.

Select-BestReleaseFromList still matched Product-N.N.N.msi only. A 4-part-only
catalog (or mixed) then fell through to an old 3-part tag such as v0.1.17 and
Check logged no-matching-asset even when bob-*.msi existed on the newer tag.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

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
    (root / "VERSION").write_text("0.1.16\n", encoding="utf-8")
    state = tmp_path / "state"

    def run(*extra, release_list=None, release=None):
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
            "Check",
            "-DryRun",
            "-ForceCheck",
        ]
        if release_list is not None:
            rj = tmp_path / "release-list.json"
            rj.write_text(json.dumps(release_list), encoding="utf-8")
            args += ["-ReleaseListJson", str(rj)]
        if release is not None:
            one = tmp_path / "release.json"
            one.write_text(json.dumps(release), encoding="utf-8")
            args += ["-ReleaseJson", str(one)]
        args += list(extra)
        e = {
            k: v
            for k, v in os.environ.items()
            if k not in ("BOB_AUTOUPDATE", "BOBIVERSE_NO_UPDATE")
        }
        # FR #5642: temp InstallRoot defaults allow intake; force local-only unless caller overrides.
        e["BOB_CRASH_REPORT"] = "local-only"
        e["BOBIVERSE_CRASH_REPORT"] = "local-only"
        p = subprocess.run(args, capture_output=True, text=True, env=e, timeout=120)
        log = (state / "update.log").read_text(encoding="utf-8") if (state / "update.log").exists() else ""
        return p, log

    return run


def test_fr5412_list_and_check_share_four_part_msi_regex():
    text = UPD.read_text(encoding="utf-8-sig")
    assert "\u2014" not in text
    assert text.count(r"\d+\.\d+\.\d+(?:\.\d+)?") >= 2
    assert "Select-BestReleaseFromList" in text
    assert "FR #5412" in text or "FR #5429" in text


@win
def test_fr5412_list_picks_four_part_over_old_three_part(env):
    catalog = [
        _rel("0.1.17", prerelease=True),
        _rel("1.0.0.1", prerelease=True),
    ]
    p, log = env(release_list=catalog)
    assert p.returncode == 0, log + p.stdout + p.stderr
    assert "no-matching-asset" not in log, log
    assert "would-update" in log and "1.0.0.1" in log, log
    assert "latest=0.1.17" not in log


@win
def test_fr5412_three_part_v0117_still_matches(env):
    p, log = env(release=_rel("0.1.17", prerelease=False))
    assert p.returncode == 0, log
    assert "no-matching-asset" not in log
    assert "would-update local=0.1.16 latest=0.1.17" in log
