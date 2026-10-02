function Get-BobFuelModelConfig {
    $bundled = Join-Path (Get-ModuleRoot) 'config\default.json'
    $cfg = $null
    try { $cfg = Read-JsonFile $bundled } catch { }
    $fuelMap = @{}
    $families = @{}
    if ($cfg) {
        if ($cfg.fuelModelFamilies) {
            foreach ($p in $cfg.fuelModelFamilies.PSObject.Properties) {
                $fuelMap[[string]$p.Name] = [string]$p.Value
            }
        }
        if ($cfg.modelFamilies) {
            foreach ($p in $cfg.modelFamilies.PSObject.Properties) {
                $families[[string]$p.Name] = @($p.Value)
            }
        }
    }
    if ($fuelMap.Count -eq 0) {
        $fuelMap['cursor-models'] = 'cursor'
        $fuelMap['grok-build'] = 'grok'
        $fuelMap['grok-bot'] = 'grok'
        $fuelMap['on-demand'] = 'grok'
        $fuelMap['copilot'] = 'none'
    }
    if ($families.Count -eq 0) {
        $families['cursor'] = @('^composer-', '^claude-', '^gpt-', '^cursor-', '^muse-', '^grok-4\.')
        $families['grok'] = @('^grok-', '^build0\.1$', '(?i)^grok-build-', '^build-0\.1$')
        $families['none'] = @()
    }
    return [pscustomobject]@{ fuelModelFamilies = $fuelMap; modelFamilies = $families }
}

function Test-BobPacketMissingFuel {
    [CmdletBinding()]
    param(
        [string]$Fuel,
        [string]$Model
    )
    $fuel = [string]$Fuel
    if ($fuel) {
        return [pscustomobject]@{ ok = $true; summary = $null }
    }
    $model = [string]$Model
    if ([string]::IsNullOrWhiteSpace($model)) {
        return [pscustomobject]@{
            ok      = $false
            summary = 'missing_fuel_and_model'
        }
    }
    return [pscustomobject]@{
        ok      = $false
        summary = "missing_fuel model=$model"
    }
}

function Test-BobFuelModelCompatible {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Fuel,
        [string]$Model
    )
    $fuel = [string]$Fuel
    if (-not $fuel) {
        return [pscustomobject]@{ ok = $true; summary = $null }
    }
    $cfg = Get-BobFuelModelConfig
    $family = $cfg.fuelModelFamilies[$fuel]
    if (-not $family) {
        return [pscustomobject]@{
            ok      = $false
            summary = "fuel_model_mismatch unknown fuel=$fuel model=$Model"
        }
    }
    $model = [string]$Model
    if ([string]::IsNullOrWhiteSpace($model)) {
        return [pscustomobject]@{ ok = $true; summary = $null }
    }
    if ($family -eq 'none') {
        return [pscustomobject]@{
            ok      = $false
            summary = "fuel_model_mismatch fuel=$fuel model=$model (copilot takes no model)"
        }
    }
    $patterns = @($cfg.modelFamilies[$family])
    if (-not $patterns -or $patterns.Count -eq 0) {
        return [pscustomobject]@{
            ok      = $false
            summary = "fuel_model_mismatch fuel=$fuel model=$model (no patterns for family $family)"
        }
    }
    foreach ($pat in $patterns) {
        if ([string]::IsNullOrWhiteSpace($pat)) { continue }
        if ($model -match [string]$pat) {
            return [pscustomobject]@{ ok = $true; summary = $null }
        }
    }
    return [pscustomobject]@{
        ok      = $false
        summary = "fuel_model_mismatch fuel=$fuel model=$model"
    }
}

function Get-BobJobModel {
    [CmdletBinding()]
    param(
        [ValidateSet('mrb', 'build')][string]$Kind = 'build',
        [string]$Fuel
    )
    $bundled = Join-Path (Get-ModuleRoot) 'config\default.json'
    $cfg = $null
    try { $cfg = Read-JsonFile $bundled } catch { }
    $m = $null
    if ($cfg) { $m = $cfg.models }
    $fuel = [string]$Fuel
    if ($Kind -eq 'mrb') {
        if ($fuel -eq 'cursor-models') {
            if ($m -and $m.mrbCursor) { return [string]$m.mrbCursor }
            return 'grok-4.6'
        }
        if ($m -and $m.mrbGrok) { return [string]$m.mrbGrok }
        return 'grok-4.6'
    }
    if ($fuel -eq 'cursor-models') {
        if ($m -and $m.buildCursor) { return [string]$m.buildCursor }
        return 'composer-2.5'
    }
    if ($m -and $m.buildGrok) { return [string]$m.buildGrok }
    return 'build0.1'
}

