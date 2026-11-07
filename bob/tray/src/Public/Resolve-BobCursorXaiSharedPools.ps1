# FR #6214: Cursor and xAI share one quota pool for display/capacity identity.
# Pure helpers (no network, no digest). Distinct pool_id values stay distinct.
# Unknown/null remaining stays null — never fabricate 0 or 100.

function Resolve-BobCursorXaiSharedPools {
    <#
      .SYNOPSIS
        Merge Cursor + xAI quota refs that share pool_id into one canonical pool each.
      .NOTES
        FR #6214. Each ref: pool_id, family (cursor|xai), remaining_pct, period_end, label.
        Blank/missing pool_id defaults to 'local-unified' so local TipForm/Status collapse.
        When both remainings are known and differ, keep the lesser (do not inflate capacity).
    #>
    param(
        [Parameter(Mandatory = $false)]
        $Refs
    )
    $rows = @($Refs | Where-Object { $_ })
    if ($rows.Count -eq 0) { return @() }

    $byId = [ordered]@{}
    foreach ($r in $rows) {
        # Never use $pid — PowerShell automatic $PID is read-only.
        $poolKey = $null
        try { $poolKey = [string]$r.pool_id } catch { $poolKey = $null }
        if (-not $poolKey -or $poolKey.Trim() -eq '') { $poolKey = 'local-unified' }
        $fam = $null
        try { $fam = [string]$r.family } catch { $fam = $null }
        if (-not $fam) { $fam = '' }
        $fam = $fam.Trim().ToLowerInvariant()
        if ($fam -eq 'grok' -or $fam -eq 'grok-build' -or $fam -eq 'x-ai') { $fam = 'xai' }
        if ($fam -eq 'cursor-models' -or $fam -eq 'cu' -or $fam -eq 'auto') { $fam = 'cursor' }

        if (-not $byId.Contains($poolKey)) {
            $byId[$poolKey] = [pscustomobject]@{
                pool_id       = $poolKey
                families      = New-Object System.Collections.Generic.List[string]
                remaining_pct = $null
                period_end    = $null
                label         = $null
                known         = $false
            }
        }
        $pool = $byId[$poolKey]
        if ($fam -and -not ($pool.families -contains $fam)) {
            [void]$pool.families.Add($fam)
        }
        $rp = $null
        if ($null -ne $r.remaining_pct -and [string]$r.remaining_pct -ne '') {
            try { $rp = [int]$r.remaining_pct } catch { $rp = $null }
        }
        if ($null -ne $rp) {
            if ($null -eq $pool.remaining_pct -or [string]$pool.remaining_pct -eq '') {
                $pool.remaining_pct = $rp
            }
            else {
                # Lesser-ratchet: never claim more capacity than either meter shows.
                if ([int]$rp -lt [int]$pool.remaining_pct) { $pool.remaining_pct = $rp }
            }
            $pool.known = $true
        }
        $pe = $null
        try { if ($r.period_end) { $pe = [string]$r.period_end } } catch { }
        if ($pe -and (-not $pool.period_end -or [string]$pool.period_end -eq '')) {
            $pool.period_end = $pe
        }
        $lab = $null
        try { if ($r.label) { $lab = [string]$r.label } } catch { }
        if ($lab -and (-not $pool.label)) { $pool.label = $lab }
    }

    $out = @()
    foreach ($key in @($byId.Keys)) {
        $p = $byId[$key]
        if (-not $p.label) {
            $fams = @($p.families)
            if (($fams -contains 'cursor') -and ($fams -contains 'xai')) {
                $p.label = 'Cursor / xAI weekly'
            }
            elseif ($fams -contains 'xai') { $p.label = 'xAI weekly' }
            elseif ($fams -contains 'cursor') { $p.label = 'Cursor Models' }
            else { $p.label = 'Cursor / xAI weekly' }
        }
        $out += ,[pscustomobject]@{
            pool_id       = [string]$p.pool_id
            families      = @($p.families)
            remaining_pct = $(if ($null -ne $p.remaining_pct -and [string]$p.remaining_pct -ne '') { [int]$p.remaining_pct } else { $null })
            period_end    = $(if ($p.period_end) { [string]$p.period_end } else { $null })
            label         = [string]$p.label
            known         = [bool]$p.known
        }
    }
    return $out
}

function Get-BobSharedCursorXaiAggregateRemaining {
    <#
      .SYNOPSIS
        Sum remaining_pct across distinct shared pools (same pool_id counted once).
      .NOTES
        FR #6214. Unknown pools contribute nothing (not zero). Returns $null when no known %.
    #>
    param(
        [Parameter(Mandatory = $false)]
        $Refs
    )
    $pools = @(Resolve-BobCursorXaiSharedPools -Refs $Refs)
    $sum = $null
    foreach ($p in $pools) {
        if ($null -eq $p.remaining_pct -or [string]$p.remaining_pct -eq '') { continue }
        try { $v = [int]$p.remaining_pct } catch { continue }
        if ($null -eq $sum) { $sum = 0 }
        $sum = [int]$sum + $v
    }
    return $sum
}

function Format-BobCursorXaiSharedPoolTitle {
    <#
      .SYNOPSIS
        Display title for the shared Cursor/xAI capacity row.
    #>
    param(
        $Pool,
        [string]$AccountLabel,
        [string]$AccountName
    )
    $base = 'Cursor / xAI weekly'
    if ($Pool -and $Pool.label) { $base = [string]$Pool.label }
    $suffix = $null
    if ($AccountLabel) { $suffix = [string]$AccountLabel }
    elseif ($AccountName) { $suffix = [string]$AccountName }
    if ($suffix) { return ('{0} - {1}' -f $base, $suffix) }
    return $base
}
