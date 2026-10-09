#Requires -Version 4.0
<#
.SYNOPSIS
  Install Airc service (renamed from airc-console). Tree <ai root>\airc (the <drive>:\ai found on the fixed disks), service Airc.
  Nick {machinename}_console - see airc_console_service shop-mode.
#>
[CmdletBinding()]
param(
    [string]$Nssm = '',
    [string]$InstallRoot = '',   # '' = <discovered ai root>\airc (t780u)
    [string]$MachineId = '',
    [string]$ConsoleHome = '',
    # FR #3639: retired (no operators list; auth is live control-channel +o/+h). Accepted, ignored.
    [string[]]$Operators = @(),
    [string]$Python = '',
    [switch]$NoStart,
    [switch]$ForceTools,
    # FR #3290: opt-in agent toolchain (git/gh/python/node). Fresh airc.exe MSI skips by default.
    [switch]$WithTools,
    [string]$InstallTools = '',   # MSI AIRC_INSTALL_TOOLS=1
    [switch]$SkipCopy,
    # #70: MSI public property SKIPCOPY=1 (optional; FR #2982 also implies SkipCopy from ProductVersion).
    [string]$MsiSkipCopy = '',
    # FR #2564: MSI ProductVersion forwarded by RunInstall for VERSION assert.
    [string]$MsiProductVersion = '',
    # FR #3287: MSI AIRC_SHELL / AIRC_JOBS / AIRC_UPDATE / AIRC_REQUIRE_ACCOUNT / AIRC_ACCOUNTS.
    [string]$ShellMode = '',
    [string]$Jobs = '',
    [string]$UpdateCap = '',
    [string]$RequireAccount = '',
    [string]$Accounts = '',
    # FR #3639: retired MSI AIRC_OPERATORS / -OperatorsExtra. Accepted (old callers bind), logged, ignored.
    [string]$OperatorsExtra = '',
    # FR #3289: MSI AIRC_SYNC_FROM_REPO / AIRC_SELF_UPDATE (0|1|true|false; empty = preserve / fresh default).
    [string]$SyncFromRepo = '',
    [string]$SelfUpdate = '',
    # FR #3292 / #3401: MSI AIRC_PROFILE=fleet|workstation|client; AIRC_AGENT_LAYER=0 skips agent briefings/skills.
    [string]$Profile = '',
    [string]$AgentLayer = '',
    # FR #3291: MSI BOBIVERSE_CRASH_REPORT (0|off|local-only|1|full|no-log-tail; empty = preserve / shell=off default).
    [string]$CrashReport = ''
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
# FR #3290: frozen airc.exe needs no git/gh/python/node. Skip bootstrap unless opt-in or legacy (no exe).
$installToolsOn = $WithTools -or $ForceTools
$itRaw = ([string]$InstallTools).Trim().ToLowerInvariant()
if ($itRaw -in @('1', 'true', 'yes', 'on')) { $installToolsOn = $true }
$hasAircExe = $false
foreach ($cand in @(
        (Join-Path $InstallRoot 'airc\airc.exe'),
        (Join-Path $InstallRoot 'airc.exe'),
        (Join-Path $repoRoot 'airc\airc.exe'),
        (Join-Path $repoRoot 'airc.exe')
    )) {
    if ($cand -and (Test-Path -LiteralPath $cand)) { $hasAircExe = $true; break }
}
$bootstrap = Join-Path $here 'Install-BootstrapTools.ps1'
if (Test-Path -LiteralPath $bootstrap) {
    if ($installToolsOn) {
        if ($ForceTools) { & $bootstrap -ForceTools } else { & $bootstrap }
    } elseif (-not $hasAircExe) {
        Write-Host 'INFO bootstrap-tools legacy (no airc.exe; installing agent toolchain)'
        & $bootstrap
    } else {
        Write-Host 'INFO bootstrap-tools skipped (airc exe; AIRC_INSTALL_TOOLS not set) FR #3290'
    }
}

# FR #2564 / #3652: write install-begin FIRST so CA / install-airc.log show progress
# even if a later ACL pass is slow. Get-BobiverseMsiLogDir already uses LogsOnly.
Write-BobiverseMsiInstallLog -Product airc -Message ("install-begin installRoot=$InstallRoot msiVer=$MsiProductVersion")

# FR #3394 / #3652: lock ProgramData\Bobiverse root + logs only. Default Full -Recurse
# walks update\bob + update\jeeves self-update backups (100k+ files on fleet boxes) and
# hung ionos airc upgrades 55+ min. Jeeves/bob MSI log paths already use LogsOnly.
Ensure-BobiverseProgramDataRoot -FailClosed -ProtectMode LogsOnly | Out-Null
$script:AircInstallOk = $false
# FR #3584: inner Install-AircConsole catch may already have filed intake before rethrow.
$script:AircInstallFailReported = $false
# FR #3759: PS 4.0 powershell.exe -File leaves process exit 0 on uncaught throw.
# Track nonzero exit explicitly; call exit after finally so Install-Airc.cmd sees it.
$script:AircExitCode = 0
try {

# Stage into <ai root>\airc then call legacy Install-AircConsole with new names
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'scripts'), (Join-Path $InstallRoot 'config') | Out-Null
# FR #3394 / FR #3678: lock install-root directory (not -Recurse) before copy so the
# folder itself is not user-writable; CI|OI ACEs cover new children. One Full
# -Recurse FailClosed runs after Install-AircConsole before Start-Service
# (ionos: two -Recurse + takeown /R passes cost ~12 min on ~5k items).
Protect-BobiverseInstallTree -Path $InstallRoot -FailClosed
if (-not $SkipCopy) {
    Copy-BobiverseTree -Source $here -Destination (Join-Path $InstallRoot 'scripts') -ContentsOnly
}
Copy-BobiverseVersion -InstallRoot $InstallRoot -RepoRoot $repoRoot -MsiProductVersion $MsiProductVersion
# FR #2564: fail closed when MSI ProductVersion disagrees with the laid VERSION file.
Assert-BobiverseInstallVersion -InstallRoot $InstallRoot -ExpectedVersion $MsiProductVersion -Product airc

# FR #3292: workstation / AgentLayer=0 -> no agent briefings or skills (agent-free box).
$prof = ([string]$Profile).Trim().ToLowerInvariant()
if ($prof -notin @('fleet', 'workstation', 'client')) { $prof = '' }
$agentLayerRaw = ([string]$AgentLayer).Trim().ToLowerInvariant()
$wantAgentLayer = $true
if ($prof -in @('workstation', 'client')) { $wantAgentLayer = $false }
if ($agentLayerRaw -in @('0', 'false', 'no', 'off')) { $wantAgentLayer = $false }
if ($agentLayerRaw -in @('1', 'true', 'yes', 'on')) { $wantAgentLayer = $true }
if (-not $prof) { $prof = $(if ($wantAgentLayer) { 'fleet' } else { 'workstation' }) }
$script:AircInstallProfile = $prof
$script:AircWantAgentLayer = $wantAgentLayer
$script:AircManifestPaths = New-Object System.Collections.Generic.List[string]

if ($wantAgentLayer) {
    Install-BobiverseAgentLayer -RepoRoot $repoRoot -InstallRoot $InstallRoot -Product 'airc'
    $skillsSrc = Get-BobiverseRepoMergedDir -Root $repoRoot -Sub '.grok\skills'
    if (Test-Path $skillsSrc) {
        $skillsDest = Join-Path $InstallRoot '.grok\skills'
        New-Item -ItemType Directory -Force -Path $skillsDest | Out-Null
        if (-not $SkipCopy) {
            Copy-BobiverseTree -Source $skillsSrc -Destination $skillsDest -ContentsOnly
        }
        # FR #3292: install-root skills only - never copy into the installing user's profile from airc MSI.
        Write-Host ("INFO FR #3292 skills under install root only: {0}" -f $skillsDest)
        [void]$script:AircManifestPaths.Add($skillsDest)
    }
} else {
    Write-Host 'INFO agent-layer skipped (workstation|client / AIRC_AGENT_LAYER=0) FR #3292/#3401'
    # FR #3392: workstation deny-list strip of agent briefings/scripts.
    # FR #3514: client uses an allow-list (airc.exe + service + install tooling only).
    if ($prof -eq 'client') {
        $purged = @(Remove-BobiverseAircClientExtraPayload -InstallRoot $InstallRoot)
        Write-Host 'INFO FR #3514 client allow-list payload applied'
    } else {
        $purged = @(Remove-BobiverseAircWorkstationAgentPayload -InstallRoot $InstallRoot)
    }
    foreach ($p in $purged) {
        if ($p) { [void]$script:AircManifestPaths.Add(("removed:{0}" -f $p)) }
    }
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
# is already registered - that caused SASL 904 / NickServ 433 after 0.1.20->0.1.21.
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
            Write-Host "INFO FR #1552: no AppParameters - using $snapPath"
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

# Under MSI LocalSystem, USERPROFILE is often C:\Users\Default - that loses the
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

# FR #3287: resolve capabilities (MSI props > prior AppParameters/json > fresh off / upgrade operators).
$hadPriorService = [bool](Get-Service -Name 'Airc' -ErrorAction SilentlyContinue) -or [bool]$priorAppParams -or ($priorId -and $priorId.ConsoleHome)
$priorShell = ''
if ($priorId -and $priorId.PSObject.Properties['ShellMode'] -and $priorId.ShellMode) { $priorShell = [string]$priorId.ShellMode }
$capPathGuess = Join-Path $InstallRoot 'config\airc.json'
if (-not $priorShell -and (Test-Path -LiteralPath $capPathGuess)) {
    try {
        $priorCap = Get-Content -LiteralPath $capPathGuess -Raw -Encoding utf8 | ConvertFrom-Json
        if ($priorCap.shell) { $priorShell = [string]$priorCap.shell }
        elseif ($priorCap.shell_mode) { $priorShell = [string]$priorCap.shell_mode }
    } catch {}
}
$expShell = ([string]$ShellMode).Trim().ToLowerInvariant()
if ($expShell -notin @('off', 'operators')) { $expShell = '' }
if ($priorShell) { $priorShell = $priorShell.Trim().ToLowerInvariant() }
# FR #3393: workstation defaults shell=off unless MSI/CLI set explicitly (ignore prior).
if ($expShell) { $resolvedShell = $expShell }
elseif ($prof -eq 'workstation') { $resolvedShell = 'off' }
elseif ($prof -eq 'client') { $resolvedShell = 'operators' }  # FR #3401 full remote
elseif ($priorShell -in @('off', 'operators')) { $resolvedShell = $priorShell }
elseif ($hadPriorService) { $resolvedShell = 'operators' }
else { $resolvedShell = 'off' }

$expJobs = ([string]$Jobs).Trim().ToLowerInvariant()
if ($expJobs -in @('off', 'on')) { $resolvedJobs = $expJobs }
elseif ($prof -eq 'workstation') { $resolvedJobs = 'off' }
elseif ($prof -eq 'client') { $resolvedJobs = 'on' }  # FR #3401
elseif ($priorId -and $priorId.PSObject.Properties['Jobs'] -and $priorId.Jobs) {
    $resolvedJobs = ([string]$priorId.Jobs).Trim().ToLowerInvariant()
    if ($resolvedJobs -notin @('off', 'on')) { $resolvedJobs = 'on' }
} else { $resolvedJobs = 'on' }

$expUpdate = ([string]$UpdateCap).Trim().ToLowerInvariant()
if ($expUpdate -in @('off', 'on')) { $resolvedUpdate = $expUpdate }
elseif ($prof -eq 'workstation') { $resolvedUpdate = 'off' }
elseif ($prof -eq 'client') { $resolvedUpdate = 'on' }  # FR #3401 ops-gated UPDATE
elseif ($priorId -and $priorId.PSObject.Properties['UpdateCap'] -and $priorId.UpdateCap) {
    $resolvedUpdate = ([string]$priorId.UpdateCap).Trim().ToLowerInvariant()
    if ($resolvedUpdate -notin @('off', 'on')) { $resolvedUpdate = 'on' }
} else { $resolvedUpdate = 'on' }

# FR #3393: workstation defaults require_account=true unless MSI/CLI set explicitly.
$expRequire = $null
$reqRaw = ([string]$RequireAccount).Trim().ToLowerInvariant()
if ($reqRaw -in @('1', 'true', 'yes', 'on')) { $expRequire = $true }
elseif ($reqRaw -in @('0', 'false', 'no', 'off')) { $expRequire = $false }
if ($null -ne $expRequire) { $resolvedRequire = [bool]$expRequire }
elseif ($prof -eq 'workstation') { $resolvedRequire = $true }
elseif ($prof -eq 'client') { $resolvedRequire = $false }  # FR #3401: IRC ops, no account ACL
elseif ($priorId -and $priorId.PSObject.Properties['RequireAccount'] -and $priorId.RequireAccount) { $resolvedRequire = [bool]$priorId.RequireAccount }
else { $resolvedRequire = $false }

$resolvedAccounts = @()
if (([string]$Accounts).Trim()) {
    $resolvedAccounts = @(([string]$Accounts) -split '[,;\s]+' | Where-Object { $_ })
} elseif ($priorId -and $priorId.PSObject.Properties['Accounts'] -and $priorId.Accounts) {
    $resolvedAccounts = @(([string]$priorId.Accounts) -split '[,;\s]+' | Where-Object { $_ })
}

# FR #3401 / #3639: every profile (fleet, workstation, client) authorises by live
# control-channel +o/+h. No operators.txt, no fleet-operators roster, no nick allow-list.
if (([string]$OperatorsExtra).Trim()) {
    Write-Host 'INFO FR #3639 ignoring AIRC_OPERATORS / -OperatorsExtra (auth is control-channel +o/+h)'
}
if (@($Operators | Where-Object { $_ -and ([string]$_).Trim() }).Count -gt 0) {
    Write-Host 'INFO FR #3639 ignoring -Operators (auth is control-channel +o/+h)'
}
$Operators = @()

# FR #3289: sync_from_repo default OFF (unsigned main must not run as SYSTEM); self_update default ON.
function ConvertTo-AircBoolOrNull {
    param([string]$Raw)
    $t = ([string]$Raw).Trim().ToLowerInvariant()
    if (-not $t) { return $null }
    if ($t -in @('1', 'true', 'yes', 'on')) { return $true }
    if ($t -in @('0', 'false', 'no', 'off')) { return $false }
    return $null
}
$priorSync = $null
$priorSelf = $null
if (Test-Path -LiteralPath $capPathGuess) {
    try {
        $priorCap2 = Get-Content -LiteralPath $capPathGuess -Raw -Encoding utf8 | ConvertFrom-Json
        if ($null -ne $priorCap2.PSObject.Properties['sync_from_repo']) { $priorSync = [bool]$priorCap2.sync_from_repo }
        if ($null -ne $priorCap2.PSObject.Properties['self_update']) { $priorSelf = [bool]$priorCap2.self_update }
    } catch {}
}
$expSync = ConvertTo-AircBoolOrNull -Raw $SyncFromRepo
$expSelf = ConvertTo-AircBoolOrNull -Raw $SelfUpdate
# FR #3289 fresh default sync off; FR #3462: client/workstation ignore prior fleet sync=true
# unless MSI/CLI AIRC_SYNC_FROM_REPO is explicit (mirrors self_update force-off).
if ($null -ne $expSync) { $resolvedSync = [bool]$expSync }
elseif ($prof -in @('workstation', 'client')) { $resolvedSync = $false }  # FR #3462 / #3393/#3401
elseif ($null -ne $priorSync) { $resolvedSync = [bool]$priorSync }
else { $resolvedSync = $false }
# FR #3393: workstation defaults self_update=false (no SYSTEM GitHub MSI channel) unless MSI/CLI set.
if ($null -ne $expSelf) { $resolvedSelf = [bool]$expSelf }
elseif ($prof -in @('workstation', 'client')) { $resolvedSelf = $false }  # FR #3393/#3401
elseif ($null -ne $priorSelf) { $resolvedSelf = [bool]$priorSelf }
else { $resolvedSelf = $true }

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
        Launcher     = $(if ($priorId.Launcher -and (Test-Path -LiteralPath $priorId.Launcher)) { $priorId.Launcher } else { '' })
        ShellMode    = $resolvedShell
        Jobs         = $resolvedJobs
        UpdateCap    = $resolvedUpdate
        RequireAccount = $resolvedRequire
        Accounts     = ($resolvedAccounts -join ',')
        SyncFromRepo = $resolvedSync
        SelfUpdate   = $resolvedSelf
        Profile      = $(if ($script:AircInstallProfile) { $script:AircInstallProfile } else { 'fleet' })
        AgentLayer   = [bool]$script:AircWantAgentLayer
        updated      = (Get-Date).ToUniversalTime().ToString('o')
    }
    ($snap | ConvertTo-Json) | Set-Content -LiteralPath $idPath -Encoding utf8
    Write-Host "INFO wrote $idPath"
} catch {
    Write-Host ("WARN airc-install.json: {0}" -f $_.Exception.Message)
}

