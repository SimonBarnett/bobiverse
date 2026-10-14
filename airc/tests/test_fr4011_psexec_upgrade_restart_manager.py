"""FR #4011: PsExec SYSTEM msiexec upgrade must not hit Restart Manager 351 / exit 1601.

Root cause: MajorUpgrade RemoveExistingProducts under session 0 (psexec -h -s) lets
Restart Manager try to shut down Airc; RM error 351 then crashes Windows Installer (1601).
Fix: bake MSIRESTARTMANAGERCONTROL=Disable; stop Airc before RemoveExistingProducts.
"""

from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
UPDATER = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"
OPS = ROOT / "airc" / "docs" / "airc-ops.md"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def _pack() -> str:
    return PACK.read_text(encoding="utf-8-sig")


def test_fr4011_pack_disables_restart_manager():
    text = _pack()
    assert "FR #4011" in text
    assert 'MSIRESTARTMANAGERCONTROL" Value="Disable"' in text or (
        "MSIRESTARTMANAGERCONTROL" in text and 'Value="Disable"' in text
    )


def test_fr4011_airc_stops_service_before_removeexistingproducts():
    text = _pack()
    assert "StopAircBeforeUpgrade" in text
    assert "SetStopAircUpgradeCmd" in text
    assert 'Before="RemoveExistingProducts"' in text
    assert "WIX_UPGRADE_DETECTED" in text
    assert "sc.exe" in text and "stop Airc" in text
    # Keep FR #1566 uninstall path (full /x) separate from upgrade stop.
    assert 'NOT UPGRADINGPRODUCTCODE' in text
    assert "RunUninstall" in text


def test_fr4011_ops_documents_psexec_property_and_checklist():
    text = OPS.read_text(encoding="utf-8-sig")
    assert "FR #4011" in text
    assert "MSIRESTARTMANAGERCONTROL=Disable" in text
    assert "1601" in text or "Restart Manager" in text
    assert "psexec" in text.lower()


def test_fr4011_troubleshooting_row():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4011" in text
    assert "1601" in text
    assert "MSIRESTARTMANAGERCONTROL" in text
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr4011_updater_passes_restart_manager_disable():
    text = UPDATER.read_text(encoding="utf-8-sig")
    assert "FR #4011" in text
    assert "MSIRESTARTMANAGERCONTROL=Disable" in text
