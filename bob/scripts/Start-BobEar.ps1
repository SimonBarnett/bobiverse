# Start exactly one irc_agent after deterministic prior cleanup.
# Watch-Bobiverse (agentic_build tools/Watch-Bobiverse.ps1) calls this
# instead of Start-Process -WindowStyle Hidden.
# Password stays in the environment (BOB_IRC_PASSWORD). It is not an argument and is not logged.
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$AgentPath,
    [Parameter(Mandatory = $true)][string]$Nick,
    [Parameter(Mandatory = $true)][string]$Home,
    [Parameter(Mandatory = $true)][string]$IrcHost,
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][string]$Channel,
    [string]$WorkingDirectory = '',
    [string[]]$ExtraArg = @()
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'IrcProcess.ps1')
# FR #9861: do not Start-Process a second ear while one already holds this --home
# (NSSM/service path uses bob-ear.exe; this helper is Watch-Bobiverse / python path).
$homeNorm = [string]$Home
if ($homeNorm) {
  $alive = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $cl = [string]($_.CommandLine)
    if (-not $cl) { return $false }
    if ($cl -notmatch '(?i)(bob-ear\.exe|irc_agent\.py)') { return $false }
    $escaped = [regex]::Escape($homeNorm.TrimEnd('\'))
    # Single-quoted pattern: character class for optional " or ' (ParseFile-safe).
    $homePat = ('(?i)--home\s+["'']?{0}["'']?' -f $escaped)
    return $cl -match $homePat
  })
  if ($alive.Count -gt 0) {
    Write-Output ("ERROR ear already running for home=$Home pids={0} (FR #9861); refusing second start" -f (($alive | ForEach-Object { $_.ProcessId }) -join ','))
    exit 3
  }
}
$prior = Join-Path $PSScriptRoot 'prior_irc.py'
Invoke-PriorIrcClean -Python $Python -ScriptPath $prior -Nick $Nick -Home $Home
$argList = @(
    '-u', $AgentPath,
    '--host', $IrcHost,
    '--port', "$Port",
    '--nick', $Nick,
    '--channel', $Channel,
    '--home', $Home
)
if ($ExtraArg) { $argList += $ExtraArg }
$procId = Start-HiddenPython -Python $Python -ArgumentList $argList -WorkingDirectory $WorkingDirectory
Write-Output "INFO started irc_agent pid=$procId nick=$Nick"
