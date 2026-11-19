# FR #7692 / FR #8321: the only seat identities are the ones Si clicked.
# One line per seat: nick<TAB>kind<TAB>machine<TAB>model. Kind is grok, cursor, or opencode.
# The model is the clicked seat's launch model (paid or free) so every restart keeps it.

function Get-BobTrayClickedSeatPath {
    param([Parameter(Mandatory)][string]$Root)
    return (Join-Path (Join-Path $Root 'run') 'clicked-seats.txt')
}

function Get-BobTrayClickedSeat {
    <#
    FR #8321: full clicked record. Legacy 2/3-column lines have no model.
    #>
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Nick)
    $path = Get-BobTrayClickedSeatPath -Root $Root
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $want = ([string]$Nick).Trim().ToLowerInvariant()
    if (-not $want) { return $null }
    foreach ($line in @(Get-Content -LiteralPath $path -ErrorAction SilentlyContinue)) {
        $parts = ([string]$line).Split("`t")
        if ($parts.Count -lt 2) { continue }
        if ($parts[0].Trim().ToLowerInvariant() -ne $want) { continue }
        $model = ''
        if ($parts.Count -ge 4) { $model = ([string]$parts[3]).Trim() }
        return [pscustomobject]@{
            Nick    = ([string]$parts[0]).Trim()
            Kind    = ([string]$parts[1]).Trim().ToLowerInvariant()
            Machine = $(if ($parts.Count -ge 3) { ([string]$parts[2]).Trim().ToLowerInvariant() } else { '' })
            Model   = $model
        }
    }
    return $null
}

function Get-BobTrayClickedSeatKind {
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Nick)
    $rec = Get-BobTrayClickedSeat -Root $Root -Nick $Nick
    if (-not $rec) { return '' }
    return [string]$rec.Kind
}

function Get-BobTrayClickedSeatModel {
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Nick)
    $rec = Get-BobTrayClickedSeat -Root $Root -Nick $Nick
    if (-not $rec) { return '' }
    return [string]$rec.Model
}

function Get-BobTrayClickModelConfigPaths {
    param([string]$Root)
    $out = @()
    if ($Root) {
        $out += (Join-Path $Root 'tray\config\default.json')
        $out += (Join-Path $Root 'bob\tray\config\default.json')
        $out += (Join-Path $Root 'config\default.json')
    }
    $la = $env:LOCALAPPDATA
    if (-not $la) { $la = Join-Path $env:USERPROFILE 'AppData\Local' }
    $out += (Join-Path $la 'Bobiverse\tray-models.json')
    return $out
}

function Get-BobTrayClickedLaunchModel {
    <#
    FR #8321: the model this click will launch with, from the same precedence the
    worker uses: env pin, then tray workerStartModels, then (OpenCode) free default.
    #>
    param([string]$Root, [Parameter(Mandatory)][string]$Kind)
    $kind = ([string]$Kind).Trim().ToLowerInvariant()
    if (@('grok', 'cursor', 'opencode') -notcontains $kind) { return '' }
    $envKeys = switch ($kind) {
        'grok' { @('BOB_GROK_MODEL', 'BOB_WORKER_MODEL') }
        'cursor' { @('BOB_CURSOR_MODEL', 'BOB_WORKER_MODEL') }
        'opencode' { @('BOB_OPENCODE_MODEL', 'BOB_WORKER_MODEL') }
    }
    foreach ($key in @($envKeys)) {
        $v = ([string][Environment]::GetEnvironmentVariable($key)).Trim()
        if ($v -and $v -notmatch '\$') { return $v }
    }
    $models = @{}
    $free = ''
    foreach ($path in @(Get-BobTrayClickModelConfigPaths -Root $Root)) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        try {
            $doc = Get-Content -LiteralPath $path -Raw -ErrorAction Stop | ConvertFrom-Json
            if ($doc.PSObject.Properties.Name -contains 'workerStartModels' -and $doc.workerStartModels) {
                foreach ($p in @($doc.workerStartModels.PSObject.Properties)) {
                    $models[([string]$p.Name).ToLowerInvariant()] = ([string]$p.Value).Trim()
                }
            }
            if ($doc.PSObject.Properties.Name -contains 'models' -and $doc.models) {
                if ($doc.models.PSObject.Properties.Name -contains 'opencodeFree' -and $doc.models.opencodeFree) {
                    $free = ([string]$doc.models.opencodeFree).Trim()
                }
            }
        } catch { }
    }
    $got = ([string]$models[$kind]).Trim()
    if ($got -and $got -notmatch '\$') { return $got }
    if ($kind -eq 'opencode') {
        if ($free -and $free -notmatch '\$') { return $free }
        return 'opencode/deepseek-v4.1-flash-free'
    }
    return ''
}

function Add-BobTrayClickedSeat {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Nick,
        [Parameter(Mandatory)][string]$Kind,
        [string]$Machine = '',
        [string]$Model = ''
    )
    $kind = ([string]$Kind).Trim().ToLowerInvariant()
    if (@('grok', 'cursor', 'opencode') -notcontains $kind) { return }
    $nick = ([string]$Nick).Trim()
    if (-not $nick) { return }
    # The record is tab-separated ASCII: never let a model id add a column/newline.
    $model = ([string]$Model).Trim() -replace "[`t`r`n]", ''
    $path = Get-BobTrayClickedSeatPath -Root $Root
    $dir = Split-Path -Parent $path
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $keep = @()
    if (Test-Path -LiteralPath $path) {
        foreach ($line in @(Get-Content -LiteralPath $path -ErrorAction SilentlyContinue)) {
            $parts = ([string]$line).Split("`t")
            if ($parts.Count -lt 2) { continue }
            if ($parts[0].Trim().ToLowerInvariant() -eq $nick.ToLowerInvariant()) { continue }
            $keep += [string]$line
        }
    }
    $keep += ($nick + "`t" + $kind + "`t" + ([string]$Machine).Trim().ToLowerInvariant() + "`t" + $model)
    Set-Content -LiteralPath $path -Value $keep -Encoding ascii
}
