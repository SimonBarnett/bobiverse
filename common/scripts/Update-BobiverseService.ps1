#Requires -Version 5.1
<#
.SYNOPSIS
  Service-start self-update for ircBob / ircJeeves / Airc (v0.1.17). Small, deterministic, token-less.
.DESCRIPTION
  Mode Check (default; called by Start-Bob / Start-Jeeves / Start-AircConsole BEFORE the main process):
    - honours the opt-out (BOB_AUTOUPDATE=0, BOBIVERSE_NO_UPDATE=1, or <InstallRoot>\config\autoupdate.disabled)
    - asks the public GitHub releases/latest endpoint (no token, 15 s timeout, no gh needed)
    - compares with <InstallRoot>\VERSION (never downgrades)
    - if newer and not loop-guarded: writes a plan and starts a DETACHED helper (scheduled task as SYSTEM,
      falling back to a WMI-created process). It never installs inline: msiexec replaces the very service
      that is running this script, so doing it here would deadlock on the service stop.
    - ALWAYS exits 0. Offline, rate limited (403/429), bad JSON, anything: log it and let the caller start
      the currently installed version.
  Mode Apply (the detached helper):
    download MSI + .sha256 -> verify the hash (mismatch = abort, service untouched) -> stop the service
    (only that service; no process is killed) -> back up the install tree and the small config/state homes
    -> msiexec /i (MajorUpgrade removes the previous install; the MSI custom action reinstalls the service)
    -> refresh skills -> verify VERSION + service -> start. On ANY failure: restore the backup, re-register
    the service from the restored tree, start the previous version, and record the failure.
  Loop guard: <StateDir>\state.json. A tag that failed MaxAttempts times is never retried; attempts are
  spaced by CooldownMinutes; a pending update blocks a second helper for 40 minutes.
  FR #2563: backup-only Apply failures (robocopy >=8) record lastResult=backup-failed without burning
  MaxAttempts; -ForceCheck clears a blocked tag so operators can escape a stuck loop-guard. Backup excludes
  volatile dirs/files (.pytest_cache, peers.json locks), retries once, and warns when free disk is low.
  Log: <StateDir>\update.log - one line per attempt/outcome. Secrets are never read or printed.
.NOTES
  PowerShell 5.1 only. Does not touch the IRC server (Ergo) or its files, never stops or kills any process
  other than the one service it is updating.
#>
[CmdletBinding()]
param(
    [string]$Product = '',
    [string]$InstallRoot = '',
    [string]$ServiceName = '',
    [string]$Repo = 'SimonBarnett/bobiverse',
    [string]$Mode = 'Check',
    [string]$PlanFile = '',
    [string]$StateDir = '',
    [string]$ReleaseJson = '',      # test hook: local release JSON instead of GitHub
    [string]$TargetVersion = '',    # FR #77: pin UPDATE airc|bob|jeeves <ver> (tag vX.Y.Z)
    [switch]$AllowLocalAssets,      # test hook: plan asset "urls" may be local files
    [switch]$DryRun,                # Check: decide + log only
    [switch]$NoSpawn,               # Check: write plan/state but do not start the helper
    [switch]$VerifyOnly,            # Apply: download + verify the hash, then stop (service untouched)
    [switch]$ForceCheck,            # FR #77: IRC UPDATE bypasses the 2-minute lookup throttle
    [int]$DelaySeconds = 15,
    [int]$MaxAttempts = 2,
    [int]$CooldownMinutes = 10
)

$ErrorActionPreference = 'Stop'
$script:LogFile = $null
$script:StateFile = $null
$script:PendingMinutes = 40

