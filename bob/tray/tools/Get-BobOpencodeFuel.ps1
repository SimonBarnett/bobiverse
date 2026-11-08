<#
.SYNOPSIS
  Return OpenCode fuel readings for Get-BobAgentFuel.ps1 (issue #6120).
.DESCRIPTION
  Computes opencode-free / opencode-go remaining percentages from the ``opencode stats --models``
  plain-text table, translating it into the shape expected by the shared Python helper.
  Usage is queried separately for the weekly and monthly cap windows so the most-
  restrictive window drives the fuel reading.  The 5-hour rolling cap is enforced at
  run time by the OpenCode wrapper and is not read from stats.
  When opencode is not installed, an environment fixture can supply the stats text or legacy
  JSON.  Never prints a key or credential. Exit code is always 0.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

$out = [ordered]@{
    free = $null; go = $null; models = [ordered]@{}; free_model_ids = @()
    windows = $null; limiting = $null; read_state = 'unavailable'; fetched_at = $null
    local_costs = $null; history = $null; reader = 'user'
}
try {
    $wid = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    if ($wid -and $wid.IsSystem) { $out.reader = 'service' }
} catch { }
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
        if (-not $exe) { $out.read_state = 'opencode_missing' }
        if ($exe) {
            # Plain-text model table is the only machine-readable source available.
            # OpenCode caps are rolling: 50% per week, 100% per month.  The 5-hour
            # cap is handled at run time by the OpenCode wrapper.
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
                @{ window = 'week';  args = 'stats --models --days 7' },
                @{ window = 'month'; args = 'stats --models --days 30' }
            )
            foreach ($job in $jobs) {
                $statsByWindow[$job.window] = Invoke-OpencodeTimed $job.args
            }
        }
    }

    if ($statsByWindow) {
        # FR #6159: resolve opencode_fuel.py as a FILE. Flat installs compose it to
        # <root>\scripts\opencode_fuel.py; repo checkouts keep common\scripts\.
        # Prefer scripts\ then common\scripts\ at each ancestor. An empty
        # common\scripts directory must not stop the search.
        $pyDir = $null
        $current = $PSScriptRoot
        while ($current) {
            foreach ($rel in @('scripts\opencode_fuel.py', 'common\scripts\opencode_fuel.py')) {
                $candidate = Join-Path $current $rel
                if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                    $pyDir = Split-Path -Parent $candidate
                    break
                }
            }
            if ($pyDir) { break }
            $parent = Split-Path -Parent $current
            if ($parent -eq $current) { break }
            $current = $parent
        }
        if ($pyDir) {
            $env:PYTHONPATH = "$pyDir;$env:PYTHONPATH"
        } else {
            $out.read_state = 'parser_missing'
        }
        $py = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        if (-not $py) {
            $py = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        }
        if (-not $py) {
            $out.read_state = 'parser_missing'
            $py = 'python.exe'
        }
        $script = @'
import json, sys, opencode_fuel
raw = sys.stdin.read()
windowed = json.loads(raw)
models_text = windowed.pop('models', None)
available_free = opencode_fuel.parse_opencode_models_text(models_text)
free_model_ids = opencode_fuel.parse_opencode_model_ids(models_text)
# Fixtures supplied as a single monthly/all-time window use the plain aggregator
# for backward compatibility; live multi-window data uses rolling-cap logic.
stats_keys = set(windowed.keys())
if stats_keys == {'month'}:
    stats = opencode_fuel.parse_opencode_stats_text_or_json(windowed['month'])
    stats['free_models'] = list(dict.fromkeys(stats.get('free_models', []) + available_free))
    stats['free_model_ids'] = list(dict.fromkeys(stats.get('free_model_ids', []) + free_model_ids))
    print(json.dumps(opencode_fuel.fuel_from_stats(stats)))
