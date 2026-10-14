"""MRB #3905 hostile pins for FR #3899 nssm MSI upgrade lay (no NeverOverwrite).

After product merge #3905:
- Pack removes NeverOverwrite on nssm; keeps Permanent + stable GUID; ergo still NeverOverwrite
- Install-AircConsole Fetch-Nssm self-heal before throw
- Client allow-list includes Fetch-Nssm.ps1
- Troubleshooting + post-install document the upgrade gap
"""
from __future__ import annotations

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
PRODUCT_PIN = ROOT / "airc" / "tests" / "test_fr3899_nssm_upgrade_lay.py"


def test_mrb3905_pack_nssm_remove_neveroverwrite_contiguous():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "FR #3899" in text
    assert "do NOT set NeverOverwrite on nssm" in text
    nssm_idx = text.index("nssm.exe component not found")
    nssm_block = text[nssm_idx : nssm_idx + 900]
    assert "RemoveAttribute('NeverOverwrite')" in nssm_block
    assert "SetAttribute('Permanent', 'yes')" in nssm_block
    assert "bobiverse-$Name-nssm-component" in text
    assert "SetAttribute('NeverOverwrite', 'yes')" not in nssm_block
    assert "Permanent+stable GUID (no NeverOverwrite; FR #3899)" in text
    # ergo keeps NeverOverwrite (hardlink / bounce).
    ergo_idx = text.index("ergo\\ergo.exe component not found")
    ergo_block = text[ergo_idx - 200 : ergo_idx + 500]
    assert "SetAttribute('NeverOverwrite', 'yes')" in ergo_block


def test_mrb3905_install_fetch_nssm_self_heal_contiguous():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3899" in text
    assert "nssm missing; Fetch-Nssm" in text
    assert "Fetch-Nssm.ps1" in text
    assert "third_party\\nssm\\win64" in text
    assert "nssm missing: unpack third_party" in text


def test_mrb3905_allow_list_and_docs_skill_pins():
    common = COMMON.read_text(encoding="utf-8-sig")
    start = common.index("function Get-BobiverseAircClientAllowedScriptNames")
    block = common[start : start + 1400]
    assert "'Fetch-Nssm.ps1'" in block
    assert "FR #3899" in block

    post = POST.read_text(encoding="utf-8")
    assert "FR #3899" in post
    assert "no `NeverOverwrite`" in post or "no NeverOverwrite" in post
    assert "Fetch-Nssm" in post
    assert not POST.read_bytes().startswith(b"\xef\xbb\xbf")

    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3899" in skill
    assert "NeverOverwrite" in skill
    assert "Fetch-Nssm" in skill
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")

    assert PRODUCT_PIN.is_file(), "product pin test_fr3899_nssm_upgrade_lay.py missing"
