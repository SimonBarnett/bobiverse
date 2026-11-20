#Requires -Version 5.1
<#
.SYNOPSIS
  updatefleet: deploy bob-worker.exe to every IRC digest machine (FR #8420 / #8532).

.DESCRIPTION
  Machine list comes from GET /bob/v1/report machines keys (same set the systray
  paints: flamingo, marchhare, redqueen, ...). Credentials are wonderland\administrator
  from Windows CredMan target Bobiverse/UpdateFleet (store once with -StoreCredential).
  Per machine: WinRM copy artifact into <ai>\bob\worker, verify sha256, queue
  recycleseat/startworker for the interactive tray. Local machine uses filesystem
  copy. Digest online does not imply WinRM (FR #8429 / #8532): when CredMan+WinRM
  from this host is closed (timeout / cannot complete), the row is method=winrm-closed
  with fallback=tray-local (run Update-BobFleet locally on that shop, or airc/tray
  seat start after a local install) — never assume flamingo can reach every shop.
  One JSON object on stdout. Never prints secrets.

.PARAMETER StoreCredential
  Prompt for password (SecureString) and write CredMan Bobiverse/UpdateFleet.

.PARAMETER User
  CredMan username (default wonderland\administrator).

.PARAMETER ArtifactDir
  Folder with bob-worker.exe + bob-worker.exe.sha256 (+ optional scripts\, provenance.txt).
  When omitted: download latest successful build-bob-worker.yml artifact via gh, else
  use the local <AiRoot>\bob\worker install.

.PARAMETER DigestUrl
  Digest report URL (default https://bob.ntsa.uk/bob/v1/report).

.PARAMETER AiRoot
  Fleet ai root (default from Get-BobiverseAiRoot or C:\ai).

.PARAMETER Machine
  Limit to these machine ids (default: all digest machines).

.PARAMETER SkipMachine
  Skip these machine ids.

.PARAMETER DryRun
  List targets and plan only; no copy, no WinRM mutate, no recycle queue.

.PARAMETER NoRecycle
  Install only; do not queue recycleseat/startworker.

.PARAMETER CredTarget
  CredMan generic target name (default Bobiverse/UpdateFleet).
#>
[CmdletBinding()]
param(
    [switch]$StoreCredential,
    [string]$User = 'wonderland\administrator',
    [string]$ArtifactDir = '',
    [string]$DigestUrl = 'https://bob.ntsa.uk/bob/v1/report',
    [string]$AiRoot = '',
    [string[]]$Machine = @(),
    [string[]]$SkipMachine = @(),
    [switch]$DryRun,
    [switch]$NoRecycle,
    [string]$CredTarget = 'Bobiverse/UpdateFleet',
    [int]$WinRmTimeoutSec = 120,
    [int]$RecycleTtlSec = 300
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-UpdateFleetJson {
    param([hashtable]$Obj)
    $json = $Obj | ConvertTo-Json -Compress -Depth 8
    Write-Output $json
}

function Get-UpdateFleetAiRoot {
    param([string]$Override)
    if ($Override -and $Override.Trim()) { return [IO.Path]::GetFullPath($Override.Trim()) }
    if ($env:BOB_AI_ROOT -and $env:BOB_AI_ROOT.Trim()) { return [IO.Path]::GetFullPath($env:BOB_AI_ROOT.Trim()) }
    $common = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
    if (Test-Path -LiteralPath $common) {
        . $common
        if (Get-Command Get-BobiverseAiRoot -ErrorAction SilentlyContinue) {
            try { return [string](Get-BobiverseAiRoot) } catch { }
        }
    }
    return 'C:\ai'
}

function Get-UpdateFleetMachineId {
    $envId = [string]$env:BOB_MACHINE_ID
    if ($envId -and $envId.Trim()) { return $envId.Trim().ToLowerInvariant() }
    $hn = [string]$env:COMPUTERNAME
    if (-not $hn) { return '' }
    return ($hn.ToLowerInvariant() -replace '[^a-z0-9-]', '')
}

# --- CredMan (generic credential; never log blob) ---
$script:CredManTypeReady = $false
function Ensure-UpdateFleetCredManType {
    if ($script:CredManTypeReady) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class BobUpdateFleetCredMan {
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

function Save-UpdateFleetCredential {
    param([string]$Target, [string]$UserName, [System.Security.SecureString]$Password)
    Ensure-UpdateFleetCredManType
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        $bytes = [Text.Encoding]::Unicode.GetBytes($plain)
        $cred = New-Object BobUpdateFleetCredMan+CREDENTIAL
        $cred.Type = [BobUpdateFleetCredMan]::CRED_TYPE_GENERIC
        $cred.TargetName = $Target
        $cred.UserName = $UserName
        $cred.CredentialBlobSize = [uint32]$bytes.Length
        $cred.CredentialBlob = [Runtime.InteropServices.Marshal]::AllocHGlobal($bytes.Length)
        $cred.Persist = [BobUpdateFleetCredMan]::CRED_PERSIST_LOCAL_MACHINE
        try {
            [Runtime.InteropServices.Marshal]::Copy($bytes, 0, $cred.CredentialBlob, $bytes.Length)
            $ok = [BobUpdateFleetCredMan]::CredWrite([ref]$cred, 0)
            if (-not $ok) { throw "CredWrite failed winerror=$([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }
        }
        finally {
            if ($cred.CredentialBlob -ne [IntPtr]::Zero) {
                [Runtime.InteropServices.Marshal]::FreeHGlobal($cred.CredentialBlob)
            }
        }
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
}

function Get-UpdateFleetPSCredential {
    param([string]$Target, [string]$DefaultUser)
    Ensure-UpdateFleetCredManType
    $ptr = [IntPtr]::Zero
    $ok = [BobUpdateFleetCredMan]::CredRead($Target, [BobUpdateFleetCredMan]::CRED_TYPE_GENERIC, 0, [ref]$ptr)
    if (-not $ok -or $ptr -eq [IntPtr]::Zero) {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "CredMan missing target=$Target winerror=$err; run Update-BobFleet.ps1 -StoreCredential"
    }
    try {
        $cred = [Runtime.InteropServices.Marshal]::PtrToStructure($ptr, [type][BobUpdateFleetCredMan+CREDENTIAL])
        $user = [string]$cred.UserName
        if (-not $user) { $user = $DefaultUser }
        $size = [int]$cred.CredentialBlobSize
        if ($size -le 0 -or $cred.CredentialBlob -eq [IntPtr]::Zero) {
            throw "CredMan empty blob target=$Target"
        }
        $even = $size - ($size % 2)
        $bytes = New-Object byte[] $even
        [Runtime.InteropServices.Marshal]::Copy($cred.CredentialBlob, $bytes, 0, $even)
        $plain = [Text.Encoding]::Unicode.GetString($bytes)
        $sec = ConvertTo-SecureString $plain -AsPlainText -Force
        return New-Object System.Management.Automation.PSCredential ($user, $sec)
    }
    finally {
        [void][BobUpdateFleetCredMan]::CredFree($ptr)
    }
}

function Test-UpdateFleetWinRmClosed {
    <#
    FR #8532: true when the remote path is unreachable / timed out (not a CredMan
    Access Denied). Digest online != WinRM; classify so callers can fall back.
    #>
    param([string]$Message)
    if (-not $Message) { return $false }
    $m = [string]$Message
    if ($m -match '(?i)access\s+is\s+denied|AccessDenied|0x80070005') { return $false }
    return [bool]($m -match '(?i)WinRM.*cannot complete|cannot complete the operation|operation timed out|timed out|Connecting to remote server|The client cannot connect|WPSremotingTransportException|WinRM.*firewall|Error code:\s*215085\d+')
}

function Get-UpdateFleetWinRmClosedFallback {
    <#
    FR #8532: structured fallback when WinRM from the operator host is closed.
    Prefer tray-local Update-BobFleet on the shop (or airc after local install).
    #>
    param([Parameter(Mandatory)][string]$MachineId)
    $mid = ([string]$MachineId).Trim().ToLowerInvariant()
    return [ordered]@{
        method   = 'winrm-closed'
        fallback = 'tray-local'
        hint     = ("WinRM closed to {0} from this host. Run Update-BobFleet.ps1 -Machine {0} on {0} (tray-local), or install via airc then tray/!startworker. Digest online does not imply WinRM (FR #8532)." -f $mid)
    }
}

function Get-UpdateFleetDigestMachines {
    param([string]$Url)
    $headers = @{ 'User-Agent' = 'Bobiverse-bobreport' }
    $doc = Invoke-RestMethod -Uri $Url -Headers $headers -TimeoutSec 30
    if (-not $doc -or -not $doc.machines) {
        throw "digest has no machines: $Url"
    }
    $ids = @()
    $props = @($doc.machines.PSObject.Properties)
    foreach ($p in $props) {
        $id = [string]$p.Name
        if ($id -and $id.Trim()) { $ids += $id.Trim().ToLowerInvariant() }
    }
    return @($ids | Select-Object -Unique | Sort-Object)
}

function Resolve-UpdateFleetArtifactDir {
    param([string]$Requested, [string]$BobRoot)
    if ($Requested -and $Requested.Trim()) {
        $p = [IO.Path]::GetFullPath($Requested.Trim())
        if (-not (Test-Path -LiteralPath (Join-Path $p 'bob-worker.exe'))) {
            throw "ArtifactDir missing bob-worker.exe: $p"
        }
        return $p
    }
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if ($gh) {
        $tmp = Join-Path $env:TEMP ('bob-worker-updatefleet-' + [guid]::NewGuid().ToString('n').Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        try {
            $runJson = & gh run list -R SimonBarnett/bobiverse --workflow build-bob-worker.yml --branch main --status success --limit 1 --json databaseId 2>$null
            $runs = @($runJson | ConvertFrom-Json)
            if ($runs.Count -gt 0 -and $runs[0].databaseId) {
                $rid = [string]$runs[0].databaseId
                & gh run download $rid -R SimonBarnett/bobiverse -n bob-worker -D $tmp 2>$null | Out-Null
                $exe = Get-ChildItem -LiteralPath $tmp -Recurse -Filter 'bob-worker.exe' -File -ErrorAction SilentlyContinue |
                    Select-Object -First 1
                if ($exe) { return [string]$exe.Directory.FullName }
            }
        }
        catch {
            # fall through to local install
        }
    }
    $local = Join-Path $BobRoot 'worker'
    if (Test-Path -LiteralPath (Join-Path $local 'bob-worker.exe')) {
        return [IO.Path]::GetFullPath($local)
    }
    throw 'No ArtifactDir, gh download failed, and local worker\bob-worker.exe missing'
}

function Get-UpdateFleetExpectedSha {
    param([string]$Dir)
    $shaFile = Join-Path $Dir 'bob-worker.exe.sha256'
    if (Test-Path -LiteralPath $shaFile) {
        $raw = (Get-Content -LiteralPath $shaFile -Raw).Trim()
        if ($raw -match '([A-Fa-f0-9]{64})') { return $Matches[1].ToLowerInvariant() }
    }
    return (Get-FileHash -LiteralPath (Join-Path $Dir 'bob-worker.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Install-UpdateFleetWorkerLocal {
    param(
        [string]$ArtifactDir,
        [string]$InstallWorker,
        [string]$ExpectedSha,
        [switch]$DryRun
    )
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = Join-Path (Split-Path $InstallWorker -Parent) ('_hotpatch_{0}-worker-updatefleet' -f $stamp)
    $result = [ordered]@{
        method     = 'local'
        install    = $InstallWorker
        backup     = $backup
        expected   = $ExpectedSha
        installed  = $null
        ok         = $false
        error      = $null
    }
    if ($DryRun) {
        $result.ok = $true
        $result.installed = 'dry-run'
        return [pscustomobject]$result
    }
    try {
        if (-not (Test-Path -LiteralPath $InstallWorker)) {
            New-Item -ItemType Directory -Force -Path $InstallWorker | Out-Null
        }
        if (Test-Path -LiteralPath (Join-Path $InstallWorker 'bob-worker.exe')) {
            New-Item -ItemType Directory -Force -Path $backup | Out-Null
            Copy-Item -LiteralPath (Join-Path $InstallWorker 'bob-worker.exe') -Destination (Join-Path $backup 'bob-worker.exe') -Force
            $shaSrc = Join-Path $InstallWorker 'bob-worker.exe.sha256'
            if (Test-Path -LiteralPath $shaSrc) {
                Copy-Item -LiteralPath $shaSrc -Destination (Join-Path $backup 'bob-worker.exe.sha256') -Force
            }
        }
        Copy-Item -LiteralPath (Join-Path $ArtifactDir 'bob-worker.exe') -Destination (Join-Path $InstallWorker 'bob-worker.exe') -Force
        $artSha = Join-Path $ArtifactDir 'bob-worker.exe.sha256'
        if (Test-Path -LiteralPath $artSha) {
            Copy-Item -LiteralPath $artSha -Destination (Join-Path $InstallWorker 'bob-worker.exe.sha256') -Force
        }
        else {
            Set-Content -LiteralPath (Join-Path $InstallWorker 'bob-worker.exe.sha256') -Value "$ExpectedSha  bob-worker.exe" -Encoding ascii
        }
        $artScripts = Join-Path $ArtifactDir 'scripts'
        if (Test-Path -LiteralPath $artScripts) {
            $destScripts = Join-Path $InstallWorker 'scripts'
            New-Item -ItemType Directory -Force -Path $destScripts | Out-Null
            Copy-Item -Path (Join-Path $artScripts '*') -Destination $destScripts -Recurse -Force
        }
        foreach ($extra in @('provenance.txt', 'provenance-8400.txt')) {
            $ep = Join-Path $ArtifactDir $extra
            if (Test-Path -LiteralPath $ep) {
                Copy-Item -LiteralPath $ep -Destination (Join-Path $InstallWorker $extra) -Force
            }
        }
        $got = (Get-FileHash -LiteralPath (Join-Path $InstallWorker 'bob-worker.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
        $result.installed = $got
        if ($got -ne $ExpectedSha) { throw "sha256 mismatch got=$got expected=$ExpectedSha" }
        $result.ok = $true
    }
    catch {
        $result.error = [string]$_.Exception.Message
        $result.ok = $false
    }
    return [pscustomobject]$result
}

function Install-UpdateFleetWorkerRemote {
    param(
        [string]$ComputerName,
        [System.Management.Automation.PSCredential]$Credential,
        [string]$ArtifactDir,
        [string]$InstallWorker,
        [string]$ExpectedSha,
        [int]$TimeoutSec,
        [switch]$DryRun
    )
    $result = [ordered]@{
        method     = 'winrm'
        host       = $ComputerName
        install    = $InstallWorker
        expected   = $ExpectedSha
        installed  = $null
        backup     = $null
        ok         = $false
        error      = $null
        fallback   = $null
        hint       = $null
    }
    if ($DryRun) {
        $result.ok = $true
        $result.installed = 'dry-run'
        return [pscustomobject]$result
    }
    $session = $null
    try {
        # FR #8532: honour -WinRmTimeoutSec (was unused); fail closed into winrm-closed.
        $timeoutMs = [Math]::Max(1000, [int]$TimeoutSec * 1000)
        $sessOpt = New-PSSessionOption -OpenTimeout $timeoutMs -OperationTimeout $timeoutMs
        $session = New-PSSession -ComputerName $ComputerName -Credential $Credential -SessionOption $sessOpt -ErrorAction Stop
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backup = Invoke-Command -Session $session -ScriptBlock {
            param($InstallWorker, $Stamp)
            $backup = Join-Path (Split-Path $InstallWorker -Parent) ('_hotpatch_{0}-worker-updatefleet' -f $Stamp)
            if (-not (Test-Path -LiteralPath $InstallWorker)) {
                New-Item -ItemType Directory -Force -Path $InstallWorker | Out-Null
            }
            if (Test-Path -LiteralPath (Join-Path $InstallWorker 'bob-worker.exe')) {
                New-Item -ItemType Directory -Force -Path $backup | Out-Null
                Copy-Item -LiteralPath (Join-Path $InstallWorker 'bob-worker.exe') -Destination (Join-Path $backup 'bob-worker.exe') -Force
                $shaSrc = Join-Path $InstallWorker 'bob-worker.exe.sha256'
                if (Test-Path -LiteralPath $shaSrc) {
                    Copy-Item -LiteralPath $shaSrc -Destination (Join-Path $backup 'bob-worker.exe.sha256') -Force
                }
            }
            return $backup
        } -ArgumentList $InstallWorker, $stamp
        $result.backup = [string]$backup

        $remoteExe = Join-Path $InstallWorker 'bob-worker.exe'
        $remoteSha = Join-Path $InstallWorker 'bob-worker.exe.sha256'
        Copy-Item -LiteralPath (Join-Path $ArtifactDir 'bob-worker.exe') -Destination $remoteExe -ToSession $session -Force
        $artSha = Join-Path $ArtifactDir 'bob-worker.exe.sha256'
        if (Test-Path -LiteralPath $artSha) {
            Copy-Item -LiteralPath $artSha -Destination $remoteSha -ToSession $session -Force
        }

        $artScripts = Join-Path $ArtifactDir 'scripts'
        if (Test-Path -LiteralPath $artScripts) {
            $remoteScripts = Join-Path $InstallWorker 'scripts'
            Invoke-Command -Session $session -ScriptBlock {
                param($p)
                New-Item -ItemType Directory -Force -Path $p | Out-Null
            } -ArgumentList $remoteScripts
            Copy-Item -Path (Join-Path $artScripts '*') -Destination $remoteScripts -ToSession $session -Recurse -Force
        }

        $got = Invoke-Command -Session $session -ScriptBlock {
            param($ExePath, $ShaPath, $Expected)
            if (-not (Test-Path -LiteralPath $ShaPath)) {
                Set-Content -LiteralPath $ShaPath -Value "$Expected  bob-worker.exe" -Encoding ascii
            }
            return (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLowerInvariant()
        } -ArgumentList $remoteExe, $remoteSha, $ExpectedSha
        $result.installed = [string]$got
        if ([string]$got -ne $ExpectedSha) { throw "sha256 mismatch got=$got expected=$ExpectedSha" }
        $result.ok = $true
    }
    catch {
        $msg = [string]$_.Exception.Message
        $result.error = $msg
        $result.ok = $false
        if (Test-UpdateFleetWinRmClosed -Message $msg) {
            $fb = Get-UpdateFleetWinRmClosedFallback -MachineId $ComputerName
            $result.method = [string]$fb.method
            $result.fallback = [string]$fb.fallback
            $result.hint = [string]$fb.hint
        }
    }
    finally {
        if ($session) { Remove-PSSession $session -ErrorAction SilentlyContinue }
    }
    return [pscustomobject]$result
}

function Invoke-UpdateFleetRecycle {
    param(
        [string]$ComputerName,
        [System.Management.Automation.PSCredential]$Credential,
        [string]$BobRoot,
        [string]$MachineId,
        [switch]$IsLocal,
        [int]$TtlSec,
        [switch]$DryRun
    )
    $out = [ordered]@{
        ok            = $false
        method        = $(if ($IsLocal) { 'local' } else { 'winrm' })
        seats_found   = @()
        queued        = @()
        describe_kill = 0
        disabled      = $false
        error         = $null
    }
    $scriptBlock = {
        param($BobRoot, $MachineId, $TtlSec, $DryRun)
        $ErrorActionPreference = 'Stop'
        $result = [ordered]@{
            seats_found   = @()
            queued        = @()
            describe_kill = 0
            disabled      = $false
            startworker   = @()
            error         = $null
        }
        try {
            $disable = Join-Path $BobRoot 'home\recycleseat.disabled'
            if (Test-Path -LiteralPath $disable) {
                $result.disabled = $true
            }
            # Kill hung --describe-launch (blocks tray startworker timer)
            $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                    $_.Name -match '^bob-worker' -and $_.CommandLine -match '--describe-launch'
                })
            foreach ($p in $procs) {
                if (-not $DryRun) {
                    try { Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue } catch { }
                }
                $result.describe_kill++
            }
            # Live seat nicks
            $seatDir = Join-Path $env:LOCALAPPDATA 'Bobiverse\worker\run\seats'
            $nicks = @()
            if (Test-Path -LiteralPath $seatDir) {
                Get-ChildItem -LiteralPath $seatDir -Filter ($MachineId + '-*.irc.json') -File -ErrorAction SilentlyContinue | ForEach-Object {
                    # File is <nick>.irc.json; BaseName is <nick>.irc -- strip trailing .irc
                    $base = [string]$_.BaseName
                    if ($base -match '^(.*)\.irc$') { $nicks += $Matches[1] }
                    else { $nicks += $base }
                }
            }
            if ($nicks.Count -eq 0) {
                # Fallback: running agent bob-worker command lines with --nick
                Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                    $_.Name -match '^bob-worker' -and $_.CommandLine -notmatch '--mode\s+plan' -and $_.CommandLine -notmatch '--describe-launch'
                } | ForEach-Object {
                    if ($_.CommandLine -match '--nick\s+(\S+)') { $nicks += $Matches[1] }
                    elseif ($_.CommandLine -match '\s([a-z0-9]+-\d+)\s') { }
                }
            }
            $nicks = @($nicks | Select-Object -Unique)
            $result.seats_found = $nicks

            if ($result.disabled) {
                return [pscustomobject]$result
            }

            $qdir = Join-Path $BobRoot 'run\recycleseat'
            if (-not (Test-Path -LiteralPath $qdir)) {
                New-Item -ItemType Directory -Force -Path $qdir | Out-Null
            }
            $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            foreach ($nick in $nicks) {
                $rid = ([guid]::NewGuid().ToString('n').Substring(0, 12))
                $body = @{
                    id      = $rid
                    nick    = $nick
                    by      = 'updatefleet'
                    kind    = 'agent'
                    ts      = [double]$now
                    expires = [int]($now + [Math]::Max(60, $TtlSec))
                }
                if (-not $DryRun) {
                    $tmp = Join-Path $qdir ('.req-{0}.tmp' -f $rid)
                    $dst = Join-Path $qdir ('req-{0}.json' -f $rid)
                    $utf8 = New-Object System.Text.UTF8Encoding $false
                    [IO.File]::WriteAllText($tmp, ($body | ConvertTo-Json -Compress), $utf8)
                    [IO.File]::Move($tmp, $dst)
                }
                $result.queued += $nick
            }
            if ($nicks.Count -eq 0) {
                # No live seats: queue startworker up to hard cap 2
                $swDir = Join-Path $BobRoot 'run\startworker'
                if (-not (Test-Path -LiteralPath $swDir)) {
                    New-Item -ItemType Directory -Force -Path $swDir | Out-Null
                }
                for ($i = 0; $i -lt 2; $i++) {
                    $rid = ([guid]::NewGuid().ToString('n').Substring(0, 12))
                    $body = @{
                        id      = $rid
                        mode    = 'agent'
                        by      = 'updatefleet'
                        kind    = 'opencode'
                        ts      = [double]$now
                        expires = [int]($now + [Math]::Max(60, $TtlSec))
                    }
                    if (-not $DryRun) {
                        $tmp = Join-Path $swDir ('.req-{0}.tmp' -f $rid)
                        $dst = Join-Path $swDir ('req-{0}.json' -f $rid)
                        $utf8 = New-Object System.Text.UTF8Encoding $false
                        [IO.File]::WriteAllText($tmp, ($body | ConvertTo-Json -Compress), $utf8)
                        [IO.File]::Move($tmp, $dst)
                    }
                    $result.startworker += $rid
                }
            }
        }
        catch {
            $result.error = [string]$_.Exception.Message
        }
        return [pscustomobject]$result
    }

    try {
        if ($DryRun -and -not $IsLocal) {
            # Do not open WinRM just to plan recycle.
            $out.ok = $true
            $out.seats_found = @()
            $out.queued = @('dry-run')
            return [pscustomobject]$out
        }
        if ($IsLocal) {
            $r = & $scriptBlock $BobRoot $MachineId $TtlSec $DryRun
        }
        else {
            $r = Invoke-Command -ComputerName $ComputerName -Credential $Credential -ScriptBlock $scriptBlock -ArgumentList $BobRoot, $MachineId, $TtlSec, $DryRun
        }
        $out.seats_found = @($r.seats_found)
        $out.queued = @($r.queued)
        $out.describe_kill = [int]$r.describe_kill
        $out.disabled = [bool]$r.disabled
        if ($r.error) { $out.error = [string]$r.error; $out.ok = $false }
        else { $out.ok = $true }
        if ($r.startworker) { $out.startworker = @($r.startworker) }
    }
    catch {
        $out.error = [string]$_.Exception.Message
        $out.ok = $false
    }
    return [pscustomobject]$out
}

# --- main ---
if ($StoreCredential) {
    $sec = Read-Host -AsSecureString -Prompt ("Password for {0} (CredMan {1})" -f $User, $CredTarget)
    Save-UpdateFleetCredential -Target $CredTarget -UserName $User -Password $sec
    Write-UpdateFleetJson @{
        ok          = $true
        action      = 'store-credential'
        cred_target = $CredTarget
        user        = $User
    }
    exit 0
}

$ai = Get-UpdateFleetAiRoot -Override $AiRoot
$bobRoot = Join-Path $ai 'bob'
$installWorker = Join-Path $bobRoot 'worker'
$selfId = Get-UpdateFleetMachineId

try {
    $machines = @(Get-UpdateFleetDigestMachines -Url $DigestUrl)
}
catch {
    Write-UpdateFleetJson @{
        ok     = $false
        check  = 'updatefleet'
        error  = ('digest: ' + [string]$_.Exception.Message)
        digest = $DigestUrl
    }
    exit 2
}

if ($Machine -and $Machine.Count -gt 0) {
    $want = @($Machine | ForEach-Object { $_.ToLowerInvariant() })
    $machines = @($machines | Where-Object { $want -contains $_ })
}
if ($SkipMachine -and $SkipMachine.Count -gt 0) {
    $skip = @($SkipMachine | ForEach-Object { $_.ToLowerInvariant() })
    $machines = @($machines | Where-Object { $skip -notcontains $_ })
}

$cred = $null
$needRemote = @($machines | Where-Object { $_ -ne $selfId }).Count -gt 0
if (-not $DryRun -and $needRemote) {
    try {
        $cred = Get-UpdateFleetPSCredential -Target $CredTarget -DefaultUser $User
    }
    catch {
        Write-UpdateFleetJson @{
            ok          = $false
            check       = 'updatefleet'
            error       = [string]$_.Exception.Message
            cred_target = $CredTarget
            machines    = $machines
        }
        exit 2
    }
}

try {
    $artifact = Resolve-UpdateFleetArtifactDir -Requested $ArtifactDir -BobRoot $bobRoot
    $expected = Get-UpdateFleetExpectedSha -Dir $artifact
}
catch {
    Write-UpdateFleetJson @{
        ok    = $false
        check = 'updatefleet'
        error = ('artifact: ' + [string]$_.Exception.Message)
    }
    exit 2
}

$results = @()
$anyFail = $false
foreach ($mid in $machines) {
    $row = [ordered]@{
        machine  = $mid
        host     = $mid
        local    = ($mid -eq $selfId)
        install  = $null
        recycle  = $null
        ok       = $false
    }
    try {
        if ($row.local) {
            $row.install = Install-UpdateFleetWorkerLocal -ArtifactDir $artifact -InstallWorker $installWorker -ExpectedSha $expected -DryRun:$DryRun
        }
        else {
            if (-not $cred -and -not $DryRun) { throw "missing CredMan credential for remote $mid" }
            $row.install = Install-UpdateFleetWorkerRemote -ComputerName $mid -Credential $cred -ArtifactDir $artifact -InstallWorker $installWorker -ExpectedSha $expected -TimeoutSec $WinRmTimeoutSec -DryRun:$DryRun
        }
        # FR #8532: do not attempt WinRM recycle when install already classified winrm-closed.
        if (-not $row.install.ok -and [string]$row.install.method -eq 'winrm-closed') {
            $row.fallback = [string]$row.install.fallback
            $row.hint = [string]$row.install.hint
            if (-not $NoRecycle) {
                $row.recycle = [pscustomobject]@{
                    ok      = $false
                    method  = 'skipped'
                    skipped = $true
                    error   = 'winrm-closed'
                }
            }
        }
        elseif (-not $NoRecycle) {
            $row.recycle = Invoke-UpdateFleetRecycle -ComputerName $mid -Credential $cred -BobRoot $bobRoot -MachineId $mid -IsLocal:([bool]$row.local) -TtlSec $RecycleTtlSec -DryRun:$DryRun
        }
        $row.ok = [bool]$row.install.ok -and ($NoRecycle -or [bool]$row.recycle.ok -or ($row.recycle -and $row.recycle.disabled))
        if (-not $row.ok) { $anyFail = $true }
    }
    catch {
        $row.error = [string]$_.Exception.Message
        $row.ok = $false
        $anyFail = $true
    }
    $results += [pscustomobject]$row
}

$payload = [ordered]@{
    ok            = (-not $anyFail)
    check         = 'updatefleet'
    dry_run       = [bool]$DryRun
    digest        = $DigestUrl
    self          = $selfId
    artifact_dir  = $artifact
    expected_sha  = $expected
    sha12         = $expected.Substring(0, [Math]::Min(12, $expected.Length))
    machines      = $machines
    results       = $results
}
Write-UpdateFleetJson $payload
if ($anyFail) { exit 1 }
exit 0
