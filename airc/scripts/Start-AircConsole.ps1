#Requires -Version 5.1
<#
.SYNOPSIS
  Launch airc console service host (FR #253). Use -ServiceMode under NSSM.

.NOTES
  FR #259: do not use $PSScriptRoot in param() defaults. With [CmdletBinding()],
  Windows PowerShell 5.1 leaves $PSScriptRoot empty while evaluating defaults
  (mapped drives / download zips included). Resolve the script dir in the body.

  Never name a parameter $Home - PowerShell's automatic $Home is read-only and
  binding -Home fails with VariableNotWritable (same class of seat bugs).
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$Python = '',
    [string]$HostName = 'irc.ntsa.uk',
    [int]$Port = 6697,
    # Empty/auto -> Python {machine}_console (ChanServ shop) / {machine} lobby.
    [string]$Nick = 'auto',
    # Fleet shop id (ionos/flamingo/...). Prefer BOB_MACHINE_ID over COMPUTERNAME.
    [string]$MachineId = '',
    # Domain/workgroup lobby channel id; default AIRC_CONSOLE_DOMAIN / Windows join.
    [string]$Domain = '',
    # auto | registered | domain-lobby
    [ValidateSet('auto', 'registered', 'domain-lobby')]
    [string]$ShopMode = 'auto',
    [Alias('Home')]
    [string]$ConsoleHome = '',
    [string]$PasswordFile = '',
    [string[]]$Operators = @(),
    [string]$OperatorsFile = '',
    [string[]]$Accounts = @(),
    [switch]$RequireAccount,
    # FR #3287: capability gates (also --shell off|operators on the Python host).
    [ValidateSet('', 'off', 'operators')]
    [string]$ShellMode = '',
    # FR #3401: operators (nick ACL) or irc_ops (channel +o/+h; AIRC_PROFILE=client).
    [ValidateSet('', 'operators', 'irc_ops')]
    [string]$AuthMode = '',
    [ValidateSet('', 'off', 'on')]
    [string]$Jobs = '',
    [ValidateSet('', 'off', 'on')]
    [string]$UpdateCap = '',
    [switch]$TlsInsecure,
    [switch]$ServiceMode,
    # Reserved {machine}_console needs SASL before NICK (Ergo nick reservation).
    # Default on; pass -Sasl:$false only for lab servers without NickServ.
    [switch]$Sasl,
    [switch]$NoSasl,
    [switch]$SelfTest
)
if (-not $PSBoundParameters.ContainsKey('Sasl')) { $Sasl = $true }
if ($NoSasl) { $Sasl = $false }

$ErrorActionPreference = 'Stop'

function Get-AircConsoleScriptDir {
    if ($PSScriptRoot) { return $PSScriptRoot }
    if ($PSCommandPath) { return (Split-Path -Parent $PSCommandPath) }
    if ($MyInvocation.MyCommand.Path) {
        return (Split-Path -Parent $MyInvocation.MyCommand.Path)
    }
    throw 'cannot resolve Start-AircConsole.ps1 directory (FR #259)'
}

$scriptDir = Get-AircConsoleScriptDir
if (-not $RepoRoot -or -not (Test-Path -LiteralPath $RepoRoot)) {
    $RepoRoot = Split-Path -Parent $scriptDir
}