function Write-UpdLog {
    param([string]$Msg)
    $line = '{0} product={1} {2}' -f (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz'), $Product, $Msg
    Write-Host "INFO self-update: $Msg"
    if (-not $script:LogFile) { return }
    try {
        if ((Test-Path -LiteralPath $script:LogFile) -and ((Get-Item -LiteralPath $script:LogFile).Length -gt 524288)) {
            Move-Item -LiteralPath $script:LogFile -Destination ($script:LogFile + '.1') -Force
        }
        Add-Content -LiteralPath $script:LogFile -Value $line -Encoding UTF8
    } catch { }
}

function Get-OptOutReason {
    foreach ($scope in @('Process', 'Machine')) {
        $v = [Environment]::GetEnvironmentVariable('BOB_AUTOUPDATE', $scope)
        if ($v -and ($v.Trim() -match '^(0|false|no|off)$')) { return "BOB_AUTOUPDATE=$($v.Trim())" }
        $n = [Environment]::GetEnvironmentVariable('BOBIVERSE_NO_UPDATE', $scope)
        if ($n -and ($n.Trim() -eq '1')) { return 'BOBIVERSE_NO_UPDATE=1' }
    }
    if ($InstallRoot -and (Test-Path -LiteralPath (Join-Path $InstallRoot 'config\autoupdate.disabled'))) {
        return 'config\autoupdate.disabled present'
    }
    return $null
}

function ConvertTo-Ver {
    param([string]$Text)
    if ($Text -and ($Text -match '(\d+)\.(\d+)\.(\d+)')) {
        return [version]('{0}.{1}.{2}' -f $Matches[1], $Matches[2], $Matches[3])
    }
    return $null
}

function Get-State {
    $s = @{ pending = $null; failures = @{}; lastResult = ''; lastTag = ''; lastAttemptUtc = ''; lastCheckUtc = '' }
    if ($script:StateFile -and (Test-Path -LiteralPath $script:StateFile)) {
        try {
            $o = Get-Content -LiteralPath $script:StateFile -Raw | ConvertFrom-Json
            if ($o.pending) { $s.pending = @{ tag = [string]$o.pending.tag; atUtc = [string]$o.pending.atUtc } }
            if ($o.failures) { foreach ($p in $o.failures.PSObject.Properties) { $s.failures[$p.Name] = [int]$p.Value } }
            $s.lastResult = [string]$o.lastResult
            $s.lastTag = [string]$o.lastTag
            $s.lastAttemptUtc = [string]$o.lastAttemptUtc
            $s.lastCheckUtc = [string]$o.lastCheckUtc
        } catch { Write-UpdLog 'state-unreadable (reset)' }
    }
    return $s
}

function Save-State {
    param($State)
    $tmp = $script:StateFile + '.tmp'
    ($State | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $script:StateFile -Force
}

function ConvertTo-UtcDate {
    param([string]$Text)
    if (-not $Text) { return $null }
    try { return [datetime]::Parse($Text, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime() } catch { return $null }
}

function Get-LatestRelease {
    if ($ReleaseJson) { return (Get-Content -LiteralPath $ReleaseJson -Raw | ConvertFrom-Json) }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $uri = "https://api.github.com/repos/$Repo/releases/latest"
    $tv = ConvertTo-Ver $TargetVersion
    if ($tv) {
        # FR #77: UPDATE <product> <ver> pins an allowlisted release tag (never a free-form URL).
        $uri = "https://api.github.com/repos/$Repo/releases/tags/v$($tv.ToString())"
    }
    return (Invoke-RestMethod -Uri $uri `
            -Headers @{ 'User-Agent' = 'bobiverse-self-update'; Accept = 'application/vnd.github+json' } -TimeoutSec 15)
}

function Test-AssetUrl {
    param([string]$Url)
    if ($Url -match '^https://') {
        return ($Url -match ('^https://github\.com/{0}/releases/download/[^?#\s]+$' -f [regex]::Escape($Repo)))
    }
    return ($AllowLocalAssets -and (Test-Path -LiteralPath $Url))
}

function Get-Asset {
    # FR #1545: hard timeout + retries + curl.exe fallback. Invoke-WebRequest can stall
    # forever on a half-open GitHub TLS socket (0-byte OutFile, mutex held). curl --max-time
    # fails closed so Apply can Set-Failure download-failed and release the mutex.
    param(
        [string]$Url,
        [string]$Dest,
        [int]$TimeoutSec = 120,
        [int]$Retries = 2
    )
    if (-not (Test-AssetUrl -Url $Url)) { throw "asset url rejected" }
    if ($Url -notmatch '^https://') {
        Copy-Item -LiteralPath $Url -Destination $Dest -Force
        return
    }
    $dir = Split-Path -Parent $Dest
    if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $attempts = 1 + [Math]::Max(0, $Retries)
    $lastErr = $null
    for ($i = 1; $i -le $attempts; $i++) {
        Remove-Item -LiteralPath $Dest -Force -ErrorAction SilentlyContinue
        # 1) IWR with hard TimeoutSec (no-progress stalls still hang on some WinPS builds — keep short).
        try {
            Write-UpdLog ("download-try method=iwr attempt={0}/{1} timeout={2}s url={3}" -f $i, $attempts, $TimeoutSec, $Url)
            Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing -TimeoutSec $TimeoutSec -Headers @{ 'User-Agent' = 'bobiverse-self-update' }
            if ((Test-Path -LiteralPath $Dest) -and ((Get-Item -LiteralPath $Dest).Length -gt 0)) {
                Write-UpdLog ("download-ok method=iwr bytes={0}" -f (Get-Item -LiteralPath $Dest).Length)
                return
            }
            $lastErr = 'iwr produced empty file'
            Write-UpdLog "download-warn $lastErr"
        } catch {
            $lastErr = "$($_.Exception.GetType().Name): $($_.Exception.Message)"
            Write-UpdLog "download-warn method=iwr $lastErr"
        }
        Remove-Item -LiteralPath $Dest -Force -ErrorAction SilentlyContinue
        # 2) curl.exe fallback (Windows 10+ ships curl).
        $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
        if (-not (Test-Path -LiteralPath $curl)) {
            $cmd = Get-Command curl.exe -ErrorAction SilentlyContinue
            if ($cmd) { $curl = $cmd.Source }
        }
        if (Test-Path -LiteralPath $curl) {
            try {
                Write-UpdLog ("download-try method=curl attempt={0}/{1} max-time={2}s" -f $i, $attempts, $TimeoutSec)
                $prev = $ErrorActionPreference
                $ErrorActionPreference = 'Continue'
                $clog = & $curl -sSL --fail --retry 2 --retry-delay 2 --connect-timeout 30 --max-time $TimeoutSec `
                    -A 'bobiverse-self-update' -o $Dest $Url 2>&1
                $ccode = $LASTEXITCODE
                $ErrorActionPreference = $prev
                if ($ccode -eq 0 -and (Test-Path -LiteralPath $Dest) -and ((Get-Item -LiteralPath $Dest).Length -gt 0)) {
                    Write-UpdLog ("download-ok method=curl bytes={0}" -f (Get-Item -LiteralPath $Dest).Length)
                    return
                }
                $lastErr = "curl exit=$ccode $(($clog | Select-Object -First 3) -join ' ')"
                Write-UpdLog "download-warn method=curl $lastErr"
            } catch {
                $lastErr = "curl $($_.Exception.GetType().Name): $($_.Exception.Message)"
                Write-UpdLog "download-warn $lastErr"
            }
        } else {
            Write-UpdLog 'download-warn curl.exe not found'
        }
        if ($i -lt $attempts) { Start-Sleep -Seconds ([Math]::Min(5 * $i, 15)) }
    }
    Remove-Item -LiteralPath $Dest -Force -ErrorAction SilentlyContinue
    throw "download-failed after $attempts attempts: $lastErr"
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Set-Failure {
    param(
        [string]$Tag,
        [string]$Result,
        [switch]$NoCount   # FR #2563: record outcome without burning MaxAttempts (backup-only fails)
    )
    $st = Get-State
    if (-not $NoCount) {
        $n = 0
        if ($st.failures.ContainsKey($Tag)) { $n = [int]$st.failures[$Tag] }
        $st.failures[$Tag] = $n + 1
    }
    $st.pending = $null
    $st.lastResult = $Result
    $st.lastTag = $Tag
    $st.lastAttemptUtc = (Get-Date).ToUniversalTime().ToString('o')
    Save-State $st
}

function Ensure-ServiceRunning {
    # FR #2563: after pre-msiexec Apply abort (esp. backup fail) leave the service Running.
    param([string]$Why = 'apply-abort')
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $svc) { Write-UpdLog "ensure-running-skip missing=$ServiceName why=$Why"; return }
    if ($svc.Status -eq 'Running') { Write-UpdLog "ensure-running already=$ServiceName why=$Why"; return }
    try {
        Start-Service -Name $ServiceName -ErrorAction Stop
        if (Wait-ServiceState -Name $ServiceName -Status 'Running' -Seconds 60) {
            Write-UpdLog "ensure-running ok=$ServiceName why=$Why"
        } else {
            Write-UpdLog "ensure-running-timeout $ServiceName why=$Why"
        }
    } catch {
        Write-UpdLog "ensure-running-failed $ServiceName why=$Why $($_.Exception.GetType().Name)"
    }
}

function Start-DetachedApply {
    param([string]$Plan)
    $runDir = Join-Path $StateDir 'run'
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    # Run from a copy: the MSI replaces <InstallRoot>\scripts while the helper is still running.
    $helper = Join-Path $runDir 'Update-BobiverseService.ps1'
    Copy-Item -LiteralPath $PSCommandPath -Destination $helper -Force
    $psArgs = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Product {1} -Mode Apply -InstallRoot "{2}" -ServiceName {3} -StateDir "{4}" -PlanFile "{5}" -Repo {6}' -f `
        $helper, $Product, $InstallRoot, $ServiceName, $StateDir, $Plan, $Repo
    $taskName = "bobiverse-update-$Product"
    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $psArgs
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null
        Start-ScheduledTask -TaskName $taskName
        return 'scheduled-task'
    } catch {
        Write-UpdLog "scheduled-task-failed ($($_.Exception.GetType().Name)); trying WMI process"
    }
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = ('powershell.exe ' + $psArgs); CurrentDirectory = $runDir }
    if ($r.ReturnValue -ne 0) { throw "Win32_Process Create failed ($($r.ReturnValue))" }
    return 'wmi-process'
}

