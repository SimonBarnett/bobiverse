"""FR #4215: Airc registers AV exclusions before laying airc.exe.

Avast/Defender can refuse creating the unsigned exe during install.
Register-BobiverseAvExclusions.ps1 must exist (Defender + Avast/AVG best-effort);
Install-Airc.ps1 must call it before New-Item/staging; Pack must schedule a
Defender CA Before InstallFiles; docs must mention FR #4215.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

AV = ROOT / "common" / "scripts" / "Register-BobiverseAvExclusions.ps1"
INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
CONSOLE = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
OPS = ROOT / "airc" / "docs" / "airc-ops.md"

WIN = pytest.mark.skipif(os.name != "nt", reason="Windows only")


def test_fr4215_av_script_pins_defender_and_avast():
    raw = AV.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    for needle in (
        "FR #4215",
        "Add-MpPreference",
        "ExclusionPath",
        "ExclusionProcess",
        "AVAST Software",
        "ExcludedFolders",
        "ControlledFolderAccessAllowedApplications",
    ):
        assert needle in text, needle


def test_fr4215_install_airc_calls_av_before_staging():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "Register-BobiverseAvExclusions" in t
    assert "FR #4215" in t
    av = t.find("Register-BobiverseAvExclusions")
    stage = t.find("New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'scripts')")
    assert av >= 0 and stage >= 0
    assert av < stage, "AV exclusions must run before InstallRoot staging New-Item"


def test_fr4215_install_airc_console_calls_av():
    t = CONSOLE.read_text(encoding="utf-8-sig")
    assert "Register-BobiverseAvExclusions" in t
    assert "FR #4215" in t


def test_fr4215_pack_schedules_av_before_installfiles():
    t = PACK.read_text(encoding="utf-8-sig")
    assert "FR #4215" in t
    assert "RunAvExclude" in t
    assert "SetAvExcludeCmd" in t
    assert "Add-MpPreference" in t
    # Sequence pin: RunAvExclude Before InstallFiles
    assert re.search(
        r'Custom Action="RunAvExclude" Before="InstallFiles"',
        t,
    ), "MSI must run AvExclude before InstallFiles"


def test_fr4215_airc_ops_documents_av():
    t = OPS.read_text(encoding="utf-8")
    assert "FR #4215" in t
    assert "Register-BobiverseAvExclusions" in t or "Antivirus" in t


@WIN
def test_fr4215_av_script_whatif_runs(tmp_path: Path):
    target = tmp_path / "ai" / "airc"
    target.mkdir(parents=True)
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(AV),
            "-Paths",
            str(target),
            "-Processes",
            "airc.exe",
            "-Product",
            "airc",
            "-WhatIf",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "FR #4215" in out
    assert "WhatIf" in out or "Defender" in out or "skipped" in out.lower()
