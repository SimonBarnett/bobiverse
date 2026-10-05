"""FR #2564: MSI UI 1603 / rollback must leave a ProgramData log and restart the service.

Acceptance:
1. Documented/required msiexec /l*v path under ProgramData\\Bobiverse\\logs.
2. Install CA / recover path restarts ircBob/Airc/ircJeeves after failed upgrade.
3. Install asserts InstallRoot VERSION matches MSI ProductVersion when supplied (no silent ARP/VERSION lie).
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts"
BOB = ROOT / "bob" / "scripts"
JEEVES = ROOT / "jeeves" / "scripts"
DOCS = ROOT / "common" / "docs"
SKILL = ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_common_exposes_programdata_msi_log_helpers():
    t = _read(COMMON / "Bobiverse-Common.ps1")
    assert "function Get-BobiverseMsiLogDir" in t
    assert "ProgramData" in t and "Bobiverse" in t and "logs" in t
    assert "function Write-BobiverseMsiInstallLog" in t
    assert "function Assert-BobiverseInstallVersion" in t
    assert "function Restore-BobiverseServiceAfterFailedInstall" in t


def test_recover_script_exists_and_starts_service():
    ps1 = COMMON / "Recover-BobiverseService.ps1"
    cmd = COMMON / "Recover-BobiverseService.cmd"
    assert ps1.is_file(), "Recover-BobiverseService.ps1 must ship in common/scripts"
    assert cmd.is_file(), "Recover-BobiverseService.cmd wrapper required for CAQuietExec"
    text = _read(ps1)
    assert "Restore-BobiverseServiceAfterFailedInstall" in text or "Start-Service" in text
    assert "Get-BobiverseMsiLogDir" in text or "Bobiverse" in text
    assert "ircBob" in text and "Airc" in text and "ircJeeves" in text


def test_pack_schedules_rollback_recover_ca():
    p = _read(COMMON / "Pack-BobiverseRelease.ps1")
    assert "RollbackRecover" in p
    assert 'Execute="rollback"' in p
    assert "Recover-BobiverseService.cmd" in p
    assert "MsiProductVersion" in p or "ProductVersion" in p
    assert "-MsiProductVersion" in p


def test_install_bob_logs_and_recovers_on_failure():
    t = _read(BOB / "Install-Bob.ps1")
    assert "Write-BobiverseMsiInstallLog" in t or "Get-BobiverseMsiLogDir" in t
    assert "Restore-BobiverseServiceAfterFailedInstall" in t
    assert "Assert-BobiverseInstallVersion" in t
    assert "MsiProductVersion" in t


def test_install_jeeves_logs_and_recovers_on_failure():
    t = _read(JEEVES / "Install-Jeeves.ps1")
    assert "Write-BobiverseMsiInstallLog" in t or "Get-BobiverseMsiLogDir" in t
    assert "Restore-BobiverseServiceAfterFailedInstall" in t
    assert "Assert-BobiverseInstallVersion" in t
    assert "MsiProductVersion" in t




def test_install_airc_logs_and_recovers_on_failure():
    """MRB #2566 hostile: airc must get the same ProgramData log + recover path as bob/jeeves."""
    airc = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
    t = _read(airc)
    assert "Write-BobiverseMsiInstallLog" in t or "Get-BobiverseMsiLogDir" in t
    assert "Restore-BobiverseServiceAfterFailedInstall" in t
    assert "Assert-BobiverseInstallVersion" in t
    assert "MsiProductVersion" in t
    assert "AircInstallOk" in t
    assert "Install-Airc-catch" in t or "Why 'Install-Airc-catch'" in t


def test_assert_version_empty_is_noop_and_mismatch_throws():
    """MRB #2566: empty ExpectedVersion skips; mismatch must throw (FR #2564)."""
    t = _read(COMMON / "Bobiverse-Common.ps1")
    fn = t[t.index("function Assert-BobiverseInstallVersion") : t.index("function Restore-BobiverseServiceAfterFailedInstall")]
    assert "Empty ExpectedVersion = no-op" in fn or "if (-not $ExpectedVersion" in fn
    assert "throw" in fn and "expected" in fn.lower()


def test_pack_rollback_recover_scheduled_before_runinstall():
    """MRB #2566: WiX Execute=rollback CA must be sequenced before deferred RunInstall."""
    p = _read(COMMON / "Pack-BobiverseRelease.ps1")
    assert 'Execute="rollback"' in p
    assert 'After="RollbackRecover"' in p
    assert 'Return="ignore"' in p


def test_recover_script_always_exits_zero():
    """MRB #2566: rollback CA Return=ignore - recover must never fail the MSI rollback."""
    text = _read(COMMON / "Recover-BobiverseService.ps1")
    assert "exit 0" in text
    assert "ErrorActionPreference = 'Continue'" in text or "$ErrorActionPreference = 'Continue'" in text


def test_post_install_docs_require_lstar_v_under_programdata():
    doc = _read(DOCS / "post-install.md")
    assert "/l*v" in doc
    assert "ProgramData" in doc and "Bobiverse" in doc
    assert "1603" in doc
    assert "self-update" in doc.lower() or "Restart-Service" in doc


def test_fleet_ops_known_failure_row_for_ui_1603():
    skill = _read(SKILL)
    assert "1603" in skill
    assert "ProgramData" in skill or "/l*v" in skill
    assert "FR #2564" in skill