# FR #3287 / #3289: admin-readable capability + start-update policy file.
try {
    $capPath = Join-Path $InstallRoot 'config\airc.json'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $capPath) | Out-Null
    # FR #3639: irc_ops on every profile (control-channel +o/+h; no operators list).
    $authMode = 'irc_ops'
    $capObj = [ordered]@{
        shell = $resolvedShell
        jobs = $resolvedJobs
        update = $resolvedUpdate
        require_account = $resolvedRequire
        accounts = @($resolvedAccounts)
        sync_from_repo = $resolvedSync
        self_update = $resolvedSelf
        profile = $prof
        auth_mode = $authMode
    }
    ($capObj | ConvertTo-Json) | Set-Content -LiteralPath $capPath -Encoding utf8
    Write-Host ("INFO FR #3287/#3289/#3393 wrote {0} profile={1} shell={2} jobs={3} update={4} require_account={5} sync_from_repo={6} self_update={7}" -f $capPath, $prof, $resolvedShell, $resolvedJobs, $resolvedUpdate, $resolvedRequire, $resolvedSync, $resolvedSelf)
} catch {
    Write-Host ("WARN airc.json: {0}" -f $_.Exception.Message)
}

# FR #3291: crash-report.json (MSI BOBIVERSE_CRASH_REPORT > prior file > shell=off => disabled).
try {
    $crPath = Join-Path $InstallRoot 'config\crash-report.json'
    $priorCr = $null
    if (Test-Path -LiteralPath $crPath) {
        try { $priorCr = Get-Content -LiteralPath $crPath -Raw -Encoding utf8 | ConvertFrom-Json } catch {}
    }
    $expCr = ([string]$CrashReport).Trim().ToLowerInvariant()
    $crObj = $null
    if ($expCr -in @('0', 'false', 'no', 'off')) {
        $crObj = [ordered]@{ enabled = $false; mode = 'off'; source = 'msi' }
    } elseif ($expCr -in @('local', 'local-only', 'local_only', 'spool')) {
        $crObj = [ordered]@{ enabled = $false; mode = 'local-only'; source = 'msi' }
    } elseif ($expCr -in @('1', 'true', 'yes', 'on', 'full')) {
        $crObj = [ordered]@{ enabled = $true; mode = 'full'; include_log_tail = $true; source = 'msi' }
    } elseif ($expCr -in @('no-log-tail', 'nologtail', 'no_log_tail')) {
        $crObj = [ordered]@{ enabled = $true; mode = 'full'; include_log_tail = $false; source = 'msi' }
    } elseif ($prof -eq 'workstation') {
        # FR #3393: workstation defaults crash-report off (no intake from client boxes).
        $crObj = [ordered]@{ enabled = $false; mode = 'off'; source = 'workstation-profile' }
    } elseif ($prof -eq 'client') {
        # FR #3401: client keeps crash reports ON (redacted intake); explicit off still wins above.
        $crObj = [ordered]@{ enabled = $true; mode = 'full'; source = 'client-profile' }
    } elseif ($null -ne $priorCr) {
        # Upgrade preserve: leave prior file untouched.
        Write-Host ("INFO FR #3291 keep prior {0}" -f $crPath)
    } elseif ($resolvedShell -eq 'off') {
        $crObj = [ordered]@{ enabled = $false; mode = 'off'; source = 'airc-shell-off' }
    }
    if ($null -ne $crObj) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $crPath) | Out-Null
        ($crObj | ConvertTo-Json) | Set-Content -LiteralPath $crPath -Encoding utf8
        Write-Host ("INFO FR #3291 wrote {0} enabled={1} mode={2}" -f $crPath, $crObj.enabled, $crObj.mode)
    }
} catch {
    Write-Host ("WARN crash-report.json: {0}" -f $_.Exception.Message)
}

