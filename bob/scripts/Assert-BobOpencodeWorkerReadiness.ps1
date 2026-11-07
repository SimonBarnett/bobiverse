#Requires -Version 5.1
<#
.SYNOPSIS
  FR #6240: OpenCode Windows worker readiness - native search, worktree consent, gh auth.

.DESCRIPTION
  Preflight for OpenCode seats on Windows. Never assumes Unix grep/head.
  Never reads hosts.yml / token files / credential stores. Exit codes:

    0  all requested checks passed
    1  native search failed
    2  worktree consent / cwd mismatch / rejected permission / git status-branch fail
    3  gh auth missing or unusable / scoped PR lookup fail
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

.PARAMETER SkipGit
  Skip read-only git status/branch against the worktree.

.PARAMETER SkipGhAuth
  Skip gh auth status.

.PARAMETER SkipPrLookup
  Skip scoped read-only gh pr view after auth.

.PARAMETER VerifyPr
  owner/repo#N for scoped lookup (default SimonBarnett/bobiverse#6147).

.PARAMETER Needle
  Search needle (default opencode).

.PARAMETER MaxHits
  Bound search hits (default 50).

.PARAMETER GhAuthStdout / GhAuthStderr / GhAuthExitCode
  Fixture overrides for tests (skip live gh).

.PARAMETER PrLookupStdout / PrLookupStderr / PrLookupExitCode
  Fixture overrides for scoped PR lookup tests.

.PARAMETER GitStatusStdout / GitStatusStderr / GitStatusExitCode
.PARAMETER GitBranchStdout / GitBranchStderr / GitBranchExitCode
  Fixture overrides for git classifiers.

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
    [switch]$SkipGit,
    [switch]$SkipGhAuth,
    [switch]$SkipPrLookup,
    [string]$VerifyPr = 'SimonBarnett/bobiverse#6147',
    [string]$Needle = 'opencode',
    [int]$MaxHits = 50,
    [string]$GhAuthStdout = '',
    [string]$GhAuthStderr = '',
    [Nullable[int]]$GhAuthExitCode = $null,
    [string]$PrLookupStdout = '',
    [string]$PrLookupStderr = '',
    [Nullable[int]]$PrLookupExitCode = $null,
    [string]$GitStatusStdout = '',
    [string]$GitStatusStderr = '',
    [Nullable[int]]$GitStatusExitCode = $null,
    [string]$GitBranchStdout = '',
    [string]$GitBranchStderr = '',
    [Nullable[int]]$GitBranchExitCode = $null
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

function Invoke-Fr6240PythonJson {
    param([string]$PythonExe, [string]$HelperDir, [string]$Snippet)
    $env:BOB_FR6240_PY_PATH = $HelperDir
    try {
        $json = & $PythonExe -c $Snippet
        return $json
    } finally {
        Remove-Item Env:BOB_FR6240_PY_PATH -ErrorAction SilentlyContinue
    }
}

