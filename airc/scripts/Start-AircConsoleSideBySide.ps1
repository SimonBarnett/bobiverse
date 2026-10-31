#Requires -Version 4.0
<#
.SYNOPSIS
  Detached from-source / tip airc console beside the production Airc service (FR #5079).

.DESCRIPTION
  Starts airc_console_service.py with a distinct -Nick and -ConsoleHome so production
  marchhare_console (NSSM Airc) stays untouched. Logs via Python --log-file (child-owned
  handle). Do NOT use Start-Process -RedirectStandardOutput/-RedirectStandardError for a
  long-lived console: when the parent PowerShell exits, those pipes close and the host
  dies after NAMES sync with an empty stderr (FR #5079 / live MarchHare #5069 retest).

.EXAMPLE
  .\Start-AircConsoleSideBySide.ps1 -Nick marchhare_t5069_console -ConsoleHome D:\tmp\t5069-home
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$Python = '',
    [Parameter(Mandatory = $true)]
    [string]$Nick,
    [string]$MachineId = '',
    [ValidateSet('auto', 'registered', 'wonderland', 'domain-lobby')]
    [string]$ShopMode = 'registered',
    [Alias('Home')]
    [Parameter(Mandatory = $true)]
    [string]$ConsoleHome,
    [string]$PasswordFile = '',
    [string]$HostName = 'irc.ntsa.uk',
    [int]$Port = 993,
    [ValidateSet('', 'off', 'operators')]
    [string]$ShellMode = 'operators',
    [ValidateSet('', 'off', 'on')]
    [string]$Jobs = 'on',
    [ValidateSet('', 'off', 'on')]
    [string]$UpdateCap = 'off',
    [ValidateSet('', 'off', 'on')]
    [string]$ExtensionCap = 'off',
    [switch]$Sasl,
    [switch]$NoSasl,
    [string]$LogFile = '',
    [string]$PidFile = ''
)

if (-not $PSBoundParameters.ContainsKey('Sasl')) { $Sasl = $true }
if ($NoSasl) { $Sasl = $false }

$ErrorActionPreference = 'Stop'

function Get-AircSideBySideScriptDir {
    if ($PSScriptRoot) { return $PSScriptRoot }
    if ($PSCommandPath) { return (Split-Path -Parent $PSCommandPath) }
    if ($MyInvocation.MyCommand.Path) {
        return (Split-Path -Parent $MyInvocation.MyCommand.Path)
    }
    throw 'cannot resolve Start-AircConsoleSideBySide.ps1 directory (FR #259)'
}

$scriptDir = Get-AircSideBySideScriptDir
if (-not $RepoRoot -or -not (Test-Path -LiteralPath $RepoRoot)) {
    $RepoRoot = Split-Path -Parent $scriptDir
}

if (-not $MachineId) {
    $MachineId = if ($env:BOB_MACHINE_ID) { $env:BOB_MACHINE_ID }
    elseif ($env:AIRC_CONSOLE_MACHINE) { $env:AIRC_CONSOLE_MACHINE }
    else { $env:COMPUTERNAME.ToLowerInvariant() }
}
$MachineId = ($MachineId -replace '[^a-zA-Z0-9\-]', '').ToLowerInvariant()
if (-not $MachineId) { throw 'MachineId empty' }

if (-not (Test-Path -LiteralPath $ConsoleHome)) {
    New-Item -ItemType Directory -Path $ConsoleHome -Force | Out-Null
}
$logDir = Join-Path $ConsoleHome 'logs'
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
if (-not $LogFile) { $LogFile = Join-Path $logDir 'side-by-side.log' }
if (-not $PidFile) { $PidFile = Join-Path $ConsoleHome 'side-by-side.pid' }
if (-not $PasswordFile) {
    $PasswordFile = Join-Path $ConsoleHome 'console.password'
}

$resolvePy = Join-Path $scriptDir 'Resolve-AircConsolePython.ps1'
if (-not $Python) {
    if (Test-Path -LiteralPath $resolvePy) {
        $Python = & $resolvePy -RepoRoot $RepoRoot
    } else {
        $Python = (Get-Command python.exe -ErrorAction Stop).Source
    }
}

$hostPy = Join-Path $scriptDir 'airc_console_service.py'
if (-not (Test-Path -LiteralPath $hostPy)) {
    throw "missing airc_console_service.py under $scriptDir"
}

# Prefer tip scripts on PYTHONPATH when RepoRoot is a worktree.
$tipScripts = Join-Path $RepoRoot 'airc\scripts'
$commonScripts = Join-Path $RepoRoot 'common\scripts'
$env:PYTHONPATH = (@($tipScripts, $scriptDir, $commonScripts) -join ';')
$env:PYTHONUNBUFFERED = '1'
$env:BOBIVERSE_NO_UPDATE = '1'

$argList = @(
    '-u', $hostPy,
    '--host', $HostName,
    '--port', "$Port",
    '--tls',
    '--nick', $Nick,
    '--machine', $MachineId,
    '--shop-mode', $ShopMode,
    '--home', $ConsoleHome,
    '--password-file', $PasswordFile,
    '--log-file', $LogFile,
    '--auth-mode', 'irc_ops'
)
if ($Sasl) { $argList += '--sasl' } else { $argList += '--no-sasl' }
if ($ShellMode -in @('off', 'operators')) { $argList += @('--shell-mode', $ShellMode) }
if ($Jobs -in @('off', 'on')) { $argList += @('--jobs', $Jobs) }
if ($UpdateCap -in @('off', 'on')) { $argList += @('--update', $UpdateCap) }
if ($ExtensionCap -in @('off', 'on')) { $argList += @('--extension', $ExtensionCap) }

Write-Host ("INFO FR #5079 side-by-side nick={0} home={1} log={2}" -f $Nick, $ConsoleHome, $LogFile)
Write-Host 'INFO do not use Start-Process -RedirectStandardOutput for long-lived consoles (parent exit closes pipes)'

# Detached: no RedirectStandard*; child owns --log-file.
$p = Start-Process -FilePath $Python -ArgumentList $argList -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden -PassThru
[System.IO.File]::WriteAllText($PidFile, "$($p.Id)`n", (New-Object System.Text.UTF8Encoding $false))
Write-Host ("INFO started pid={0} pidfile={1}" -f $p.Id, $PidFile)
Write-Output ([pscustomobject]@{
    Pid      = $p.Id
    PidFile  = $PidFile
    LogFile  = $LogFile
    Nick     = $Nick
    Home     = $ConsoleHome
})
