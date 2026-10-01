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
    # v0.1.17: an existing Ergo (ergo.exe + ircd.yaml + BobIrcd service) is left completely alone
    # (an update must never restart or reconfigure the IRC server). -ForceErgo re-runs Install-BobIrcd.
    [switch]$ForceErgo,
    [switch]$NoStart,
    [switch]$ForceTools,
    [switch]$PromptServicePassword,
    [switch]$SkipCopy,
    # IRC operator credentials for the chair (DPAPI file <InstallRoot>\config\oper.cred).
    # Prompt-less: -OperFile <existing ergo-oper file>  OR  -OperName + env BOB_OPER_PASSWORD.
    # Without either, an existing config\oper.cred is kept, else Desktop\ergo-oper*.txt is used.
    [string]$OperFile = '',
    [string]$OperName = '',
    # NickServ account(s) Simon is verified under (comma list). Jeeves gives +o ONLY to a logged-in
    # nick whose services account matches (never on nick alone). Stored in <InstallRoot>\config\op-accounts.txt.
    [string]$OpAccounts = ''
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
    $adminChair = Join-Path $env:SystemDrive 'Users\Administrator\.jeeves'
    if (Test-BobiverseIsLocalSystem) {
        if (Test-Path -LiteralPath $adminChair) {
            $ChairHome = $adminChair
            Write-Host "INFO LocalSystem using existing Admin ChairHome=$ChairHome"
        } else {
            $ChairHome = Join-Path $InstallRoot 'home-jeeves'
            Write-Host "INFO LocalSystem ChairHome=$ChairHome (avoid Default profile)"
        }
    } else {
        $ChairHome = Join-Path $env:USERPROFILE '.jeeves'
    }
}
New-Item -ItemType Directory -Force -Path $ChairHome | Out-Null
if (Test-BobiverseIsLocalSystem) {
    $adminDigest = Join-Path $env:SystemDrive 'Users\Administrator\.bobiverse'
    if (Test-Path -LiteralPath $adminDigest) {
        $digestHome = $adminDigest
    } else {
        $digestHome = Join-Path $InstallRoot 'home'
    }
} else {
    $digestHome = Join-Path $env:USERPROFILE '.bobiverse'
}
New-Item -ItemType Directory -Force -Path $digestHome | Out-Null

# #53: first-run migration of the pre-0.1.15 ~\.agentic-irc-* homes into the jeeves/bobiverse homes
# (copy only; the old homes stay as backup). The chair also repeats this on first start.
$cfgDir = Join-Path $InstallRoot 'config'
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
$homeMigrate = Join-Path $here 'bob_home.py'
if ((Test-Path -LiteralPath $homeMigrate) -and $Python) {
    try {
        & $Python $homeMigrate migrate --chair-home $ChairHome --digest-home $digestHome --config-dir $cfgDir
    } catch {
        Write-Host "WARN home migration: $($_.Exception.Message)"
    }
}

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
if (-not $SkipErgo -and -not $ForceErgo -and
    (Test-Path -LiteralPath (Join-Path $ErgoRoot 'ergo.exe')) -and
    (Test-Path -LiteralPath (Join-Path $ErgoRoot 'ircd.yaml')) -and
    (Get-Service -Name 'BobIrcd' -ErrorAction SilentlyContinue)) {
    Write-Host 'INFO existing Ergo found - leaving ergo.exe, ircd.yaml and the BobIrcd service untouched (-ForceErgo to re-run Install-BobIrcd)'
    try {
        $ircdImg = [string](Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\BobIrcd' -Name ImagePath -ErrorAction Stop).ImagePath
        if ($ircdImg -and $ircdImg.ToLowerInvariant().Contains($InstallRoot.TrimEnd('\').ToLowerInvariant() + '\')) {
            Write-Host "WARN BobIrcd runs from the MSI-owned $ircdImg - upgrading FROM a pre-0.1.19 jeeves MSI replaces that file and bounces Ergo (0.1.19+ packs keep nssm.exe in place). Before that one upgrade, in a maintenance window: copy it to $ErgoRoot\nssm.exe, sc config BobIrcd binPath= `"$ErgoRoot\nssm.exe`", restart BobIrcd once (#70)."
        }
    } catch { }
    $SkipErgo = $true
}
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

if ($OpAccounts.Trim()) {
    $opFile = Join-Path $cfgDir 'op-accounts.txt'
    Set-Content -LiteralPath $opFile -Value (($OpAccounts -split '[,;\s]+' | Where-Object { $_ }) -join "`r`n") -Encoding ASCII
    Write-Host "INFO op accounts written to $opFile"
}
$envLines = @("BOB_DIGEST_HOME=$digestHome", "BOB_HOME=$ChairHome", "BOB_CONFIG_DIR=$cfgDir")
if ($env:BOB_IRC_PASSWORD) { $envLines += "BOB_IRC_PASSWORD=$($env:BOB_IRC_PASSWORD)" }
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

# Chair IRC-operator credentials (DPAPI machine scope). Status only; the value is never printed.
$operPy = Join-Path $here 'chair_oper.py'
if (Test-Path -LiteralPath $operPy) {
    try {
        $opArgs = @($operPy, 'provision', '--config-dir', $cfgDir)
        if ($OperFile) { $opArgs += @('--oper-file', $OperFile) }
        if ($OperName) { $opArgs += @('--name', $OperName) }
        & $Python @opArgs
    } catch {
        Write-Host "WARN oper provisioning: $($_.Exception.Message)"
    }
}
# Supervised BobCallback (ONSTART) — adopts/replaces ad-hoc tasks
try {
    $pyCb = if ($Python) { $Python } else { Resolve-BobiversePython }
    $cbScript = Join-Path $InstallRoot 'scripts\bobcallback.py'
    $tr = "`"$pyCb`" -u `"$cbScript`" --home `"$digestHome`" --bind 127.0.0.1 --port 7700"
    schtasks /Create /TN BobCallback /SC ONSTART /RU SYSTEM /RL HIGHEST /F /TR $tr | Out-Null
    Write-Host 'INFO registered scheduled task BobCallback'
    # v0.1.16: webhooks need NO password/secret (no shared secret is generated or copied). The digest
    # accepts POSTs from machine ids on the roster this Jeeves publishes (registered-machines.json).
    Write-Host 'INFO webhooks: no password/secret required (roster-gated by the machine list Jeeves publishes)'
    $ghTok = Join-Path $cfgDir 'github.token'
    if (-not (Test-Path -LiteralPath $ghTok)) {
        # OPTIONAL. Receiving GitHub/Jira/bob webhooks needs no token; it is only used to FILE issues from
        # intake/jira. Without it filings wait in the durable intake outbox (or use an existing `gh auth login`).
        Write-Host "INFO github token not set ($ghTok) - optional; webhooks work without it, issue filing queues in the intake outbox"
    } else {
        & icacls $ghTok /inheritance:r /grant:r 'NT AUTHORITY\SYSTEM:(F)' 'BUILTIN\Administrators:(F)' 2>&1 | Out-Null
        Write-Host "INFO github token present: $ghTok"
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
