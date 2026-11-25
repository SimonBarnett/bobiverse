<#
.SYNOPSIS
  FR #9880 helper: list active held lessons fr-digest children vs session findings.
.DESCRIPTION
  Thin wrapper around tools\monitor\lessons_digest_harvest.py (checklist 9830_harvest).
  Resolves the active OPEN+held lessons digest (env / detection / documented default #9830),
  lists open Depends-on children, and EXIT 1 when -FindingsPath entries are unfiled.
.PARAMETER FindingsPath
  JSON list of {title,fingerprint,body} session findings (also via env JEEVES_LESSONS_SESSION_FINDINGS).
.PARAMETER Digest
  Override digest as N or owner/repo#N (env JEEVES_LESSONS_DIGEST / BOB_LESSONS_DIGEST).
.PARAMETER FixturePath
  Offline fixture JSON (env JEEVES_LESSONS_DIGEST_FIXTURE).
#>
[CmdletBinding()]
param(
    [string]$FindingsPath = '',
    [string]$Digest = '',
    [string]$FixturePath = '',
    [string]$InstallRoot = '',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$here = if ($InstallRoot) { $InstallRoot } else { Split-Path -Parent $PSScriptRoot }
$py = Join-Path $here 'tools\monitor\lessons_digest_harvest.py'
if (-not (Test-Path -LiteralPath $py)) {
    Write-Error "missing $py"
    exit 2
}
if ($FindingsPath) { $env:JEEVES_LESSONS_SESSION_FINDINGS = $FindingsPath }
if ($Digest) { $env:JEEVES_LESSONS_DIGEST = $Digest }
if ($FixturePath) { $env:JEEVES_LESSONS_DIGEST_FIXTURE = $FixturePath }
$python = $null
foreach ($c in @('python.exe', 'py.exe')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) { Write-Error 'python.exe not found'; exit 2 }
$argv = @($py)
if ($DryRun) { $argv += '--dry-run' }
& $python @argv
exit $LASTEXITCODE