# ---------------------------------------------------------------- Apply-mode helpers
function Wait-ServiceState {
    param([string]$Name, [string]$Status, [int]$Seconds)
    try {
        (Get-Service -Name $Name -ErrorAction Stop).WaitForStatus($Status, [TimeSpan]::FromSeconds($Seconds))
        return $true
    } catch { return $false }
}

function Get-ExternalHomes {
    $leaves = switch ($Product) {
        'jeeves' { @('.jeeves', '.bobiverse') }
        'bob' { @('.bobiverse') }
        default { @('.airc', '.airc-console') }
    }
    $roots = @((Join-Path $env:SystemDrive 'Users\Administrator'))
    if ($env:USERPROFILE) { $roots += $env:USERPROFILE }
    $seen = @{}
    foreach ($r in $roots) {
        foreach ($l in $leaves) {
            $p = Join-Path $r $l
            if ((Test-Path -LiteralPath $p) -and -not $seen.ContainsKey($p.ToLowerInvariant())) {
                $seen[$p.ToLowerInvariant()] = $true
                $p
            }
        }
    }
}

function Backup-Install {
    # FR #2563: robocopy 0-7 = success; on >=8 log failing paths, retry once after service settle,
    # exclude volatile dirs/files so locked peers.json / .pytest_cache cannot burn MaxAttempts.
    param([string]$OldVersion)
    try {
        $rootItem = Get-Item -LiteralPath $InstallRoot -ErrorAction Stop
        $driveName = $rootItem.PSDrive.Name
        if (-not $driveName -and $InstallRoot -match '^[A-Za-z]:') { $driveName = $InstallRoot.Substring(0, 1) }
        if ($driveName) {
            $freeGB = [math]::Round((Get-PSDrive -Name $driveName).Free / 1GB, 2)
            if ($freeGB -lt 2) {
                Write-UpdLog "backup-warn disk-low freeGB=$freeGB (want >=2 before backup)"
            }
        }
    } catch { }

    $dest = Join-Path $StateDir ('backup\{0}-{1}' -f $OldVersion, (Get-Date).ToString('yyyyMMddHHmmss'))
    $tree = Join-Path $dest 'tree'
    New-Item -ItemType Directory -Force -Path $tree | Out-Null
    # Volatile / locked under live installs: test caches, update staging, worker run copies, peers.json.
    $xd = @('ergo', 'logs', '.git', '__pycache__', 'update', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'node_modules')
    $xf = @('*.msi', 'peers.json', '*.lock')
    $roboBase = @($InstallRoot, $tree, '/E')
    foreach ($d in $xd) { $roboBase += @('/XD', $d) }
    foreach ($f in $xf) { $roboBase += @('/XF', $f) }

    $rc = 8
    $maxTries = 2
    for ($try = 1; $try -le $maxTries; $try++) {
        if ($try -gt 1) {
            Start-Sleep -Seconds 3
            Write-UpdLog "backup-retry attempt=$try after robocopy $rc"
        }
        $quietArgs = $roboBase + @('/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
        & robocopy.exe @quietArgs | Out-Null
        $rc = [int]$LASTEXITCODE
        if ($rc -lt 8) { break }
        # Diagnostic pass (/L = list-only): surface ERROR lines without rewriting the tree.
        $diagArgs = $roboBase + @('/L', '/R:0', '/W:0', '/NJH', '/NJS', '/NP')
        $diagLines = @(& robocopy.exe @diagArgs 2>&1 | ForEach-Object { "$_" } |
                Where-Object { $_ -match '(?i)ERROR|Access is denied|being used by another' } |
                Select-Object -First 12)
        if ($diagLines.Count -gt 0) {
            Write-UpdLog ("backup-robocopy-errors exit={0} paths={1}" -f $rc, (($diagLines -join ' | ').Substring(0, [Math]::Min(400, (($diagLines -join ' | ').Length)))))
        } else {
            Write-UpdLog "backup-robocopy-errors exit=$rc paths=(none listed; check locks under InstallRoot)"
        }
    }
    if ($rc -ge 8) { throw "backup of install tree failed (robocopy $rc)" }

    $i = 0
    foreach ($h in @(Get-ExternalHomes)) {
        $i++
        $d = Join-Path $dest ('external\{0}-{1}' -f $i, (Split-Path -Leaf $h))
        & robocopy.exe $h $d /E /XD logs __pycache__ .pytest_cache /XF peers.json *.lock /MAX:52428800 /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) {
            Write-UpdLog "backup-external-warn home=$h robocopy=$LASTEXITCODE (continuing; tree backup ok)"
        }
    }
    # the backup holds credentials: SYSTEM + Administrators only
    try { & icacls.exe $dest /inheritance:r /grant:r 'NT AUTHORITY\SYSTEM:(OI)(CI)F' 'BUILTIN\Administrators:(OI)(CI)F' 2>&1 | Out-Null } catch { }
    $global:LASTEXITCODE = 0
    return $dest
}

function Remove-OldBackups {
    $root = Join-Path $StateDir 'backup'
    if (-not (Test-Path -LiteralPath $root)) { return }
    Get-ChildItem -LiteralPath $root -Directory | Sort-Object Name -Descending | Select-Object -Skip 2 |
        ForEach-Object { try { Remove-Item -LiteralPath $_.FullName -Recurse -Force } catch { } }
}

