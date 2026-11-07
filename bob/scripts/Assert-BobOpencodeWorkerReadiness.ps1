#Requires -Version 5.1
<#
.SYNOPSIS
  FR #6240: OpenCode Windows worker readiness - native search, worktree consent, gh auth.

.DESCRIPTION
  Preflight for OpenCode seats on Windows. Never assumes Unix grep/head.
  Never reads hosts.yml / token files / credential stores. Exit codes:

    0  all requested checks passed
    1  native search failed
    2  worktree consent / cwd mismatch / rejected permission
    3  gh auth missing or unusable
    4  unexpected error

  CAST IRON: never Get-Content hosts.yml; never invent GH_TOKEN; never widen
  external_directory after a denial.

.PARAMETER InstallRoot
  Root for native scoped search (default: bob product root).

.PARAMETER WorktreePath
  Assigned job worktree. When set, cwd must be inside it (or -Permission rejected/missing).

.PARAMETER Permission
  Approval-flow outcome: authorized | missing | rejected (default authorized).

.PARAMETER SkipSearch
  Skip native file discovery.

.PARAMETER SkipWorktree
  Skip worktree/cwd check.

.PARAMETER SkipGhAuth
  Skip gh auth status.

.PARAMETER Needle
  Search needle (default opencode).

.PARAMETER MaxHits
  Bound search hits (default 50).

.PARAMETER GhAuthStdout / GhAuthStderr / GhAuthExitCode
  Fixture overrides for tests (skip live gh).

.EXAMPLE
  .\Assert-BobOpencodeWorkerReadiness.ps1 -WorktreePath $env:BOB_JOB_WORKTREE
.EXAMPLE
  .\Assert-BobOpencodeWorkerReadiness.ps1 -SkipGhAuth -Permission rejected -WorktreePath C:\wt\fr-1
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$WorktreePath = '',
    [ValidateSet('authorized', 'missing', 'rejected')]
    [string]$Permission = 'authorized',
    [switch]$SkipSearch,
    [switch]$SkipWorktree,
    [switch]$SkipGhAuth,
    [string]$Needle = 'opencode',
    [int]$MaxHits = 50,
    [string]$GhAuthStdout = '',
    [string]$GhAuthStderr = '',
    [Nullable[int]]$GhAuthExitCode = $null
)

$ErrorActionPreference = 'Stop'
$script:FailCode = 0

function Write-Ready {
    param([string]$Msg)
    Write-Output ("opencode-ready: " + $Msg)
}

function Fail-Ready {
    param([int]$Code, [string]$Msg)
    Write-Ready ("FAIL: " + $Msg)
    if ($script:FailCode -eq 0) { $script:FailCode = $Code }
}

$here = $PSScriptRoot
$cm = Join-Path $here 'Bobiverse-Common.ps1'
if (-not (Test-Path -LiteralPath $cm)) {
    $cm = Join-Path (Split-Path -Parent (Split-Path -Parent $here)) 'common\scripts\Bobiverse-Common.ps1'
}
if (Test-Path -LiteralPath $cm) { . $cm }

if (-not $InstallRoot) {
    if (Get-Command Get-BobiverseProductRoot -ErrorAction SilentlyContinue) {
        try { $InstallRoot = Get-BobiverseProductRoot -Product bob } catch { $InstallRoot = '' }
    }
    if (-not $InstallRoot) {
        $InstallRoot = Split-Path -Parent $here
        if ((Split-Path -Leaf $InstallRoot) -eq 'scripts') {
            $InstallRoot = Split-Path -Parent $InstallRoot
        }
    }
}

$pyHelper = Join-Path $here 'opencode_worker_readiness.py'
if (-not (Test-Path -LiteralPath $pyHelper)) {
    $alt = Join-Path (Split-Path -Parent (Split-Path -Parent $here)) 'common\scripts\opencode_worker_readiness.py'
    if (Test-Path -LiteralPath $alt) { $pyHelper = $alt }
}
if (-not (Test-Path -LiteralPath $pyHelper)) {
    Fail-Ready 4 "missing opencode_worker_readiness.py"
    exit 4
}

$python = $null
if (Get-Command Resolve-BobiversePython -ErrorAction SilentlyContinue) {
    try { $python = Resolve-BobiversePython -AllowMissing } catch { $python = $null }
}
if (-not $python) {
    foreach ($c in @((Get-Command python.exe -ErrorAction SilentlyContinue).Source, 'C:\Program Files\Python312\python.exe', 'C:\Python312\python.exe')) {
        if ($c -and (Test-Path -LiteralPath $c)) { $python = $c; break }
    }
}
if (-not $python) {
    Fail-Ready 4 'python.exe not found'
    exit 4
}

