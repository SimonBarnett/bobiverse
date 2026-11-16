# -*- coding: utf-8 -*-
"""FR #7878: third-party antivirus is warned and named when airc.exe cannot start."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repo_layout import ROOT

AV = ROOT / "common" / "scripts" / "Register-BobiverseAvExclusions.ps1"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"


def _run(tmp: Path, extra: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(AV),
            "-Paths",
            str(tmp / "airc"),
            "-Processes",
            "airc.exe",
            "-Product",
            "airc",
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def test_fr7878_third_party_av_warns_and_reports(tmp_path: Path):
    log = tmp_path / "update.log"
    shop = tmp_path / "outbox.txt"
    r = _run(
        tmp_path,
        [
            "-AntivirusProductsJson",
            json.dumps(["Avast Antivirus"]),
            "-UpdateLog",
            str(log),
            "-ShopOutbox",
            str(shop),
        ],
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "WARN FR #7878" in out
    assert "Avast Antivirus" in out
    assert "airc.exe" in out
    assert str(tmp_path / "airc") in out or "airc" in out
    logged = log.read_text(encoding="utf-8")
    assert "Avast Antivirus" in logged
    assert "PRIVMSG #shop :" in shop.read_text(encoding="ascii")


def test_fr7878_defender_only_is_quiet(tmp_path: Path):
    r = _run(
        tmp_path,
        ["-AntivirusProductsJson", json.dumps(["Windows Defender"])],
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "WARN FR #7878" not in out


def test_fr7878_missing_exe_names_the_av(tmp_path: Path):
    missing = tmp_path / "airc" / "airc.exe"
    r = _run(
        tmp_path,
        [
            "-AntivirusProductsJson",
            json.dumps(["Avast Antivirus"]),
            "-AssertExePath",
            str(missing),
        ],
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 2, out
    assert "ERROR FR #7878" in out
    assert "Avast Antivirus" in out
    assert "airc.exe is missing" in out


def test_fr7878_msi_ca_still_adds_defender_and_warns():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "Add-MpPreference" in text
    assert "root/SecurityCenter2" in text
    assert "FR #7878" in text
    assert 'Custom Action="RunAvExclude" Before="InstallFiles"' in text
