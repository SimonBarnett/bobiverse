"""FR #2301 / WP3: Build-Jeeves + pack stage + Install NSSM cutover (Refs #1993)."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

BUILD = ROOT / "jeeves/scripts/Build-Jeeves.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "jeeves/scripts/Install-Jeeves.ps1"
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"

HIDDEN = (
    "irc_agent",
    "bobcallback",
    "gitclaim",
    "bobreport",
    "intake",
    "chair_commands",
    "chair_health",
    "chair_oper",
    "shop_chanserv",
    "shop_listen",
    "shop_ops",
)


def test_fr2301_build_jeeves_script_hidden_imports():
    text = BUILD.read_text(encoding="utf-8")
    assert "jeeves_main.py" in text
    assert "--name', 'jeeves'" in text or '--name", "jeeves"' in text or "--name', 'jeeves'" in text
    assert "--onefile" in text
    for h in HIDDEN:
        assert h in text, h
    assert "--self-test" in text
    assert not BUILD.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr2301_pack_stages_jeeves_exe_and_skip_gate():
    text = PACK.read_text(encoding="utf-8")
    assert "SkipJeevesExe" in text
    assert "Build-Jeeves.ps1" in text
    assert r"jeeves\jeeves.exe" in text or "jeeves\\jeeves.exe" in text
    assert re.search(r"SkipJeevesExe.{0,120}SkipMsi|SkipMsi.{0,120}SkipJeevesExe", text, re.S)
    assert "2301" in text


def test_fr2301_install_nssm_cutover_and_no_second_callback():
    text = INSTALL.read_text(encoding="utf-8")
    assert r"jeeves\jeeves.exe" in text or "jeeves\\jeeves.exe" in text
    assert "$useJeevesExe" in text
    assert "--chair --http 127.0.0.1:7700" in text
    assert "--digest-home" in text
    assert "skipping Python BobCallback" in text or "skipping Python BobCallback task" in text
    assert "Start-Jeeves.ps1" in text  # legacy path kept
    assert not INSTALL.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr2301_docs_wp3_landed_refs_living_fr():
    text = DOC.read_text(encoding="utf-8")
    assert "2301" in text
    assert "WP3" in text
    assert "never `Closes`" in text or "never Closes" in text or "Refs" in text
    assert "jeeves.exe" in text