$installLegacy = Join-Path $InstallRoot 'scripts\Install-AircConsole.ps1'
$args = @{
    ServiceName = 'Airc'
    ConsoleHome = $ConsoleHome
    ShellMode   = $resolvedShell
    Jobs        = $resolvedJobs
    UpdateCap   = $resolvedUpdate
    Profile     = $prof
    AuthMode    = 'irc_ops'
}
if ($Nssm) { $args.Nssm = $Nssm }
if ($MachineId) { $args.MachineId = $MachineId }
if ($Python) { $args.Python = $Python }
# FR #3394: always delay Start-Service until Protect FailClosed after Install-AircConsole.
$args.NoStart = $true
if ($resolvedRequire) { $args.RequireAccount = $true }
if ($resolvedAccounts.Count -gt 0) { $args.Accounts = $resolvedAccounts }
# FR #1552: pass through prior PasswordFile / Launcher when still on disk (FR #3639: no OperatorsFile).
if ($priorId -and $priorId.PasswordFile -and (Test-Path -LiteralPath $priorId.PasswordFile)) {
    $args.PasswordFile = $priorId.PasswordFile
}
if ($priorId -and $priorId.Launcher -and (Test-Path -LiteralPath $priorId.Launcher)) {
    $args.Launcher = $priorId.Launcher
}