else:
    parsed = {}
    for k, v in windowed.items():
        s = opencode_fuel.parse_opencode_stats_text_or_json(v)
        s['free_models'] = list(dict.fromkeys(s.get('free_models', []) + available_free))
        s['free_model_ids'] = list(dict.fromkeys(s.get('free_model_ids', []) + free_model_ids))
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
            if ($parsed.free_model_ids) {
                $out.free_model_ids = @($parsed.free_model_ids)
            }
            # FR #6147: pass through Go rolling/weekly/monthly window records + limiting id.
            if ($parsed.windows) { $out.windows = $parsed.windows }
            if ($null -ne $parsed.limiting -and [string]$parsed.limiting -ne '') {
                $out.limiting = [string]$parsed.limiting
            }
            if ($parsed.local_costs) { $out.local_costs = $parsed.local_costs }
            if ($parsed.history) { $out.history = $parsed.history }
            $out.read_state = 'ok'
            if ($env:BOB_OPENCODE_USAGE_URL) {
                # Configured provider read must not fall back to stats windows.
                $out.go = $null
                $out.limiting = $null
                $env:BOB_OPENCODE_PROVIDER_PREVIOUS = ''
                try {
                    $prevCache = $env:BOB_OPENCODE_FUEL_CACHE_FILE
                    if (-not $prevCache) {
                        $prevRoot = $env:BOB_INSTALL_ROOT
                        if (-not $prevRoot) { $prevRoot = Split-Path -Parent $PSScriptRoot }
                        $prevCache = Join-Path (Join-Path $prevRoot 'run') 'opencode-fuel.json'
                    }
                    if (Test-Path -LiteralPath $prevCache -PathType Leaf) {
                        $prevDoc = [System.IO.File]::ReadAllText($prevCache) | ConvertFrom-Json
                        $providerPrev = $false
                        foreach ($id in @('rolling', 'week', 'month')) {
                            $rec = $null
                            try { $rec = $prevDoc.windows.$id } catch { $rec = $null }
                            if ($rec -and [string]$rec.source -eq 'provider') { $providerPrev = $true }
                        }
                        if ($providerPrev -and $prevDoc.windows) {
                            $env:BOB_OPENCODE_PROVIDER_PREVIOUS = ($prevDoc.windows | ConvertTo-Json -Compress -Depth 6)
                        }
                    }
                } catch { $env:BOB_OPENCODE_PROVIDER_PREVIOUS = '' }
                # Single-quoted Python literals only: Windows PowerShell 5.1 strips
                # embedded " when -c is a native argument (same contract as $script above).
                $limitsScript = @'
import json, os, opencode_fuel
prev = None
raw = os.environ.get('BOB_OPENCODE_PROVIDER_PREVIOUS') or ''
if raw.strip():
    try:
        prev = json.loads(raw)
    except json.JSONDecodeError:
        prev = None
read = opencode_fuel.fetch_usage_limits(
    os.environ.get('BOB_OPENCODE_USAGE_URL') or '',
    os.environ.get('OPENCODE_SERVER_PASSWORD') or None,
    os.environ.get('OPENCODE_SERVER_USERNAME') or None,
)
windows = opencode_fuel.windows_from_usage_read(read, previous=prev)
print(json.dumps({'provider_read': read.get('kind'), 'windows': windows}))
'@
                $limitsRaw = $null
                try { $limitsRaw = & $py -c $limitsScript } catch { $limitsRaw = $null }
                $env:BOB_OPENCODE_PROVIDER_PREVIOUS = ''
                $limits = $null
                if ($limitsRaw) {
                    try { $limits = $limitsRaw | ConvertFrom-Json } catch { $limits = $null }
                }
                $unknownProvider = { [ordered]@{ status = 'unknown'; used_pct = $null; remaining_pct = $null; reset_label = $null; source = 'provider' } }
                $readWindows = $null
                try { $readWindows = $limits.windows } catch { $readWindows = $null }
                if ($readWindows -and ($readWindows.rolling -or $readWindows.week -or $readWindows.month)) {
                    $out.windows = $readWindows
                } else {
                    $out.windows = [ordered]@{
                        rolling = (& $unknownProvider)
                        week    = (& $unknownProvider)
                        month   = (& $unknownProvider)
                    }
                }
                $kind = ''
                try { if ($limits.provider_read) { $kind = [string]$limits.provider_read } } catch { $kind = '' }
                if (-not $kind) { $kind = 'unavailable' }
                $out.provider_read = $kind
                $out.provider = 'usage-limits'
            }
        } elseif ($out.read_state -eq 'unavailable') {
            $out.read_state = 'parser_missing'
        }
    }
} catch { }
if (-not $out.windows) {
    # No stats document. Do not call rolling "Starts on first use" — that is only
    # honest after a completed stats read. opencode has no remaining-quota API
    # and stats does not return the 5-hour window or a reset time.
    $unknownWindow = { [ordered]@{ status = 'unknown'; used_pct = $null; remaining_pct = $null; reset_label = $null } }
    $out.windows = [ordered]@{
        rolling = (& $unknownWindow)
        week    = (& $unknownWindow)
        month   = (& $unknownWindow)
    }
}
$out.fetched_at = [DateTime]::UtcNow.ToString('o')
$json = $out | ConvertTo-Json -Compress -Depth 6
try {
    $cache = $env:BOB_OPENCODE_FUEL_CACHE_FILE
    if (-not $cache) {
        $root = $env:BOB_INSTALL_ROOT
        if (-not $root) { $root = Split-Path -Parent $PSScriptRoot }
        $run = Join-Path $root 'run'
        if (-not (Test-Path -LiteralPath $run)) { New-Item -ItemType Directory -Force -Path $run | Out-Null }
        $cache = Join-Path $run 'opencode-fuel.json'
    }
    $keepExisting = $false
    $emptyNow = $false
    try { if ($out.history -and $out.history.empty) { $emptyNow = $true } } catch { }
    $refuseEmpty = ([string]$out.read_state -ne 'ok') -or $emptyNow
    if ($refuseEmpty -and (Test-Path -LiteralPath $cache -PathType Leaf)) {
        try {
            $prev = [System.IO.File]::ReadAllText($cache) | ConvertFrom-Json
            foreach ($id in @('rolling', 'week', 'month')) {
                $rec = $null
                try { $rec = $prev.windows.$id } catch { $rec = $null }
                if (-not $rec) { continue }
                $st = ''
                try { $st = [string]$rec.status } catch { }
                if ($st -and $st -ne 'unknown') { $keepExisting = $true }
                if ($null -ne $rec.remaining_pct -and [string]$rec.remaining_pct -ne '') { $keepExisting = $true }
            }
            foreach ($k in @('free', 'go', 'opencode-free', 'opencode-go')) {
                $v = $null
                try { $v = $prev.$k } catch { $v = $null }
                if ($null -ne $v -and [string]$v -ne '') { $keepExisting = $true }
            }
            if ($emptyNow) {
                $prevSessions = 0
                try { if ($prev.history -and $null -ne $prev.history.sessions) { $prevSessions = [int]$prev.history.sessions } } catch { }
                $prevCosts = $false
                try { if ($prev.local_costs) { $prevCosts = $true } } catch { }
                if ($prevSessions -gt 0 -or $prevCosts) { $keepExisting = $true }
            }
        } catch { }
    }
    if (-not $keepExisting) {
        $tmp = $cache + '.tmp'
        $cacheDir = Split-Path -Parent $cache
        if ($cacheDir -and -not (Test-Path -LiteralPath $cacheDir)) { New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null }
        [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding $false))
        if (Test-Path -LiteralPath $cache) {
            [System.IO.File]::Replace($tmp, $cache, [NullString]::Value)
        } else {
            [System.IO.File]::Move($tmp, $cache)
        }
    }
} catch { }
[Console]::Out.WriteLine($json)
exit 0
