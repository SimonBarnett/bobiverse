# Start exactly one irc_agent after deterministic prior cleanup.
# Watch-Bobiverse (agentic_build tools/Watch-Bobiverse.ps1) calls this
# instead of Start-Process -WindowStyle Hidden.
# Password stays in the environment (AGENTIC_IRC_PASSWORD). It is not an argument and is not logged.
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