function Update-SkillsInProfiles {
    # Refresh this product's skills in every profile that already has a .grok\skills folder (the MSI custom
    # action runs as SYSTEM, so its own skill copy lands in the SYSTEM profile). File copies only.
    $src = Join-Path $InstallRoot '.grok\skills'
    if (-not (Test-Path -LiteralPath $src)) { Write-UpdLog 'skills-skip (no .grok\skills in install)'; return }
    $names = @(Get-ChildItem -LiteralPath $src -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq "bobiverse-$Product" -or $_.Name -like "bobiverse-$Product-*" -or
                $_.Name -in @('bobiverse-fleet-ops', 'harvest', 'harvest-agent-skills') } | ForEach-Object { $_.Name })
    $profiles = @()
    $usersRoot = Join-Path $env:SystemDrive 'Users'
    if (Test-Path -LiteralPath $usersRoot) {
        $profiles = @(Get-ChildItem -LiteralPath $usersRoot -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -notmatch '^(Public|Default.*|All Users)$' } |
                ForEach-Object { Join-Path $_.FullName '.grok\skills' } |
                Where-Object { Test-Path -LiteralPath $_ })
    }
    $n = 0
    foreach ($dstRoot in $profiles) {
        foreach ($name in $names) {
            $from = Join-Path $src $name
            if (-not (Test-Path -LiteralPath $from)) { continue }
            try {
                $to = Join-Path $dstRoot $name
                $tmp = $to + '.new'
                if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
                Copy-Item -LiteralPath $from -Destination $tmp -Recurse -Force
                if (Test-Path -LiteralPath $to) { Remove-Item -LiteralPath $to -Recurse -Force }
                Rename-Item -LiteralPath $tmp -NewName $name
                $n++
            } catch { Write-UpdLog "skills-warn $name $($_.Exception.GetType().Name)" }
        }
    }
    Write-UpdLog "skills-refreshed copies=$n profiles=$($profiles.Count)"
}

function Get-ServiceAppParameters {
    try {
        $k = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
        if (Test-Path -LiteralPath $k) { return [string](Get-ItemProperty -LiteralPath $k -Name AppParameters -ErrorAction Stop).AppParameters }
    } catch { }
    return ''
}

function Get-BobiverseArpProduct {
    # FR #1432: Uninstall registry row for bobiverse <$Product> (DisplayVersion / ProductCode).
    $want = "bobiverse $Product"
    foreach ($root in @(
            'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
        )) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        foreach ($k in @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue)) {
            try {
                $p = Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction Stop
                if ([string]$p.DisplayName -ne $want) { continue }
                $ver = ConvertTo-Ver ([string]$p.DisplayVersion)
                return [pscustomobject]@{
                    ProductCode    = [string]$k.PSChildName
                    DisplayVersion = [string]$p.DisplayVersion
                    Version        = $ver
                }
            } catch { }
        }
    }
    return $null
}

function Invoke-BobiverseArpUninstall {
    # Quietly remove a registered product so the next /i is a real install, not maintenance mode.
    param([Parameter(Mandatory)][string]$ProductCode, [string]$Why = 'arp-heal')
    if ($ProductCode -notmatch '^\{[0-9A-Fa-f-]{36}\}$') {
        Write-UpdLog "$Why-skip bad ProductCode"
        return $false
    }
    $mlog = Join-Path $StateDir ('msiexec-uninstall-{0}.log' -f ($Why -replace '[^a-z0-9-]', ''))
    $p = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\msiexec.exe') -PassThru -WindowStyle Hidden `
        -ArgumentList @('/x', $ProductCode, '/qn', '/norestart', 'REBOOT=ReallySuppress', '/l*v', ('"{0}"' -f $mlog))
    $null = $p.Handle
    if (-not $p.WaitForExit(600000)) {
        Write-UpdLog "$Why-timeout ProductCode=$ProductCode"
        return $false
    }
    $code = [int]$p.ExitCode
    Write-UpdLog "$Why msiexec-uninstall-exit=$code ProductCode=$ProductCode"
    return (@(0, 1605, 3010) -contains $code)  # 1605 = already uninstalled
}

function Get-AppParam {
    param([string]$AppParameters, [string]$Name)
    if ($AppParameters -match ('-{0}\s+"([^"]+)"' -f $Name)) { return $Matches[1] }
    if ($AppParameters -match ('-{0}\s+([A-Za-z0-9_.-]+)' -f $Name)) { return $Matches[1] }
    return ''
}

function Invoke-ServiceReregister {
    # Re-run the product's own installer script from the installed tree (no copy, no start, Ergo untouched),
    # carrying over the identity the service was registered with. Used by rollback and by the post-install
    # identity reconcile.
    param([string]$AppParameters, [string]$LogName, [string]$What)
    $inst = Join-Path $InstallRoot ('scripts\Install-{0}.ps1' -f (Get-Culture).TextInfo.ToTitleCase($Product))
    if (-not (Test-Path -LiteralPath $inst)) { Write-UpdLog "$What-warn install script missing"; return }
    $ia = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $inst, '-NoStart')
    $mid = Get-AppParam -AppParameters $AppParameters -Name 'MachineId'
    switch ($Product) {
        'bob' {
            $ia += '-SkipCopy'
            if ($mid) { $ia += @('-MachineId', $mid) }
            $h = Get-AppParam -AppParameters $AppParameters -Name 'BobHome'
            if ($h) { $ia += @('-BobHome', $h) }
        }
        'jeeves' {
            $ia += @('-SkipCopy', '-SkipErgo')
            $h = Get-AppParam -AppParameters $AppParameters -Name 'ChairHome'
            if ($h) { $ia += @('-ChairHome', $h) }
        }
        'airc' {
            if ($mid) { $ia += @('-MachineId', $mid) }
            $h = Get-AppParam -AppParameters $AppParameters -Name 'ConsoleHome'
            if ($h) { $ia += @('-ConsoleHome', $h) }
        }
    }
    $rlog = Join-Path $StateDir $LogName
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & powershell.exe @ia *> $rlog } finally { $ErrorActionPreference = $prev }
    Write-UpdLog "$What-service-reregistered exit=$LASTEXITCODE (log: $LogName)"
}

function Invoke-Rollback {
    param([string]$BackupDir, [string]$AppParameters, [string]$Why)
    Write-UpdLog "rollback-start reason=$Why"
    try {
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -ne 'Stopped') {
            try { Stop-Service -Name $ServiceName -ErrorAction Stop } catch { }
            [void](Wait-ServiceState -Name $ServiceName -Status 'Stopped' -Seconds 60)
        }
        $tree = Join-Path $BackupDir 'tree'
        if (Test-Path -LiteralPath $tree) {
            & robocopy.exe $tree $InstallRoot /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
            $global:LASTEXITCODE = 0
            Write-UpdLog 'rollback-files-restored'
        }
        if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) {
            Invoke-ServiceReregister -AppParameters $AppParameters -LogName 'rollback-install.log' -What 'rollback'
        }
        if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
            try { Start-Service -Name $ServiceName -ErrorAction Stop } catch { Write-UpdLog "rollback-warn start failed $($_.Exception.GetType().Name)" }
        }
        $ok = (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue).Status -eq 'Running'
        Write-UpdLog "rollback-done service_running=$ok"
    } catch {
        Write-UpdLog "rollback-error $($_.Exception.GetType().Name): $($_.Exception.Message)"
    }
}

