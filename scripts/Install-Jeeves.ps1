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
    [string]$ErgoRoot = 'C:\ai\ergo',
    [switch]$SkipErgo,
    [switch]$NoStart,
    [switch]$ForceTools,
    [switch]$PromptServicePassword,
    [switch]$SkipCopy
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
if (-not $Nssm) { throw 'nssm missing - pack third_party\nssm\win64\nssm.exe or pass -Nssm' }
if (-not $Python) { $Python = Resolve-BobiversePython }
# Chair home: under MSI LocalSystem, $env:USERPROFILE is often C:\Users\Default — that
# breaks DPAPI identity and loses the real Administrator chair. Prefer an existing
# Admin chair, else InstallRoot\home-jeeves (issue: win-mpre cutover 2026-09-29).
if (-not $ChairHome) {
    $adminChair = Join-Path $env:SystemDrive 'Users\Administrator\.agentic-irc-jeeves'
    if (Test-BobiverseIsLocalSystem) {
        if (Test-Path -LiteralPath $adminChair) {
            $ChairHome = $adminChair
            Write-Host "INFO LocalSystem using existing Admin ChairHome=$ChairHome"
        } else {
            $ChairHome = Join-Path $InstallRoot 'home-jeeves'
            Write-Host "INFO LocalSystem ChairHome=$ChairHome (avoid Default profile)"
        }
    } else {
        $ChairHome = Join-Path $env:USERPROFILE '.agentic-irc-jeeves'
    }
}
New-Item -ItemType Directory -Force -Path $ChairHome | Out-Null
if (Test-BobiverseIsLocalSystem) {
    $adminDigest = Join-Path $env:SystemDrive 'Users\Administrator\.agentic-irc-bobiverse'
    if (Test-Path -LiteralPath $adminDigest) {
        $digestHome = $adminDigest
    } else {
        $digestHome = Join-Path $InstallRoot 'home'
    }
} else {
    $digestHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'
}
New-Item -ItemType Directory -Force -Path $digestHome | Out-Null

# Clean prior ircJeeves + remove legacy gh-Jeeves chair (both fight for nick Jeeves)
Remove-BobiverseService -Nssm $Nssm -Name $ServiceName
Remove-BobiverseLegacyService -Name 'BobJeeves' -Nssm $Nssm
Get-ScheduledTask -TaskName 'BobJeeves-chair' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
# Lay tree: copy scripts + skills into InstallRoot (skip when MSI already staged - issue #2)
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'scripts'), (Join-Path $InstallRoot 'config') | Out-Null
if (-not $SkipCopy) {
    Copy-BobiverseTree -Source $here -Destination (Join-Path $InstallRoot 'scripts') -ContentsOnly
}
Copy-BobiverseVersion -InstallRoot $InstallRoot -RepoRoot $repoRoot
$skillsSrc = Join-Path $repoRoot '.grok\skills'
if (Test-Path $skillsSrc) {
    $skillsDest = Join-Path $InstallRoot '.grok\skills'
    New-Item -ItemType Directory -Force -Path $skillsDest | Out-Null
    if (-not $SkipCopy) {
        Copy-BobiverseTree -Source $skillsSrc -Destination $skillsDest -ContentsOnly
    }
    Install-BobiverseSkills -RepoSkillsRoot $skillsDest -SkillNames @('bobiverse-jeeves', 'harvest', 'harvest-agent-skills')
}
Install-BobiversePythonDeps -Python $Python

# Seed operators for !register
$ops = Join-Path $ChairHome 'operators.txt'
if (-not (Test-Path -LiteralPath $ops)) {
    [IO.File]::WriteAllText($ops, "Simon`n", [Text.UTF8Encoding]::new($false))
}

# Ergo payload: pack lays ergo\ under InstallRoot; BobIrcd AppDirectory is ErgoRoot (C:\ai\ergo)
if (-not $SkipErgo) {
    $packErgo = Join-Path $InstallRoot 'ergo'
    if (-not (Test-Path -LiteralPath (Join-Path $packErgo 'ergo.exe'))) {
        $packErgo = Join-Path $repoRoot 'ergo'
    }
    $installBobIrcd = Join-Path $here 'Install-BobIrcd.ps1'
    if (Test-Path -LiteralPath $installBobIrcd) {
        $ircdArgs = @{
            ErgoRoot    = $ErgoRoot
            NssmSource  = $Nssm
            NoStart     = $NoStart
        }
        if (Test-Path -LiteralPath (Join-Path $packErgo 'ergo.exe')) {
            $ircdArgs['PackErgoDir'] = $packErgo
        }
        & $installBobIrcd @ircdArgs
    } else {
        Write-Host 'WARN Install-BobIrcd.ps1 missing'
    }
}

