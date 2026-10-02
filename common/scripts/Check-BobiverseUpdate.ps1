#Requires -Version 5.1
<#
.SYNOPSIS
  Back-compat wrapper (v0.1.17): delegates to Update-BobiverseService.ps1.
.DESCRIPTION
  The old implementation ran msiexec synchronously from inside the running service (deadlock risk, no
  rollback, no loop guard). Update-BobiverseService.ps1 replaces it: detached helper, sha256 check,
  backup + rollback, loop guard, update.log. -DryRun only decides and logs.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('jeeves', 'bob', 'airc')]
    [string]$Product,
    [string]$Repo = 'SimonBarnett/bobiverse',
    [string]$InstallRoot = '',
    [switch]$DryRun
)
$u = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'Update-BobiverseService.ps1'
$a = @{ Product = $Product; Repo = $Repo; DryRun = $DryRun }
if ($InstallRoot) { $a['InstallRoot'] = $InstallRoot }
& $u @a
exit 0
