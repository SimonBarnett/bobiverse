#Requires -Version 5.1
<#
.SYNOPSIS
  Clean-install ircJeeves (+ optional BobIrcd if Ergo present). Nick Jeeves.
#>
[CmdletBinding()]
param(
    [string]$Nssm = '',
    [string]$InstallRoot = '',   # '' = <discovered ai root>\jeeves (t780u)
    [string]$ServiceName = 'ircJeeves',
    [string]$Python = '',
    [string]$ChairHome = '',
    [string]$ErgoRoot = '',   # '' = <discovered ai root>\ergo (t780u)
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
    [string]$OpAccounts = '',
    # #70: MSI public properties (msiexec ... SKIPERGO=1 SKIPCOPY=1) arrive as strings via RunInstall.
    [string]$MsiSkipErgo = '',
    [string]$MsiSkipCopy = ''
)

# #70: map MSI property strings onto the real switches (empty / unset = no-op).
if ($MsiSkipErgo -eq '1') { $SkipErgo = $true }
if ($MsiSkipCopy -eq '1') { $SkipCopy = $true }

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
if (-not $InstallRoot) { $InstallRoot = Join-Path (Get-BobiverseAiRoot -Create) 'jeeves' }
if (-not $ErgoRoot) { $ErgoRoot = Join-Path (Get-BobiverseAiRoot -Create) 'ergo' }


if (-not (Test-BobiverseIsAdmin)) {
    Request-BobiverseUacRelaunch -Bound $PSBoundParameters
}

$repoRoot = if ($splitRepo) { $splitRepo } else { Split-Path -Parent $here }
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
Install-BobiverseAgentLayer -RepoRoot $repoRoot -InstallRoot $InstallRoot -Product 'jeeves'
$skillsSrc = Get-BobiverseRepoMergedDir -Root $repoRoot -Sub '.grok\skills'
if (Test-Path $skillsSrc) {
    $skillsDest = Join-Path $InstallRoot '.grok\skills'
    New-Item -ItemType Directory -Force -Path $skillsDest | Out-Null
    if (-not $SkipCopy) {
        Copy-BobiverseTree -Source $skillsSrc -Destination $skillsDest -ContentsOnly
    }
    Install-BobiverseSkills -RepoSkillsRoot $skillsDest -SkillNames (Get-BobiverseSkillNames -SkillsRoot $skillsDest -Product 'jeeves')
}
Install-BobiversePythonDeps -Python $Python

# Seed operators for !register
$ops = Join-Path $ChairHome 'operators.txt'
if (-not (Test-Path -LiteralPath $ops)) {
    [IO.File]::WriteAllText($ops, "Simon`n", [Text.UTF8Encoding]::new($false))
}

