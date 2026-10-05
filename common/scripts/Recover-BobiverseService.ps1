#Requires -Version 5.1
<#
.SYNOPSIS
  FR #2564: WiX rollback / failed MSI CA best-effort Start-Service for bob/jeeves/airc.

  Scheduled as Execute=rollback after RunInstall so a 1603 / custom-action failure does not leave
  ircBob/Airc/ircJeeves Stopped (seats wiped). Also callable by hand after a failed UI msiexec.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('bob', 'jeeves', 'airc')][string]$Product,
    [string]$InstallRoot = '',
    [string]$ServiceName = '',
    [string]$Why = 'msi-rollback'
)

$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'Bobiverse-Common.ps1')

if (-not $ServiceName) {
    $ServiceName = switch ($Product) {
        'bob' { 'ircBob' }
        'jeeves' { 'ircJeeves' }
        'airc' { 'Airc' }
    }
}
if (-not $InstallRoot) {
    try { $InstallRoot = Join-Path (Get-BobiverseAiRoot) $Product } catch { $InstallRoot = '' }
}

Write-BobiverseMsiInstallLog -Product $Product -Message ("recover-begin service=$ServiceName installRoot=$InstallRoot why=$Why") -Leaf ("recover-$Product.log")
[void](Restore-BobiverseServiceAfterFailedInstall -ServiceName $ServiceName -Product $Product -Why $Why)
# Always exit 0: rollback CA uses Return=ignore; never block MSI rollback on recover failure.
exit 0