try {

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
$pyDir = Split-Path -Parent $pyHelper

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

# --- 1) Native search (no grep/head); paths via env (never string-interpolate into Python) ---
if (-not $SkipSearch) {
    $env:BOB_FR6240_INSTALL_ROOT = [string]$InstallRoot
    $env:BOB_FR6240_NEEDLE = [string]$Needle
    $env:BOB_FR6240_MAX_HITS = [string]$MaxHits
    try {
        $searchJson = Invoke-Fr6240PythonJson -PythonExe $python -HelperDir $pyDir -Snippet @"
import json, os, sys
sys.path.insert(0, os.environ.get('BOB_FR6240_PY_PATH') or '')
import opencode_worker_readiness as r
print(json.dumps(r.windows_native_search(
    os.environ.get('BOB_FR6240_INSTALL_ROOT') or '',
    needle=os.environ.get('BOB_FR6240_NEEDLE') or 'opencode',
    max_hits=int(os.environ.get('BOB_FR6240_MAX_HITS') or '50'),
)))
"@
    } finally {
        Remove-Item Env:BOB_FR6240_INSTALL_ROOT -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_NEEDLE -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_MAX_HITS -ErrorAction SilentlyContinue
    }
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
$resolvedWt = ''
if (-not $SkipWorktree) {
    $cwd = (Get-Location).Path
    $wtArg = if ($WorktreePath) { $WorktreePath } else { $cwd }
    $resolvedWt = $wtArg
    $env:BOB_FR6240_CWD = [string]$cwd
    $env:BOB_FR6240_WORKTREE = [string]$wtArg
    $env:BOB_FR6240_PERMISSION = [string]$Permission
    try {
        $wtJson = Invoke-Fr6240PythonJson -PythonExe $python -HelperDir $pyDir -Snippet @"
import json, os, sys
sys.path.insert(0, os.environ.get('BOB_FR6240_PY_PATH') or '')
import opencode_worker_readiness as r
print(json.dumps(r.classify_worktree_access(
    cwd=os.environ.get('BOB_FR6240_CWD') or '',
    worktree=os.environ.get('BOB_FR6240_WORKTREE') or '',
    permission=os.environ.get('BOB_FR6240_PERMISSION') or 'authorized',
)))
"@
    } finally {
        Remove-Item Env:BOB_FR6240_CWD -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_WORKTREE -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_PERMISSION -ErrorAction SilentlyContinue
    }
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
    if ($WorktreePath) { $resolvedWt = $WorktreePath } else { $resolvedWt = (Get-Location).Path }
}

# --- 2b) Read-only git status/branch against the worktree ---
if (-not $SkipGit) {
    if (-not $resolvedWt) { $resolvedWt = if ($WorktreePath) { $WorktreePath } else { (Get-Location).Path } }
    $gsOut = $GitStatusStdout
    $gsErr = $GitStatusStderr
    $gsCode = $GitStatusExitCode
    $gbOut = $GitBranchStdout
    $gbErr = $GitBranchStderr
    $gbCode = $GitBranchExitCode
    if ($null -eq $gsCode -and -not $GitStatusStdout -and -not $GitStatusStderr) {
        $prev = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $probe = & git -C $resolvedWt status 2>&1
            $gsCode = $LASTEXITCODE
            $gsOut = ($probe | Out-String)
            $gsErr = ''
        } finally {
            $ErrorActionPreference = $prev
        }
    }
    if ($null -eq $gbCode -and -not $GitBranchStdout -and -not $GitBranchStderr) {
        $prev = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $probe = & git -C $resolvedWt branch --show-current 2>&1
            $gbCode = $LASTEXITCODE
            $gbOut = ($probe | Out-String)
            $gbErr = ''
        } finally {
            $ErrorActionPreference = $prev
        }
    }
    if ($null -eq $gsCode) { $gsCode = 1 }
    if ($null -eq $gbCode) { $gbCode = 1 }
    $env:BOB_FR6240_GS_OUT = [string]$gsOut
    $env:BOB_FR6240_GS_ERR = [string]$gsErr
    $env:BOB_FR6240_GS_CODE = [string]$gsCode
    $env:BOB_FR6240_GB_OUT = [string]$gbOut
    $env:BOB_FR6240_GB_ERR = [string]$gbErr
    $env:BOB_FR6240_GB_CODE = [string]$gbCode
    try {
        $gitJson = Invoke-Fr6240PythonJson -PythonExe $python -HelperDir $pyDir -Snippet @"
import json, os, sys
sys.path.insert(0, os.environ.get('BOB_FR6240_PY_PATH') or '')
import opencode_worker_readiness as r
print(json.dumps(r.classify_git_worktree(
    status_exit=int(os.environ.get('BOB_FR6240_GS_CODE') or '1'),
    status_stdout=os.environ.get('BOB_FR6240_GS_OUT') or '',
    status_stderr=os.environ.get('BOB_FR6240_GS_ERR') or '',
    branch_exit=int(os.environ.get('BOB_FR6240_GB_CODE') or '1'),
    branch_stdout=os.environ.get('BOB_FR6240_GB_OUT') or '',
    branch_stderr=os.environ.get('BOB_FR6240_GB_ERR') or '',
)))
"@
    } finally {
        Remove-Item Env:BOB_FR6240_GS_OUT -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_GS_ERR -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_GS_CODE -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_GB_OUT -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_GB_ERR -ErrorAction SilentlyContinue
        Remove-Item Env:BOB_FR6240_GB_CODE -ErrorAction SilentlyContinue
    }
    if ($LASTEXITCODE -ne 0 -or -not $gitJson) {
        Fail-Ready 2 'git classifier failed'
    } else {
        $gitR = $gitJson | ConvertFrom-Json
        if (-not $gitR.ok) {
            Fail-Ready 2 ("git blocked ($($gitR.blocker)): $($gitR.next_step)")
        } else {
            Write-Ready ("git ok branch=$($gitR.branch)")
        }
    }
} else {
    Write-Ready 'git skipped'
}

# --- 3) gh auth status only (never hosts.yml) ---
$ghAuthorized = $false
if (-not $SkipGhAuth) {
    $ghOut = $GhAuthStdout
    $ghErr = $GhAuthStderr
    $ghCode = $GhAuthExitCode
    if ($null -eq $ghCode -and -not $GhAuthStdout -and -not $GhAuthStderr) {
        $prev = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $probe = & gh auth status 2>&1
            $ghCode = $LASTEXITCODE
            $ghOut = ($probe | Out-String)
            $ghErr = ''
        } catch {
            $ghCode = 1
            $ghOut = ''
            $ghErr = [string]$_.Exception.Message
        } finally {
            $ErrorActionPreference = $prev
        }
    }
    if ($null -eq $ghCode) { $ghCode = 1 }
    $env:BOB_FR6240_GH_OUT = [string]$ghOut
    $env:BOB_FR6240_GH_ERR = [string]$ghErr
    $env:BOB_FR6240_GH_CODE = [string]$ghCode
    try {
        $ghJson = Invoke-Fr6240PythonJson -PythonExe $python -HelperDir $pyDir -Snippet @"
import json, os, sys
sys.path.insert(0, os.environ.get('BOB_FR6240_PY_PATH') or '')
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
            $ghAuthorized = $true
            Write-Ready ("gh ok state=$($gh.state) detail=$($gh.detail)")
        }
    }
} else {
    Write-Ready 'gh auth skipped'
}