function Get-BobGrokCatalogIds {
    $ids = New-Object System.Collections.Generic.List[string]
    $cache = Join-Path $env:USERPROFILE '.grok\models_cache.json'
    if (Test-Path $cache) {
        try {
            $j = Read-JsonFile $cache
            if ($j.models) {
                foreach ($p in $j.models.PSObject.Properties) { [void]$ids.Add([string]$p.Name) }
            }
        }
        catch { }
    }
    if ($ids.Count -eq 0) {
        [void]$ids.Add('grok-4.6')
        [void]$ids.Add('grok-4.5')
    }
    return $ids
}

function Resolve-BobGrokCliModel {
    # grok.exe -m rejects unknown ids (build0.1 is not in `grok models` today).
    # Map to a catalog id so builders still start. Prefer buildGrokFallback.
    [CmdletBinding()]
    param([string]$Wanted)
    if (-not $Wanted) { return $null }
    $ids = Get-BobGrokCatalogIds
    if ($ids.Contains($Wanted)) { return $Wanted }
    if ($Wanted -match '^(grok-\d+\.\d+)-build$') {
        $base = $Matches[1]
        if ($ids.Contains($base)) { return $base }
    }
    $isBuild = $Wanted -match '(?i)^(build0\.1|grok-build-0\.1|build-0\.1)$'
    if ($isBuild) {
        $cfg = $null
        try { $cfg = Read-JsonFile (Join-Path (Get-ModuleRoot) 'config\default.json') } catch { }
        $fb = $null
        if ($cfg -and $cfg.models -and $cfg.models.buildGrokFallback) {
            $fb = [string]$cfg.models.buildGrokFallback
        }
        if ($fb -and $ids.Contains($fb)) { return $fb }
        if ($ids.Contains('grok-4.5')) { return 'grok-4.5' }
        if ($ids.Contains('grok-4.6')) { return 'grok-4.6' }
        if ($ids.Count -gt 0) { return [string]$ids[$ids.Count - 1] }
    }
    if ($ids.Contains('grok-4.6')) { return 'grok-4.6' }
    if ($ids.Count -gt 0) { return [string]$ids[0] }
    return $Wanted
}

function Get-BobFuelOrder {
    param(
        [switch]$AllowOnDemand,
        [switch]$AllowCopilot
    )
    # Default: Cursor Models then Grok Build. Copilot only when -AllowCopilot (CCA often off).
    $order = @('cursor-models', 'grok-build')
    if ($AllowCopilot) { $order += 'copilot' }
    $order += 'grok-bot'
    if ($AllowOnDemand) { $order += 'on-demand' }
    return $order
}

function Get-BobRemainingPctValue {
    param($Owner)
    if ($null -eq $Owner) { return $null }
    $raw = $null
    if ($Owner -is [int] -or $Owner -is [long] -or $Owner -is [double]) {
        $raw = $Owner
    }
    elseif ($Owner.PSObject -and $Owner.PSObject.Properties['remaining_pct']) {
        $raw = $Owner.remaining_pct
    }
    if ($null -eq $raw -or [string]$raw -eq '') { return $null }
    try { return [int]$raw } catch { return $null }
}

function Get-BobGrokAuthSnapshot {
    <#
    .SYNOPSIS
      Read-only local Grok auth/subscription snapshot from settings_cache.json.
    .NOTES
      FR #430: never logs secrets. Override path with BOB_GROK_SETTINGS_CACHE for tests.
    #>
    param([string]$Path)
    if (-not $Path) {
        if ($env:BOB_GROK_SETTINGS_CACHE -and [string]$env:BOB_GROK_SETTINGS_CACHE.Trim()) {
            $Path = [string]$env:BOB_GROK_SETTINGS_CACHE.Trim()
        }
        else {
            $Path = Join-Path $env:USERPROFILE '.grok\settings_cache.json'
        }
    }
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $wrap = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $wrap.payload) { return $null }
        $payload = $wrap.payload
        if ($payload -is [string]) { $payload = $payload | ConvertFrom-Json }
        $s = $payload.settings
        if (-not $s) { return $null }
        return [pscustomobject]@{
            allow_access              = $s.allow_access
            subscription_tier_display = [string]$s.subscription_tier_display
            default_model             = [string]$s.default_model
            fetched_at                = [string]$payload.fetched_at
            grok_version_reported     = [string]$payload.grok_version
            source                    = 'settings_cache.json'
        }
    }
    catch { return $null }
}

