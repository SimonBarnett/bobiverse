#Requires -Version 5.1
<#
.SYNOPSIS
  Refuse checking out a foreign GitHub PR when CWD is the bobiverse install tree.

.DESCRIPTION
  FR #4925: gh pr checkout N --repo SimonBarnett/a-search (or any non-bobiverse
  --repo) run from C:\ai\bob / bob\worker creates a local intake/... branch on the
  install sparse work tree and leaves bobiverse off main.

  Call this before any foreign gh pr checkout. Exit 0 when safe (same repo, or
  cwd is not a git work tree, or remote is not bobiverse). Exit 2 when the cwd
  remote resolves to SimonBarnett/bobiverse (or */bobiverse) and -Repo names a
  different owner/name - use a %TEMP% worktree/clone instead.

.PARAMETER Repo
  Target owner/name for the intended checkout (e.g. SimonBarnett/a-search).

.PARAMETER Path
  Directory whose .git remote is checked (default: current location).

.PARAMETER WarnOnly
  Print the refuse message but exit 0 instead of 2 (soft warn).

.EXAMPLE
  .\Assert-BobiverseForeignPrCheckout.ps1 -Repo SimonBarnett/a-search
.EXAMPLE
  .\Assert-BobiverseForeignPrCheckout.ps1 -Repo SimonBarnett/bobiverse -Path C:\ai\bob
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,

    [string]$Path = (Get-Location).Path,

    [switch]$WarnOnly
)

$ErrorActionPreference = 'Stop'

function Get-BobiverseNormalizedOwnerRepo {
    param([Parameter(Mandatory = $true)][string]$Raw)
    $s = $Raw.Trim()
    if ([string]::IsNullOrWhiteSpace($s)) { return $null }
    # strip scheme + host; accept git@host:owner/repo(.git) and https://host/owner/repo(.git)
    $s = $s -replace '^git@[^:]+:', ''
    $s = $s -replace '^https?://[^/]+/', ''
    $s = $s -replace '\.git$', ''
    $s = $s.Trim('/')
    if ($s -notmatch '^[^/]+/[^/]+$') { return $null }
    return $s.ToLowerInvariant()
}

$want = Get-BobiverseNormalizedOwnerRepo -Raw $Repo
if (-not $want) {
    Write-Error "Assert-BobiverseForeignPrCheckout: -Repo must be owner/name (got '$Repo')"
    exit 1
}

$root = $Path
if (-not (Test-Path -LiteralPath $root)) {
    Write-Output "Assert-BobiverseForeignPrCheckout: path missing ($root) - allow"
    exit 0
}

$gitDir = Join-Path $root '.git'
if (-not (Test-Path -LiteralPath $gitDir)) {
    Write-Output "Assert-BobiverseForeignPrCheckout: not a git work tree ($root) - allow"
    exit 0
}

$remoteUrl = $null
try {
    $remoteUrl = (& git -C $root remote get-url origin 2>$null | Select-Object -First 1)
} catch {
    $remoteUrl = $null
}
if ([string]::IsNullOrWhiteSpace($remoteUrl)) {
    Write-Output 'Assert-BobiverseForeignPrCheckout: no origin remote - allow'
    exit 0
}

$have = Get-BobiverseNormalizedOwnerRepo -Raw $remoteUrl
if (-not $have) {
    Write-Output "Assert-BobiverseForeignPrCheckout: unparseable origin ($remoteUrl) - allow"
    exit 0
}

$isBobiverseInstall = ($have -eq 'simonbarnett/bobiverse') -or ($have -match '/bobiverse$')
if (-not $isBobiverseInstall) {
    Write-Output "Assert-BobiverseForeignPrCheckout: origin $have is not bobiverse - allow"
    exit 0
}

if ($have -eq $want) {
    Write-Output "Assert-BobiverseForeignPrCheckout: same repo $want - allow"
    exit 0
}

$msg = "REFUSE (FR #4925): cwd remote is $have but -Repo is $want. Never run gh pr checkout --repo $Repo from the bob install tree ($root). Use a %TEMP% worktree/clone of the product repo instead."
Write-Warning $msg
if ($WarnOnly) {
    Write-Output 'Assert-BobiverseForeignPrCheckout: WARN-only; exit 0'
    exit 0
}
Write-Output 'Assert-BobiverseForeignPrCheckout: refuse exit 2'
exit 2
