"""FR #2397: Build-Airc + pack stage airc.exe + Install NSSM cutover (Jeeves WP3 pattern)."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

BUILD = ROOT / "airc/scripts/Build-Airc.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "airc/scripts/Install-AircConsole.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
SERVICE = ROOT / "airc/scripts/airc_console_service.py"
THIS = Path(__file__)

MOJIBAKE_DASH = ("\u00e2" + "\u20ac")

HIDDEN = ("account_map", "airc_console", "airc_jobs")


def test_fr2397_build_airc_script_hidden_imports():
    text = BUILD.read_text(encoding="utf-8")
    assert "airc_console_service.py" in text
    assert "--name', 'airc'" in text or '--name", "airc"' in text
    assert "--onefile" in text
    for h in HIDDEN:
        assert h in text, h
    assert "--selftest" in text
    assert "--help" in text
    assert not BUILD.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr2397_pack_stages_airc_exe_and_skip_gate():
    text = PACK.read_text(encoding="utf-8")
    assert "SkipAircExe" in text
    assert "Build-Airc.ps1" in text
    assert r"airc\airc.exe" in text or "airc\\airc.exe" in text
    assert re.search(r"SkipAircExe.{0,120}SkipMsi|SkipMsi.{0,120}SkipAircExe", text, re.S)
    assert "2397" in text


def test_fr2397_install_nssm_cutover_preserves_legacy():
    text = INSTALL.read_text(encoding="utf-8")
    assert r"airc\airc.exe" in text or "airc\\airc.exe" in text
    assert "$useAircExe" in text
    assert "--home" in text
    assert "--password-file" in text
    assert "--sasl" in text
    assert "Start-AircConsole.ps1" in text  # legacy path kept
    assert "FR #2397" in text
    assert not INSTALL.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr2397_identity_parser_accepts_argparse_home():
    text = COMMON.read_text(encoding="utf-8")
    assert "password-file" in text
    assert "operators-file" in text
    assert "FR #2397" in text
    # Get-BobiverseAppParam single-dash match covers --home via Name 'home'
    assert "Get-BobiverseAppParam -AppParameters $AppParameters -Name 'home'" in text


def test_fr2397_service_selftest_flag_present():
    text = SERVICE.read_text(encoding="utf-8")
    assert "--selftest" in text
    assert "def selftest(" in text


def test_fr2397_encoding_utf8_no_bom_no_mojibake():
    for path in (BUILD, PACK, INSTALL, COMMON, THIS):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path}"
        assert raw.endswith(b"\n"), f"missing trailing newline in {path}"
        text = raw.decode("utf-8")
        assert "\ufeff" not in text
        if path != THIS:
            assert MOJIBAKE_DASH not in text, f"mojibake in {path}"
