#Requires -Version 5.1
<#
.SYNOPSIS
  FR #9376: deterministic build-resolve + WinRM hotpatch of jeeves.exe onto walrus.

.DESCRIPTION
  Operator-host tool (typically redqueen). Resolves a green build-jeeves artifact
  (or -ArtifactDir), verifies SHA-256, checks the Depends-on / Plan-agent gate
  issue list, then either prints a DryRun plan (default) or — only with -SiYes —
  opens WinRM to walrus, writes backup + ROLLBACK.ps1, swaps jeeves.exe (+ sha /
  MANIFEST / provenance) under C:\ai\jeeves\jeeves\, restarts ircJeeves only, and
  probes remote :7700/health.

  CAST IRON:
  - Live mutate requires -SiYes (agent/automation "go" is not enough).
  - Never touches ErgoWalrus, BobIrcd, ircd.yaml, NSSM env, CredMan, identity,
    queue.json, or IIS.
  - Never installs from red main / hash mismatch.
  - Default is DryRun when -SiYes is absent.

  One JSON object on stdout. Never prints secrets.

.PARAMETER SiYes
  Explicit Simon approval for this live walrus install. Required to mutate.

.PARAMETER DryRun
  Plan only (forced when -SiYes is omitted).

.PARAMETER SkipGateCheck
  Skip the open-issue gate list (test / Si override only).

.PARAMETER ArtifactDir
  Folder with jeeves.exe + jeeves.exe.sha256 + MANIFEST.json (+ provenance.txt).

.PARAMETER WorkflowRunId
  Optional successful build-jeeves.yml run id; otherwise latest green on main.
