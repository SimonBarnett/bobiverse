#Requires -Version 5.1
<#
.SYNOPSIS
  Per-box OpenCode fleet smoke checklist (FR #6160 / FR-OC-FLEET). Never prints secrets.

.DESCRIPTION
  Checks winget/PATH visibility of opencode.exe, auth.json presence + ACL (never
  reads the body), optional live ``opencode run`` pong, and bob-worker --dry-run
  seeing an OpenCode-capable exe (opencode_cmd true in JSON).

  Exit codes:
    0  all requested checks passed
    1  opencode missing from PATH / unresolved
    2  auth.json missing or ACL not restricted to current user
    3  live pong smoke failed (nonzero / timeout / no pong-class reply)
    4  bob-worker missing or dry-run JSON lacks opencode_cmd / parse fail
    5  unexpected error

  CAST IRON: never Get-Content / type / cat auth.json. Report path + length only.

.PARAMETER SkipPong
  Skip the live ``opencode run`` smoke (CI / offline seats).

.PARAMETER SkipDryRun
  Skip bob-worker --dry-run.

.PARAMETER SkipAuth
  Skip auth.json presence/ACL (install-only PATH check).

.PARAMETER RequireOpencodeDecision
  Fail dry-run unless decision=opencode (usually needs Grok+Cursor exhausted fixtures).

.PARAMETER WorkerExe
  Path to bob-worker.exe (default: <InstallRoot>\worker\bob-worker.exe then PATH).

.PARAMETER InstallRoot
  Bob install root for --dry-run --install-root (default: parent of this scripts folder).

.PARAMETER AuthPath
  Override auth.json path (default: %USERPROFILE%\.local\share\opencode\auth.json).

.PARAMETER PongModel
  Model id for the pong smoke (default: opencode/beam-free).

.PARAMETER PongTimeoutSec
  Seconds to wait for opencode run (default: 120).

.EXAMPLE
  .\Assert-BobOpencodeFleetSmoke.ps1 -SkipPong
.EXAMPLE
  .\Assert-BobOpencodeFleetSmoke.ps1 -SkipPong -SkipDryRun
#>
[CmdletBinding()]
param(
    [switch]$SkipPong,
    [switch]$SkipDryRun,
    [switch]$SkipAuth,
    [switch]$RequireOpencodeDecision,
    [string]$WorkerExe = '',
    [string]$InstallRoot = '',
    [string]$AuthPath = '',
    [string]$PongModel = 'opencode/beam-free',
    [int]$PongTimeoutSec = 120
)

$ErrorActionPreference = 'Stop'
$script:FailCode = 0

function Write-Smoke {
    param([string]$Msg)
    Write-Output ("opencode-fleet: " + $Msg)
}

function Fail-Smoke {
    param([int]$Code, [string]$Msg)
    Write-Smoke ("FAIL: " + $Msg)
    if ($script:FailCode -eq 0) { $script:FailCode = $Code }
}

function Resolve-OpencodeExe {
    $cmd = Get-Command opencode.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return [string]$cmd.Source }
    $cmd = Get-Command opencode -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return [string]$cmd.Source }
    $links = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\opencode.exe'
    if (Test-Path -LiteralPath $links) { return $links }
    $portable = Join-Path $env:LOCALAPPDATA 'Programs\opencode\opencode.exe'
    if (Test-Path -LiteralPath $portable) { return $portable }
    return $null
}

function Test-AuthAclRestricted {
    param([Parameter(Mandatory = $true)][string]$Path)
    # Presence + inheritance disabled + ONLY current user Allow-read (setup skill icacls posture).
    # Never read body. Reject extra Allow grants to other principals (FR #6160 MRB).
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $acl = Get-Acl -LiteralPath $Path
        if ($acl.AreAccessRulesProtected -ne $true) {
            # inheritance still on --- not the restricted posture from the setup skill
            return $false
        }
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $userOk = $false
        foreach ($r in @($acl.Access)) {
            $rights = $r.FileSystemRights.ToString()
            $reads = $rights -match 'Read|FullControl|Modify|Write|Delete|ChangePermissions|TakeOwnership'
            if (-not $reads) { continue }
            if ($r.AccessControlType -eq 'Deny') {
                # Deny to current user blocks seat read; Deny to others is fine
                if ($r.IdentityReference.Value -eq $user) { return $false }
                continue
            }
            # Allow with read-ish rights
            if ($r.IdentityReference.Value -eq $user) {
                $userOk = $true
            } else {
                # another principal still has Allow read/write --- not exclusive
                return $false
            }
        }
        return $userOk
    } catch {
        return $false
    }
}

# --- resolve install root ---
if (-not $InstallRoot) {
    $InstallRoot = Split-Path -Parent $PSScriptRoot
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)

# --- 1) PATH / version ---
$oc = Resolve-OpencodeExe
if (-not $oc) {
    Fail-Smoke 1 "opencode.exe not on PATH (winget Links / Programs\opencode). See bob-setup-opencode Troubleshoot."
} else {
    Write-Smoke ("opencode exe=$oc")
    $prevEap = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $verLines = & $oc --version 2>&1
        $verExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($verExit -ne 0) {
            Fail-Smoke 1 ("opencode --version exit=" + $verExit)
        } else {
            $ver = (($verLines | ForEach-Object { "$_" }) -join ' ' -replace '\s+', ' ').Trim()
            if (-not $ver) { Fail-Smoke 1 "opencode --version returned empty" }
            else { Write-Smoke ("version=$ver") }
        }
    } catch {
        $ErrorActionPreference = $prevEap
        Fail-Smoke 1 ("opencode --version failed: " + $_.Exception.Message)
    }
}