# --- 1) Native search (no grep/head) ---
if (-not $SkipSearch) {
    $searchJson = & $python -c @"
import json, sys
sys.path.insert(0, r'$($pyHelper | Split-Path -Parent)')
import opencode_worker_readiness as r
print(json.dumps(r.windows_native_search(r'''$InstallRoot''', needle=r'''$Needle''', max_hits=$MaxHits)))
"@
    if ($LASTEXITCODE -ne 0 -or -not $searchJson) {
        Fail-Ready 1 'native search helper failed'
    } else {
        $search = $searchJson | ConvertFrom-Json
        if (-not $search.ok) {
            Fail-Ready 1 ("native search blocked: " + $search.error)
        } elseif (@($search.hits).Count -lt 1) {
            Fail-Ready 1 ("native search found 0 hits for '$Needle' under $InstallRoot (tool=$($search.tool))")
        } else {
            Write-Ready ("search ok tool=$($search.tool) hits=$(@($search.hits).Count) scanned=$($search.scanned)")
        }
    }
} else {
    Write-Ready 'search skipped'
}

# --- 2) Worktree consent / cwd ---
if (-not $SkipWorktree) {
    $cwd = (Get-Location).Path
    $wtArg = if ($WorktreePath) { $WorktreePath } else { $cwd }
    $wtJson = & $python -c @"
import json, sys
sys.path.insert(0, r'$($pyHelper | Split-Path -Parent)')
import opencode_worker_readiness as r
print(json.dumps(r.classify_worktree_access(cwd=r'''$cwd''', worktree=r'''$wtArg''', permission=r'''$Permission''')))
"@
    if ($LASTEXITCODE -ne 0 -or -not $wtJson) {
        Fail-Ready 2 'worktree classifier failed'
    } else {
        $wt = $wtJson | ConvertFrom-Json
        if (-not $wt.ok) {
            Fail-Ready 2 ("worktree blocked ($($wt.blocker)): $($wt.next_step)")
        } else {
            Write-Ready ("worktree ok state=$($wt.state)")
        }
    }
} else {
    Write-Ready 'worktree skipped'
}

# --- 3) gh auth status only (never hosts.yml) ---
if (-not $SkipGhAuth) {
    $ghOut = $GhAuthStdout
    $ghErr = $GhAuthStderr
    $ghCode = $GhAuthExitCode
    if ($null -eq $ghCode -and -not $GhAuthStdout -and -not $GhAuthStderr) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $probe = & gh auth status 2>&1
        $ghCode = $LASTEXITCODE
        $ErrorActionPreference = $prev
        $ghOut = ($probe | Out-String)
        $ghErr = ''
    }
    if ($null -eq $ghCode) { $ghCode = 1 }
    # Escape for Python: use env vars to avoid quote hell / secret argv
    $env:BOB_FR6240_GH_OUT = [string]$ghOut
    $env:BOB_FR6240_GH_ERR = [string]$ghErr
    $env:BOB_FR6240_GH_CODE = [string]$ghCode
    try {
        $ghJson = & $python -c @"
import json, os, sys
sys.path.insert(0, r'$($pyHelper | Split-Path -Parent)')
import opencode_worker_readiness as r
print(json.dumps(r.classify_gh_auth(
    exit_code=int(os.environ.get('BOB_FR6240_GH_CODE') or '1'),
    stdout=os.environ.get('BOB_FR6240_GH_OUT') or '',
    stderr=os.environ.get('BOB_FR6240_GH_ERR') or '',
)))
"@
    } finally {
        Remove-Item Env:BOB_FR6240_GH_OUT -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_GH_ERR -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_GH_CODE -ErrorAction SilentlyContinue
    }
    if ($LASTEXITCODE -ne 0 -or -not $ghJson) {
        Fail-Ready 3 'gh auth classifier failed'
    } else {
        $gh = $ghJson | ConvertFrom-Json
        if (-not $gh.ok) {
            Fail-Ready 3 ("gh blocked ($($gh.blocker)): $($gh.next_step)")
        } else {
            Write-Ready ("gh ok state=$($gh.state) detail=$($gh.detail)")
        }
    }
} else {
    Write-Ready 'gh auth skipped'
}

if ($script:FailCode -eq 0) {
    Write-Ready 'OK FR #6240 worker readiness passed'
    exit 0
}
Write-Ready ("blocked exit=$($script:FailCode) (not DONE - fix blockers then re-run)")
exit $script:FailCode