#>
[CmdletBinding()]
param(
    [switch]$SiYes,
    [switch]$DryRun,
    [switch]$SkipGateCheck,
    [switch]$StoreCredential,
    [string]$ComputerName = 'walrus',
    [string]$AiRoot = 'C:\ai',
    [string]$ArtifactDir = '',
    [string]$WorkflowRunId = '',
    [string]$Repo = 'SimonBarnett/bobiverse',
    [string]$Workflow = 'build-jeeves.yml',
    [string]$ArtifactName = 'jeeves',
    [string]$CredTarget = 'Bobiverse/UpdateFleet',
    [string]$User = 'wonderland\administrator',
    [int]$WinRmTimeoutSec = 180,
    [int]$HealthWaitSec = 45,
    [string[]]$GateIssues = @(
        'SimonBarnett/bobiverse#8833',
        'SimonBarnett/skills-visionary#155',
        'SimonBarnett/skills-visionary#156',
        'SimonBarnett/skills-visionary#190'
    )
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-JeevesWalrusJson {
    param([hashtable]$Obj)
    Write-Output ($Obj | ConvertTo-Json -Compress -Depth 10)
}

function Get-JeevesWalrusSha256File {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

# --- CredMan (same contract as Update-BobFleet; never log blob) ---
$script:CredManTypeReady = $false
function Ensure-JeevesWalrusCredManType {
    if ($script:CredManTypeReady) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class BobJeevesWalrusCredMan {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct CREDENTIAL {
    public uint Flags; public uint Type; public string TargetName; public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public uint CredentialBlobSize; public IntPtr CredentialBlob; public uint Persist;
    public uint AttributeCount; public IntPtr Attributes; public string TargetAlias; public string UserName;
  }
  [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern bool CredRead(string target, uint type, uint reservedFlag, out IntPtr credentialPtr);
  [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern bool CredWrite([In] ref CREDENTIAL userCredential, uint flags);
  [DllImport("advapi32.dll", SetLastError = true)]
  public static extern bool CredFree(IntPtr cred);
  public const uint CRED_TYPE_GENERIC = 1;
  public const uint CRED_PERSIST_LOCAL_MACHINE = 2;
}
'@
    $script:CredManTypeReady = $true
}

function Set-JeevesWalrusCredential {
    param([string]$Target, [string]$UserName)
    Ensure-JeevesWalrusCredManType
    $sec = Read-Host -AsSecureString -Prompt ("Password for $UserName (CredMan $Target)")
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        $bytes = [Text.Encoding]::Unicode.GetBytes($plain)
        $pin = [Runtime.InteropServices.Marshal]::AllocHGlobal($bytes.Length)
        try {
            [Runtime.InteropServices.Marshal]::Copy($bytes, 0, $pin, $bytes.Length)
            $cred = New-Object BobJeevesWalrusCredMan+CREDENTIAL
            $cred.Type = [BobJeevesWalrusCredMan]::CRED_TYPE_GENERIC
            $cred.TargetName = $Target
            $cred.UserName = $UserName
            $cred.CredentialBlobSize = [uint32]$bytes.Length
            $cred.CredentialBlob = $pin
            $cred.Persist = [BobJeevesWalrusCredMan]::CRED_PERSIST_LOCAL_MACHINE
            $ok = [BobJeevesWalrusCredMan]::CredWrite([ref]$cred, 0)
            if (-not $ok) {
                throw ("CredWrite failed winerror=" + [Runtime.InteropServices.Marshal]::GetLastWin32Error())
            }
        }
        finally {
            [Runtime.InteropServices.Marshal]::FreeHGlobal($pin)
        }
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
}

function Get-JeevesWalrusPSCredential {
    param([string]$Target, [string]$DefaultUser)
    Ensure-JeevesWalrusCredManType
    $ptr = [IntPtr]::Zero
    $ok = [BobJeevesWalrusCredMan]::CredRead($Target, [BobJeevesWalrusCredMan]::CRED_TYPE_GENERIC, 0, [ref]$ptr)
    if (-not $ok -or $ptr -eq [IntPtr]::Zero) {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "CredMan missing target=$Target winerror=$err; run Install-JeevesWalrusWinRm.ps1 -StoreCredential"
    }
    try {
        $cred = [Runtime.InteropServices.Marshal]::PtrToStructure($ptr, [type][BobJeevesWalrusCredMan+CREDENTIAL])
        $userName = [string]$cred.UserName
        if (-not $userName) { $userName = $DefaultUser }
        $size = [int]$cred.CredentialBlobSize
        if ($size -le 0 -or $cred.CredentialBlob -eq [IntPtr]::Zero) {
            throw "CredMan empty blob target=$Target"
        }
        $even = $size - ($size % 2)
        $bytes = New-Object byte[] $even
        [Runtime.InteropServices.Marshal]::Copy($cred.CredentialBlob, $bytes, 0, $even)
        $plain = ([Text.Encoding]::Unicode.GetString($bytes)).TrimEnd([char]0)
        $sec = ConvertTo-SecureString $plain -AsPlainText -Force
        return New-Object System.Management.Automation.PSCredential ($userName, $sec)
    }
    finally {
        [void][BobJeevesWalrusCredMan]::CredFree($ptr)
    }
}

function Parse-JeevesWalrusGateRef {
    param([string]$Ref)
    $m = [regex]::Match([string]$Ref, '^\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\s*$')
    if (-not $m.Success) { throw "bad gate ref (want owner/name#N): $Ref" }
    return @{ Repo = $m.Groups[1].Value; Number = [int]$m.Groups[2].Value }
}

function Test-JeevesWalrusGateIssuesClosed {
    param([string[]]$Issues)
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) {
        return @{ ok = $false; reason = 'gh_missing'; open = @($Issues); closed = @() }
    }
    $open = New-Object System.Collections.Generic.List[string]
    $closed = New-Object System.Collections.Generic.List[string]
    foreach ($ref in @($Issues)) {
        if (-not $ref -or -not $ref.Trim()) { continue }
        $p = Parse-JeevesWalrusGateRef -Ref $ref
        $json = & gh issue view $p.Number -R $p.Repo --json state,title 2>$null
        if (-not $json) {
            $open.Add("$ref (gh_view_failed)")
            continue
        }
        $doc = $json | ConvertFrom-Json
        $st = [string]$doc.state
        if ($st -eq 'CLOSED') { $closed.Add($ref) }
        else { $open.Add($ref) }
    }
    return @{
        ok     = ($open.Count -eq 0)
        reason = $(if ($open.Count -eq 0) { 'all_closed' } else { 'gate_open' })
        open   = @($open)
        closed = @($closed)
    }
}

function Resolve-JeevesWalrusArtifactDir {
    param([string]$Requested, [string]$RunId, [string]$RepoName, [string]$WorkflowName, [string]$ArtName)
    if ($Requested -and $Requested.Trim()) {
        $p = [IO.Path]::GetFullPath($Requested.Trim())
        if (-not (Test-Path -LiteralPath (Join-Path $p 'jeeves.exe'))) {
            throw "ArtifactDir missing jeeves.exe: $p"
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
            throw "no successful $WorkflowName run on main"
        }
        $rid = [string]$runs[0].databaseId
    }
    $tmp = Join-Path $env:TEMP ('jeeves-walrus-' + [guid]::NewGuid().ToString('n').Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    & gh run download $rid -R $RepoName -n $ArtName -D $tmp 2>$null | Out-Null
    $exe = Get-ChildItem -LiteralPath $tmp -Recurse -Filter 'jeeves.exe' -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $exe) { throw "gh run download $rid missing jeeves.exe under $tmp" }
    return @{ path = $exe.Directory.FullName; run_id = $rid; source = 'gh_run_download' }
}

function Assert-JeevesWalrusArtifact {
    param([string]$Dir)
    $exe = Join-Path $Dir 'jeeves.exe'
    $shaFile = Join-Path $Dir 'jeeves.exe.sha256'
    $man = Join-Path $Dir 'MANIFEST.json'
    if (-not (Test-Path -LiteralPath $exe)) { throw "missing $exe" }
    $got = Get-JeevesWalrusSha256File -Path $exe
    $expect = $null
    if (Test-Path -LiteralPath $man) {
        $m = Get-Content -LiteralPath $man -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($m.exe_sha256) { $expect = ([string]$m.exe_sha256).ToLowerInvariant() }
        if ($m.source_commit -and [string]$m.source_commit -match '(?i)red') {
            # soft note only; red-main refusal uses workflow conclusion + branch
        }
        $script:JeevesWalrusManifest = $m
    }
    if (-not $expect -and (Test-Path -LiteralPath $shaFile)) {
        $line = (Get-Content -LiteralPath $shaFile -TotalCount 1).Trim()
        if ($line -match '([a-fA-F0-9]{64})') { $expect = $Matches[1].ToLowerInvariant() }
    }
    if (-not $expect) { throw 'artifact missing MANIFEST.exe_sha256 and jeeves.exe.sha256' }
    if ($got -ne $expect) { throw "hash mismatch got=$got expect=$expect" }
    return @{
        exe_sha256    = $got
        source_commit = $(if ($script:JeevesWalrusManifest) { [string]$script:JeevesWalrusManifest.source_commit } else { '' })
        workflow_run_id = $(if ($script:JeevesWalrusManifest -and $script:JeevesWalrusManifest.workflow_run_id) { [string]$script:JeevesWalrusManifest.workflow_run_id } else { '' })
        size_bytes    = (Get-Item -LiteralPath $exe).Length
    }
}

function New-JeevesWalrusRollbackScript {
    param(
        [string]$WriteDir,
        [string]$BackupDir,
        [string]$InstallExeDir,
        [string]$PrevHash
    )
    # WriteDir = local staging; BackupDir = remote bak path embedded for walrus ROLLBACK.
    $bakEsc = $BackupDir.Replace("'", "''")
    $dirEsc = $InstallExeDir.Replace("'", "''")
    $hashEsc = $PrevHash.Replace("'", "''")
    $body = @"
# ROLLBACK.ps1 - generated by Install-JeevesWalrusWinRm.ps1 (FR #9376). Exe-only; never touches Ergo.
`$ErrorActionPreference = 'Stop'
`$bak = '$bakEsc'
`$dest = '$dirEsc'
sc.exe stop ircJeeves | Out-Null
for (`$i = 0; `$i -lt 60; `$i++) {
  if ((Get-Service ircJeeves).Status -eq 'Stopped' -and -not (Get-Process jeeves -ErrorAction SilentlyContinue)) { break }
  Start-Sleep 1
}
Copy-Item (Join-Path `$bak 'jeeves.exe') (Join-Path `$dest 'jeeves.exe') -Force
foreach (`$f in 'jeeves.exe.sha256','MANIFEST.json','provenance.txt') {
  `$src = Join-Path `$bak `$f
  if (Test-Path -LiteralPath `$src) { Copy-Item `$src (Join-Path `$dest `$f) -Force }
}
`$h = (Get-FileHash (Join-Path `$dest 'jeeves.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
if (`$h -ne '$hashEsc') { throw "rollback exe hash mismatch got=`$h expect=$hashEsc" }
sc.exe start ircJeeves | Out-Null
Start-Sleep 15
(Invoke-WebRequest http://127.0.0.1:7700/health -UseBasicParsing).Content
"@
    if (-not (Test-Path -LiteralPath $WriteDir)) {
        New-Item -ItemType Directory -Force -Path $WriteDir | Out-Null
    }
    $path = Join-Path $WriteDir 'ROLLBACK.ps1'
    [IO.File]::WriteAllText($path, $body, (New-Object System.Text.UTF8Encoding $false))
    $null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$null)
    return $path
}

# --- main ---
if ($StoreCredential) {
    Set-JeevesWalrusCredential -Target $CredTarget -UserName $User
    Write-JeevesWalrusJson @{ ok = $true; action = 'store_credential'; cred_target = $CredTarget; user = $User }
    exit 0
}

$live = [bool]$SiYes
if (-not $live) { $DryRun = $true }
if ($live -and $DryRun) {
    Write-JeevesWalrusJson @{ ok = $false; error = 'refuse_both_SiYes_and_DryRun' }
    exit 2
}

$gate = $null
if (-not $SkipGateCheck) {
    $gate = Test-JeevesWalrusGateIssuesClosed -Issues $GateIssues
    # Live mutate refuses open gates. DryRun still plans and reports gate status.
    if (-not $gate.ok -and $live) {
        Write-JeevesWalrusJson @{
            ok            = $false
            error         = 'gate_open'
            fr            = 9376
            gate          = $gate
            hint          = 'Close GateIssues (or -SkipGateCheck with Si override); live still needs -SiYes'
            dry_run       = $false
            si_yes        = [bool]$SiYes
        }
        exit 1
    }
}
else {
    $gate = @{ ok = $true; reason = 'skip_gate_check'; open = @(); closed = @() }
}

$resolved = Resolve-JeevesWalrusArtifactDir -Requested $ArtifactDir -RunId $WorkflowRunId -RepoName $Repo -WorkflowName $Workflow -ArtName $ArtifactName
$meta = Assert-JeevesWalrusArtifact -Dir $resolved.path
$installRoot = Join-Path $AiRoot 'jeeves'
$exeDir = Join-Path $installRoot 'jeeves'
$sha8 = $meta.exe_sha256.Substring(0, 8)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupName = "_hotpatch_${stamp}-jeeves-$sha8"
$backupRemote = Join-Path $installRoot $backupName

$plan = [ordered]@{
    ok              = $true
    fr              = 9376
    action          = $(if ($live) { 'live_winrm_hotpatch' } else { 'dry_run' })
    computer_name   = $ComputerName
    ai_root         = $AiRoot
    exe_dir         = $exeDir
    backup_dir      = $backupRemote
    artifact_dir    = $resolved.path
    artifact_source = $resolved.source
    run_id          = $(if ($resolved.run_id) { $resolved.run_id } else { $meta.workflow_run_id })
    exe_sha256      = $meta.exe_sha256
    source_commit   = $meta.source_commit
    gate            = $gate
    si_yes          = [bool]$SiYes
    dry_run         = [bool]$DryRun
    never           = @('ErgoWalrus', 'BobIrcd', 'ircd.yaml', 'NSSM env', 'identity.json', 'queue.json', 'IIS')
    services        = @('ircJeeves')
}

if (-not $live) {
    Write-JeevesWalrusJson $plan
    exit 0
}

# Live path
$cred = Get-JeevesWalrusPSCredential -Target $CredTarget -DefaultUser $User
$sessOpt = New-PSSessionOption -OpenTimeout ($WinRmTimeoutSec * 1000) -OperationTimeout ($WinRmTimeoutSec * 1000)
$session = $null
try {
    $session = New-PSSession -ComputerName $ComputerName -Credential $cred -SessionOption $sessOpt -ErrorAction Stop

    # Build locks / busy soft-check on remote chair home (best-effort)
    $pre = Invoke-Command -Session $session -ScriptBlock {
        param($ExeDir, $InstallRoot, $BackupRemote, $HealthWaitSec)
        $ErrorActionPreference = 'Stop'
        $result = [ordered]@{
            service_before = [string](Get-Service ircJeeves -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Status)
            prev_hash      = $null
            build_locks_empty = $null
        }
        $exe = Join-Path $ExeDir 'jeeves.exe'
        if (Test-Path -LiteralPath $exe) {
            $result.prev_hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        $locks = Join-Path $env:USERPROFILE '.jeeves\build-locks.json'
        if (Test-Path -LiteralPath $locks) {
            try {
                $doc = Get-Content -LiteralPath $locks -Raw -Encoding UTF8 | ConvertFrom-Json
                $builds = $doc.builds
                $result.build_locks_empty = (-not $builds -or (@($builds.PSObject.Properties).Count -eq 0))
            }
            catch { $result.build_locks_empty = $false }
        }
        else {
            $result.build_locks_empty = $true
        }
        if ($result.build_locks_empty -eq $false) {
            throw 'build-locks.json shows active builds; refuse restart'
        }
        New-Item -ItemType Directory -Force -Path $BackupRemote | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $BackupRemote 'new') | Out-Null
        foreach ($f in @('jeeves.exe', 'jeeves.exe.sha256', 'MANIFEST.json', 'provenance.txt')) {
            $src = Join-Path $ExeDir $f
            if (Test-Path -LiteralPath $src) {
                Copy-Item -LiteralPath $src -Destination (Join-Path $BackupRemote $f) -Force
            }
        }
        return $result
    } -ArgumentList $exeDir, $installRoot, $backupRemote, $HealthWaitSec

    if (-not $pre.prev_hash) { throw 'remote missing previous jeeves.exe; refuse blind install' }

    # ROLLBACK.ps1 is generated locally (embedded paths point at walrus) then copied into the remote backup dir.
    $stageRbDir = Join-Path $env:TEMP ('jeeves-rb-' + $sha8)
    New-Item -ItemType Directory -Force -Path $stageRbDir | Out-Null
    $rbLocal = New-JeevesWalrusRollbackScript -WriteDir $stageRbDir -BackupDir $backupRemote -InstallExeDir $exeDir -PrevHash $pre.prev_hash

    $remoteNew = Join-Path $backupRemote 'new'
    foreach ($f in @('jeeves.exe', 'jeeves.exe.sha256', 'MANIFEST.json', 'provenance.txt')) {
        $src = Join-Path $resolved.path $f
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $remoteNew $f) -ToSession $session -Force
        }
    }
    Copy-Item -LiteralPath $rbLocal -Destination (Join-Path $backupRemote 'ROLLBACK.ps1') -ToSession $session -Force

    $swap = Invoke-Command -Session $session -ScriptBlock {
        param($ExeDir, $BackupRemote, $ExpectHash, $HealthWaitSec)
        $ErrorActionPreference = 'Stop'
        $newDir = Join-Path $BackupRemote 'new'
        $newExe = Join-Path $newDir 'jeeves.exe'
        $got = (Get-FileHash -LiteralPath $newExe -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($got -ne $ExpectHash) { throw "staged hash mismatch got=$got expect=$ExpectHash" }

        sc.exe stop ircJeeves | Out-Null
        for ($i = 0; $i -lt 90; $i++) {
            if ((Get-Service ircJeeves).Status -eq 'Stopped' -and -not (Get-Process jeeves -ErrorAction SilentlyContinue)) { break }
            Start-Sleep 1
        }
        if ((Get-Service ircJeeves).Status -ne 'Stopped') { throw 'ircJeeves did not stop' }

        Copy-Item -LiteralPath $newExe -Destination (Join-Path $ExeDir 'jeeves.exe') -Force
        foreach ($f in @('jeeves.exe.sha256', 'MANIFEST.json', 'provenance.txt')) {
            $src = Join-Path $newDir $f
            if (Test-Path -LiteralPath $src) {
                Copy-Item -LiteralPath $src -Destination (Join-Path $ExeDir $f) -Force
            }
        }
        $after = (Get-FileHash -LiteralPath (Join-Path $ExeDir 'jeeves.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($after -ne $ExpectHash) { throw "post-copy hash mismatch got=$after expect=$ExpectHash" }

        sc.exe start ircJeeves | Out-Null
        $health = $null
        $deadline = (Get-Date).AddSeconds([Math]::Max(15, $HealthWaitSec))
        while ((Get-Date) -lt $deadline) {
            try {
                $health = (Invoke-WebRequest -Uri 'http://127.0.0.1:7700/health' -UseBasicParsing -TimeoutSec 5).Content
                if ($health -match '"ok"\s*:\s*true' -or $health -match '"ok":true') { break }
            }
            catch { }
            Start-Sleep 2
        }
        return [ordered]@{
            service_after = [string](Get-Service ircJeeves).Status
            installed_hash = $after
            health        = $health
            backup_dir    = $BackupRemote
        }
    } -ArgumentList $exeDir, $backupRemote, $meta.exe_sha256, $HealthWaitSec

    $plan.action = 'live_winrm_hotpatch_done'
    $plan.pre = $pre
    $plan.swap = $swap
    $plan.ok = ($swap.installed_hash -eq $meta.exe_sha256 -and $swap.service_after -eq 'Running')
    Write-JeevesWalrusJson $plan
    if (-not $plan.ok) { exit 1 }
    exit 0
}
catch {
    Write-JeevesWalrusJson @{
        ok      = $false
        fr      = 9376
        error   = 'live_failed'
        message = [string]$_.Exception.Message
        dry_run = $false
        si_yes  = $true
    }
    exit 2
}
finally {
    if ($session) { Remove-PSSession -Session $session -ErrorAction SilentlyContinue }
}
