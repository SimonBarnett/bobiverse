"""FR #1481: ship the bob-* ear (irc_agent) as self-contained bob-ear.exe."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_layout import ROOT

BOB = ROOT / "bob"
SCRIPTS = ROOT / "scripts"
BUILD = BOB / "scripts" / "Build-BobEar.ps1"
INSTALL_EXE = BOB / "scripts" / "Install-BobEarExe.ps1"
START = BOB / "scripts" / "Start-Bob.ps1"
INSTALL_BOB = BOB / "scripts" / "Install-Bob.ps1"
PACK = SCRIPTS / "Pack-BobiverseRelease.ps1"
DOC = BOB / "docs" / "bob-ear.md"
SKILL = BOB / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")


def test_fr1481_build_and_install_scripts_exist():
    assert BUILD.is_file(), BUILD
    assert INSTALL_EXE.is_file(), INSTALL_EXE
    assert "bob-ear" in BUILD.read_text(encoding="utf-8-sig")
    assert "PyInstaller" in BUILD.read_text(encoding="utf-8-sig")
    assert "bob-ear.exe.bak" in INSTALL_EXE.read_text(encoding="utf-8-sig")
    assert "restored previous" in INSTALL_EXE.read_text(encoding="utf-8-sig")


def test_fr1481_start_bob_prefers_ear_exe():
    t = START.read_text(encoding="utf-8-sig")
    assert "bob-ear.exe" in t
    assert "FR #1481" in t
    assert "via=bob-ear.exe" in t
    assert "irc_agent.py" in t  # fallback
    assert t.index("bob-ear.exe") < t.index("irc_agent.py") or "useEarExe" in t


def test_fr1481_pack_stages_ear_exe():
    t = PACK.read_text(encoding="utf-8-sig")
    assert "SkipEarExe" in t
    assert "Build-BobEar.ps1" in t
    assert "scripts\\bob-ear.exe" in t or "scripts\\bob-ear.exe" in t.replace("/", "\\")
    assert "FR #1481" in t


def test_fr1481_docs_and_skill_mention_exe():
    assert "bob-ear.exe" in DOC.read_text(encoding="utf-8")
    assert "FR #1481" in DOC.read_text(encoding="utf-8")
    sk = SKILL.read_text(encoding="utf-8")
    assert "bob-ear.exe" in sk
    assert "FR #1481" in sk


def test_fr1481_install_bob_notes_missing_ear():
    t = INSTALL_BOB.read_text(encoding="utf-8-sig")
    assert "bob-ear.exe" in t
    assert "FR #1481" in t


@win
def test_fr1481_install_ear_exe_rollback_on_bad_source(tmp_path):
    """Install-BobEarExe restores .bak when the new binary fails smoke."""
    root = tmp_path / "bob"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    good = scripts / "bob-ear.exe"
    # Minimal stub that answers --help like the real ear smoke check expects.
    stub = tmp_path / "good-ear.cmd"
    # Use a tiny PowerShell-built exe substitute: a .bat renamed won't work as .exe.
    # Instead create a previous "good" file and a bad source that is not executable.
    good.write_bytes(b"MZ-fake-prev")
    bad = tmp_path / "bad.exe"
    bad.write_text("not-an-exe", encoding="ascii")
    # SkipSmoke false will try to run bad.exe and fail → restore bak
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSTALL_EXE),
            "-InstallRoot",
            str(root),
            "-SourceExe",
            str(bad),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode != 0
    assert good.read_bytes() == b"MZ-fake-prev"
    assert (scripts / "bob-ear.exe.bak").is_file()
    assert "restored previous" in (r.stdout + r.stderr)
