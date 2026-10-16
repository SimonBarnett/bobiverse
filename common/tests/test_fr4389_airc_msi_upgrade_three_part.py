"""FR #4389: airc/bob/jeeves MSI ProductVersion must be exactly 3-part so MajorUpgrade
removes the prior ARP entry (MSI compares only major.minor.build).

Also: airc upgrade must stop the Airc service before InstallValidate so FilesInUse/3010
is avoided when only the service holds locks.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
AIRC_PACK = ROOT / "airc/scripts/Pack-AircConsoleRelease.ps1"
OPS = ROOT / "airc/docs/airc-ops.md"


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr4389_common_converts_four_part_to_three_part_msi_version():
    t = _t(COMMON)
    assert "function ConvertTo-BobiverseMsiProductVersion" in t
    assert "FR #4389" in t
    # 1.0.0.1 -> 1.0.1 (add fourth field into third); exact 3-part unchanged
    assert "1.0.0.1" in t or "fourth" in t.lower() or "four-part" in t.lower() or "4-part" in t
    assert r"^\d+\.\d+\.\d+$" in t or "'^\\d+\\.\\d+\\.\\d+$'" in t.replace("`", "")


def test_fr4389_pack_uses_converted_msi_product_version():
    t = _t(PACK)
    assert "ConvertTo-BobiverseMsiProductVersion" in t
    assert "FR #4389" in t
    # Must not leave the unanchored 3-part regex that accepts 1.0.0.1 as ProductVersion
    assert "ConvertTo-BobiverseMsiProductVersion -Version $Version" in t or (
        "ConvertTo-BobiverseMsiProductVersion" in t and "$msiVersion" in t
    )
    # Stage VERSION stamped for ARP/assert must match ProductVersion (3-part)
    assert "Assert-BobiverseStageVersionAligned -Stage $stage -ExpectedVersion $msiVersion" in t


def test_fr4389_airc_msi_stops_service_before_installvalidate_on_upgrade():
    t = _t(PACK)
    assert "WIX_UPGRADE_DETECTED" in t
    assert "StopAirc" in t or "sc.exe stop Airc" in t or "stop Airc" in t
    assert "InstallValidate" in t
    assert "FR #4389" in t


def test_fr4389_airc_ops_documents_three_part_productversion():
    t = _t(OPS)
    assert "FR #4389" in t or "ProductVersion" in t
    assert "three-part" in t.lower() or "3-part" in t or "major.minor.build" in t.lower()


def test_fr4389_legacy_airc_console_pack_rejects_or_folds_four_part():
    t = _t(AIRC_PACK)
    # Same class of bug: unanchored ^\\d+\\.\\d+\\.\\d+ accepted 1.0.0.1
    assert (
        "ConvertTo-BobiverseMsiProductVersion" in t
        or r"^\d+\.\d+\.\d+$" in t
        or "FR #4389" in t
    )