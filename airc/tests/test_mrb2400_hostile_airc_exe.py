"""MRB #2400 hostile: airc.exe PyInstaller pack + NSSM cutover gates (FR #2397)."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

BUILD = ROOT / "airc/scripts/Build-Airc.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "airc/scripts/Install-AircConsole.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
OPS = ROOT / "airc/docs/airc-ops.md"
JEEVES_BUILD = ROOT / "jeeves/scripts/Build-Jeeves.ps1"


def test_mrb2400_build_mirrors_jeeves_onefile_smoke():
    a = BUILD.read_text(encoding="utf-8")
    j = JEEVES_BUILD.read_text(encoding="utf-8")
    for needle in ("--onefile", "--noconfirm", "--clean", "PyInstaller"):
        assert needle in a and needle in j
    assert "--selftest" in a
    assert "--name', 'airc'" in a or '--name", "airc"' in a
    assert "account_map" in a and "airc_console" in a and "airc_jobs" in a


def test_mrb2400_skip_airc_exe_requires_skip_msi():
    text = PACK.read_text(encoding="utf-8")
    assert "SkipAircExe" in text
    assert re.search(
        r"SkipAircExe\s+-and\s+-not\s+\$SkipMsi|SkipAircExe.{0,80}SkipMsi",
        text,
        re.S,
    )
    assert "must never ship" in text
    assert r"airc\airc.exe" in text or "airc\\airc.exe" in text
    assert "Build-Airc.ps1" in text


def test_mrb2400_install_exe_branch_argparse_and_legacy():
    text = INSTALL.read_text(encoding="utf-8")
    assert "$useAircExe" in text
    assert "INFO Airc Application=airc.exe" in text
    assert "INFO Airc Application=powershell" in text
    start = text.index("if ($useAircExe)")
    end = text.index("} else {", start)
    window = text[start:end]
    assert "--home" in window
    assert "--password-file" in window
    assert "--sasl" in window
    assert "--machine" in window
    assert "Start-AircConsole.ps1" in text


def test_mrb2400_identity_parser_argparse_fallback_order():
    text = COMMON.read_text(encoding="utf-8")
    # Prefer PowerShell -ConsoleHome then argparse --home
    i_ch = text.index("Get-BobiverseAppParam -AppParameters $AppParameters -Name 'ConsoleHome'")
    i_home = text.index("Get-BobiverseAppParam -AppParameters $AppParameters -Name 'home'")
    assert i_ch < i_home
    i_pf = text.index("Name 'PasswordFile'")
    i_pfd = text.index("Name 'password-file'")
    assert i_pf < i_pfd


def test_mrb2400_ops_doc_documents_cutover():
    text = OPS.read_text(encoding="utf-8")
    assert "FR #2397" in text
    assert "airc.exe" in text
    assert "Build-Airc.ps1" in text
    assert "--selftest" in text


def test_mrb2400_files_encoding():
    for p in (BUILD, PACK, INSTALL, COMMON, Path(__file__)):
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), p
        assert raw.endswith(b"\n"), p
