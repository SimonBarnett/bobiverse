<#
.SYNOPSIS
  Run bobcallback.py in a restart loop (FR #1455 / MRB #1462 / FR #1767).

.DESCRIPTION
  The BobCallback scheduled task is ONSTART + Interactive. When the python process
  exits (kill, wedge recycle, lock fight), the task goes Ready and does not come
  back until the next boot or a manual Start. This wrapper keeps :7700 up by
  restarting bobcallback after a short delay until the task is stopped.

  On wrapper exit (Stop-ScheduledTask / Ctrl+C), the child python is stopped so
  it is not left orphaned without a supervisor.

  FR #1767 / #1831: only one supervised parent may own the loop. A second launch
  (monitor Start-Process heal race, Register fallback while task already running)
  exits 0 immediately so digest.lock fights and INTAKE 502 flaps stop.
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

function Get-BobCallbackSupervisedParentIds {
    <#
    .SYNOPSIS
      PIDs of PowerShell processes whose command line runs Start-BobCallbackSupervised.ps1.
      ExcludeCurrentPid: skip $PID (heal shells matching the script name).
    #>
    param([switch]$ExcludeCurrentPid)
    $ids = @()
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" -ErrorAction SilentlyContinue
        foreach ($p in @($procs)) {
            $cmd = [string]$p.CommandLine
            if (-not $cmd) { continue }
            if ($cmd -notmatch 'Start-BobCallbackSupervised\.ps1') { continue }
            if ($ExcludeCurrentPid -and [int]$p.ProcessId -eq $PID) { continue }
            $ids += [int]$p.ProcessId
        }
    } catch { }
    return @($ids | Select-Object -Unique)
}

# FR #1767: refuse a second Wait-Process parent (digest.lock fight / INTAKE 502).
$others = @(Get-BobCallbackSupervisedParentIds -ExcludeCurrentPid)
if ($others.Count -ge 1) {
    Write-Host ("WARN refuse second Start-BobCallbackSupervised; already running pid(s)={0} (FR #1767)" -f ($others -join ','))
    exit 0
}

$argList = @('-u', $ScriptPath, '--home', $DigestHome, '--bind', $Bind, '--port', "$Port")
Write-Host ("INFO supervised bobcallback python={0} script={1} home={2} port={3}" -f $Python, $ScriptPath, $DigestHome, $Port)

$script:Child = $null
function Stop-BobCallbackChild {
    if ($null -eq $script:Child) { return }
    try {
        if (-not $script:Child.HasExited) {
            Stop-Process -Id $script:Child.Id -Force -ErrorAction SilentlyContinue
            Write-Host ("INFO stopped orphan bobcallback pid={0}" -f $script:Child.Id)
        }
    } catch { }
    $script:Child = $null
}

trap {
    Stop-BobCallbackChild
    break
}

try {
    while ($true) {
        $script:Child = Start-Process -FilePath $Python -ArgumentList $argList -PassThru -WindowStyle Hidden
        Write-Host ("INFO bobcallback started pid={0}" -f $script:Child.Id)
        Wait-Process -Id $script:Child.Id
        $code = $script:Child.ExitCode
        Write-Host ("WARN bobcallback exited pid={0} code={1}; restart in {2}s" -f $script:Child.Id, $code, $RestartDelaySec)
        $script:Child = $null
        Start-Sleep -Seconds $RestartDelaySec
    }
}
finally {
    Stop-BobCallbackChild
}
