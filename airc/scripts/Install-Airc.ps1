#Requires -Version 5.1
<#
.SYNOPSIS
  Install Airc service (renamed from airc-console). Tree <ai root>\airc (the <drive>:\ai found on the fixed disks), service Airc.
  Nick {machinename}_console — see airc_console_service shop-mode.
#>
[CmdletBinding()]
param(
    [string]$Nssm = '',
    [string]$InstallRoot = '',   # '' = <discovered ai root>\airc (t780u)
    [string]$MachineId = '',
    [string]$ConsoleHome = '',
    [string[]]$Operators = @('Simon'),
    [string]$Python = '',
    [switch]$NoStart,
    [switch]$ForceTools,
    [switch]$SkipCopy,
    # #70: MSI public property SKIPCOPY=1 (optional; FR #2982 also implies SkipCopy from ProductVersion).
    [string]$MsiSkipCopy = '',
    # FR #2564: MSI ProductVersion forwarded by RunInstall for VERSION assert.
    [string]$MsiProductVersion = ''
)

# #70 / FR #2982: MSI property strings + ProductVersion => keep heat-laid files.
if ($MsiSkipCopy -eq '1') { $SkipCopy = $true }
if (([string]$MsiProductVersion).Trim() -match '^\d+\.\d+\.\d+') {
    if (-not $SkipCopy) {
        Write-Host ("INFO FR #2982 MSI ProductVersion={0} -> SkipCopy (keep MSI-laid scripts/skills)" -f $MsiProductVersion.Trim())
    }
    $SkipCopy = $true
}

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# t773u: a split repo checkout (<repo>\<service>\scripts) -> compose the flat scripts dir this installer expects. A stage / install tree is already flat.
$splitRepo = ''
$g = Split-Path -Parent (Split-Path -Parent $here)
if ($g -and (Test-Path -LiteralPath (Join-Path $g 'common\VERSION'))) {
    $splitRepo = $g
    $flat = Join-Path ([IO.Path]::GetTempPath()) ('bobiverse-flat-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path (Join-Path $flat 'scripts') | Out-Null
    foreach ($s in 'common', 'jeeves', 'bob', 'airc') {
        $d = Join-Path $g "$s\scripts"
        if (Test-Path -LiteralPath $d) { Copy-Item -Path (Join-Path $d '*') -Destination (Join-Path $flat 'scripts') -Recurse -Force }
    }
    $here = Join-Path $flat 'scripts'
}
. (Join-Path $here 'Bobiverse-Common.ps1')
# t780u: no hard-coded C:\ai - the <drive>:\ai root is discovered on the fixed disks (BOB_AI_ROOT overrides).
if (-not $InstallRoot) { $InstallRoot = Join-Path (Get-BobiverseAiRoot -Create) 'airc' }


if (-not (Test-BobiverseIsAdmin)) {
    Request-BobiverseUacRelaunch -Bound $PSBoundParameters
}

$repoRoot = if ($splitRepo) { $splitRepo } else { Split-Path -Parent $here }
$bootstrap = Join-Path $here 'Install-BootstrapTools.ps1'
if (Test-Path -LiteralPath $bootstrap) {
    if ($ForceTools) { & $bootstrap -ForceTools } else { & $bootstrap }
}

# FR #2564: CA log under ProgramData\Bobiverse\logs even when UI msiexec omitted /l*v.
Write-BobiverseMsiInstallLog -Product airc -Message ("install-begin installRoot=$InstallRoot msiVer=$MsiProductVersion")
$script:AircInstallOk = $false
try {

# Stage into <ai root>\airc then call legacy Install-AircConsole with new names
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'scripts'), (Join-Path $InstallRoot 'config') | Out-Null
if (-not $SkipCopy) {
    Copy-BobiverseTree -Source $here -Destination (Join-Path $InstallRoot 'scripts') -ContentsOnly
}
Copy-BobiverseVersion -InstallRoot $InstallRoot -RepoRoot $repoRoot -MsiProductVersion $MsiProductVersion
# FR #2564: fail closed when MSI ProductVersion disagrees with the laid VERSION file.
Assert-BobiverseInstallVersion -InstallRoot $InstallRoot -ExpectedVersion $MsiProductVersion -Product airc
Install-BobiverseAgentLayer -RepoRoot $repoRoot -InstallRoot $InstallRoot -Product 'airc'
$skillsSrc = Get-BobiverseRepoMergedDir -Root $repoRoot -Sub '.grok\skills'
if (Test-Path $skillsSrc) {
    $skillsDest = Join-Path $InstallRoot '.grok\skills'
    New-Item -ItemType Directory -Force -Path $skillsDest | Out-Null
    if (-not $SkipCopy) {
        Copy-BobiverseTree -Source $skillsSrc -Destination $skillsDest -ContentsOnly
    }
    Install-BobiverseSkills -RepoSkillsRoot $skillsDest -SkillNames (Get-BobiverseSkillNames -SkillsRoot $skillsDest -Product 'airc')
}

# Package ergo.password into staged config if available on packer
$packErgo = Join-Path $repoRoot 'config\ergo.password'
$destErgo = Join-Path $InstallRoot 'config\ergo.password'
$configDir = Join-Path $InstallRoot 'config'
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
if (-not (Test-Path $destErgo)) {
    foreach ($c in @($packErgo, (Join-Path $env:USERPROFILE '.grok\ergo\connect.password'))) {
        if (Test-Path -LiteralPath $c) {
            Copy-Item -LiteralPath $c -Destination $destErgo -Force
            Write-Host "INFO staged config\ergo.password from $c"
            break
        }
    }
}
# FR #3288: lock staged config secrets (and upgrade existing world-readable ACLs).
if (Get-Command Protect-BobiverseSecretPath -ErrorAction SilentlyContinue) {
    Protect-BobiverseSecretPath -Path $configDir -Recurse
    if (Test-Path -LiteralPath $destErgo) {
        Protect-BobiverseSecretPath -Path $destErgo
    }
}

# FR #1552: MSI / reinstall must keep the live service identity (ConsoleHome, MachineId,
# PasswordFile, OperatorsFile). Never default to the invoking user's profile when Airc
# is already registered — that caused SASL 904 / NickServ 433 after 0.1.20->0.1.21.
# Prefer live AppParameters; fall back to config\airc-install.json when the service is gone.
$priorAppParams = Get-BobiverseServiceAppParameters -ServiceName 'Airc'
$priorId = Get-BobiverseAircIdentityFromAppParameters -AppParameters $priorAppParams
if (-not $priorAppParams) {
    $snapPath = Join-Path $InstallRoot 'config\airc-install.json'
    if (Test-Path -LiteralPath $snapPath) {
        try {
            $snap = Get-Content -LiteralPath $snapPath -Raw -Encoding utf8 | ConvertFrom-Json
            $priorId = [pscustomobject]@{
                ConsoleHome   = [string]($snap.ConsoleHome)
                MachineId     = [string]($snap.MachineId)
                PasswordFile  = [string]($snap.PasswordFile)
                OperatorsFile = [string]($snap.OperatorsFile)
                Launcher      = [string]($snap.Launcher)
                Raw           = ''
            }
            Write-Host "INFO FR #1552: no AppParameters — using $snapPath"
        } catch {
            Write-Host ("WARN airc-install.json read: {0}" -f $_.Exception.Message)
        }
    }
}
if ($priorId -and ($priorId.ConsoleHome -or $priorId.MachineId -or $priorId.PasswordFile -or $priorId.Launcher)) {
    Write-Host 'INFO FR #1552: preserving identity fields from prior install'
    if (-not $ConsoleHome -and $priorId.ConsoleHome) {
        $ConsoleHome = $priorId.ConsoleHome
        Write-Host "INFO preserving ConsoleHome"
    }
    if (-not $MachineId -and $priorId.MachineId) {
        $MachineId = $priorId.MachineId
        Write-Host "INFO preserving MachineId"
    }
}

# Under MSI LocalSystem, USERPROFILE is often C:\Users\Default — that loses the
# Admin NickServ GUID and breaks {machine}_console reclaim (marchhare 2026-09-30).
# Mirror Install-Jeeves: prefer existing Admin home, else InstallRoot\home.
# Only when no prior service identity and no explicit -ConsoleHome.
if (-not $ConsoleHome) {
    $adminHome = Join-Path $env:SystemDrive 'Users\Administrator\.airc'
    if (Test-BobiverseIsLocalSystem) {
        if (Test-Path -LiteralPath $adminHome) {
            $ConsoleHome = $adminHome
            Write-Host "INFO LocalSystem using existing Admin ConsoleHome=$ConsoleHome"
        } else {
            $ConsoleHome = Join-Path $InstallRoot 'home'
            Write-Host "INFO LocalSystem ConsoleHome=$ConsoleHome (avoid Default profile)"
        }
    } else {
        $ConsoleHome = Join-Path $env:USERPROFILE '.airc'
    }
}
# Migrate from .airc-console / Default bake if needed (never when prior ConsoleHome exists).
$legacyCandidates = @(
    (Join-Path $env:USERPROFILE '.airc-console'),
    (Join-Path $env:SystemDrive 'Users\Default\.airc'),
    (Join-Path $env:SystemDrive 'Users\Default\.airc-console')
)
if (-not (Test-Path -LiteralPath $ConsoleHome)) {
    foreach ($legacy in $legacyCandidates) {
        if (Test-Path -LiteralPath $legacy) {
            Copy-Item -LiteralPath $legacy -Destination $ConsoleHome -Recurse -Force
            Write-Host "INFO migrated $legacy -> $ConsoleHome"
            break
        }
    }
}

# Snapshot identity for the next upgrade (opaque paths only; no secret contents).
try {
    $idPath = Join-Path $InstallRoot 'config\airc-install.json'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $idPath) | Out-Null
    $snap = [ordered]@{
        v            = 1
        service      = 'Airc'
        ConsoleHome  = $ConsoleHome
        MachineId    = $MachineId
        PasswordFile = $(if ($priorId.PasswordFile) { $priorId.PasswordFile } else { Join-Path $ConsoleHome 'console.password' })
        OperatorsFile = $(if ($priorId.OperatorsFile) { $priorId.OperatorsFile } else { Join-Path $ConsoleHome 'operators.txt' })
        Launcher     = $(if ($priorId.Launcher -and (Test-Path -LiteralPath $priorId.Launcher)) { $priorId.Launcher } else { '' })
        updated      = (Get-Date).ToUniversalTime().ToString('o')
    }
    ($snap | ConvertTo-Json) | Set-Content -LiteralPath $idPath -Encoding utf8
    Write-Host "INFO wrote $idPath"
} catch {
    Write-Host ("WARN airc-install.json: {0}" -f $_.Exception.Message)
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
# FR #1552: pass through prior PasswordFile / OperatorsFile / Launcher when still on disk.
if ($priorId -and $priorId.PasswordFile -and (Test-Path -LiteralPath $priorId.PasswordFile)) {
    $args.PasswordFile = $priorId.PasswordFile
}
if ($priorId -and $priorId.Launcher -and (Test-Path -LiteralPath $priorId.Launcher)) {
    $args.Launcher = $priorId.Launcher
}
# OperatorsFile is not a direct Install-AircConsole param; Install-AircConsole re-reads
# AppParameters / opsFile. Snapshot still records OperatorsFile for the json fallback.

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

# ONE all-users Start Menu folder "Bobiverse" (shared with bob/jeeves); dedupes older scattered entries.
try {
    [void](Install-BobiverseStartMenu -Product airc -InstallRoot $InstallRoot -MachineId $MachineId)
} catch {
    Write-Host ("WARN Start Menu folder: {0}" -f $_.Exception.Message)
}

Write-Host 'INFO Install-Airc done (service Airc)'
Write-BobiverseMsiInstallLog -Product airc -Message 'install-ok'
$script:AircInstallOk = $true
} catch {
    Write-BobiverseMsiInstallLog -Product airc -Message ("install-fail $($_.Exception.Message)")
    throw
} finally {
    # FR #2564: best-effort Start-Service Airc after a failed RunInstall.
    if (-not $script:AircInstallOk) {
        [void](Restore-BobiverseServiceAfterFailedInstall -ServiceName 'Airc' -Product airc -Why 'Install-Airc-catch')
    }
}
