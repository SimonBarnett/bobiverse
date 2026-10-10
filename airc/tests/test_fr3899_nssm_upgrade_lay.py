"""FR #3899: airc MSI upgrade must lay nssm.exe (no NeverOverwrite costing skip)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"


def test_fr3899_pack_nssm_permanent_without_neveroverwrite():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "FR #3899" in text
    assert "do NOT set NeverOverwrite on nssm" in text or "no NeverOverwrite" in text
    # Stable GUID + Permanent retained (#70).
    assert "bobiverse-$Name-nssm-component" in text
    assert "SetAttribute('Permanent', 'yes')" in text
    # nssm block must remove NeverOverwrite if heat/prior left it; must not set it on nssm.
    nssm_idx = text.index("nssm.exe component not found")
    nssm_block = text[nssm_idx : nssm_idx + 900]
    assert "SetAttribute('Permanent', 'yes')" in nssm_block
    assert "RemoveAttribute('NeverOverwrite')" in nssm_block
    assert "SetAttribute('NeverOverwrite', 'yes')" not in nssm_block
    # ergo may still use NeverOverwrite (hardlink / Ergo bounce risk).
    assert "bobiverse-$Name-ergo-component" in text


def test_fr3899_install_airc_console_fetches_when_missing():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3899" in text
    assert "Fetch-Nssm" in text
    assert "nssm missing; Fetch-Nssm" in text
    # Still fail closed if fetch cannot restore.
    assert "nssm missing: unpack third_party" in text


def test_fr3899_client_allow_list_keeps_fetch_nssm():
    text = COMMON.read_text(encoding="utf-8-sig")
    start = text.index("function Get-BobiverseAircClientAllowedScriptNames")
    block = text[start : start + 1200]
    assert "'Fetch-Nssm.ps1'" in block or '"Fetch-Nssm.ps1"' in block


def test_fr3899_troubleshooting_documents_nssm_upgrade_gap():
    skill = (
        ROOT
        / "airc"
        / ".grok"
        / "skills"
        / "bobiverse-airc-troubleshooting"
        / "SKILL.md"
    )
    text = skill.read_text(encoding="utf-8")
    assert "FR #3899" in text
    assert "nssm missing" in text
    assert "NeverOverwrite" in text
    assert not skill.read_bytes().startswith(b"\xef\xbb\xbf")
