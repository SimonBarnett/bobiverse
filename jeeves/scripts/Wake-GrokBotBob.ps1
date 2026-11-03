<#
.SYNOPSIS
  FR #6066: wake Grok Bot Bob (SendGrokBotUserMessage). Not chair !assign.
.DESCRIPTION
  Runs on Bob's Grok Bot desktop (require_machine = BOB_GROK_BOT_WAKE_MACHINE).
  Detection may run on ionos; this script is the LOCKED wake host adapter.
  Never prints tokens or sandbox URLs.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Repo,
    [Parameter(Mandatory)][string]$Number,
    [string]$Event = 'closed',
    [string]$Kind = 'issue',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSScriptRoot
$py = Join-Path $here 'tools\monitor\wake_grok_bot_bob.py'
if (-not (Test-Path -LiteralPath $py)) { Write-Error "missing $py"; exit 2 }
$python = $null
foreach ($c in @('python.exe', 'py.exe')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) { Write-Error 'python.exe not found'; exit 2 }
$argv = @($py, '--repo', $Repo, '--number', $Number, '--event', $Event, '--kind', $Kind)
if ($DryRun) { $argv += '--dry-run' }
& $python @argv
exit $LASTEXITCODE
