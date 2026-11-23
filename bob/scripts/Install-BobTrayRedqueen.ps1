#Requires -Version 5.1
<#
.SYNOPSIS
  FR #9419: deterministic build-bob-tray resolve + local redqueen bob-tray hotpatch.

.DESCRIPTION
  Operator-host tool (redqueen first). Resolves a green build-bob-tray artifact
  (or -ArtifactDir / -WorkflowRunId), verifies SHA-256 against MANIFEST.json /
  *.sha256, then either prints a DryRun JSON plan (default) or - with -Install -
  backs up the live install, writes ROLLBACK.ps1, copies tools/src/assets via
  Install-BobTrayHotpatch.ps1, and restarts TipForm in the interactive session.

  CAST IRON:
  - Default is DryRun when -Install is absent.
  - Never touches ircBob, Ergo, BobIrcd, seats, CredMan, identity, or queue.json.
  - Never installs from a failed/red build-bob-tray run or hash mismatch.
  - If no successful build-bob-tray artifact: exit without install; FR the build
    failures (operator/monitor). Do not -Install.

  One JSON object on stdout. Never prints secrets. ASCII-only.

.PARAMETER Install
  Apply the local hotpatch on this box (redqueen first). Required to mutate.

.PARAMETER DryRun
  Plan only (forced when -Install is omitted).

.PARAMETER ArtifactDir
  Folder with bob-tray.exe + MANIFEST.json (+ *.sha256 / tools/src/assets).

.PARAMETER WorkflowRunId
  Optional successful build-bob-tray.yml run id; otherwise latest green on main.
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$DryRun,
    [string]$InstallRoot = '',
    [string]$ArtifactDir = '',
    [string]$WorkflowRunId = '',
    [string]$Repo = 'SimonBarnett/bobiverse',
    [string]$Workflow = 'build-bob-tray.yml',
    [string]$ArtifactName = 'bob-tray',
    [string]$MachineId = '',
    [switch]$SkipTrayRestart
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-BobTrayRedqueenJson {
    param([hashtable]$Obj)
    Write-Output ($Obj | ConvertTo-Json -Compress -Depth 10)
}