$launcher = Join-Path $InstallRoot 'scripts\Start-Jeeves.ps1'
$user = Resolve-BobiverseServiceUser
# No -Python in AppParameters (spaces break NSSM quoting - issue #3)
$appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -ChairHome `"$ChairHome`" -RepoRoot `"$InstallRoot`""

[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('install', $ServiceName, 'powershell.exe'))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Application', 'powershell.exe'))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppDirectory', (Join-Path $InstallRoot 'scripts')))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppParameters', $appParams))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'DisplayName', 'bobiverse Jeeves chair'))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Start', 'SERVICE_AUTO_START'))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppExit', 'Default', 'Restart'))
# Keep crash loops out of the airc console pipe — always log to files.
$logsDir = Join-Path $InstallRoot 'logs'
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppStdout', (Join-Path $logsDir 'stdout.log')))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppStderr', (Join-Path $logsDir 'stderr.log')))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppStdoutCreationDisposition', '4'))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppStderrCreationDisposition', '4'))
# Issue #6: never Get-Credential under msiexec /qn (UserInteractive can still be $true).
$doPrompt = $PromptServicePassword -or (
    -not (Test-BobiverseMsiOrQuiet) -and [Environment]::UserInteractive -and -not (Test-BobiverseIsLocalSystem)
)
[void](Import-BobiverseErgoPassword -InstallRoot $InstallRoot -HomeDir $ChairHome)
$objectOk = Set-BobiverseServiceObjectName -Nssm $Nssm -ServiceName $ServiceName -User $user `
    -InstallRoot $InstallRoot -PromptIfMissing:$doPrompt -AllowLocalSystem

$envLines = @("BOB_DIGEST_HOME=$digestHome")
if ($env:AGENTIC_IRC_PASSWORD) { $envLines += "AGENTIC_IRC_PASSWORD=$($env:AGENTIC_IRC_PASSWORD)" }
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppEnvironmentExtra', ($envLines -join "`n")))

if (-not $objectOk) {
    $logonPs1 = Join-Path $InstallRoot 'scripts\Complete-BobiverseServiceLogon.ps1'
    $desk = [Environment]::GetFolderPath('Desktop')
    if (Test-Path -LiteralPath $logonPs1) {
        New-BobiverseShortcut -LinkPath (Join-Path $desk 'Complete bobiverse service logon.lnk') `
            -TargetPath 'powershell.exe' `
            -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$logonPs1`" -Product jeeves -InstallRoot `"$InstallRoot`"" `
            -WorkingDirectory (Join-Path $InstallRoot 'scripts') `
            -Description 'Set ircJeeves ObjectName password'
    }
}
# Prefer Ergo up before chair when both are installed
# IIS rewrite → bobcallback :7700 (report/git/intake/jira)
$installWh = Join-Path $here 'Install-BobWebhooks.ps1'
if (Test-Path -LiteralPath $installWh) {
    try { & $installWh } catch {
        Write-Host "WARN Install-BobWebhooks: $($_.Exception.Message)"
    }
}

# Supervised BobCallback (ONSTART) — adopts/replaces ad-hoc tasks
try {
    $pyCb = if ($Python) { $Python } else { Resolve-BobiversePython }
    $cbScript = Join-Path $InstallRoot 'scripts\bobcallback.py'
    $tr = "`"$pyCb`" -u `"$cbScript`" --home `"$digestHome`" --bind 127.0.0.1 --port 7700"
    schtasks /Create /TN BobCallback /SC ONSTART /RU SYSTEM /RL HIGHEST /F /TR $tr | Out-Null
    Write-Host 'INFO registered scheduled task BobCallback'
    # #53: webhook secrets live in THIS install's config\ (not agentic_irc). Say so if absent.
    $cfgDir = Join-Path $InstallRoot 'config'
    New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
    foreach ($sec in @('report.secret', 'github.token')) {
        if (-not (Test-Path -LiteralPath (Join-Path $cfgDir $sec))) {
            Write-Host "WARN webhook secret missing: $cfgDir\$sec (report POSTs rejected / issue filing off until provided; never in git/MSI)"
        }
    }
    if (-not $NoStart) {
        schtasks /Run /TN BobCallback 2>&1 | Out-Null
    }
} catch {
    Write-Host "WARN BobCallback task: $($_.Exception.Message)"
}

if (-not $SkipErgo -and -not $NoStart) {
    $ircd = Get-Service -Name 'BobIrcd' -ErrorAction SilentlyContinue
    if ($ircd -and $ircd.Status -ne 'Running') {
        Start-Service -Name 'BobIrcd' -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

if (-not $NoStart) {
    try {
        Start-Service $ServiceName -ErrorAction Stop
        Start-Sleep -Seconds 2
    } catch {
        Write-Host "WARN Start-Service $ServiceName failed: $($_.Exception.Message) - complete service logon then start"
        $report = Join-Path $here 'Report-BobiverseIntakeIssue.ps1'
        if (Test-Path -LiteralPath $report) {
            try {
                & $report -Title "jeeves install: Start-Service $ServiceName failed" -Body $_.Exception.Message -InstallRoot $InstallRoot
            } catch {}
        }
    }
}
Get-Service $ServiceName, BobIrcd -ErrorAction SilentlyContinue | Format-Table Name, Status, StartType -AutoSize
Write-Host 'INFO Install-Jeeves done'