# FR #3289 start-up update policy (config\airc.json + env):
#   sync_from_repo default OFF for MSI (unsigned main must not run as SYSTEM).
#   self_update default ON (sha256-checked release MSI). Lock workstations set both false.
#   BOBIVERSE_NO_UPDATE=1 skips both; BOBIVERSE_SYNC_FROM_REPO / BOBIVERSE_SELF_UPDATE override;
#   BOB_AUTOUPDATE=0 skips self-update only.
function Get-AircStartUpdatePolicy {
    param([Parameter(Mandatory)][string]$InstallRoot)
    $syncOn = $false
    $selfOn = $true
    if ($env:BOBIVERSE_NO_UPDATE -eq '1') {
        return [pscustomobject]@{ SyncFromRepo = $false; SelfUpdate = $false }
    }
    $capPath = Join-Path $InstallRoot 'config\airc.json'
    if (Test-Path -LiteralPath $capPath) {
        try {
            $cap = Get-Content -LiteralPath $capPath -Raw -Encoding utf8 | ConvertFrom-Json
            if ($null -ne $cap.PSObject.Properties['sync_from_repo']) {
                $syncOn = [bool]$cap.sync_from_repo
            }
            if ($null -ne $cap.PSObject.Properties['self_update']) {
                $selfOn = [bool]$cap.self_update
            }
        } catch { }
    }
    if ($env:BOBIVERSE_SYNC_FROM_REPO -eq '1') { $syncOn = $true }
    elseif ($env:BOBIVERSE_SYNC_FROM_REPO -eq '0') { $syncOn = $false }
    if ($env:BOBIVERSE_SELF_UPDATE -eq '1') { $selfOn = $true }
    elseif ($env:BOBIVERSE_SELF_UPDATE -eq '0') { $selfOn = $false }
    if ($env:BOB_AUTOUPDATE -eq '0') { $selfOn = $false }
    return [pscustomobject]@{ SyncFromRepo = $syncOn; SelfUpdate = $selfOn }
}
$aircPolicy = Get-AircStartUpdatePolicy -InstallRoot $RepoRoot
Write-Host ("INFO sync-from-repo={0} (config)" -f $(if ($aircPolicy.SyncFromRepo) { 'on' } else { 'off' }))
Write-Host ("INFO self-update={0} (config)" -f $(if ($aircPolicy.SelfUpdate) { 'on' } else { 'off' }))
$sync = Join-Path $scriptDir 'Sync-BobiverseFromRepo.ps1'
if ($aircPolicy.SyncFromRepo -and (Test-Path -LiteralPath $sync)) {
    try { & $sync -Product airc -InstallRoot $RepoRoot }
    catch { Write-Host "WARN sync-from-repo: $($_.Exception.Message)" }
}
# v0.1.17 self-update on service start: token-less GitHub latest-release check; when newer, a DETACHED
# helper (scheduled task) downloads + sha256-verifies the MSI, replaces the install and rolls back on failure.
if ($ServiceMode -and $aircPolicy.SelfUpdate) {
    $updater = Join-Path $scriptDir 'Update-BobiverseService.ps1'
    if (Test-Path -LiteralPath $updater) {
        try { & $updater -Product airc -InstallRoot $RepoRoot -ServiceName Airc }
        catch { Write-Host "WARN self-update: $($_.Exception.Message)" }
    }
}

$script = Join-Path $scriptDir 'airc_console_service.py'
if (-not (Test-Path -LiteralPath $script)) { throw "missing $script" }

if (-not $ConsoleHome) {
    $ConsoleHome = Join-Path $env:USERPROFILE '.airc-console'
}
New-Item -ItemType Directory -Force -Path $ConsoleHome | Out-Null

# Fleet machine id: explicit > env > refuse Windows hostname-only for service.
if (-not $MachineId) {
    $MachineId = ($env:AIRC_CONSOLE_MACHINE, $env:BOB_MACHINE_ID | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1)
}
if ($MachineId) {
    $MachineId = ($MachineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
    $env:BOB_MACHINE_ID = $MachineId
    $env:AIRC_CONSOLE_MACHINE = $MachineId
    Write-Host "INFO machineId=$MachineId (fleet shop #${MachineId})"
} else {
    Write-Warning ("airc-console: no -MachineId / BOB_MACHINE_ID; falling back to COMPUTERNAME={0}. Pass -MachineId ionos (etc.) so the console joins #ionos, not #win-..." -f $env:COMPUTERNAME)
}

# Seed Ergo server PASS from release zip when ConsoleHome lacks ergo.password.
$ergoDest = Join-Path $ConsoleHome 'ergo.password'
if (-not (Test-Path -LiteralPath $ergoDest) -or -not (Get-Content -LiteralPath $ergoDest -Raw -ErrorAction SilentlyContinue).Trim()) {
    $packagedErgo = Join-Path $RepoRoot 'config\ergo.password'
    if (Test-Path -LiteralPath $packagedErgo) {
        $secret = (Get-Content -LiteralPath $packagedErgo -Raw).Trim()
        if ($secret) {
            [IO.File]::WriteAllText($ergoDest, $secret + "`n", [Text.UTF8Encoding]::new($false))
            Write-Host "INFO seeded ergo.password from package $packagedErgo"
        }
    }
}
if (-not (Test-Path -LiteralPath $ergoDest) -or -not (Get-Content -LiteralPath $ergoDest -Raw -ErrorAction SilentlyContinue).Trim()) {
    if (-not $env:BOB_IRC_PASSWORD -and -not $env:AGENTIC_IRC_PASSWORD -and -not $env:AIRC_CONSOLE_SERVER_PASSWORD) {
        throw 'Ergo server PASS missing: need ConsoleHome\ergo.password or package config\ergo.password (or AGENTIC_IRC_PASSWORD). Without PASS, irc.ntsa.uk drops the TLS link (EOF) - looks like "does not connect".'
    }
}

# Issue #282: LocalSystem service has no user PATH - resolve absolute python.exe.
$resolvePy = Join-Path $scriptDir 'Resolve-AircConsolePython.ps1'
if (Test-Path -LiteralPath $resolvePy) { . $resolvePy }
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    $hint = ''
    if ($ConsoleHome -match '^(.*)\\\.airc-console\\?$') {
        $hint = $Matches[1]
    } elseif ($env:USERPROFILE) {
        $hint = $env:USERPROFILE
    }
    if (Get-Command Resolve-AircConsolePythonPath -ErrorAction SilentlyContinue) {
        $Python = Resolve-AircConsolePythonPath -Preferred $Python -HintUserProfile $hint
    }
}
if (-not $Python) {
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($py) { $Python = $py.Source }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw 'python.exe not found (LocalSystem has no PATH; pass -Python or install Python for all users). Issue #282.'
}
$Python = (Resolve-Path -LiteralPath $Python).Path
Write-Host "INFO python=$Python"

