<#
.SYNOPSIS
  Run bobcallback.py in a restart loop (FR #1455).

.DESCRIPTION
  The BobCallback scheduled task is ONSTART + Interactive. When the python process
  exits (kill, wedge recycle, lock fight), the task goes Ready and does not come
  back until the next boot or a manual Start. This wrapper keeps :7700 up by
  restarting bobcallback after a short delay until the task is stopped.
#>
[CmdletBinding()]
param(
    [string]$Python = 'C:\Python\Python312\python.exe',
    [string]$ScriptPath = '',
    [string]$DigestHome = '',
    [string]$Bind = '127.0.0.1',
    [int]$Port = 7700,
    [int]$RestartDelaySec = 3
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptPath) {
    $ScriptPath = Join-Path $here 'bobcallback.py'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "bobcallback.py not found: $ScriptPath"
}
if (-not $DigestHome) {
    $DigestHome = $env:BOB_DIGEST_HOME
}
if (-not $DigestHome) {
    $DigestHome = Join-Path $env:USERPROFILE '.bobiverse'
}
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = 'python'
}

$argList = @('-u', $ScriptPath, '--home', $DigestHome, '--bind', $Bind, '--port', "$Port")
Write-Host ("INFO supervised bobcallback python={0} script={1} home={2} port={3}" -f $Python, $ScriptPath, $DigestHome, $Port)

while ($true) {
    $p = Start-Process -FilePath $Python -ArgumentList $argList -PassThru -WindowStyle Hidden
    Write-Host ("INFO bobcallback started pid={0}" -f $p.Id)
    Wait-Process -Id $p.Id
    $code = $p.ExitCode
    Write-Host ("WARN bobcallback exited pid={0} code={1}; restart in {2}s" -f $p.Id, $code, $RestartDelaySec)
    Start-Sleep -Seconds $RestartDelaySec
}
