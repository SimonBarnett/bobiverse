<#
.SYNOPSIS
  Return OpenCode fuel readings for Get-BobAgentFuel.ps1 (issue #6120).
.DESCRIPTION
  Computes opencode-free / opencode-go remaining percentages from a stats document.
  When opencode is not installed, an environment fixture can supply the stats JSON.
  Never prints a key or credential. Exit code is always 0.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

$out = [ordered]@{ free = $null; go = $null; models = [ordered]@{} }
try {
    $statsJson = $null
    $fixture = $env:BOB_OPENCODE_FUEL_FIXTURE
    if ($fixture) {
        $statsJson = $fixture
    } else {
        $exe = $env:BOB_OPENCODE_EXE
        if (-not $exe) {
            $winget = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\opencode.exe'
            if (Test-Path -LiteralPath $winget) { $exe = $winget }
        }
        if (-not $exe) {
            $exe = (Get-Command opencode.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        }
        if (-not $exe) {
            $exe = (Get-Command opencode -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        }
        if ($exe) {
            # Try JSON stats first; fall back to plain text.
            $raw = & $exe stats --output json 2>$null
            if (-not $raw) { $raw = & $exe stats 2>$null }
            if ($raw) { $statsJson = [string]($raw | Out-String) }
        }
    }

    if ($statsJson) {
        # Use the Python helper so caps/fallback logic is shared with the worker.
        $common = Join-Path (Split-Path -Parent $PSScriptRoot) '..\common\scripts'
        $env:PYTHONPATH = "$common;$env:PYTHONPATH"
        $py = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        if (-not $py) { $py = 'python.exe' }
        $script = @'
import json, sys, opencode_fuel
try:
    stats = json.loads(sys.argv[1]) if sys.argv[1] else {}
except Exception:
    stats = {}
print(json.dumps(opencode_fuel.fuel_from_stats(stats)))
'@
        $result = & $py -c $script $statsJson
        if ($result) {
            $parsed = $result | ConvertFrom-Json -ErrorAction Stop
            if ($parsed.'opencode-free' -ne $null) { $out.free = [int]$parsed.'opencode-free' }
            if ($parsed.'opencode-go' -ne $null) { $out.go = [int]$parsed.'opencode-go' }
            if ($parsed.models) {
                $parsed.models | Get-Member -MemberType NoteProperty | ForEach-Object {
                    $out.models[$_.Name] = [int]$parsed.models.($_.Name)
                }
            }
        }
    }
} catch { }
[Console]::Out.WriteLine(($out | ConvertTo-Json -Compress -Depth 5))
exit 0