function Test-BobGrokAllowAccessTrue {
    param($Auth)
    if (-not $Auth) { return $false }
    $a = $Auth.allow_access
    if ($a -is [bool]) { return [bool]$a }
    $s = [string]$a
    return ($s -eq 'True' -or $s -eq 'true' -or $s -eq '1')
}

function Get-BobGrokAvailability {
    <#
    .SYNOPSIS
      Explicit Grok Build availability state (FR #430) — separate from remaining_pct.
    .OUTPUTS
      state: available | exhausted | unknown | auth-failed | stale
      Never invents remaining_pct. Never spends credits / prompts / network beyond local files.
    #>
    param(
        $Weekly,
        $Auth,
        [datetime]$UtcNow = [datetime]::UtcNow,
        [int]$AuthMaxAgeHours = 168
    )
    if (-not $UtcNow.Kind -or $UtcNow.Kind -eq [DateTimeKind]::Unspecified) {
        $UtcNow = [DateTime]::SpecifyKind($UtcNow, [DateTimeKind]::Utc)
    }
    else { $UtcNow = $UtcNow.ToUniversalTime() }
    $checked = $UtcNow.ToString('o')
    $periodEnd = $null
    if ($Weekly -and $Weekly.period_end) { $periodEnd = [string]$Weekly.period_end }

    $pct = Get-BobRemainingPctValue $Weekly
    # t785u: a % from a period that has already ended is last week's number - never 'available 8%' for it.
    if ($null -ne $pct -and $periodEnd) {
        try {
            $peChk = [datetime]::Parse($periodEnd, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
            if ($peChk -lt $UtcNow) { $pct = $null }
        } catch { }
    }
    if ($null -ne $pct) {
        if ($pct -gt 0) {
            return [pscustomobject]@{
                state         = 'available'
                reason        = 'legacy-remaining-pct'
                remaining_pct = $pct
                period_end    = $periodEnd
                checked_at    = $checked
                format        = $(if ($Weekly -and $Weekly.format) { [string]$Weekly.format } else { 'legacy' })
            }
        }
        return [pscustomobject]@{
            state         = 'exhausted'
            reason        = 'legacy-remaining-pct-zero'
            remaining_pct = 0
            period_end    = $periodEnd
            checked_at    = $checked
            format        = $(if ($Weekly -and $Weekly.format) { [string]$Weekly.format } else { 'legacy' })
        }
    }

    if (-not $Auth) { $Auth = Get-BobGrokAuthSnapshot }
    if (-not $Auth) {
        return [pscustomobject]@{
            state         = 'unknown'
            reason        = 'no-auth-snapshot'
            remaining_pct = $null
            period_end    = $periodEnd
            checked_at    = $checked
            format        = $(if ($Weekly -and $Weekly.format) { [string]$Weekly.format } else { $null })
        }
    }
    if (-not (Test-BobGrokAllowAccessTrue $Auth)) {
        return [pscustomobject]@{
            state         = 'auth-failed'
            reason        = 'allow_access-false'
            remaining_pct = $null
            period_end    = $periodEnd
            checked_at    = $checked
            format        = $(if ($Weekly -and $Weekly.format) { [string]$Weekly.format } else { $null })
        }
    }

    $authFresh = $true
    if ($Auth.fetched_at) {
        try {
            $fa = [datetime]::Parse([string]$Auth.fetched_at, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
            if (($UtcNow - $fa).TotalHours -gt [double]$AuthMaxAgeHours) { $authFresh = $false }
        }
        catch { }
    }
    if (-not $authFresh) {
        return [pscustomobject]@{
            state         = 'stale'
            reason        = 'auth-snapshot-stale'
            remaining_pct = $null
            period_end    = $periodEnd
            checked_at    = $checked
            format        = $(if ($Weekly -and $Weekly.format) { [string]$Weekly.format } else { $null })
        }
    }

    if ($Weekly -and $periodEnd) {
        $pe = $null
        try {
            $pe = [datetime]::Parse($periodEnd, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
        }
        catch { }
        if ($pe -and $pe -lt $UtcNow) {
            return [pscustomobject]@{
                state         = 'stale'
                reason        = 'period-end-past'
                remaining_pct = $null
                period_end    = $periodEnd
                checked_at    = $checked
                format        = $(if ($Weekly.format) { [string]$Weekly.format } else { $null })
            }
        }
        # Grok 1.0.41+: null % + current weekly period + local allow_access — verified local seat.
        return [pscustomobject]@{
            state         = 'available'
            reason        = $(if ($Weekly.stale) { 'period-rolled-unmeasured' } else { 'verified-local-auth-weekly-period' })
            remaining_pct = $null
            period_end    = $periodEnd
            checked_at    = $checked
            format        = $(if ($Weekly.format) { [string]$Weekly.format } else { 'grok-1.0.41' })
        }
    }

    return [pscustomobject]@{
        state         = 'unknown'
        reason        = $(if ($Weekly) { 'weekly-pct-unknown' } else { 'no-weekly-billing' })
        remaining_pct = $null
        period_end    = $periodEnd
        checked_at    = $checked
        format        = $(if ($Weekly -and $Weekly.format) { [string]$Weekly.format } else { $null })
    }
}

function Get-BobMachineJobCount {
    param($Machine)
    if ($null -eq $Machine) { return 0 }
    $j = $Machine.jobs
    if ($null -eq $j) {
        if ($null -ne $Machine.job_count -and [string]$Machine.job_count -ne '') {
            try { return [int]$Machine.job_count } catch { return 0 }
        }
        return 0
    }
    if ($j -is [int] -or $j -is [long] -or $j -is [double]) { return [int]$j }
    if ($j -is [string]) {
        if ([string]::IsNullOrWhiteSpace($j) -or $j -eq '-') { return 0 }
        try { return [int]$j } catch { return @($j).Count }
    }
    return @($j).Count
}

function Test-BobGitEligibleMachine {
    param($Machine)
    if ($null -eq $Machine) { return $false }
    if ($null -ne $Machine.gitEligible -and [string]$Machine.gitEligible -ne '') {
        try { return [bool]$Machine.gitEligible } catch { }
    }
    $kind = [string]$Machine.kind
    $id = [string]$Machine.id
    $hostName = [string]$Machine.hostname
    if ($kind -match '(?i)dumb') { return $false }
    if ($id -match '2012' -or $hostName -match '2012') { return $false }
    $roots = @($Machine.cwdRoots)
    if ($roots.Count -eq 0) { return $false }
    return $true
}

function Get-BobMachineFuels {
    param($Machine)
    if ($null -eq $Machine) { return @() }
    if ($Machine.fuels) { return @($Machine.fuels | ForEach-Object { [string]$_ }) }
    if (-not (Test-BobGitEligibleMachine $Machine)) { return @() }
    return @('cursor-models', 'grok-build', 'copilot', 'grok-bot')
}

function Test-BobMachineCanStrikeFuel {
    param($Machine, [string]$Fuel)
    if (-not $Fuel) { return $false }
    $fuels = @(Get-BobMachineFuels $Machine)
    return ($fuels -contains $Fuel)
}

function Test-BobFuelHasIncluded {
    param(
        $Capacity,
        $Machine,
        [string]$Fuel,
        [switch]$AllowOnDemand
    )
    switch ($Fuel) {
        'cursor-models' {
            $p = Get-BobRemainingPctValue $Capacity.cursor_models
            return ($null -ne $p -and $p -gt 0)
        }
        'grok-build' {
            $p = Get-BobRemainingPctValue $Machine.grok_build
            if ($null -ne $p) { return ($p -gt 0) }
            # FR #430: null % is not exhaustion — use explicit availability when present.
            $st = $null
            if ($Machine.grok_build -and $Machine.grok_build.PSObject.Properties['availability']) {
                $st = [string]$Machine.grok_build.availability
            }
            if ($st -eq 'available') { return $true }
            if ($st -eq 'exhausted') { return $false }
            return $false
        }
        'grok-bot' {
            $p = Get-BobRemainingPctValue $Machine.grok_bot
            return ($null -ne $p -and $p -gt 0)
        }
        'copilot' {
            $c = $Capacity.copilot
            if ($c -and $c.PSObject.Properties['available'] -and $c.available -eq $false) { return $false }
            $p = Get-BobRemainingPctValue $c
            if ($null -eq $p) { return $true }
            return ($p -gt 0)
        }
        'on-demand' {
            if (-not $AllowOnDemand) { return $false }
            $o = $Capacity.on_demand
            if (-not $o) { return $false }
            if ($o.PSObject.Properties['enabled'] -and $o.enabled -eq $false) { return $false }
            $p = Get-BobRemainingPctValue $o
            return ($null -ne $p -and $p -gt 0)
        }
        default { return $false }
    }
}

function Get-BobFuelPeriodEnd {
    param($Capacity, $Machine, [string]$Fuel)
    $owner = $null
    switch ($Fuel) {
        'cursor-models' { $owner = $Capacity.cursor_models }
        'on-demand' { $owner = $Capacity.on_demand }
        'copilot' { $owner = $Capacity.copilot }
        'grok-build' { $owner = $Machine.grok_build }
        'grok-bot' { $owner = $Machine.grok_bot }
    }
    if ($owner -and $owner.period_end) { return [string]$owner.period_end }
    return $null
}

function ConvertTo-BobCapacitySnapshot {
    param($Raw)
    if ($null -eq $Raw) { return $null }
    if ($Raw -is [string]) {
        if (-not (Test-Path $Raw)) { return $null }
        $Raw = Get-Content $Raw -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    return $Raw
}

function Get-BobCapacity {
    [CmdletBinding()]
    param()
    if ($env:BOB_CAPACITY_FILE -and (Test-Path $env:BOB_CAPACITY_FILE)) {
        return ConvertTo-BobCapacitySnapshot $env:BOB_CAPACITY_FILE
    }

    $cursor = $null
    try { $cursor = Get-BobCursorAgentWeeklyRemaining } catch { $cursor = $null }
    $cursorPct = Get-BobRemainingPctValue $cursor
    $localWeek = $null
    try { $localWeek = Get-BobWeeklyRemaining } catch { $localWeek = $null }
    $thisId = $null
    try { $thisId = Get-ThisMachineId } catch { }

    $hover = $null
    try { $hover = Get-BobTrayHover } catch { $hover = $null }

    $byId = @{}
    foreach ($m in @(Get-BobMachines)) {
        if ($m -and $m.id) { $byId[[string]$m.id] = $m }
    }
    if ($hover -and $hover.machines) {
        foreach ($t in @($hover.machines)) {
            $tid = [string]$t.id
            if (-not $tid) { continue }
            if (-not $byId.ContainsKey($tid)) {
                $byId[$tid] = [pscustomobject]@{
                    id       = $tid
                    kind     = 'windows'
                    cwdRoots = @($(if ($env:BOB_AI_ROOT) { $env:BOB_AI_ROOT } else { 'C:\ai' }))   # t780u: BOB_AI_ROOT set by Start-BobTray
                    hostname = $tid
                }
            }
        }
    }

    $jobCount = @{}
    foreach ($j in @(Get-BobBuilds)) {
        $mid = [string]$j.machine
        if (-not $mid) { continue }
        if (-not $jobCount.ContainsKey($mid)) { $jobCount[$mid] = 0 }
        if ([string]$j.lane -eq 'inbox' -or [string]$j.lane -eq 'running' -or [string]$j.state -eq 'running' -or [string]$j.state -eq 'queued') {
            $jobCount[$mid] = [int]$jobCount[$mid] + 1
        }
    }

    $machines = @()
    foreach ($id in @($byId.Keys | Sort-Object)) {
        $rec = $byId[$id]
        $tile = $null
        if ($hover) { $tile = @($hover.machines | Where-Object { [string]$_.id -eq $id })[0] }
        $alive = $true
        if ($tile -and $tile.reach -eq 'not-in-moot') { $alive = $false }
        $gBuildPct = $null
        $gBuildEnd = $null
        $gBuildAvail = $null
        $gBuildAvailReason = $null
        if ($tile -and $null -ne $tile.remaining_pct -and [string]$tile.remaining_pct -ne '') {
            $gBuildPct = [int]$tile.remaining_pct
            $gBuildEnd = [string]$tile.period_end
        }
        elseif ($thisId -and $id -eq $thisId -and $localWeek) {
            $gBuildPct = Get-BobRemainingPctValue $localWeek
            if ($localWeek.period_end) { $gBuildEnd = [string]$localWeek.period_end }
        }
        elseif ($tile -and $tile.period_end) {
            $gBuildEnd = [string]$tile.period_end
        }
        if ($thisId -and $id -eq $thisId) {
            $authSnap = $null
            try { $authSnap = Get-BobGrokAuthSnapshot } catch { $authSnap = $null }
            $weekForAvail = $localWeek
            if (-not $weekForAvail -and ($null -ne $gBuildPct -or $gBuildEnd)) {
                $weekForAvail = [pscustomobject]@{
                    remaining_pct = $gBuildPct
                    period_end    = $gBuildEnd
                    format        = $(if ($localWeek -and $localWeek.format) { $localWeek.format } else { $null })
                }
            }
            try {
                $av = Get-BobGrokAvailability -Weekly $weekForAvail -Auth $authSnap
                if ($av) {
                    $gBuildAvail = [string]$av.state
                    $gBuildAvailReason = [string]$av.reason
                    if (-not $gBuildEnd -and $av.period_end) { $gBuildEnd = [string]$av.period_end }
                }
            }
            catch { }
        }
        elseif ($tile -and $tile.availability) {
            $gBuildAvail = [string]$tile.availability
            if ($tile.availability_reason) { $gBuildAvailReason = [string]$tile.availability_reason }
        }
        $jobs = 0
        if ($jobCount.ContainsKey($id)) { $jobs = [int]$jobCount[$id] }
        elseif ($tile -and $null -ne $tile.job_count) { $jobs = [int]$tile.job_count }
        $row = [pscustomobject]@{
            id          = $id
            kind        = $(if ($rec.kind) { [string]$rec.kind } else { 'windows' })
            hostname    = [string]$rec.hostname
            gitEligible = $null
            alive       = $alive
            jobs        = $jobs
            cwdRoots    = @($rec.cwdRoots)
            grok_build  = [pscustomobject]@{
                remaining_pct         = $gBuildPct
                period_end            = $gBuildEnd
                availability          = $gBuildAvail
                availability_reason   = $gBuildAvailReason
            }
            grok_bot    = [pscustomobject]@{ remaining_pct = $null; period_end = $null }
            fuels       = @()
            gh_posting  = $null
        }
        if ($rec.gh_posting) {
            $row.gh_posting = $rec.gh_posting
        }
        elseif ($thisId -and $id -eq $thisId) {
            try {
                $liveGh = Get-BobGhPostingReadiness
                $row.gh_posting = [pscustomobject]@{
                    present               = [bool]$liveGh.present
                    authenticated         = [bool]$liveGh.authenticated
                    issue_posting_ready   = [bool]$liveGh.issue_posting_ready
                    probed_at             = [DateTime]::UtcNow.ToString('o')
                }
            }
            catch { }
        }
        $row.gitEligible = Test-BobGitEligibleMachine $row
        $row.fuels = @(Get-BobMachineFuels $row)
        $machines += $row
    }

    $onDemandPct = $null
    $onDemandEnabled = $false
    if ($cursor -and $null -ne $cursor.overage_gbp) {
        $onDemandEnabled = $true
    }

    $sandRemain = $null
    $sandEnd = $null
    if ($cursor) {
        if ($null -ne $cursor.sand_remaining_pct -and [string]$cursor.sand_remaining_pct -ne '') {
            $sandRemain = [int]$cursor.sand_remaining_pct
        }
        if ($cursor.sand_period_end) { $sandEnd = [string]$cursor.sand_period_end }
    }

    if ($sandRemain -ne $null -or $sandEnd) {
        $machines = @($machines | ForEach-Object {
                $_ | Add-Member -NotePropertyName grok_bot -NotePropertyValue ([pscustomobject]@{
                        remaining_pct = $sandRemain
                        period_end    = $sandEnd
                    }) -Force -PassThru
            })
    }

    return [pscustomobject]@{
        cursor_models = [pscustomobject]@{
            remaining_pct = $cursorPct
            period_end    = $(if ($cursor -and $cursor.period_end) { [string]$cursor.period_end } else { $null })
            source        = 'account'
        }
        on_demand     = [pscustomobject]@{
            remaining_pct = $onDemandPct
            enabled       = $onDemandEnabled
        }
        copilot       = [pscustomobject]@{
            remaining_pct = $null
            available     = $true
        }
        machines      = $machines
    }
}

function Select-BobGitWorker {
    [CmdletBinding()]
    param(
        $Capacity,
        [string]$Machine,
        [string]$Fuel,
        [switch]$AllowOnDemand,
        [switch]$AllowCopilot,
        [string]$Repo,
        [ValidateSet('mrb', 'build')][string]$Kind = 'build'
    )
    if (-not $Capacity) {
        $Capacity = Get-BobCapacity
    }
    else {
        $Capacity = ConvertTo-BobCapacitySnapshot $Capacity
    }
    if (-not $Capacity) {
        return [pscustomobject]@{ wait = $true; machine = $null; fuel = $null; reason = 'no capacity snapshot' }
    }

    $wantMachine = $null
    if ($Machine) {
        try { $wantMachine = ConvertTo-MachineId $Machine } catch { $wantMachine = $Machine.ToLowerInvariant() }
    }
    $wantFuel = $null
    if ($Fuel) { $wantFuel = $Fuel.Trim().ToLowerInvariant() }

    $rows = @($Capacity.machines)
    function Find-BobCapacityMachine {
        param([string]$Id)
        foreach ($m in $rows) {
            if ([string]$m.id -and [string]$m.id.ToLowerInvariant() -eq $Id) { return $m }
        }
        return $null
    }

    if ($wantMachine -and $wantFuel) {
        $m = Find-BobCapacityMachine $wantMachine
        if (-not $m -or -not (Test-BobGitEligibleMachine $m)) {
            return [pscustomobject]@{ wait = $true; machine = $null; fuel = $null; reason = 'pin rejected (dumb or missing)' }
        }
        if (-not (Test-BobMachineCanStrikeFuel -Machine $m -Fuel $wantFuel)) {
            return [pscustomobject]@{ wait = $true; machine = $null; fuel = $null; reason = 'pin rejected (ineligible fuel)' }
        }
        # FR #352: pinned machine+fuel must still refuse exhausted pools (needs Simon: API key).
        if (-not (Test-BobFuelHasIncluded -Capacity $Capacity -Machine $m -Fuel $wantFuel -AllowOnDemand:$AllowOnDemand)) {
            return [pscustomobject]@{
                wait    = $true
                machine = [string]$m.id
                fuel    = $wantFuel
                reason  = 'needs Simon: API key'
                error   = 'no_tokens'
            }
        }
        if ($Kind -eq 'mrb' -and -not (Test-BobMachineGhIssuePostingReady $m)) {
            return [pscustomobject]@{ wait = $true; machine = $null; fuel = $null; reason = 'pin rejected (gh issue posting not ready)' }
        }
        return [pscustomobject]@{ wait = $false; machine = [string]$m.id; fuel = $wantFuel }
    }

    $fuelOrder = @(Get-BobFuelOrder -AllowOnDemand:$AllowOnDemand -AllowCopilot:$AllowCopilot)
    if ($wantFuel) { $fuelOrder = @($wantFuel) }

    foreach ($fuelName in $fuelOrder) {
        $candidates = @()
        foreach ($m in $rows) {
            if ($wantMachine -and [string]$m.id.ToLowerInvariant() -ne $wantMachine) { continue }
            if (-not (Test-BobGitEligibleMachine $m)) { continue }
            $alive = $true
            if ($null -ne $m.alive -and [string]$m.alive -ne '') {
                try { $alive = [bool]$m.alive } catch { $alive = $true }
            }
            if (-not $alive) { continue }
            if ((Get-BobMachineJobCount $m) -ne 0) { continue }
            if (-not (Test-BobMachineCanStrikeFuel -Machine $m -Fuel $fuelName)) { continue }
            if (-not (Test-BobFuelHasIncluded -Capacity $Capacity -Machine $m -Fuel $fuelName -AllowOnDemand:$AllowOnDemand)) { continue }
            if ($Kind -eq 'mrb' -and -not (Test-BobMachineGhIssuePostingReady $m)) { continue }
            $candidates += $m
        }
        if ($candidates.Count -eq 0) { continue }

        $sorted = @($candidates | Sort-Object -Property @(
                @{ Expression = {
                        $end = Get-BobFuelPeriodEnd -Capacity $Capacity -Machine $_ -Fuel $fuelName
                        if ($end) {
                            try { return [datetime]$end } catch { return [datetime]::MinValue }
                        }
                        return [datetime]::MinValue
                    }; Descending = $true }
                @{ Expression = {
                        if ($Repo -and $_.hasRepo -eq $true) { 0 } else { 1 }
                    } }
                @{ Expression = {
                        $p = $null
                        if ($fuelName -eq 'cursor-models') { $p = Get-BobRemainingPctValue $Capacity.cursor_models }
                        elseif ($fuelName -eq 'grok-build') { $p = Get-BobRemainingPctValue $_.grok_build }
                        elseif ($fuelName -eq 'grok-bot') { $p = Get-BobRemainingPctValue $_.grok_bot }
                        elseif ($fuelName -eq 'on-demand') { $p = Get-BobRemainingPctValue $Capacity.on_demand }
                        elseif ($fuelName -eq 'copilot') { $p = Get-BobRemainingPctValue $Capacity.copilot }
                        if ($null -eq $p) { return -1 }
                        return $p
                    }; Descending = $true }
                @{ Expression = { $g = Get-BobRemainingPctValue $_.grok_build; if ($null -eq $g) { -1 } else { $g } }; Descending = $true }
                @{ Expression = { [string]$_.id } }
            ))
        $pick = $sorted[0]
        return [pscustomobject]@{ wait = $false; machine = [string]$pick.id; fuel = $fuelName }
    }

    # FR #352: idle eligible machine(s) exist but every strike fuel is at 0% →
    # "needs Simon: API key" (not a generic wait / silent hang).
    $idleNoFuel = $false
    foreach ($m in $rows) {
        if ($wantMachine -and [string]$m.id.ToLowerInvariant() -ne $wantMachine) { continue }
        if (-not (Test-BobGitEligibleMachine $m)) { continue }
        $alive = $true
        if ($null -ne $m.alive -and [string]$m.alive -ne '') {
            try { $alive = [bool]$m.alive } catch { $alive = $true }
        }
        if (-not $alive) { continue }
        if ((Get-BobMachineJobCount $m) -ne 0) { continue }
        $hasAnyFuel = $false
        foreach ($fuelName in @(Get-BobFuelOrder -AllowOnDemand:$AllowOnDemand -AllowCopilot:$AllowCopilot)) {
            if (-not (Test-BobMachineCanStrikeFuel -Machine $m -Fuel $fuelName)) { continue }
            if (Test-BobFuelHasIncluded -Capacity $Capacity -Machine $m -Fuel $fuelName -AllowOnDemand:$AllowOnDemand) {
                $hasAnyFuel = $true
                break
            }
        }
        if (-not $hasAnyFuel) { $idleNoFuel = $true }
    }
    if ($idleNoFuel) {
        return [pscustomobject]@{
            wait    = $true
            machine = $(if ($wantMachine) { $wantMachine } else { $null })
            fuel    = $null
            reason  = 'needs Simon: API key'
            error   = 'no_tokens'
        }
    }
    return [pscustomobject]@{ wait = $true; machine = $null; fuel = $null; reason = 'no eligible worker' }
}

function Test-BobQuotaFailureText {
    <#
      FR #352: detect provider quota / 402 / 429 / out-of-credits in agent output.
      Distinct from no-progress hang (AgentMonitor #99).
    #>
    param([string]$Text)
    $t = [string]$Text
    if (-not $t) { return $false }
    if ($t -match '(?i)\b402\b') { return $true }
    if ($t -match '(?i)\b429\b') { return $true }
    if ($t -match '(?i)out of credits|out.of.tokens|insufficient.?quota|quota.?exceeded|rate.?limit') { return $true }
    if ($t -match '(?i)no tokens remaining|usage.?limit|billing|payment.?required') { return $true }
    return $false
}
