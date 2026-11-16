"""FR #7877: a failed service start restores the updater backup."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts"
UPDATE = COMMON / "Update-BobiverseService.ps1"
INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"


def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_sources_log_start_failure_and_restore_when_absent():
    common = (COMMON / "Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
    assert "function Find-BobiverseLatestUpdateBackup" in common
    assert "recover-restore service=" in common
    assert "recover-skip service=$ServiceName absent why=$Why" in common
    update = UPDATE.read_text(encoding="utf-8-sig")
    assert "Restore-BobiverseServiceAfterFailedInstall" in update
    ok = update.split("$script:ApplySucceeded = $true", 1)[1].split("} catch {", 1)[0]
    assert "Restore-BobiverseServiceAfterFailedInstall" not in ok
    install = INSTALL.read_text(encoding="utf-8-sig")
    assert "start-fail service=Airc" in install
    assert "Format-BobiverseServiceStartError" in install


def test_absent_service_is_reregistered_from_backup(tmp_path):
    backup = tmp_path / "backup" / "1.0.2-20261115095954" / "tree"
    (backup / "scripts").mkdir(parents=True)
    (backup / "VERSION").write_text("1.0.2\n", encoding="ascii")
    install = tmp_path / "airc"
    install.mkdir()
    outbox = tmp_path / "outbox.txt"
    reported = tmp_path / "reported.txt"
    ps = r"""
$ErrorActionPreference = 'Stop'
. '{common}'
$script:present = $false
$script:copied = ''
$script:registered = ''
$probe = {{ param($Name) if ($script:present) {{ [pscustomobject]@{{ Status = 'Running'; StartType = 'Automatic' }} }} else {{ $null }} }}
$copy = {{ param($Src, $Dst) $script:copied = $Src; New-Item -ItemType Directory -Force -Path $Dst | Out-Null }}
$reg = {{ param($Tree, $Root) $script:registered = $Tree; $script:present = $true }}
$start = {{ param($Name) $script:present = $true }}
$report = {{ param($Name, $Detail) Set-Content -LiteralPath '{reported}' -Value $Detail -Encoding ascii }}
$ok = Restore-BobiverseServiceAfterFailedInstall -ServiceName 'Airc' -Product airc -Why 'msi-rollback' -InstallRoot '{install}' -BackupDir '{backup_parent}' -StartError 'Cannot start service Airc (1053) The service did not respond' -ShopOutbox '{outbox}' -ShopChannel '#joker' -ServiceProbe $probe -CopyTree $copy -RegisterFromBackup $reg -StartService $start -ReportFailure $report
if (-not $ok) {{ throw 'restore returned false' }}
if (-not $script:copied) {{ throw 'tree was not copied' }}
if (-not $script:registered) {{ throw 'service was not re-registered' }}
Write-Output 'RESTORE-OK'
""".format(
        common=str(COMMON / "Bobiverse-Common.ps1"),
        reported=str(reported),
        install=str(install),
        backup_parent=str(backup.parent),
        outbox=str(outbox),
    )
    run = _ps(ps)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "RESTORE-OK" in run.stdout
    assert "1.0.2" in (backup / "VERSION").read_text(encoding="ascii")
    note = reported.read_text(encoding="ascii")
    assert "1053" in note
    shop = outbox.read_text(encoding="utf-8")
    assert shop.startswith("PRIVMSG #joker :")
    assert "1053" in shop


def test_rollback_without_backup_still_reports(tmp_path):
    reported = tmp_path / "reported.txt"
    ps = r"""
$ErrorActionPreference = 'Stop'
. '{common}'
$probe = {{ param($Name) $null }}
$report = {{ param($Name, $Detail) Set-Content -LiteralPath '{reported}' -Value $Detail -Encoding ascii }}
$ok = Restore-BobiverseServiceAfterFailedInstall -ServiceName 'Airc' -Product airc -Why 'msi-rollback' -BackupDir '{missing}' -ServiceProbe $probe -ReportFailure $report
if ($ok) {{ throw 'expected false without a tree' }}
Write-Output 'NO-BACKUP'
""".format(
        common=str(COMMON / "Bobiverse-Common.ps1"),
        reported=str(reported),
        missing=str(tmp_path / "no-such-backup"),
    )
    run = _ps(ps)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "NO-BACKUP" in run.stdout
    assert "absent" in reported.read_text(encoding="ascii").lower() or "no updater backup" in reported.read_text(encoding="ascii")


def test_shop_notice_uses_ear_home_when_outbox_unset(tmp_path):
    """FR #7877: rollback/updater have no worker BOB_OUTBOX; the ear home is the shop sink."""
    ear = tmp_path / "ear-home"
    ear.mkdir()
    ps = r"""
$ErrorActionPreference = 'Stop'
. '{common}'
Remove-Item Env:BOB_OUTBOX -ErrorAction SilentlyContinue
$env:BOB_EAR_HOME = '{ear}'
$env:BOB_MACHINE_ID = 'joker'
$ok = Publish-BobiverseShopNotice -Text 'airc update failed to start Airc: Cannot start service Airc (1053)'
if (-not $ok) {{ throw 'shop notice was not published' }}
Write-Output 'SHOP-OK'
""".format(
        common=str(COMMON / "Bobiverse-Common.ps1"),
        ear=str(ear),
    )
    run = _ps(ps)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "SHOP-OK" in run.stdout
    shop = (ear / "outbox.txt").read_text(encoding="utf-8")
    assert shop.startswith("PRIVMSG #joker :")
    assert "1053" in shop
