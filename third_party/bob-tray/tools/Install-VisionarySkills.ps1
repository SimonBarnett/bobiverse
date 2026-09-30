# Sync SimonBarnett/skills-visionary into a local sister clone and copy
# .grok/skills/*/SKILL.md into ~/.grok/skills (same pattern as Copy-BobProjectSkills /
# mud skill-book installs). Used by Bob Fleet tray Plan (top-level menu) starts.
# Never commits. Never starts IRC / Watch-Bobiverse / Start-BobBuild.
[CmdletBinding()]
param(
    [string]$CloneRoot,
    [switch]$Pull
)

$ErrorActionPreference = 'Stop'

function Resolve-BobVisionaryCloneParent {
    foreach ($c in @('D:\ai', 'C:\ai', 'C:\src')) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $fallback = 'D:\ai'
    New-Item -ItemType Directory -Force -Path $fallback | Out-Null
    return $fallback
}

function Resolve-BobVisionaryCloneRoot {
    param([string]$Hint)
    $candidates = @()
    if ($Hint) { $candidates += $Hint }
    $candidates += @(
        'D:\ai\skills-visionary',
        'C:\ai\skills-visionary',
        'C:\src\skills-visionary'
    )
    foreach ($c in $candidates) {
        $skill = Join-Path $c '.grok\skills\visionary\SKILL.md'
        if (Test-Path -LiteralPath $skill) { return [IO.Path]::GetFullPath($c) }
    }
    return $null
}

function Invoke-BobVisionaryGit {
    # Windows PowerShell 5.1 + $ErrorActionPreference = 'Stop': when a native command's stderr is
    # redirected (2>$null / 2>&1), EVERY stderr line becomes a terminating NativeCommandError.
    # git writes progress/info to stderr on success ("From https://github.com/..." on every
    # `git pull origin main`), so tray Plan died with "Install-VisionarySkills failed (exit 1)".
    # Run git with Continue, capture the text, and return git's real exit code.
    param([string[]]$GitArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& git @GitArgs 2>&1 | ForEach-Object { [string]$_ })
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prev
    }
    return [pscustomobject]@{ Code = $code; Lines = $lines }
}

function Get-BobVisionaryGitReason([object]$Result) {
    $first = @($Result.Lines | Where-Object { $_ -match '\S' } | Select-Object -First 1)
    if ($first.Count) { return ([string]$first[0]).Trim() }
    return 'no output'
}

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) { throw 'git not found (required to sync skills-visionary)' }

$root = Resolve-BobVisionaryCloneRoot -Hint $CloneRoot
$cloned = $false
$pulled = $false
$pullWarning = $null
if (-not $root) {
    $parent = Resolve-BobVisionaryCloneParent
    $root = Join-Path $parent 'skills-visionary'
    Write-Host ("clone:   https://github.com/SimonBarnett/skills-visionary -> {0}" -f $root)
    $cl = Invoke-BobVisionaryGit -GitArgs @('clone', '--depth', '1', 'https://github.com/SimonBarnett/skills-visionary.git', $root)
    if ($cl.Code -ne 0) { throw ("git clone skills-visionary failed (exit {0}): {1}" -f $cl.Code, (Get-BobVisionaryGitReason $cl)) }
    $cloned = $true
}
elseif ($Pull) {
    $st = Invoke-BobVisionaryGit -GitArgs @('-C', $root, 'status', '--porcelain')
    if ($st.Code -ne 0) {
        $pullWarning = ("git status failed (exit {0}): {1}" -f $st.Code, (Get-BobVisionaryGitReason $st))
    }
    elseif (@($st.Lines | Where-Object { $_ -match '\S' }).Count -gt 0) {
        Write-Host 'git: dirty skills-visionary tree, skipped pull'
    }
    else {
        $pl = Invoke-BobVisionaryGit -GitArgs @('-C', $root, 'pull', '--ff-only', 'origin', 'main')
        $pulled = ($pl.Code -eq 0)
        if (-not $pulled) { $pullWarning = ("git pull failed (exit {0}): {1}" -f $pl.Code, (Get-BobVisionaryGitReason $pl)) }
    }
    # An existing clone still has the skill book: warn and keep going (offline / non-ff / auth).
    if ($pullWarning) { Write-Host ("warning: {0}; using existing skills-visionary copy" -f $pullWarning) }
}

$skillRoot = Join-Path $root '.grok\skills'
if (-not (Test-Path -LiteralPath $skillRoot)) {
    throw "skills-visionary missing .grok/skills at $root"
}
$skillDstRoot = Join-Path $env:USERPROFILE '.grok\skills'
$copied = @()
foreach ($dir in @(Get-ChildItem -LiteralPath $skillRoot -Directory -ErrorAction SilentlyContinue)) {
    $src = Join-Path $dir.FullName 'SKILL.md'
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dstDir = Join-Path $skillDstRoot $dir.Name
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
    Copy-Item -LiteralPath $src -Destination (Join-Path $dstDir 'SKILL.md') -Force
    $copied += $dir.Name
}

$rp = Invoke-BobVisionaryGit -GitArgs @('-C', $root, 'rev-parse', 'HEAD')
$sha = if ($rp.Code -eq 0 -and $rp.Lines.Count) { ([string]$rp.Lines[0]).Trim() } else { $null }
Write-Host ("repo:    {0}" -f $root)
Write-Host ("HEAD:    {0}" -f $(if ($sha) { $sha } else { 'n/a' }))
Write-Host ("cloned:  {0}" -f $cloned)
Write-Host ("pulled:  {0}" -f $pulled)
Write-Host ("skills:  {0}" -f ($(if ($copied.Count) { ($copied | Sort-Object) -join ', ' } else { '(none)' })))
Write-Host ("dst:     {0}" -f $skillDstRoot)

[pscustomobject]@{
    ok     = $true
    repo   = $root
    sha    = $sha
    cloned = $cloned
    pulled = $pulled
    warning = $pullWarning
    skills = @($copied | Sort-Object)
}
