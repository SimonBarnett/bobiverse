#Requires -Version 5.1
<#
.SYNOPSIS
  Assert NSSM AppExit Default and 0 are Restart for ircJeeves (FR #1055).
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'ircJeeves',
    [string]$Nssm = ''
)

$ErrorActionPreference = 'Stop'
if (-not $Nssm) {
    foreach ($c in @(
        'C:\ai\jeeves\third_party\nssm\win64\nssm.exe',
        'C:\ai\bob\third_party\nssm\win64\nssm.exe'
    )) {
        if (Test-Path -LiteralPath $c) { $Nssm = $c; break }
    }
}
if (-not $Nssm -or -not (Test-Path -LiteralPath $Nssm)) { throw 'nssm.exe not found' }

function Get-NssmValue([string]$Key) {
    $out = & $Nssm get $ServiceName $Key 2>&1 | Out-String
    return ($out -replace '\0','').Trim()
}
function Get-NssmAppExit([string]$Code) {
    $out = & $Nssm get $ServiceName AppExit $Code 2>&1 | Out-String
    return ($out -replace '\0','').Trim()
}

$failures = @()
$def = Get-NssmAppExit 'Default'
$z = Get-NssmAppExit '0'
Write-Host "INFO AppExit Default=$def"
Write-Host "INFO AppExit 0=$z"
if ($def -ne 'Restart') { $failures += "AppExit Default expected Restart got '$def'" }
if ($z -ne 'Restart') { $failures += "AppExit 0 expected Restart got '$z'" }

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svc) { $failures += "service $ServiceName missing" }
else { Write-Host ("INFO service Status={0}" -f $svc.Status) }

if ($failures.Count -gt 0) {
    Write-Host 'FAIL Assert-BobJeevesNssmRestart:'
    $failures | ForEach-Object { Write-Host ("  - " + $_) }
    exit 1
}
Write-Host 'PASS Assert-BobJeevesNssmRestart AppExit Default+0=Restart'
exit 0