function Get-BobTrayRedqueenSha256File {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Resolve-BobTrayRedqueenInstallRoot {
    param([string]$Requested)
    if ($Requested -and $Requested.Trim()) {
        return [IO.Path]::GetFullPath($Requested.Trim().TrimEnd('\', '/'))
    }
    foreach ($cand in @($env:BOB_TRAY_INSTALL_ROOT, $env:BOB_INSTALL_ROOT, 'C:\ai\bob', 'D:\ai\bob')) {
        if (-not $cand) { continue }
        $p = [IO.Path]::GetFullPath([string]$cand)
        if (Test-Path -LiteralPath (Join-Path $p 'scripts\Start-BobTray.ps1')) { return $p }
        if (Test-Path -LiteralPath (Join-Path $p 'tools\Watch-BobTray.ps1')) { return $p }
    }
    return [IO.Path]::GetFullPath('C:\ai\bob')
}

function Resolve-BobTrayRedqueenArtifactDir {
    param([string]$Requested, [string]$RunId, [string]$RepoName, [string]$WorkflowName, [string]$ArtName)
    if ($Requested -and $Requested.Trim()) {
        $p = [IO.Path]::GetFullPath($Requested.Trim())
        $exe = Join-Path $p 'bob-tray.exe'
        if (-not (Test-Path -LiteralPath $exe)) {
            $exe2 = Join-Path $p 'tools\bob-tray.exe'
            if (-not (Test-Path -LiteralPath $exe2)) {
                throw "ArtifactDir missing bob-tray.exe: $p"
            }
        }
        return @{ path = $p; run_id = $null; source = 'artifact_dir' }
    }
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) { throw 'gh missing; pass -ArtifactDir' }
    $rid = [string]$RunId
    if (-not $rid) {
        $runJson = & gh run list -R $RepoName --workflow $WorkflowName --branch main --status success --limit 1 --json databaseId,headSha,displayTitle,url 2>$null
        $runs = @($runJson | ConvertFrom-Json)
        if ($runs.Count -lt 1 -or -not $runs[0].databaseId) {
            throw "no successful $WorkflowName run on main; FR the build failures; do not -Install"
        }
        $rid = [string]$runs[0].databaseId
    }
    else {
        # Refuse non-success runs when an id is supplied.
        $one = & gh run view $rid -R $RepoName --json conclusion,status,headBranch,workflowName 2>$null | ConvertFrom-Json
        if (-not $one) { throw "gh run view failed for $rid" }
        $conc = [string]$one.conclusion
        $st = [string]$one.status
        if ($st -ne 'completed' -or $conc -ne 'success') {
            throw "workflow run $rid is not successful (status=$st conclusion=$conc); never install from failed/red run"
        }
    }
    $tmp = Join-Path $env:TEMP ('bob-tray-rq-' + [guid]::NewGuid().ToString('n').Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    & gh run download $rid -R $RepoName -n $ArtName -D $tmp 2>$null | Out-Null
    $exe = Get-ChildItem -LiteralPath $tmp -Recurse -Filter 'bob-tray.exe' -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $exe) { throw "gh run download $rid missing bob-tray.exe under $tmp; FR the build failures" }
    # Prefer the directory that also has MANIFEST.json beside the exe (or parent stage root).
    $dir = $exe.Directory.FullName
    if (-not (Test-Path -LiteralPath (Join-Path $dir 'MANIFEST.json'))) {
        $parent = $exe.Directory.Parent
        if ($parent -and (Test-Path -LiteralPath (Join-Path $parent.FullName 'MANIFEST.json'))) {
            $dir = $parent.FullName
        }
    }
    return @{ path = $dir; run_id = $rid; source = 'gh_run_download' }
}

function Assert-BobTrayRedqueenArtifact {
    param([string]$Dir)
    $exe = Join-Path $Dir 'bob-tray.exe'
    if (-not (Test-Path -LiteralPath $exe)) {
        $exe = Join-Path $Dir 'tools\bob-tray.exe'
    }
    if (-not (Test-Path -LiteralPath $exe)) { throw "missing bob-tray.exe under $Dir" }
    $got = Get-BobTrayRedqueenSha256File -Path $exe
    $expect = $null
    $manPath = Join-Path $Dir 'MANIFEST.json'
    if (-not (Test-Path -LiteralPath $manPath)) {
        $manPath = Join-Path $Dir 'tools\MANIFEST.json'
    }
    $script:BobTrayRedqueenManifest = $null
    if (Test-Path -LiteralPath $manPath) {
        $m = Get-Content -LiteralPath $manPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $script:BobTrayRedqueenManifest = $m
        if ($m.files) {
            foreach ($key in @('bob-tray.exe', 'tools/bob-tray.exe')) {
                $prop = $m.files.PSObject.Properties[$key]
                if ($prop -and $prop.Value) {
                    $expect = ([string]$prop.Value).ToLowerInvariant()
                    break
                }
            }
        }
        if (-not $expect -and $m.exe_sha256) {
            $expect = ([string]$m.exe_sha256).ToLowerInvariant()
        }
    }
    $shaFile = Join-Path $Dir 'bob-tray.exe.sha256'
    if (-not (Test-Path -LiteralPath $shaFile)) {
        $shaFile = Join-Path $Dir 'tools\bob-tray.exe.sha256'
    }
    if (-not $expect -and (Test-Path -LiteralPath $shaFile)) {
        $line = (Get-Content -LiteralPath $shaFile -TotalCount 1).Trim()
        if ($line -match '([a-fA-F0-9]{64})') { $expect = $Matches[1].ToLowerInvariant() }
    }
    if (-not $expect) { throw 'artifact missing MANIFEST bob-tray.exe hash and bob-tray.exe.sha256' }
    if ($got -ne $expect) { throw "hash mismatch got=$got expect=$expect" }
    $watch = Join-Path $Dir 'tools\Watch-BobTray.ps1'
    if (-not (Test-Path -LiteralPath $watch)) {
        throw "artifact missing tools\Watch-BobTray.ps1 under $Dir"
    }
    return @{
        exe_path      = $exe
        exe_sha256    = $got
        source_commit = $(if ($script:BobTrayRedqueenManifest -and $script:BobTrayRedqueenManifest.source_commit) { [string]$script:BobTrayRedqueenManifest.source_commit } elseif ($script:BobTrayRedqueenManifest -and $script:BobTrayRedqueenManifest.commit) { [string]$script:BobTrayRedqueenManifest.commit } else { '' })
        workflow_run_id = $(if ($script:BobTrayRedqueenManifest -and $script:BobTrayRedqueenManifest.workflow_run_id) { [string]$script:BobTrayRedqueenManifest.workflow_run_id } else { '' })
        size_bytes    = (Get-Item -LiteralPath $exe).Length
    }
}

function New-BobTrayRedqueenRollbackScript {
    param(
        [string]$WriteDir,
        [string]$BackupDir,
        [string]$Root,
        [string]$PrevHash
    )
    $bakEsc = $BackupDir.Replace("'", "''")
    $rootEsc = $Root.Replace("'", "''")
    $hashEsc = $PrevHash.Replace("'", "''")
    $body = @"
# ROLLBACK.ps1 - generated by Install-BobTrayRedqueen.ps1 (FR #9419).
# Restores tools/src/assets from backup. Never touches ircBob, Ergo, BobIrcd, seats, CredMan.
`$ErrorActionPreference = 'Stop'
`$bak = '$bakEsc'
`$root = '$rootEsc'
foreach (`$leaf in @('tools','src','assets')) {
  `$src = Join-Path `$bak `$leaf
  if (-not (Test-Path -LiteralPath `$src)) { continue }
  `$dest = Join-Path `$root `$leaf
  New-Item -ItemType Directory -Force -Path `$dest | Out-Null
  Copy-Item -Path (Join-Path `$src '*') -Destination `$dest -Recurse -Force
}
`$exe = Join-Path `$root 'tools\bob-tray.exe'
if (-not (Test-Path -LiteralPath `$exe)) { `$exe = Join-Path `$root 'bob-tray.exe' }
if (Test-Path -LiteralPath `$exe) {
  `$h = (Get-FileHash -LiteralPath `$exe -Algorithm SHA256).Hash.ToLowerInvariant()
  if (`$h -ne '$hashEsc' -and '$hashEsc' -ne '') {
    throw "rollback bob-tray hash mismatch got=`$h expect=$hashEsc"
  }
}
Write-Output 'INFO bob-tray ROLLBACK done'
"@
    if (-not (Test-Path -LiteralPath $WriteDir)) {
        New-Item -ItemType Directory -Force -Path $WriteDir | Out-Null
    }
    $path = Join-Path $WriteDir 'ROLLBACK.ps1'
    [IO.File]::WriteAllText($path, $body, (New-Object System.Text.UTF8Encoding $false))
    $null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$null)
    return $path
}