# Ergo payload: pack lays ergo\ under InstallRoot; BobIrcd AppDirectory is ErgoRoot (<ai root>\ergo)
if (-not $SkipErgo -and -not $ForceErgo -and
    (Test-Path -LiteralPath (Join-Path $ErgoRoot 'ergo.exe')) -and
    (Test-Path -LiteralPath (Join-Path $ErgoRoot 'ircd.yaml')) -and
    (Get-Service -Name 'BobIrcd' -ErrorAction SilentlyContinue)) {
    Write-Host 'INFO existing Ergo found - leaving ergo.exe, ircd.yaml and the BobIrcd service untouched (-ForceErgo to re-run Install-BobIrcd)'
    # #70: an ergo.exe hard-linked to the MSI payload bounces Ergo whenever the MSI rewrites its copy: unlink it (no restart).
    try { [void](Repair-BobiverseErgoHardlink -ErgoExe (Join-Path $ErgoRoot 'ergo.exe')) }
    catch { Write-Host "WARN ergo.exe hard-link repair skipped: $($_.Exception.Message)" }
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

$user = Resolve-BobiverseServiceUser
# FR #2301 / WP3: prefer one-file jeeves.exe (chair + in-proc HTTP). Legacy: powershell Start-Jeeves.ps1.
$jeevesExe = Join-Path $InstallRoot 'jeeves\jeeves.exe'
$useJeevesExe = Test-Path -LiteralPath $jeevesExe
if ($useJeevesExe) {
    $appParams = "--chair --http 127.0.0.1:7700 --home `"$ChairHome`" --digest-home `"$digestHome`""
    [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('install', $ServiceName, $jeevesExe))
    # FR #2475: refuse missing exe; keep previous Application on failure
    $setApp = Set-BobiverseNssmApplicationSafe -Nssm $Nssm -ServiceName $ServiceName -NewApplication $jeevesExe -AppDirectory $InstallRoot
    if (-not $setApp.Ok) {
        Write-Host "WARN FR#2475 keeping previous Application=$($setApp.Application); falling back to Start-Jeeves.ps1 launcher"
        $useJeevesExe = $false
    } else {
        [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppParameters', $appParams))
        Write-Host "INFO ircJeeves Application=jeeves.exe (FR #2301 WP3 cutover; FR #2475 safe set)"
    }
}
if (-not $useJeevesExe) {
    $launcher = Join-Path $InstallRoot 'scripts\Start-Jeeves.ps1'
    # No -Python in AppParameters (spaces break NSSM quoting - issue #3)
    $appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -ChairHome `"$ChairHome`" -RepoRoot `"$InstallRoot`""
    [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('install', $ServiceName, 'powershell.exe'))
    [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Application', 'powershell.exe'))
    [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppDirectory', (Join-Path $InstallRoot 'scripts')))
    [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppParameters', $appParams))
    Write-Host 'INFO ircJeeves Application=powershell Start-Jeeves.ps1 (legacy; no jeeves\jeeves.exe)'
}
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'DisplayName', 'bobiverse Jeeves chair'))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Start', 'SERVICE_AUTO_START'))
# FR #1055: Restart on Default and on exit 0 (graceful quit).
Set-BobiverseNssmAppExitRestart -Nssm $Nssm -ServiceName $ServiceName -RestartDelayMs 2000
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
# ONE all-users Start Menu folder "Bobiverse" (shared with bob/airc); dedupes older scattered entries.
try {
    [void](Install-BobiverseStartMenu -Product jeeves -InstallRoot $InstallRoot `
            -NeedLogon:((-not $objectOk) -and (Test-Path -LiteralPath (Join-Path $InstallRoot 'scripts\Complete-BobiverseServiceLogon.ps1'))))
} catch {
    Write-Host ("WARN Start Menu folder: {0}" -f $_.Exception.Message)
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
# Supervised BobCallback (ONSTART) - FR #1316: same account as digest home owner (not SYSTEM).
# FR #2301 / WP3: when ircJeeves runs jeeves.exe (in-proc HTTP), do not register a second Python BobCallback owner.
if ($useJeevesExe) {
    Write-Host 'INFO skipping Python BobCallback task (jeeves.exe owns :7700; FR #2301 WP3)'
    try {
        $existingCb = Get-ScheduledTask -TaskName 'BobCallback' -ErrorAction SilentlyContinue
        if ($existingCb) {
            Unregister-ScheduledTask -TaskName 'BobCallback' -Confirm:$false -ErrorAction SilentlyContinue
            Write-Host 'INFO removed legacy BobCallback scheduled task (WP3 cutover)'
        }
    } catch {
        Write-Host "WARN BobCallback unregister: $($_.Exception.Message)"
    }
} else {
# Supervised BobCallback (ONSTART) — FR #1316: same account as digest home owner (not SYSTEM).
# SYSTEM + --home C:\Users\Administrator\.bobiverse wedges :7700 via cross-principal digest.lock/ACL.
try {
    $pyCb = if ($Python) { $Python } else { Resolve-BobiversePython }
    $cbScript = Join-Path $InstallRoot 'scripts\bobcallback.py'
    $regCb = Join-Path $InstallRoot 'scripts\Register-BobCallbackTask.ps1'
    if (-not (Test-Path -LiteralPath $regCb)) {
        $regCb = Join-Path $PSScriptRoot 'Register-BobCallbackTask.ps1'
    }
    # MRB #1353: when digest home is Admin .bobiverse (or install is LocalSystem), force RunAsUser=Administrator
    # — never pass $env:USERNAME blindly (MSI/LocalSystem can yield SYSTEM / machine$ and recreate the wedge).
    $cbRunAs = if ($env:USERNAME) { $env:USERNAME } else { 'Administrator' }
    $adminDigestNorm = (Join-Path $env:SystemDrive 'Users\Administrator\.bobiverse')
    if (
        (Test-BobiverseIsLocalSystem) -or
        ($digestHome -and ([string]$digestHome).Equals($adminDigestNorm, [System.StringComparison]::OrdinalIgnoreCase))
    ) {
        $cbRunAs = 'Administrator'
    }
    if (Test-Path -LiteralPath $regCb) {
        $regArgs = @{
            DigestHome = $digestHome
            Python     = $pyCb
            ScriptPath = $cbScript
            RunAsUser  = $cbRunAs
            Port       = 7700
        }
        if (-not $NoStart) { $regArgs['Start'] = $true }
        & $regCb @regArgs
    } else {
        # Fallback: Interactive current user (never SYSTEM against Admin home).
        $tr = "`"$pyCb`" -u `"$cbScript`" --home `"$digestHome`" --bind 127.0.0.1 --port 7700"
        $ru = $cbRunAs
        schtasks /Create /TN BobCallback /SC ONSTART /RU $ru /IT /RL HIGHEST /F /TR $tr | Out-Null
        Write-Host ("INFO registered scheduled task BobCallback runAs={0} (FR #1316 fallback)" -f $ru)
        if (-not $NoStart) {
            schtasks /Run /TN BobCallback 2>&1 | Out-Null
        }
    }
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
    # Chair background jobs run INSIDE ircJeeves (no extra task/service): webhook health probe every 30 min
    # (webhook-health.json, announces #bobiverse only on up<->down) and authenticated FR/MRB resync every 15 min
    # using the token above (source logged once to <chair home>\resync-token-source.log; value never logged).
    Write-Host 'INFO chair jobs: webhook-health probe 30 min + GitHub resync 15 min (inside ircJeeves; token source logged once)'
} catch {
    Write-Host "WARN BobCallback task: $($_.Exception.Message)"
}
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