# Patch launcher path expectation: Install-AircConsole looks beside itself
try {
    & $installLegacy @args
} catch {
    Write-Host "ERROR Install-AircConsole: $($_.Exception.Message)"
    # FR #3395 / #3515 / #3584: local MSI log + redacted intake when crash-report allows (Report kept on client purge).
    # Set the flag even if Send throws so the outer catch does not double-file.
    $script:AircInstallFailReported = $true
    try {
        [void](Send-BobiverseAircInstallFailureIntake -InstallRoot $InstallRoot -ScriptsDir $here `
            -Title 'airc install: Install-AircConsole failed' `
            -Body $_.Exception.Message)
    } catch {
        Write-Host ("WARN FR #3515 Install-AircConsole failure intake: {0}" -f $_.Exception.Message)
    }
    throw
}

# Prefer one console per box: remove leftover agentic_irc AircConsole (distinct UpgradeCode).
Remove-BobiverseLegacyService -Name 'AircConsole' -Nssm $Nssm

# FR #3289 / FR #3394 / FR #3678 / FR #3716: one Full -Recurse -Force FailClosed before
# Start-Service. -Force walks children after the early root-only protect (FR #3716
# otherwise skips the ACL walk when the root is already locked). Without -Force,
# upgrades that only re-protect an already-locked tree stay seconds (skip takeown + walk).
Protect-BobiverseInstallTree -Path $InstallRoot -Recurse -Force -FailClosed