# --- 3b) Scoped read-only PR lookup (only after auth ok, or fixture override) ---
if (-not $SkipPrLookup) {
    $doLookup = $ghAuthorized -or ($null -ne $PrLookupExitCode) -or $PrLookupStdout -or $PrLookupStderr
    if (-not $doLookup -and $SkipGhAuth) {
        Write-Ready 'pr lookup skipped (gh auth skipped; pass -PrLookup* fixtures to exercise)'
    } elseif (-not $doLookup) {
        Fail-Ready 3 'pr lookup blocked: gh auth not authorized'
    } else {
        $repo = 'SimonBarnett/bobiverse'
        $num = 6147
        if ($VerifyPr -match '^(?<repo>[^#]+)#(?<n>\d+)$') {
            $repo = $Matches['repo']
            $num = [int]$Matches['n']
        }
        $prOut = $PrLookupStdout
        $prErr = $PrLookupStderr
        $prCode = $PrLookupExitCode
        if ($null -eq $prCode -and -not $PrLookupStdout -and -not $PrLookupStderr) {
            $prev = $ErrorActionPreference
            try {
                $ErrorActionPreference = 'Continue'
                $probe = & gh pr view $num --repo $repo --json number,url,title 2>&1
                $prCode = $LASTEXITCODE
                $prOut = ($probe | Out-String)
                $prErr = ''
            } catch {
                $prCode = 1
                $prOut = ''
                $prErr = [string]$_.Exception.Message
            } finally {
                $ErrorActionPreference = $prev
            }
        }
        if ($null -eq $prCode) { $prCode = 1 }
        $env:BOB_FR6240_PR_OUT = [string]$prOut
        $env:BOB_FR6240_PR_ERR = [string]$prErr
        $env:BOB_FR6240_PR_CODE = [string]$prCode
        $env:BOB_FR6240_PR_REPO = [string]$repo
        $env:BOB_FR6240_PR_NUM = [string]$num
        try {
            $prJson = Invoke-Fr6240PythonJson -PythonExe $python -HelperDir $pyDir -Snippet @"
import json, os, sys
sys.path.insert(0, os.environ.get('BOB_FR6240_PY_PATH') or '')
import opencode_worker_readiness as r
print(json.dumps(r.classify_pr_lookup(
    exit_code=int(os.environ.get('BOB_FR6240_PR_CODE') or '1'),
    stdout=os.environ.get('BOB_FR6240_PR_OUT') or '',
    stderr=os.environ.get('BOB_FR6240_PR_ERR') or '',
    expected_repo=os.environ.get('BOB_FR6240_PR_REPO') or 'SimonBarnett/bobiverse',
    expected_number=int(os.environ.get('BOB_FR6240_PR_NUM') or '6147'),
)))
"@
        } finally {
            Remove-Item Env:BOB_FR6240_PR_OUT -ErrorAction SilentlyContinue
            Remove-Item Env:BOB_FR6240_PR_ERR -ErrorAction SilentlyContinue
            Remove-Item Env:BOB_FR6240_PR_CODE -ErrorAction SilentlyContinue
            Remove-Item Env:BOB_FR6240_PR_REPO -ErrorAction SilentlyContinue
            Remove-Item Env:BOB_FR6240_PR_NUM -ErrorAction SilentlyContinue
        }
        if ($LASTEXITCODE -ne 0 -or -not $prJson) {
            Fail-Ready 3 'pr lookup classifier failed'
        } else {
            $prR = $prJson | ConvertFrom-Json
            if (-not $prR.ok) {
                Fail-Ready 3 ("pr lookup blocked ($($prR.blocker)): $($prR.next_step)")
            } else {
                Write-Ready ("pr lookup ok $($prR.repo)#$($prR.number)")
            }
        }
    }
} else {
    Write-Ready 'pr lookup skipped'
}

if ($script:FailCode -eq 0) {
    Write-Ready 'OK FR #6240 worker readiness passed'
    exit 0
}
Write-Ready ("blocked exit=$($script:FailCode) (not DONE - fix blockers then re-run)")
exit $script:FailCode

} catch {
    $msg = [string]$_.Exception.Message
    if (-not $msg) { $msg = [string]$_ }
    Write-Ready ("FAIL: unexpected error: " + $msg)
    exit 4
}