function Invoke-Apply {
    if (-not (Test-Path -LiteralPath $PlanFile)) { Write-UpdLog 'apply-abort plan missing'; return }
    $plan = Get-Content -LiteralPath $PlanFile -Raw | ConvertFrom-Json
    $tag = [string]$plan.tag
    $target = ConvertTo-Ver ([string]$plan.version)
    if (-not $target) { Write-UpdLog 'apply-abort bad plan version'; return }

    $mutex = New-Object System.Threading.Mutex($false, "Global\bobiverse-update-$Product")
    $held = $false
    try { $held = $mutex.WaitOne(5000) } catch [System.Threading.AbandonedMutexException] { $held = $true }
    if (-not $held) { Write-UpdLog 'apply-skip another helper holds the update mutex'; return }
    $backup = $null
    $appParams = ''
    $msiMutex = $null
    $msiHeld = $false
    try {
        if ($DelaySeconds -gt 0) { Start-Sleep -Seconds $DelaySeconds }   # let the current instance finish starting
        $oldVer = ConvertTo-Ver (Get-Content -LiteralPath (Join-Path $InstallRoot 'VERSION') -Raw -ErrorAction SilentlyContinue)
        $oldText = if ($oldVer) { $oldVer.ToString() } else { 'unknown' }
        Write-UpdLog "apply-start from=$oldText to=$($target.ToString()) tag=$tag"

        $work = Join-Path $StateDir ('work\' + $tag)
        New-Item -ItemType Directory -Force -Path $work | Out-Null
        $msi = Join-Path $work ([string]$plan.msiName)
        $shaFile = $msi + '.sha256'
        try {
            Get-Asset -Url ([string]$plan.msiUrl) -Dest $msi
            Get-Asset -Url ([string]$plan.shaUrl) -Dest $shaFile
        } catch {
            Write-UpdLog "download-failed $($_.Exception.GetType().Name): $($_.Exception.Message) - service untouched"
            Set-Failure -Tag $tag -Result 'download-failed'
            return
        }
        $expected = $null
        $first = (Get-Content -LiteralPath $shaFile -TotalCount 1 -ErrorAction SilentlyContinue)
        if ($first -match '^\s*([0-9a-fA-F]{64})\b') { $expected = $Matches[1].ToLowerInvariant() }
        $actual = (Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLowerInvariant()
        if (-not $expected -or $expected -ne $actual) {
            Write-UpdLog "sha256-mismatch tag=$tag expected=$expected actual=$actual - aborted, service untouched"
            Set-Failure -Tag $tag -Result 'sha256-mismatch'
            Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
            return
        }
        Write-UpdLog "sha256-verified $actual"
        if ($VerifyOnly) { Write-UpdLog 'verify-only done (service untouched)'; return }

        # Windows Installer runs one install at a time and ircBob/ircJeeves/Airc start together after a release:
        # serialise the helpers machine-wide BEFORE stopping anything, so a service is only down while its own
        # MSI is being applied.
        $msiMutex = New-Object System.Threading.Mutex($false, 'Global\bobiverse-update-msi')
        try { $msiHeld = $msiMutex.WaitOne(1800000) } catch [System.Threading.AbandonedMutexException] { $msiHeld = $true }
        if (-not $msiHeld) {
            Write-UpdLog 'apply-skip install slot busy for 30 min - will retry on a later start'
            Set-Failure -Tag $tag -Result 'install-slot-timeout'
            return
        }
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        $appParams = Get-ServiceAppParameters
        if ($svc -and $svc.Status -ne 'Stopped') {
            try { Stop-Service -Name $ServiceName -ErrorAction Stop } catch {
                Write-UpdLog "stop-failed $($_.Exception.GetType().Name) - aborted, nothing changed"
                Set-Failure -Tag $tag -Result 'stop-failed'
                return
            }
            if (-not (Wait-ServiceState -Name $ServiceName -Status 'Stopped' -Seconds 90)) {
                Write-UpdLog 'stop-timeout - aborted; restarting'
                try { Start-Service -Name $ServiceName } catch { }
                Set-Failure -Tag $tag -Result 'stop-timeout'
                return
            }
            Write-UpdLog "service-stopped $ServiceName"
        }

        $backup = Backup-Install -OldVersion $oldText
        Write-UpdLog "backup-done dir=$(Split-Path -Leaf $backup)"

        # FR #1432: a prior apply that rolled back files can leave ARP at the newer ProductCode while
        # InstallRoot\VERSION is old. The next msiexec /i then runs maintenance mode (no file rewrite)
        # and VERSION verify fails forever. Uninstall the desynced product first so /i is a real install.
        $arp = Get-BobiverseArpProduct
        if ($arp -and $arp.Version -and $oldVer -and ($arp.Version -gt $oldVer)) {
            Write-UpdLog ("arp-desync-uninstall ARP={0} file={1} ProductCode={2}" -f $arp.DisplayVersion, $oldText, $arp.ProductCode)
            [void](Invoke-BobiverseArpUninstall -ProductCode $arp.ProductCode -Why 'arp-desync-uninstall')
        } elseif ($arp -and $arp.Version -and ($arp.Version -ge $target) -and $oldVer -and ($oldVer -lt $target)) {
            Write-UpdLog ("arp-desync-uninstall ARP={0} already>=target file={1} ProductCode={2}" -f $arp.DisplayVersion, $oldText, $arp.ProductCode)
            [void](Invoke-BobiverseArpUninstall -ProductCode $arp.ProductCode -Why 'arp-desync-uninstall')
        }

        $mlog = Join-Path $StateDir ('msiexec-{0}.log' -f $tag)
        # FR #2475: serialise msiexec + retry 1618 (ERROR_INSTALL_ALREADY_RUNNING)
        if (Get-Command Invoke-BobiverseMsiexecSerialized -ErrorAction SilentlyContinue) {
            $msiResult = Invoke-BobiverseMsiexecSerialized -ArgumentList @('/i', ('"{0}"' -f $msi), '/qn', '/norestart', 'REBOOT=ReallySuppress', '/l*v', ('"{0}"' -f $mlog)) -LogPath $mlog -TimeoutMs 1200000
            $code = [int]$msiResult.ExitCode
        } else {
            $p = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\msiexec.exe') -PassThru -WindowStyle Hidden `
                -ArgumentList @('/i', ('"{0}"' -f $msi), '/qn', '/norestart', 'REBOOT=ReallySuppress', '/l*v', ('"{0}"' -f $mlog))
            $null = $p.Handle
            if (-not $p.WaitForExit(1200000)) {
                Write-UpdLog 'msiexec-timeout (20 min) - left running, no rollback while it is active'
                Set-Failure -Tag $tag -Result 'msiexec-timeout'
                return
            }
            $code = [int]$p.ExitCode
        }
        Write-UpdLog "msiexec-exit=$code (log: $(Split-Path -Leaf $mlog)) FR#2475"
        if ($code -eq 1618) { throw 'msiexec exit 1618 after serialized retries (FR #2475)' }
        if (@(0, 3010, 1641) -notcontains $code) { throw "msiexec exit $code" }

        $verPath = Join-Path $InstallRoot 'VERSION'
        $newVer = ConvertTo-Ver (Get-Content -LiteralPath $verPath -Raw -ErrorAction SilentlyContinue)
        # FR #1432: msiexec success-family can still leave VERSION stale (NeverOverwrite on VERSION).
        # Stamp only when ARP agrees the target product is registered — never paper over a no-op
        # maintenance /i that left both bits and ARP on the old build (MRB #1477 hostile).
        if (-not $newVer -or $newVer -ne $target) {
            $arpAfter = Get-BobiverseArpProduct
            if ($arpAfter -and $arpAfter.Version -and ($arpAfter.Version -eq $target)) {
                Set-Content -LiteralPath $verPath -Value ($target.ToString() + [Environment]::NewLine) -Encoding ascii
                Write-UpdLog ("version-stamped-after-msi was={0} now={1} arp={2}" -f $(if ($newVer) { $newVer.ToString() } else { 'missing' }), $target.ToString(), $arpAfter.DisplayVersion)
                $newVer = ConvertTo-Ver (Get-Content -LiteralPath $verPath -Raw -ErrorAction SilentlyContinue)
            } else {
                Write-UpdLog ("version-stamp-skipped arp={0} (want {1})" -f $(if ($arpAfter) { $arpAfter.DisplayVersion } else { 'none' }), $target.ToString())
            }
        }
        if (-not $newVer -or $newVer -ne $target) { throw "installed VERSION is '$newVer', expected $($target.ToString())" }
        if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) { throw "service $ServiceName missing after install" }
        # The MSI custom action runs as SYSTEM without the old service's environment, so it can re-derive the
        # fleet identity (machine id / home) from COMPUTERNAME. Put the identity the service had back.
        if ($appParams) {
            $newParams = Get-ServiceAppParameters
            foreach ($key in @('MachineId', 'ConsoleHome', 'ChairHome', 'BobHome')) {
                $o = Get-AppParam -AppParameters $appParams -Name $key
                $n = Get-AppParam -AppParameters $newParams -Name $key
                if ($o -and $o -ne $n) {
                    # FR #2355: never restore ConsoleHome under Users\Default (NickServ GUID orphan).
                    if ($key -eq 'ConsoleHome' -and ($o -match '(?i)(?:^|[\\/])Users[\\/]Default(?:[\\/]|$)')) {
                        Write-UpdLog "identity-reconcile skip ConsoleHome under Users\Default (keeping installer value)"
                        continue
                    }
                    Write-UpdLog "identity-reconcile $key changed by the installer - restoring the previous value"
                    Invoke-ServiceReregister -AppParameters $appParams -LogName 'reconcile-install.log' -What 'reconcile'
                    break
                }
            }
        }
        Update-SkillsInProfiles
        if ((Get-Service -Name $ServiceName).Status -ne 'Running') { Start-Service -Name $ServiceName -ErrorAction Stop }
        Start-Sleep -Seconds 10
        if ((Get-Service -Name $ServiceName).Status -ne 'Running') { throw "service $ServiceName not running after install" }

        # FR #1018: MSI upgrade left BobCallback on old code (digest PermissionError / seats stuck doing).
        # FR #3190: do NOT restart BobAutoFocus — that ops task spammed per-item !focus every 2 min and is retired.
        if ($Product -eq 'jeeves') {
            foreach ($tn in @('BobCallback', 'BobAutoFeed')) {
                try {
                    $tq = Get-ScheduledTask -TaskName $tn -ErrorAction SilentlyContinue
                    if (-not $tq) {
                        Write-UpdLog "post-upgrade-task-skip missing=$tn"
                        continue
                    }
                    try { Stop-ScheduledTask -TaskName $tn -ErrorAction SilentlyContinue } catch { }
                    Start-ScheduledTask -TaskName $tn -ErrorAction Stop
                    Write-UpdLog "post-upgrade-task-restarted $tn"
                } catch {
                    Write-UpdLog "post-upgrade-task-warn $tn $($_.Exception.Message)"
                }
            }
            # FR #3190: if a leftover BobAutoFocus task still exists, disable it (never re-enable).
            try {
                $retire = Join-Path $PSScriptRoot 'Unregister-BobAutoFocus.ps1'
                if (Test-Path -LiteralPath $retire) {
                    & $retire -Quiet
                    Write-UpdLog 'post-upgrade-bobautofocus-retired'
                }
            } catch {
                Write-UpdLog "post-upgrade-bobautofocus-retire-warn $($_.Exception.Message)"
            }
        }

        # FR #1055: re-pin NSSM AppExit so graceful quit (exit 0) still Restart.
        try {
            $common = Join-Path $InstallRoot 'scripts\Bobiverse-Common.ps1'
            if (-not (Test-Path -LiteralPath $common)) {
                $common = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
            }
            if (Test-Path -LiteralPath $common) {
                . $common
                $nssmExe = Join-Path $InstallRoot 'third_party\nssm\win64\nssm.exe'
                if (-not (Test-Path -LiteralPath $nssmExe)) { $nssmExe = Join-Path $InstallRoot 'scripts\nssm.exe' }
                if (Test-Path -LiteralPath $nssmExe) {
                    Set-BobiverseNssmAppExitRestart -Nssm $nssmExe -ServiceName $ServiceName -RestartDelayMs 2000
                    Write-UpdLog "post-upgrade-appexit-restart $ServiceName"
                } else {
                    Write-UpdLog "post-upgrade-appexit-skip nssm missing"
                }
            }
        } catch {
            Write-UpdLog "post-upgrade-appexit-warn $($_.Exception.Message)"
        }

        $st = Get-State
        $st.pending = $null
        $st.lastResult = 'updated'
        $st.lastTag = $tag
        $st.lastAttemptUtc = (Get-Date).ToUniversalTime().ToString('o')
        $st.failures.Remove($tag)
        Save-State $st
        Write-UpdLog "apply-ok now=$($newVer.ToString()) tag=$tag"
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
        Remove-OldBackups
    } catch {
        $failMsg = [string]$_.Exception.Message
        Write-UpdLog "apply-failed $($_.Exception.GetType().Name): $failMsg"
        # FR #1432: if msiexec registered the new product but verify failed, uninstall ARP before
        # restoring files so the next start is not stuck in maintenance-mode /i.
        try {
            $arpFail = Get-BobiverseArpProduct
            if ($arpFail -and $arpFail.Version -and $target -and ($arpFail.Version -ge $target)) {
                Write-UpdLog ("arp-desync-uninstall on-fail ARP={0} ProductCode={1}" -f $arpFail.DisplayVersion, $arpFail.ProductCode)
                [void](Invoke-BobiverseArpUninstall -ProductCode $arpFail.ProductCode -Why 'arp-desync-uninstall')
            }
        } catch { Write-UpdLog "arp-desync-uninstall-warn $($_.Exception.Message)" }
        # FR #2563: backup-only fails must not burn MaxAttempts; always leave the service Running.
        $isBackupFail = $failMsg -match '(?i)backup of install tree failed'
        if ($backup) { Invoke-Rollback -BackupDir $backup -AppParameters $appParams -Why 'install-failed' }
        else { Ensure-ServiceRunning -Why $(if ($isBackupFail) { 'backup-failed' } else { 'apply-failed-pre-msi' }) }
        if ($isBackupFail) {
            Set-Failure -Tag $tag -Result 'backup-failed' -NoCount
            Write-UpdLog "backup-failed-no-loop-count tag=$tag (next Check may retry; -ForceCheck clears MaxAttempts block)"
        } else {
            Set-Failure -Tag $tag -Result 'rolled-back'
        }
    } finally {
        if ($msiHeld) { try { $msiMutex.ReleaseMutex() } catch { } }
        try { $mutex.ReleaseMutex() } catch { }
        try { Unregister-ScheduledTask -TaskName "bobiverse-update-$Product" -Confirm:$false -ErrorAction SilentlyContinue } catch { }
    }
}

# ---------------------------------------------------------------- Check mode
function Invoke-Check {
    $reason = Get-OptOutReason
    if ($reason) { Write-UpdLog "check result=skipped-optout ($reason)"; return }

    $verFile = Join-Path $InstallRoot 'VERSION'
    $local = ConvertTo-Ver (Get-Content -LiteralPath $verFile -Raw -ErrorAction SilentlyContinue)
    if (-not $local) { Write-UpdLog 'check result=skipped (no installed VERSION; not an MSI install tree)'; return }

    $st = Get-State
    if ($st.pending) {
        $at = ConvertTo-UtcDate $st.pending.atUtc
        $pendingAgeMin = if ($at) { ((Get-Date).ToUniversalTime() - $at).TotalMinutes } else { [double]::PositiveInfinity }
        # FR #1018: clear orphan pending when the helper scheduled task is not Running
        # (do not block 40 min when apply never started). Ignore our own Check-mode process.
        $helperTask = "bobiverse-update-$Product"
        $taskAlive = $false
        try {
            $t = Get-ScheduledTask -TaskName $helperTask -ErrorAction SilentlyContinue
            if ($t -and $t.State -eq 'Running') { $taskAlive = $true }
        } catch { }
        if (-not $taskAlive -and $pendingAgeMin -ge 2) {
            Write-UpdLog "pending-orphan tag=$($st.pending.tag) ageMin=$([int]$pendingAgeMin) - helper task not running; clearing pending"
            $st.pending = $null
            $st.lastResult = 'pending-orphan-cleared'
            Save-State $st
            $st = Get-State
        } elseif ($pendingAgeMin -lt $script:PendingMinutes) {
            Write-UpdLog "check result=skipped-pending tag=$($st.pending.tag)"
            return
        } else {
            Write-UpdLog "pending-stale tag=$($st.pending.tag) - counted as a failed attempt"
            Set-Failure -Tag $st.pending.tag -Result 'stale-pending'
            $st = Get-State
        }
    }

    # A crash-looping service restarts every few seconds: do not hammer the unauthenticated GitHub API
    # (60 requests/hour/IP) - at most one live lookup per 2 minutes per product.
    # FR #77: IRC UPDATE uses -ForceCheck to bypass the throttle.
    # FR #2563: -ForceCheck also clears a MaxAttempts loop-guard for the same tag (operator escape).
    if (-not $ReleaseJson -and -not $ForceCheck) {
        $lc = ConvertTo-UtcDate $st.lastCheckUtc
        if ($lc -and (((Get-Date).ToUniversalTime() - $lc).TotalSeconds -lt 120)) { Write-UpdLog 'check result=throttled (checked <2 min ago)'; return }
        $st.lastCheckUtc = (Get-Date).ToUniversalTime().ToString('o')
        try { Save-State $st } catch { }
    } elseif ($ForceCheck -and -not $ReleaseJson) {
        $st.lastCheckUtc = (Get-Date).ToUniversalTime().ToString('o')
        try { Save-State $st } catch { }
    }
    $rel = $null
    try { $rel = Get-LatestRelease } catch {
        $code = $null
        try { $code = [int]$_.Exception.Response.StatusCode } catch { }
        $kind = if ($code -eq 403 -or $code -eq 429) { 'rate-limited' } elseif ($code) { "http-$code" } else { 'offline-or-error' }
        Write-UpdLog "check result=release-lookup-failed kind=$kind local=$($local.ToString()) - starting installed version"
        return
    }
    if (-not $rel -or -not $rel.assets) { Write-UpdLog 'check result=no-release-data - starting installed version'; return }

    $msi = @($rel.assets | Where-Object { $_.name -match ('^{0}-(\d+\.\d+\.\d+)\.msi$' -f [regex]::Escape($Product)) }) | Select-Object -First 1
    $tagVer = $null
    if ($rel.tag_name -match '^v?(\d+\.\d+\.\d+)$') { $tagVer = ConvertTo-Ver $Matches[1] }
    if (-not $msi -or -not $tagVer) { Write-UpdLog "check result=no-matching-asset tag=$($rel.tag_name)"; return }
    $remote = ConvertTo-Ver ([string]$msi.name)
    if (-not $remote -or $remote -ne $tagVer) { Write-UpdLog "check result=asset-tag-mismatch tag=$($rel.tag_name) asset=$($msi.name)"; return }
    $want = ConvertTo-Ver $TargetVersion
    if ($want -and $remote -ne $want) {
        Write-UpdLog "check result=target-version-mismatch want=$($want.ToString()) asset=$($remote.ToString())"
        return
    }
    $sha = @($rel.assets | Where-Object { $_.name -eq ($msi.name + '.sha256') }) | Select-Object -First 1
    if (-not $sha) { Write-UpdLog "check result=no-sha256-asset tag=$($rel.tag_name) - not updating"; return }
    if (-not (Test-AssetUrl -Url ([string]$msi.browser_download_url)) -or -not (Test-AssetUrl -Url ([string]$sha.browser_download_url))) {
        Write-UpdLog 'check result=asset-url-rejected'; return
    }

    $tag = 'v' + $remote.ToString()
    # Without TargetVersion never downgrade. Explicit IRC pin may match local only with ForceCheck.
    if (-not $want -and $remote -le $local) { Write-UpdLog "check result=current local=$($local.ToString()) latest=$($remote.ToString())"; return }
    if ($want -and $remote -lt $local) {
        Write-UpdLog "check result=current local=$($local.ToString()) latest=$($remote.ToString()) (refusing downgrade)"
        return
    }
    if ($want -and $remote -eq $local -and -not $ForceCheck) {
        Write-UpdLog "check result=current local=$($local.ToString()) latest=$($remote.ToString())"
        return
    }

    $fails = 0
    if ($st.failures.ContainsKey($tag)) { $fails = [int]$st.failures[$tag] }
    if ($fails -ge $MaxAttempts) {
        # FR #2563: -ForceCheck is the operator escape from a stuck MaxAttempts block.
        if ($ForceCheck) {
            Write-UpdLog "check result=loop-guard-bypassed ForceCheck tag=$tag failures=$fails"
            $st.failures.Remove($tag)
            Save-State $st
            $fails = 0
        } else {
            Write-UpdLog "check result=blocked-loop-guard tag=$tag failures=$fails (a newer release is needed; -ForceCheck clears)"
            return
        }
    }
    $last = ConvertTo-UtcDate $st.lastAttemptUtc
    if ($last -and $st.lastTag -eq $tag -and (((Get-Date).ToUniversalTime() - $last).TotalMinutes -lt $CooldownMinutes)) {
        Write-UpdLog "check result=cooldown tag=$tag"
        return
    }
    if ($DryRun) { Write-UpdLog "check result=would-update local=$($local.ToString()) latest=$($remote.ToString()) (DryRun)"; return }
    if (-not (Test-IsAdmin)) { Write-UpdLog 'check result=skipped-not-elevated (cannot install the MSI); starting installed version'; return }

    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    $plan = Join-Path $StateDir 'plan.json'
    @{
        product = $Product; tag = $tag; version = $remote.ToString(); msiName = [string]$msi.name
        msiUrl = [string]$msi.browser_download_url; shaUrl = [string]$sha.browser_download_url
        installRoot = $InstallRoot; serviceName = $ServiceName; fromVersion = $local.ToString()
        createdUtc = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $plan -Encoding UTF8

    $st.pending = @{ tag = $tag; atUtc = (Get-Date).ToUniversalTime().ToString('o') }
    $st.lastTag = $tag
    $st.lastAttemptUtc = (Get-Date).ToUniversalTime().ToString('o')
    $st.lastResult = 'scheduled'
    Save-State $st
    if ($NoSpawn) { Write-UpdLog "check result=scheduled-nospawn local=$($local.ToString()) latest=$($remote.ToString())"; return }
    try {
        $how = Start-DetachedApply -Plan $plan
        Write-UpdLog "check result=update-scheduled via=$how local=$($local.ToString()) latest=$($remote.ToString()) - starting installed version now"
    } catch {
        $st = Get-State
        $st.pending = $null
        $st.lastResult = 'spawn-failed'
        Save-State $st
        Write-UpdLog "check result=spawn-failed $($_.Exception.GetType().Name) - starting installed version"
    }
}

# ---------------------------------------------------------------- main (never throws in Check mode)
try {
    $Product = $Product.Trim().ToLowerInvariant()
    if (@('jeeves', 'bob', 'airc') -notcontains $Product) { Write-Host 'WARN self-update: -Product must be jeeves|bob|airc'; if ($Mode -eq 'Check') { exit 0 } else { exit 2 } }
    if (-not $InstallRoot) {
        # t780u: <drive>:\ai is discovered on the fixed disks (BOB_AI_ROOT overrides); C:\ai only if Common is missing.
        $common = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
        if (Test-Path -LiteralPath $common) { . $common; $InstallRoot = Get-BobiverseProductRoot -Product $Product }
        else { $InstallRoot = Join-Path 'C:\ai' $Product }
    }
    if (-not $ServiceName) { $ServiceName = switch ($Product) { 'bob' { 'ircBob' } 'jeeves' { 'ircJeeves' } default { 'Airc' } } }
    if ($Repo -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { Write-Host 'WARN self-update: bad -Repo'; exit 0 }
    $defaultState = -not $PSBoundParameters.ContainsKey('StateDir')
    if (-not $StateDir) {
        $pd = if ($env:ProgramData) { $env:ProgramData } else { 'C:\ProgramData' }
        $StateDir = Join-Path $pd "bobiverse\update\$Product"
    }
    try {
        New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
        # SYSTEM later runs a script copy and a plan from this folder: only SYSTEM + Administrators may write it
        # (ProgramData subfolders are user-writable by default = local privilege escalation otherwise).
        if ($defaultState -and (Test-IsAdmin)) {
            try { & icacls.exe $StateDir /inheritance:r /grant:r 'NT AUTHORITY\SYSTEM:(OI)(CI)F' 'BUILTIN\Administrators:(OI)(CI)F' 2>&1 | Out-Null } catch { }
            $global:LASTEXITCODE = 0
        }
        $script:LogFile = Join-Path $StateDir 'update.log'
        $script:StateFile = Join-Path $StateDir 'state.json'
    } catch {
        Write-Host "WARN self-update: cannot use state dir ($($_.Exception.GetType().Name))"
        exit 0
    }
    if ($Mode -eq 'Apply') { Invoke-Apply } else { Invoke-Check }
} catch {
    try { Write-UpdLog "unexpected-error $($_.Exception.GetType().Name): $($_.Exception.Message) - starting installed version" } catch { }
}
exit 0
