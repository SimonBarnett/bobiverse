"""FR #5280: bare UPDATE airc = latest GitHub Release MSI; optional pin remains."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import airc_console as ac
from repo_layout import ROOT

UPD = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")
REPO = "SimonBarnett/bobiverse"


def _release(ver: str, product: str = "airc", sha: bool = True) -> dict:
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


def test_fr5280_get_latest_release_uses_latest_api_when_unpinned():
    """FR #5280 / #5447: bare Check hits /releases/latest; FR #5353 list-fallback on 404."""
    t = UPD.read_text(encoding="utf-8-sig")
    fn = t[t.index("function Get-LatestRelease") : t.index("function Test-AssetUrl")]
    assert "/releases/latest" in fn
    assert "/releases/tags/v" in fn
    # Pin path only when ConvertTo-Ver TargetVersion is truthy
    assert "if ($tv)" in fn
    assert re.search(
        r"\$latestUri\s*=\s*\"https://api\.github\.com/repos/\$Repo/releases/latest\"",
        fn,
    )
    assert "latest-endpoint-404" in fn
    assert "Select-BestReleaseFromList" in fn
    assert "releases?per_page=" in fn


def test_fr5280_bare_schedule_omits_target_version(tmp_path, monkeypatch):
    upd = tmp_path / "Update-BobiverseService.ps1"
    upd.write_text(
        "param($Product,$Mode,$InstallRoot,$ServiceName,$TargetVersion,$ForceCheck,$NoSpawn,$DryRun)\n"
        "Write-Output \"STUB product=$Product mode=$Mode tv=[$TargetVersion] force=$ForceCheck\"\n"
        "Write-Output \"check result=current local=0.1.19 latest=0.1.19\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("0.1.19\n", encoding="utf-8")
    recorded: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        recorded.append(list(args))
        return real_run(args, **kwargs)

    monkeypatch.setattr(ac.subprocess, "run", fake_run)
    res = ac.schedule_fleet_update(
        "airc",
        version=None,
        install_root=str(root),
        updater_script=str(upd),
        dry_run=True,
        no_spawn=True,
    )
    assert recorded, "powershell updater must be invoked"
    joined = " ".join(recorded[0])
    assert "-Mode" in recorded[0] or "-mode" in joined.lower()
    assert "Check" in recorded[0]
    assert "-ForceCheck" in recorded[0]
    assert "-TargetVersion" not in recorded[0]
    assert res.ok or res.status in {
        "scheduled",
        "scheduled-nospawn",
        "current",
        "skipped-pending",
        "check-ran",
        "would-update",
    }


def test_fr5280_pin_schedule_passes_target_version(tmp_path, monkeypatch):
    upd = tmp_path / "Update-BobiverseService.ps1"
    upd.write_text(
        "param($Product,$Mode,$InstallRoot,$ServiceName,$TargetVersion,$ForceCheck)\n"
        "Write-Output \"STUB tv=$TargetVersion\"\n"
        "Write-Output \"check result=current local=0.1.19 latest=0.1.20\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("0.1.19\n", encoding="utf-8")
    recorded: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        recorded.append(list(args))
        return real_run(args, **kwargs)

    monkeypatch.setattr(ac.subprocess, "run", fake_run)
    ac.schedule_fleet_update(
        "airc",
        version="0.1.20",
        install_root=str(root),
        updater_script=str(upd),
        no_spawn=True,
    )
    assert recorded
    assert "-TargetVersion" in recorded[0]
    assert "0.1.20" in recorded[0]


@win
def test_fr5280_airc_check_without_target_selects_latest_asset(tmp_path):
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("0.1.16\n", encoding="utf-8")
    state = tmp_path / "state"
    rj = tmp_path / "release.json"
    rj.write_text(json.dumps(_release("0.1.17", product="airc")), encoding="utf-8")
    args = [
        PS,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(UPD),
        "-Product",
        "airc",
        "-InstallRoot",
        str(root),
        "-StateDir",
        str(state),
        "-Mode",
        "Check",
        "-ForceCheck",
        "-DryRun",
        "-ReleaseJson",
        str(rj),
    ]
    # Intentionally omit -TargetVersion (bare UPDATE airc)
    p = subprocess.run(args, capture_output=True, text=True, timeout=120)
    log = (state / "update.log").read_text(encoding="utf-8") if (state / "update.log").exists() else ""
    assert p.returncode == 0, (p.stdout, p.stderr, log)
    assert "would-update local=0.1.16 latest=0.1.17" in log


@win
def test_fr5280_airc_pin_mismatch_and_foreign_url_rejected(tmp_path):
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("0.1.16\n", encoding="utf-8")
    state = tmp_path / "state"

    def run_check(release: dict, *extra: str) -> str:
        rj = tmp_path / f"rel-{len(extra)}-{release['tag_name']}.json"
        rj.write_text(json.dumps(release), encoding="utf-8")
        args = [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(UPD),
            "-Product",
            "airc",
            "-InstallRoot",
            str(root),
            "-StateDir",
            str(state),
            "-Mode",
            "Check",
            "-ForceCheck",
            "-DryRun",
            "-ReleaseJson",
            str(rj),
            *extra,
        ]
        p = subprocess.run(args, capture_output=True, text=True, timeout=120)
        log = (state / "update.log").read_text(encoding="utf-8") if (state / "update.log").exists() else ""
        assert p.returncode == 0, (p.stdout, p.stderr, log)
        return log

    log = run_check(_release("0.1.17"), "-TargetVersion", "0.1.99")
    assert "target-version-mismatch" in log
    assert "would-update" not in log

    evil = _release("0.1.17")
    for a in evil["assets"]:
        a["browser_download_url"] = "https://evil.example/x/" + a["name"]
    log = run_check(evil)
    assert "asset-url-rejected" in log
    assert "would-update" not in log


def test_fr5280_docs_state_bare_is_latest():
    remote = (ROOT / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "bare" in remote.lower() or "no version" in remote.lower() or "latest" in remote.lower()
    assert "UPDATE airc" in remote
    assert "TargetVersion" in remote or "latest" in remote.lower()
    vision = (ROOT / "airc/docs/feature-request-airc-remote-update-restart-2026-10-31.md").read_text(
        encoding="utf-8"
    )
    assert "no version pin = latest" in vision or "Bare `UPDATE airc`" in vision or "Bare UPDATE" in vision
