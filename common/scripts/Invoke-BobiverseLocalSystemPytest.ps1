# FR #7103: GitHub-hosted Windows job helper. Runs pytest as LocalSystem via
# a scheduled task (not PsExec, not a self-hosted runner). Never prints tokens.
# Never creates a GitHub release.
[CmdletBinding()]
param(
    [ValidateSet('smoke', 'full')]
    [string]$Mode = 'smoke',
    [string]$RepoRoot = '',
    [string]$OutDir = '',
    [int]$TimeoutMinutes = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
if (-not $OutDir) {
    $base = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
    $OutDir = Join-Path $base 'bobiverse-localsystem-pytest'
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$py = (Get-Command python).Source
$helper = Join-Path $RepoRoot 'common\scripts\bobiverse_localsystem_ci.py'
if (-not (Test-Path -LiteralPath $helper)) { throw "missing $helper" }

$taskName = 'bobiverse-pytest-localsystem'
$wrapper = Join-Path $OutDir 'run-as-system.ps1'
$argLine = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $wrapper
@'
param()
$ErrorActionPreference = "Stop"
$envNames = @("GITHUB_TOKEN","GH_TOKEN","ACTIONS_RUNTIME_TOKEN","ACTIONS_ID_TOKEN_REQUEST_TOKEN")
foreach ($n in $envNames) { Remove-Item "Env:$n" -ErrorAction SilentlyContinue }
& python "__HELPER__" --mode __MODE__ --repo-root "__ROOT__" --out-dir "__OUT__"
exit $LASTEXITCODE
'@.Replace('__HELPER__', $helper).Replace('__MODE__', $Mode).Replace('__ROOT__', $RepoRoot).Replace('__OUT__', $OutDir) |
    Set-Content -LiteralPath $wrapper -Encoding UTF8

foreach ($n in @('GITHUB_TOKEN', 'GH_TOKEN', 'ACTIONS_RUNTIME_TOKEN')) {
    Remove-Item "Env:$n" -ErrorAction SilentlyContinue
}

try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch { }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argLine -WorkingDirectory $RepoRoot
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$limit = New-TimeSpan -Minutes ([Math]::Max($TimeoutMinutes, 5))
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit $limit -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

$summary = Join-Path $OutDir 'summary.json'
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $summary) { break }
    Start-Sleep -Seconds 3
}
try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch { }

if (-not (Test-Path -LiteralPath $summary)) {
    throw "LocalSystem pytest did not write summary.json within $TimeoutMinutes min"
}
$raw = Get-Content -LiteralPath $summary -Raw -Encoding UTF8
Write-Host $raw
$obj = $raw | ConvertFrom-Json
if (-not $obj.identity.is_localsystem) {
    throw 'scheduled task did not run as LocalSystem'
}
foreach ($s in @($obj.suites)) {
    if ([int]$s.rc -ne 0) { throw ("suite {0} rc={1}" -f $s.name, $s.rc) }
}
exit 0
