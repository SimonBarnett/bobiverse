"""FR #5764: Airc UPDATE preserves service arguments and capability config."""
from __future__ import annotations

from repo_layout import ROOT


UPDATER = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"


def test_fr5764_airc_update_restores_saved_service_state_on_success_and_rollback():
    text = UPDATER.read_text(encoding="utf-8-sig")
    restore = text[
        text.index("function Restore-AircUpdateState") :
        text.index("function Invoke-ServiceReregister")
    ]
    assert "if ($Product -ne 'airc') { return }" in restore
    assert "'airc.json', 'airc-install.json'" in restore
    assert "Copy-Item -LiteralPath $source -Destination $destination -Force" in restore
    assert "carry-over=no-prior-file" in restore
    assert "@('set', $ServiceName, 'AppParameters', $AppParameters)" in restore
    assert "Get-ServiceAppParameters) -cne $AppParameters" in restore
    assert "setting=config\\$name carry-over-failed" in restore
    assert "setting=service-AppParameters carry-over-failed" in restore

    rollback = text[
        text.index("function Invoke-Rollback") :
        text.index("# FR #3639: Get-AircSelfUpdateOperatorsProperty")
    ]
    assert rollback.index("Invoke-ServiceReregister") < rollback.index("Restore-AircUpdateState")
    assert rollback.index("Restore-AircUpdateState") < rollback.index("Start-Service")

    apply = text[text.index("function Invoke-Apply") :]
    assert apply.index("$appParams = Get-ServiceAppParameters") < apply.index("Backup-Install")
    assert apply.index("Restore-AircUpdateState -BackupDir $backup") < apply.index(
        "Start-Service -Name $ServiceName -ErrorAction Stop"
    )


def test_fr5764_restore_logs_setting_names_without_saved_values():
    text = UPDATER.read_text(encoding="utf-8-sig")
    restore = text[
        text.index("function Restore-AircUpdateState") :
        text.index("function Invoke-ServiceReregister")
    ]
    assert "carry-over=restored" in restore
    assert "carry-over-failed" in restore
    assert "Write-UpdLog $AppParameters" not in restore
