# FR #7692: the only seat identities are the ones Si clicked.
# One line per seat: nick<TAB>kind<TAB>machine. Kind is grok, cursor, or opencode.

function Get-BobTrayClickedSeatPath {
    param([Parameter(Mandatory)][string]$Root)
    return (Join-Path (Join-Path $Root 'run') 'clicked-seats.txt')
}

function Get-BobTrayClickedSeatKind {
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Nick)
    $path = Get-BobTrayClickedSeatPath -Root $Root
    if (-not (Test-Path -LiteralPath $path)) { return '' }
    $want = ([string]$Nick).Trim().ToLowerInvariant()
    if (-not $want) { return '' }
    foreach ($line in @(Get-Content -LiteralPath $path -ErrorAction SilentlyContinue)) {
        $parts = ([string]$line).Split("`t")
        if ($parts.Count -lt 2) { continue }
        if ($parts[0].Trim().ToLowerInvariant() -eq $want) { return $parts[1].Trim().ToLowerInvariant() }
    }
    return ''
}

function Add-BobTrayClickedSeat {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Nick,
        [Parameter(Mandatory)][string]$Kind,
        [string]$Machine = ''
    )
    $kind = ([string]$Kind).Trim().ToLowerInvariant()
    if (@('grok', 'cursor', 'opencode') -notcontains $kind) { return }
    $nick = ([string]$Nick).Trim()
    if (-not $nick) { return }
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
    $keep += ($nick + "`t" + $kind + "`t" + ([string]$Machine).Trim().ToLowerInvariant())
    Set-Content -LiteralPath $path -Value $keep -Encoding ascii
}
