#Requires -Version 5.1
<#
.SYNOPSIS
  Install Airc service (renamed from airc-console). Tree C:\ai\airc, service Airc.
  Nick {machinename}_console — see airc_console_service shop-mode.
#>
[CmdletBinding()]
param(
    [string]$Nssm = '',
    [string]$InstallRoot = 'C:\ai\airc',
    [string]$MachineId = '',
    [string]$ConsoleHome = '',
    [string[]]$Operators = @('Simon'),
    [string]$Python = '',
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

# Stage into C:\ai\airc then call legacy Install-AircConsole with new names
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'scripts'), (Join-Path $InstallRoot 'config') | Out-Null
Copy-BobiverseTree -Source $here -Destination (Join-Path $InstallRoot 'scripts') -ContentsOnly
Copy-BobiverseVersion -InstallRoot $InstallRoot -RepoRoot $repoRoot
$skillsSrc = Join-Path $repoRoot '.grok\skills'
if (Test-Path $skillsSrc) {
    $skillsDest = Join-Path $InstallRoot '.grok\skills'
    New-Item -ItemType Directory -Force -Path $skillsDest | Out-Null
    Copy-BobiverseTree -Source $skillsSrc -Destination $skillsDest -ContentsOnly
    Install-BobiverseSkills -RepoSkillsRoot $skillsDest -SkillNames @('bobiverse-airc', 'harvest', 'harvest-agent-skills')
}

# Package ergo.password into staged config if available on packer
$packErgo = Join-Path $repoRoot 'config\ergo.password'
$destErgo = Join-Path $InstallRoot 'config\ergo.password'
if (-not (Test-Path $destErgo)) {
    foreach ($c in @($packErgo, (Join-Path $env:USERPROFILE '.grok\ergo\connect.password'))) {
        if (Test-Path -LiteralPath $c) {
            Copy-Item -LiteralPath $c -Destination $destErgo -Force
            Write-Host "INFO staged config\ergo.password from $c"
            break
        }
    }
}

if (-not $ConsoleHome) { $ConsoleHome = Join-Path $env:USERPROFILE '.airc' }
# Migrate from .airc-console if needed
$legacy = Join-Path $env:USERPROFILE '.airc-console'
if (-not (Test-Path $ConsoleHome) -and (Test-Path $legacy)) {
    Copy-Item -LiteralPath $legacy -Destination $ConsoleHome -Recurse -Force
    Write-Host "INFO migrated $legacy -> $ConsoleHome"
}

$installLegacy = Join-Path $InstallRoot 'scripts\Install-AircConsole.ps1'
$args = @{
    ServiceName = 'Airc'
    ConsoleHome = $ConsoleHome
    Operators   = $Operators
}
if ($Nssm) { $args.Nssm = $Nssm }
if ($MachineId) { $args.MachineId = $MachineId }
if ($Python) { $args.Python = $Python }
if ($NoStart) { $args.NoStart = $true }

# Patch launcher path expectation: Install-AircConsole looks beside itself
try {
    & $installLegacy @args
} catch {
    Write-Host "ERROR Install-AircConsole: $($_.Exception.Message)"
    $report = Join-Path $here 'Report-BobiverseIntakeIssue.ps1'
    if (Test-Path -LiteralPath $report) {
        try {
            & $report -Title 'airc install: Install-AircConsole failed' -Body $_.Exception.Message -InstallRoot $InstallRoot
        } catch {}
    }
    throw
}

# Prefer one console per box: remove leftover agentic_irc AircConsole (distinct UpgradeCode).
Remove-BobiverseLegacyService -Name 'AircConsole' -Nssm $Nssm

Write-Host 'INFO Install-Airc done (service Airc)'
