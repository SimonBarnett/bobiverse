<#
.SYNOPSIS
  Return OpenCode fuel readings for Get-BobAgentFuel.ps1 (issue #6120).
.DESCRIPTION
  Computes opencode-free / opencode-go remaining percentages from the ``opencode stats --models``
  plain-text table, translating it into the shape expected by the shared Python helper.
  When opencode is not installed, an environment fixture can supply the stats text or legacy
  JSON.  Never prints a key or credential. Exit code is always 0.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

$out = [ordered]@{ free = $null; go = $null; models = [ordered]@{} }
try {
    $statsRaw = $null
    $fixture = $env:BOB_OPENCODE_FUEL_FIXTURE
    if ($fixture) {
        $statsRaw = $fixture
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
            # Plain-text model table is the only machine-readable source available.
            $raw = & $exe stats --models 2>$null
            if ($raw) { $statsRaw = [string]($raw | Out-String) }
        }
    }

    if ($statsRaw) {
        # PYTHONPATH must point at the repository-level common/scripts, not bob/common/scripts.
        $repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
        $common = Join-Path $repoRoot 'common\scripts'
        $env:PYTHONPATH = "$common;$env:PYTHONPATH"
        $py = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        if (-not $py) { $py = 'python.exe' }
        $script = @'
import json, sys, opencode_fuel
raw = sys.stdin.read()
stats = opencode_fuel.parse_opencode_stats_text_or_json(raw)
print(json.dumps(opencode_fuel.fuel_from_stats(stats)))
'@
        # Pass stats text via stdin: Windows PowerShell 5.1 can strip embedded quotes when
        # they are passed as a native argument, which breaks parsing.
        $result = $statsRaw | & $py -c $script
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