# FR #3394: start only after the tree is locked (Install-AircConsole ran with -NoStart).
if (-not $NoStart) {
    Write-Host 'INFO FR #3394 starting Airc after Protect FailClosed'
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        Start-Service -Name 'Airc' -ErrorAction Continue
    } finally {
        $ErrorActionPreference = $prevEa
    }
} else {
    Write-Host 'INFO Install-Airc -NoStart set; service not started'
}

# ONE all-users Start Menu folder "Bobiverse" (shared with bob/jeeves); dedupes older scattered entries.
try {
    [void](Install-BobiverseStartMenu -Product airc -InstallRoot $InstallRoot -MachineId $MachineId)
} catch {
    Write-Host ("WARN Start Menu folder: {0}" -f $_.Exception.Message)
}

# FR #3292: durable install manifest for purge uninstall (paths + profile).
try {
    # FR #3652: LogsOnly - never Full-Recurse the shared ProgramData update\ tree here.
    $pd = Ensure-BobiverseProgramDataRoot -FailClosed -ProtectMode LogsOnly
    if (-not $pd) { throw 'Ensure-BobiverseProgramDataRoot returned empty' }
    $manPath = Join-Path $pd 'airc-install-manifest.json'
    $paths = @(
        $InstallRoot,
        $ConsoleHome,
        (Join-Path $InstallRoot 'config'),
        (Join-Path $InstallRoot 'logs'),
        (Join-Path $InstallRoot '.git'),
        (Join-Path $InstallRoot '.grok'),
        (Join-Path $InstallRoot '.cursor'),
        (Join-Path $env:ProgramData 'Bobiverse\update\airc')
    )
    if ($script:AircManifestPaths) { $paths = @($paths + @($script:AircManifestPaths)) }
    $paths = @($paths | Where-Object { $_ } | Select-Object -Unique)
    $man = [ordered]@{
        v            = 1
        product      = 'airc'
        profile      = $(if ($script:AircInstallProfile) { $script:AircInstallProfile } else { 'fleet' })
        agent_layer  = [bool]$script:AircWantAgentLayer
        purge_default = ($(if ($script:AircInstallProfile) { $script:AircInstallProfile } else { 'fleet' }) -in @('workstation', 'client'))
        install_root = $InstallRoot
        console_home = $ConsoleHome
        paths        = @($paths)
        updated      = (Get-Date).ToUniversalTime().ToString('o')
    }
    ($man | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $manPath -Encoding utf8
    Write-Host ("INFO FR #3292 wrote {0} profile={1} agent_layer={2}" -f $manPath, $man.profile, $man.agent_layer)
} catch {
    Write-Host ("WARN airc-install-manifest.json: {0}" -f $_.Exception.Message)
}

Write-Host 'INFO Install-Airc done (service Airc)'
Write-BobiverseMsiInstallLog -Product airc -Message 'install-ok'
$script:AircInstallOk = $true
} catch {
    # FR #3515 / #3584: outer catch covers Protect / ProgramData / VERSION / Start failures.
    # Skip intake when the nested Install-AircConsole catch already reported (same failure).
    try {
        Write-BobiverseMsiInstallLog -Product airc -Message ("install-fail $($_.Exception.Message)")
    } catch { }
    if (-not $script:AircInstallFailReported) {
        try {
            [void](Send-BobiverseAircInstallFailureIntake -InstallRoot $InstallRoot -ScriptsDir $here `
                -Title 'airc install: Install-Airc failed' `
                -Body $_.Exception.Message)
            $script:AircInstallFailReported = $true
        } catch {
            Write-Host ("WARN FR #3515 outer install-fail intake: {0}" -f $_.Exception.Message)
        }
    } else {
        Write-Host 'INFO FR #3584 skip outer install-fail intake (already reported by Install-AircConsole catch)'
    }
    # FR #3759: do not bare-throw here - PS 4.0 -File would still exit 0.
    $script:AircExitCode = 1
} finally {
    # FR #2564: best-effort Start-Service Airc after a failed RunInstall.
    if (-not $script:AircInstallOk) {
        [void](Restore-BobiverseServiceAfterFailedInstall -ServiceName 'Airc' -Product airc -Why 'Install-Airc-catch')
    }
}
# FR #3759: explicit exit after finally (finally still ran). Install-Airc.cmd reads %ERRORLEVEL%.
exit [int]$script:AircExitCode