$argsList = @(
    $script,
    '--host', $HostName,
    '--port', "$Port",
    '--nick', $Nick,
    '--home', $ConsoleHome
)
if ($MachineId) {
    $argsList += @('--machine', $MachineId)
}
if (-not $Domain) {
    $Domain = ($env:AIRC_CONSOLE_DOMAIN | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1)
}
if ($Domain) {
    $argsList += @('--domain', $Domain)
}
if (-not $ShopMode -or $ShopMode -eq 'auto') {
    $envMode = ($env:AIRC_CONSOLE_SHOP_MODE | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1)
    if ($envMode) { $ShopMode = $envMode.Trim().ToLowerInvariant() }
}
if ($ShopMode -and $ShopMode -ne 'auto') {
    $argsList += @('--shop-mode', $ShopMode)
} elseif ($ShopMode -eq 'auto') {
    $argsList += @('--shop-mode', 'auto')
}
# #271: always point at console.password - Python mints a GUID if missing.
if (-not $PasswordFile) {
    $PasswordFile = Join-Path $ConsoleHome 'console.password'
}
$argsList += @('--password-file', $PasswordFile)
if ($AuthMode -ne 'irc_ops') {
    if ($OperatorsFile) { $argsList += @('--operators-file', $OperatorsFile) }
    elseif (Test-Path -LiteralPath (Join-Path $ConsoleHome 'operators.txt')) {
        $argsList += @('--operators-file', (Join-Path $ConsoleHome 'operators.txt'))
    }
}
if ($Operators.Count -gt 0) {
    $argsList += '--operators'
    $argsList += $Operators
}
if ($Accounts.Count -gt 0) {
    $argsList += '--accounts'
    $argsList += $Accounts
}
if ($RequireAccount) { $argsList += '--require-account' }
# FR #3287
if ($ShellMode -in @('off', 'operators')) { $argsList += @('--shell-mode', $ShellMode) }
if ($AuthMode -in @('operators', 'irc_ops')) { $argsList += @('--auth-mode', $AuthMode) }
if ($Jobs -in @('off', 'on')) { $argsList += @('--jobs', $Jobs) }
if ($UpdateCap -in @('off', 'on')) { $argsList += @('--update', $UpdateCap) }
if ($TlsInsecure) { $argsList += '--tls-insecure' }
# #34: always pass the choice explicitly (a bare omission must never silently flip it).
if ($Sasl) { $argsList += '--sasl' } else {
    $argsList += '--no-sasl'
    if ($ShopMode -ne 'domain-lobby') {
        Write-Warning "airc-console: --no-sasl in shop mode ($ShopMode): reserved {machine}_console cannot be held without SASL (#34)"
    }
}
if ($SelfTest) { $argsList += '--selftest' }

Write-Host ("INFO Start-AircConsole ServiceMode={0} home={1} sasl={2} scriptDir={3}" -f [bool]$ServiceMode, $ConsoleHome, [bool]$Sasl, $scriptDir)
& $Python @argsList
exit $LASTEXITCODE
