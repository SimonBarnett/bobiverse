#Requires -Version 5.1
<#
.SYNOPSIS
  Clean-install ircJeeves (+ optional BobIrcd if Ergo present). Nick Jeeves.
#>
[CmdletBinding()]
param(
    [string]$Nssm = '',
    [string]$InstallRoot = 'C:\ai\jeeves',
    [string]$ServiceName = 'ircJeeves',
    [string]$Python = '',
    [string]$ChairHome = '',
    [switch]$SkipErgo,
    [switch]$NoStart,
    [switch]$ForceTools
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'Bobiverse-Common.ps1')

if (-not (Test-BobiverseIsAdmin)) {
    Request-BobiverseUacRelaunch -Bound $PSBoundParameters
}

$repoRoot = Split-Path -Parent $here
$bootstrap = Join-Path $here 'Install-BootstrapTools.ps1'
if (Test-Path -LiteralPath $bootstrap) {
    if ($ForceTools) { & $bootstrap -ForceTools } else { & $bootstrap }
}

$Nssm = Resolve-BobiverseNssm -Preferred $Nssm -ScriptDir $here
if (-not $Nssm) { throw 'nssm missing — pack third_party\nssm\win64\nssm.exe or pass -Nssm' }
if (-not $Python) { $Python = Resolve-BobiversePython }
if (-not $ChairHome) { $ChairHome = Join-Path $env:USERPROFILE '.agentic-irc-jeeves' }
New-Item -ItemType Directory -Force -Path $ChairHome | Out-Null
$digestHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'
New-Item -ItemType Directory -Force -Path $digestHome | Out-Null

# Clean prior
Remove-BobiverseService -Nssm $Nssm -Name $ServiceName
Get-ScheduledTask -TaskName 'BobJeeves-chair' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

# Lay tree: copy scripts + skills into InstallRoot
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'scripts') | Out-Null
Copy-Item -Path (Join-Path $here '*') -Destination (Join-Path $InstallRoot 'scripts') -Recurse -Force
Copy-BobiverseVersion -InstallRoot $InstallRoot -RepoRoot $repoRoot
$skillsSrc = Join-Path $repoRoot '.grok\skills'
if (Test-Path $skillsSrc) {
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot '.grok\skills') | Out-Null
    Copy-Item -Path (Join-Path $skillsSrc '*') -Destination (Join-Path $InstallRoot '.grok\skills') -Recurse -Force
    Install-BobiverseSkills -RepoSkillsRoot (Join-Path $InstallRoot '.grok\skills') -SkillNames @('bobiverse-jeeves', 'harvest-agent-skills')
}

# Seed operators for !register
$ops = Join-Path $ChairHome 'operators.txt'
if (-not (Test-Path -LiteralPath $ops)) {
    [IO.File]::WriteAllText($ops, "Simon`n", [Text.UTF8Encoding]::new($false))
}

# Ergo / BobIrcd if present under pack or C:\ai\ergo
if (-not $SkipErgo) {
    $ergoExe = Join-Path $InstallRoot 'ergo\ergo.exe'
    if (-not (Test-Path $ergoExe)) { $ergoExe = 'C:\ai\ergo\ergo.exe' }
    if (Test-Path -LiteralPath $ergoExe) {
        Write-Host "INFO Ergo present at $ergoExe — ensure BobIrcd service separately if needed"
    } else {
        Write-Host 'WARN Ergo binary not in pack yet; install BobIrcd manually or re-pack with ergo payload'
    }
}

$launcher = Join-Path $InstallRoot 'scripts\Start-Jeeves.ps1'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -ChairHome `"$ChairHome`" -Python `"$Python`""

[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('install', $ServiceName, 'powershell.exe'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Application', 'powershell.exe'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppDirectory', (Join-Path $InstallRoot 'scripts')))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppParameters', $appParams))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'DisplayName', 'bobiverse Jeeves chair'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Start', 'SERVICE_AUTO_START'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppExit', 'Default', 'Restart'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'ObjectName', $user))
# Prompt for password is interactive; document that ObjectName may need nssm set ObjectName manually with password.
Write-Host "INFO ObjectName=$user (if service fails logon, run: nssm set $ServiceName ObjectName `"$user`" <password>)"

$envExtra = "BOB_DIGEST_HOME=$digestHome"
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppEnvironmentExtra', $envExtra))

if (-not $NoStart) {
    Start-Service $ServiceName
    Start-Sleep -Seconds 2
}
Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
Write-Host 'INFO Install-Jeeves done'
