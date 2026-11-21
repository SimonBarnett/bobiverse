# FR #8765: fail closed when changed/staged BOM-less *.ps1 carry non-ASCII.
# Cheap pre-push / seat check; CI still runs pytest-ascii-bom (FR #3391 / #3975).
[CmdletBinding()]
param(
    [string] $RepoRoot = '',
    [switch] $Staged,
    [switch] $AllTracked
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
}
$py = Join-Path $PSScriptRoot 'bobiverse_ps1_ascii.py'
if (-not (Test-Path -LiteralPath $py)) {
    throw "bobiverse_ps1_ascii.py missing at $py"
}
$python = $null
foreach ($c in @('python', 'py')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) { throw 'python not found for Assert-BobiverseChangedPs1Ascii' }

$paths = @()
if ($AllTracked) {
    & $python $py check --repo $RepoRoot
    exit $LASTEXITCODE
}

$diffArgs = @('diff', '--name-only')
if ($Staged) { $diffArgs = @('diff', '--cached', '--name-only') }
else { $diffArgs += @('HEAD') }

Push-Location -LiteralPath $RepoRoot
try {
    $names = & git @diffArgs 2>$null
} finally {
    Pop-Location
}
foreach ($n in $names) {
    if ($n -and $n -match '\.ps1$') {
        $full = Join-Path $RepoRoot ($n -replace '/', '\')
        if (Test-Path -LiteralPath $full) { $paths += $full }
    }
}
if ($paths.Count -eq 0) {
    Write-Host 'PS1_ASCII_OK count=0 (no changed *.ps1)'
    exit 0
}
$argList = @($py, 'check')
foreach ($p in $paths) { $argList += @('--path', $p) }
& $python @argList
exit $LASTEXITCODE