function Get-BobTrayRedqueenLiveHash {
    param([string]$Root)
    foreach ($rel in @('tools\bob-tray.exe', 'bob-tray.exe')) {
        $p = Join-Path $Root $rel
        if (Test-Path -LiteralPath $p) {
            return @{ path = $p; sha256 = (Get-BobTrayRedqueenSha256File -Path $p) }
        }
    }
    return @{ path = ''; sha256 = '' }
}

# --- main ---
$live = [bool]$Install
if (-not $live) { $DryRun = $true }
if ($live -and $DryRun) {
    Write-BobTrayRedqueenJson @{ ok = $false; error = 'refuse_both_Install_and_DryRun'; fr = 9419 }
    exit 2
}

$root = Resolve-BobTrayRedqueenInstallRoot -Requested $InstallRoot
try {
    $resolved = Resolve-BobTrayRedqueenArtifactDir -Requested $ArtifactDir -RunId $WorkflowRunId -RepoName $Repo -WorkflowName $Workflow -ArtName $ArtifactName
    $meta = Assert-BobTrayRedqueenArtifact -Dir $resolved.path
}
catch {
    Write-BobTrayRedqueenJson @{
        ok      = $false
        fr      = 9419
        error   = 'resolve_or_hash_failed'
        message = [string]$_.Exception.Message
        hint    = 'If no successful build-bob-tray artifact: FR the build failures; do not -Install'
        dry_run = [bool]$DryRun
        install = [bool]$Install
    }
    exit 1
}

