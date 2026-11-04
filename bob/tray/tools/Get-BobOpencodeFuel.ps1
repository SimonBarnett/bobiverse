<#
.SYNOPSIS
  Return OpenCode fuel readings for Get-BobAgentFuel.ps1 (issue #6120).
.DESCRIPTION
  Computes opencode-free / opencode-go remaining percentages from the ``opencode stats --models``
  plain-text table, translating it into the shape expected by the shared Python helper.
  Usage is queried separately for the rolling 5-hour, weekly and monthly cap windows so
  the most-restrictive window drives the fuel reading.
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
    $fixture = $env:BOB_OPENCODE_FUEL_FIXTURE
    $statsByWindow = $null
    if ($fixture) {
        # Fixtures are treated as the monthly/all-time window for backward compatibility.
        $statsByWindow = @{ month = $fixture }
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
            # OpenCode caps are rolling: 20% per 5h, 50% per week, 100% per month.
            $days5h = [math]::Round(5 / 24, 6)
            $statsByWindow = @{}

            function Invoke-OpencodeTimed($arguments) {
                $stdout = $null
                $proc = $null
                try {
                    $psi = New-Object System.Diagnostics.ProcessStartInfo
                    $psi.FileName = $exe
                    $psi.Arguments = $arguments
                    $psi.RedirectStandardOutput = $true
                    $psi.RedirectStandardError = $true
                    $psi.UseShellExecute = $false
                    $psi.CreateNoWindow = $true
                    $proc = [System.Diagnostics.Process]::Start($psi)
                    # Start draining stdout/stderr before waiting so a full pipe
                    # cannot deadlock the child before the 25 s timeout expires.
                    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
                    $stderrTask = $proc.StandardError.ReadToEndAsync()
                    if ($proc.WaitForExit(25000)) {
                        $stdout = [string]($stdoutTask.Result)
                        [void]($stderrTask.Result)
                    } else {
                        # Timed out: kill the whole OpenCode process tree and leave this
                        # window unknown so the helper still produces JSON.
                        try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { }
                        $stdout = $null
                    }
                } catch {
                    $stdout = $null
                } finally {
                    if ($proc -and -not $proc.HasExited) {
                        try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { }
                    }
                    if ($proc) { try { $proc.Dispose() } catch { } }
                }
                return $stdout
            }

            # Discover free-model availability from the catalogue (not recorded usage).
            $modelsOutput = Invoke-OpencodeTimed 'models'

            $jobs = @(
                @{ window = '5h';    args = "stats --models --days $days5h" },
                @{ window = 'week';  args = 'stats --models --days 7' },
                @{ window = 'month'; args = 'stats --models --days 30' }
            )
            foreach ($job in $jobs) {
                $statsByWindow[$job.window] = Invoke-OpencodeTimed $job.args
            }
        }
    }

    if ($statsByWindow) {
        # Resolve common\scripts from either a repo checkout (bob\tray\tools) or an
        # installed layout (<ai root>\bob\tools), keeping the lookup inside the bob work tree.
        $common = $null
        $current = $PSScriptRoot
        while ($current) {
            $candidate = Join-Path $current 'common\scripts'
            if (Test-Path -LiteralPath $candidate -PathType Container) {
                $common = $candidate
                break
            }
            $parent = Split-Path -Parent $current
            if ($parent -eq $current) { break }
            $current = $parent
        }
        if ($common -and (Test-Path -LiteralPath $common -PathType Container)) {
            $env:PYTHONPATH = "$common;$env:PYTHONPATH"
        }
        $py = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        if (-not $py) { $py = 'python.exe' }
        $script = @'
import json, sys, opencode_fuel
raw = sys.stdin.read()
windowed = json.loads(raw)
models_text = windowed.pop('models', None)
available_free = opencode_fuel.parse_opencode_models_text(models_text)
# Fixtures supplied as a single monthly/all-time window use the plain aggregator
# for backward compatibility; live multi-window data uses rolling-cap logic.
stats_keys = set(windowed.keys())
if stats_keys == {'month'}:
    stats = opencode_fuel.parse_opencode_stats_text_or_json(windowed['month'])
    stats['free_models'] = list(dict.fromkeys(stats.get('free_models', []) + available_free))
    print(json.dumps(opencode_fuel.fuel_from_stats(stats)))
else:
    parsed = {}
    for k, v in windowed.items():
        s = opencode_fuel.parse_opencode_stats_text_or_json(v)
        s['free_models'] = list(dict.fromkeys(s.get('free_models', []) + available_free))
        parsed[k] = s
    print(json.dumps(opencode_fuel.fuel_from_windowed_stats(parsed)))
'@
        # Pass stats text via stdin: Windows PowerShell 5.1 can strip embedded quotes when
        # they are passed as a native argument, which breaks parsing.
        $payload = (@{ models = $modelsOutput } + $statsByWindow) | ConvertTo-Json -Compress -Depth 3
        $result = $payload | & $py -c $script
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