# --- 2) auth.json presence + ACL (never cat) ---
if (-not $SkipAuth) {
    if (-not $AuthPath) {
        $AuthPath = Join-Path $env:USERPROFILE '.local\share\opencode\auth.json'
    }
    if (-not (Test-Path -LiteralPath $AuthPath)) {
        Fail-Smoke 2 ("auth.json missing at path (presence only; body never read): " + $AuthPath)
    } else {
        $len = (Get-Item -LiteralPath $AuthPath).Length
        Write-Smoke ("auth.json present path=$AuthPath bytes=$len (body not read)")
        if (-not (Test-AuthAclRestricted -Path $AuthPath)) {
            Fail-Smoke 2 "auth.json ACL not restricted (run icacls reset + inheritance:r + grant current user Read; see bob-setup-opencode)"
        } else {
            Write-Smoke "auth.json ACL restricted to current user (inheritance off)"
        }
    }
} else {
    Write-Smoke "auth check skipped (-SkipAuth)"
}

# --- 3) live pong ---
if (-not $SkipPong) {
    if (-not $oc) {
        Fail-Smoke 3 "pong skipped because opencode missing"
    } else {
        Write-Smoke ("pong smoke model=$PongModel timeout_s=$PongTimeoutSec")
        $outFile = Join-Path $env:TEMP ('bob-oc-fleet-pong-' + [guid]::NewGuid().ToString('n') + '.txt')
        $errFile = Join-Path $env:TEMP ('bob-oc-fleet-pong-err-' + [guid]::NewGuid().ToString('n') + '.txt')
        try {
            $p = Start-Process -FilePath $oc -ArgumentList @('run', '-m', $PongModel, 'Reply with pong only') `
                -NoNewWindow -PassThru -RedirectStandardOutput $outFile -RedirectStandardError $errFile
            if (-not $p.WaitForExit($PongTimeoutSec * 1000)) {
                try { & taskkill /T /F /PID $p.Id 2>$null | Out-Null } catch { }
                Fail-Smoke 3 "opencode run pong timed out"
            } elseif ($p.ExitCode -ne 0) {
                Fail-Smoke 3 ("opencode run pong exit=" + $p.ExitCode)
            } else {
                $txt = ''
                if (Test-Path -LiteralPath $outFile) { $txt = [IO.File]::ReadAllText($outFile) }
                if (Test-Path -LiteralPath $errFile) { $txt += "`n" + [IO.File]::ReadAllText($errFile) }
                if ($txt -notmatch '(?i)\bpong\b') {
                    Fail-Smoke 3 "opencode run exited 0 but reply lacked pong-class text"
                } else {
                    Write-Smoke "pong smoke ok"
                }
            }
        } catch {
            Fail-Smoke 3 ("opencode run pong error: " + $_.Exception.Message)
        } finally {
            foreach ($f in @($outFile, $errFile)) {
                if ($f -and (Test-Path -LiteralPath $f)) {
                    Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }
} else {
    Write-Smoke "pong smoke skipped (-SkipPong)"
}

# --- 4) bob-worker --dry-run ---
if (-not $SkipDryRun) {
    $exe = $WorkerExe
    if (-not $exe) {
        $cand = Join-Path $InstallRoot 'worker\bob-worker.exe'
        if (Test-Path -LiteralPath $cand) { $exe = $cand }
    }
    if (-not $exe) {
        $w = Get-Command bob-worker.exe -ErrorAction SilentlyContinue
        if ($w -and $w.Source) { $exe = [string]$w.Source }
    }
    if (-not $exe -or -not (Test-Path -LiteralPath $exe)) {
        Fail-Smoke 4 "bob-worker.exe not found (pass -WorkerExe or install under <InstallRoot>\worker). Dry-run cannot see OpenCode exe."
    } else {
        Write-Smoke ("dry-run exe=$exe install_root=$InstallRoot")
        $prevEap = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $rawLines = & $exe --dry-run --install-root $InstallRoot 2>&1
            $dryExit = $LASTEXITCODE
            $ErrorActionPreference = $prevEap
            if ($dryExit -ne 0) {
                Fail-Smoke 4 ("dry-run exit=" + $dryExit)
            } else {
                $raw = (($rawLines | ForEach-Object { "$_" }) -join "`n")
                $jsonLine = ($raw -split "`r?`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1)
                if (-not $jsonLine) {
                    Fail-Smoke 4 "dry-run produced no JSON object"
                } else {
                    $obj = $jsonLine | ConvertFrom-Json
                    $ocCmd = $false
                    if ($null -ne $obj.opencode_cmd) { $ocCmd = [bool]$obj.opencode_cmd }
                    Write-Smoke ("dry-run decision=$($obj.decision) opencode_cmd=$ocCmd")
                    if (-not $ocCmd) {
                        Fail-Smoke 4 "dry-run opencode_cmd=false (opencode.exe not visible to bob-worker resolve)"
                    }
                    if ($RequireOpencodeDecision -and [string]$obj.decision -ne 'opencode') {
                        Fail-Smoke 4 ("-RequireOpencodeDecision set but decision=$($obj.decision)")
                    }
                }
            }
        } catch {
            $ErrorActionPreference = $prevEap
            Fail-Smoke 4 ("dry-run failed: " + $_.Exception.Message)
        }
    }
} else {
    Write-Smoke "dry-run skipped (-SkipDryRun)"
}

if ($script:FailCode -eq 0) {
    Write-Smoke "PASS"
    exit 0
}
Write-Smoke ("DONE with failures code=$script:FailCode")
exit $script:FailCode
