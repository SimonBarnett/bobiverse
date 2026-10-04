"""FR #1432: Airc (and fleet) self-update must bump InstallRoot VERSION when a newer Release MSI exists.

UAT evidence: Restart-Service Airc left VERSION at 0.1.20 while Release v0.1.21 shipped airc-0.1.21.msi.
Root cause class: msiexec exit 0 in maintenance/reconfigure mode after a prior rollback left ARP at the
new ProductCode while files (incl. VERSION) were restored — next /i no-ops and VERSION verify fails/rolls back.
"""
from __future__ import annotations

from repo_layout import ROOT

S = ROOT / "scripts"
UPD = (S / "Update-BobiverseService.ps1").read_text(encoding="utf-8-sig")
START_AIRC = (ROOT / "airc" / "scripts" / "Start-AircConsole.ps1").read_text(encoding="utf-8-sig")
VISION = (ROOT / "common" / "docs" / "vision.md").read_text(encoding="utf-8")


def test_fr1432_start_airc_calls_updater_in_service_mode():
    assert "Update-BobiverseService.ps1" in START_AIRC
    assert "-Product airc" in START_AIRC
    assert "-ServiceName Airc" in START_AIRC
    assert "if ($ServiceMode)" in START_AIRC
    # updater must run before the long-lived python host
    assert START_AIRC.index("Update-BobiverseService.ps1") < START_AIRC.index("airc_console_service.py")


def test_fr1432_apply_stamps_version_when_msi_leaves_stale_file():
    assert "FR #1432" in UPD
    assert "version-stamped-after-msi" in UPD
    assert "installed VERSION is" in UPD
    # MRB #1477: stamp only when post-install ARP DisplayVersion matches target.
    assert "version-stamp-skipped" in UPD
    assert "Get-BobiverseArpProduct" in UPD


def test_fr1432_apply_heals_arp_version_desync_before_msiexec():
    assert "arp-desync-uninstall" in UPD
    assert "Get-BobiverseArpProduct" in UPD or "Uninstall" in UPD
    assert 'bobiverse $Product' in UPD or 'bobiverse {0}' in UPD or '"bobiverse $Product"' in UPD or "bobiverse $Product" in UPD


def test_fr1432_arp_display_name_exact_product():
    # Live ARP rows are "bobiverse airc" / "bobiverse bob" / "bobiverse jeeves".
    assert 'bobiverse $Product' in UPD


def test_fr1432_airc_asset_pattern_matches_release_msi_name():
    # Same matcher Check uses for product-version.msi assets.
    assert r"{0}-(\d+\.\d+\.\d+)\.msi$" in UPD
    assert "airc" in UPD.lower()


def test_fr1432_vision_s4_names_airc():
    assert "S4" in VISION
    assert "airc" in VISION.lower()
    assert "Self-update" in VISION or "self-update" in VISION.lower()
