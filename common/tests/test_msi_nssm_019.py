"""v0.1.19 #70: the jeeves MSI must not remove/replace nssm.exe (BobIrcd's service binary); misc install fixes."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT, scripts_dirs  # t773u: split repo; legacy flat paths resolve per service
S = ROOT / "scripts"


def _t(name):
    return (S / name).read_text(encoding="utf-8-sig")


def _all_ps1_scripts():
    """Every *.ps1 under common/jeeves/bob/airc scripts/ (split-repo union)."""
    out = []
    for d in scripts_dirs():
        out.extend(sorted(d.rglob("*.ps1")))
    return out


def test_pack_marks_nssm_component_permanent_with_stable_guid():
    """#70 Permanent+stable GUID; FR #3899 drops NeverOverwrite on nssm (upgrade FileCopy gap)."""
    p = _t("Pack-BobiverseRelease.ps1")
    assert "SetAttribute('Permanent', 'yes')" in p
    assert "bobiverse-$Name-nssm-component" in p            # stable per-product GUID, not heat's fresh one
    assert "throw 'nssm.exe component not found" in p       # packaging fails loudly rather than silently regress
    assert p.index("heat dir") < p.index("Permanent") < p.index("& $candle")
    nssm_idx = p.index("nssm.exe component not found")
    nssm_block = p[nssm_idx : nssm_idx + 900]
    assert "RemoveAttribute('NeverOverwrite')" in nssm_block
    assert "SetAttribute('NeverOverwrite', 'yes')" not in nssm_block
    # ergo still uses NeverOverwrite (hardlink / Ergo bounce).
    assert "SetAttribute('NeverOverwrite', 'yes')" in p


def test_watch_bobircd_param_typo_fixed_and_file_has_bom_for_ps51():
    raw = (S / "Watch-BobIrcd.ps1").read_bytes()
    t = raw.decode("utf-8-sig")
    assert "$AnnounceDownCooldownMinutes" in t and "AnnounceDownCoolownMinutes" not in t
    non_ascii = any(b > 127 for b in raw)
    assert (not non_ascii) or raw.startswith(b"\xef\xbb\xbf"), "BOM-less UTF-8 with non-ASCII breaks Windows PowerShell 5.1"


def test_every_script_with_non_ascii_has_a_bom():
    """FR #2301 / #2926: fleet scripts are UTF-8 (BOM optional). Gate valid UTF-8, not a BOM mandate.

    mrb-273: ROOT/"scripts" resolves only to common/scripts; must union all service script dirs.
    """
    bad = []
    for p in _all_ps1_scripts():
        raw = p.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            bad.append(f"{p.parent.parent.name}/{p.parent.name}/{p.name}")
    assert bad == []


def test_invoke_airc_remote_is_ascii_or_bom():
    """FR #238 / #2926: Invoke-AircRemote.ps1 must be valid UTF-8 (BOM optional under FR #2301)."""
    matches = [p for p in _all_ps1_scripts() if p.name == "Invoke-AircRemote.ps1"]
    assert matches, "Invoke-AircRemote.ps1 missing from service scripts/"
    raw = matches[0].read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    raw.decode("utf-8")
    assert b"\xe2\x80\xa6" not in raw  # U+2026 ellipsis must not return


def test_sync_from_repo_skips_missing_drive():
    t = _t("Sync-BobiverseFromRepo.ps1")
    assert "Substring(0, 2)" in t and "continue" in t


def test_install_jeeves_warns_when_bobircd_runs_from_the_msi_tree():
    t = _t("Install-Jeeves.ps1")
    assert "Services\\BobIrcd" in t and "#70" in t