$liveInfo = Get-BobTrayRedqueenLiveHash -Root $root
$sha8 = $meta.exe_sha256.Substring(0, 8)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $root ("_hotpatch_{0}-bob-tray-{1}" -f $stamp, $sha8)

$plan = [ordered]@{
    ok              = $true
    fr              = 9419
    action          = $(if ($live) { 'live_local_hotpatch' } else { 'dry_run' })
    install_root    = $root
    backup_dir      = $backupDir
    artifact_dir    = $resolved.path
    artifact_source = $resolved.source
    run_id          = $(if ($resolved.run_id) { $resolved.run_id } else { $meta.workflow_run_id })
    exe_sha256      = $meta.exe_sha256
    source_commit   = $meta.source_commit
    live_sha256     = $liveInfo.sha256
    live_path       = $liveInfo.path
    drift           = $(if ($liveInfo.sha256 -and ($liveInfo.sha256 -ne $meta.exe_sha256)) { $true } else { $false })
    install         = [bool]$Install
    dry_run         = [bool]$DryRun
    never           = @('ircBob', 'Ergo', 'BobIrcd', 'seats', 'CredMan', 'identity.json', 'queue.json')
    restart         = $(if ($SkipTrayRestart) { 'skip' } else { 'Start-BobTray -ForceNew -SkipTidy' })
}

if (-not $live) {
    Write-BobTrayRedqueenJson $plan
    exit 0
}

# Live local hotpatch (redqueen first)
try {
    $hotpatch = Join-Path $PSScriptRoot 'Install-BobTrayHotpatch.ps1'
    if (-not (Test-Path -LiteralPath $hotpatch)) {
        throw "missing Install-BobTrayHotpatch.ps1 beside this script"
    }
    if (-not $liveInfo.sha256) {
        # Allow first-time install when no prior exe; ROLLBACK still restores trees if present.
        $prevHash = ''
    }
    else {
        $prevHash = $liveInfo.sha256
    }

    $rb = New-BobTrayRedqueenRollbackScript -WriteDir $backupDir -BackupDir $backupDir -Root $root -PrevHash $prevHash
    $null = & $hotpatch -InstallRoot $root -ArtifactDir $resolved.path -BackupDir $backupDir
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        throw "Install-BobTrayHotpatch.ps1 exit $LASTEXITCODE"
    }

    $after = Get-BobTrayRedqueenLiveHash -Root $root
    if (-not $after.sha256) { throw 'post-install missing bob-tray.exe' }
    if ($after.sha256 -ne $meta.exe_sha256) {
        throw "post-install hash mismatch got=$($after.sha256) expect=$($meta.exe_sha256)"
    }

    $restarted = $false
    if (-not $SkipTrayRestart) {
        $startTray = Join-Path $root 'scripts\Start-BobTray.ps1'
        if (-not (Test-Path -LiteralPath $startTray)) {
            $startTray = Join-Path $PSScriptRoot 'Start-BobTray.ps1'
        }
        if (Test-Path -LiteralPath $startTray) {
            $mid = $MachineId
            if (-not $mid) { $mid = $env:COMPUTERNAME }
            $arg = @(
                '-NoProfile', '-STA', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass',
                '-File', $startTray,
                '-InstallRoot', $root,
                '-MachineId', $mid,
                '-ForceNew', '-SkipTidy', '-SkipServiceRestart'
            )
            Start-Process -FilePath 'powershell.exe' -ArgumentList $arg -WorkingDirectory $root | Out-Null
            $restarted = $true
        }
    }

    $plan.action = 'live_local_hotpatch_done'
    $plan.rollback_ps1 = $rb
    $plan.after_sha256 = $after.sha256
    $plan.tray_restarted = $restarted
    $plan.ok = ($after.sha256 -eq $meta.exe_sha256)
    Write-BobTrayRedqueenJson $plan
    if (-not $plan.ok) { exit 1 }
    exit 0
}
catch {
    Write-BobTrayRedqueenJson @{
        ok      = $false
        fr      = 9419
        error   = 'live_failed'
        message = [string]$_.Exception.Message
        dry_run = $false
        install = $true
        never   = @('ircBob', 'Ergo', 'BobIrcd', 'seats', 'CredMan')
    }
    exit 2
}
