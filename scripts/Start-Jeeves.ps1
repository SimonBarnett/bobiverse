#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Jeeves chair (used by NSSM ircJeeves). Runs MSI self-update check first.
#>
[CmdletBinding()]
param(
    [string]$ChairHome = '',
    [string]$Python = '',
    [string]$RepoRoot = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
. (Join-Path $scriptDir 'Bobiverse-Common.ps1')
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $scriptDir }
if (-not $ChairHome) {
    if (Test-BobiverseIsLocalSystem) {
        $ChairHome = Join-Path $RepoRoot 'home-jeeves'
    } else {
        $ChairHome = Join-Path $env:USERPROFILE '.agentic-irc-jeeves'
    }
}
New-Item -ItemType Directory -Force -Path $ChairHome | Out-Null
if (-not $Python) {
    try { $Python = Resolve-BobiversePython } catch { throw 'python.exe missing' }
}

[void](Import-BobiverseErgoPassword -InstallRoot $RepoRoot -HomeDir $ChairHome)

# Fast-forward C:\ai\bobiverse (or BOBIVERSE_REPO) and sync into this install tree.
# Operators may set BOBIVERSE_NO_UPDATE=1 to skip. LocalSystem is allowed to update.
$sync = Join-Path $scriptDir 'Sync-BobiverseFromRepo.ps1'
$synced = $false
if ((Test-Path -LiteralPath $sync) -and ($env:BOBIVERSE_NO_UPDATE -ne '1')) {
    try {
        & $sync -Product jeeves -InstallRoot $RepoRoot
        if ($LASTEXITCODE -eq 0) { $synced = $true }
    } catch {
        Write-Host "WARN sync-from-repo: $($_.Exception.Message)"
    }
}
if (-not $synced -and ($env:BOBIVERSE_NO_UPDATE -ne '1')) {
    $update = Join-Path $scriptDir 'Check-BobiverseUpdate.ps1'
    if (Test-Path -LiteralPath $update) {
        try {
            & $update -Product jeeves -InstallRoot $RepoRoot
        } catch {
            Write-Host "WARN update-check: $($_.Exception.Message)"
        }
    }
}

$agent = Join-Path $scriptDir 'irc_agent.py'
if (-not (Test-Path -LiteralPath $agent)) { throw "missing $agent" }

$env:BOB_DIGEST_HOME = if ($env:BOB_DIGEST_HOME) { $env:BOB_DIGEST_HOME } else {
    if (Test-BobiverseIsLocalSystem) { Join-Path $RepoRoot 'home' } else { Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
}
New-Item -ItemType Directory -Force -Path $env:BOB_DIGEST_HOME | Out-Null

# Ensure BobIrcd is up before chair (monitor path; !recycle jeeves still chair-only).
$watchIrcd = Join-Path $scriptDir 'Watch-BobIrcd.ps1'
if (Test-Path -LiteralPath $watchIrcd) {
    try { & $watchIrcd -DigestHome $env:BOB_DIGEST_HOME } catch {
        Write-Host "WARN Watch-BobIrcd: $($_.Exception.Message)"
    }
}

# Ensure bobcallback listens on 127.0.0.1:7700 (digest + intake + jira).
function Test-BobCallbackListening {
    try {
        $conns = Get-NetTCPConnection -LocalPort 7700 -State Listen -ErrorAction SilentlyContinue
        return [bool]$conns
    } catch {
        return $false
    }
}
$callback = Join-Path $scriptDir 'bobcallback.py'
if ((Test-Path -LiteralPath $callback) -and -not (Test-BobCallbackListening)) {
    Write-Host 'INFO starting bobcallback on 127.0.0.1:7700'
    $cbArgs = @(
        '-u', $callback,
        '--home', $env:BOB_DIGEST_HOME,
        '--bind', '127.0.0.1',
        '--port', '7700'
    )
    try {
        Start-Process -FilePath $Python -ArgumentList $cbArgs -WorkingDirectory $scriptDir -WindowStyle Hidden | Out-Null
        Start-Sleep -Seconds 2
    } catch {
        Write-Host "WARN bobcallback start failed: $($_.Exception.Message)"
    }
}

$watchWh = Join-Path $scriptDir 'Watch-BobWebhooks.ps1'
if (Test-Path -LiteralPath $watchWh) {
    try { & $watchWh -DigestHome $env:BOB_DIGEST_HOME } catch {
        Write-Host "WARN Watch-BobWebhooks: $($_.Exception.Message)"
    }
}

& $Python -u $agent --chair --nick Jeeves --home $ChairHome
exit $LASTEXITCODE
