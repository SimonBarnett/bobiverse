"""v0.1.19 #70: the jeeves MSI must not remove/replace nssm.exe (BobIrcd's service binary); misc install fixes."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
S = ROOT / "scripts"


def _t(name):
    return (S / name).read_text(encoding="utf-8-sig")


def test_pack_marks_nssm_component_permanent_neveroverwrite_with_stable_guid():
    p = _t("Pack-BobiverseRelease.ps1")
    assert "SetAttribute('Permanent', 'yes')" in p and "SetAttribute('NeverOverwrite', 'yes')" in p
    assert "bobiverse-$Name-nssm-component" in p            # stable per-product GUID, not heat's fresh one
    assert "throw 'nssm.exe component not found" in p       # packaging fails loudly rather than silently regress
    assert p.index("heat dir") < p.index("Permanent") < p.index("& $candle")


def test_watch_bobircd_param_typo_fixed_and_file_has_bom_for_ps51():
    raw = (S / "Watch-BobIrcd.ps1").read_bytes()
    t = raw.decode("utf-8-sig")
    assert "$AnnounceDownCooldownMinutes" in t and "CooldownDownCooldownMinutes" not in t
    non_ascii = any(b > 127 for b in raw)
    assert (not non_ascii) or raw.startswith(b"\xef\xbb\xbf"), "BOM-less UTF-8 with non-ASCII breaks Windows PowerShell 5.1"


def test_every_script_with_non_ascii_has_a_bom():
    bad = [p.name for p in S.rglob("*.ps1")
           if any(b > 127 for b in p.read_bytes()) and not p.read_bytes().startswith(b"\xef\xbb\xbf")]
    assert bad == []


def test_sync_from_repo_skips_missing_drive():
    t = _t("Sync-BobiverseFromRepo.ps1")
    assert "Substring(0, 2)" in t and "continue" in t


def test_install_jeeves_warns_when_bobircd_runs_from_the_msi_tree():
    t = _t("Install-Jeeves.ps1")
    assert "Services\\BobIrcd" in t and "#70" in t
