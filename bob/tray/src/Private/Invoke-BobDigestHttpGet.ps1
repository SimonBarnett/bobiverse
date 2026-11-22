#Requires -Version 5.1
<#
.SYNOPSIS
  FR #7602: digest GET via HttpWebRequest with Timeout + ReadWriteTimeout under PS 5.1.
.DESCRIPTION
  PowerShell 5.1 legacy web-request TimeoutSec does not reliably abort a hung or
  half-closed socket (CloseWait). HttpWebRequest.Timeout covers connect/headers;
  ReadWriteTimeout covers the response body stream. Both are set to the same budget.
  Generic: no machine names. Never logs secrets.
#>

function Invoke-BobDigestHttpGet {
    <#
    .SYNOPSIS
      GET a URL and return StatusCode + UTF-8 body, failing within TimeoutSec.
    .PARAMETER Uri
      Absolute http(s) URL.
    .PARAMETER TimeoutSec
      Connect/headers and read/write budget in seconds (minimum 1).
    .PARAMETER Accept
      Accept header value (default application/json).
    .OUTPUTS
      [pscustomobject] @{ StatusCode = [int]; Bytes = [byte[]]; Text = [string] }
      Throws on timeout, DNS, TLS, or transport failure.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Uri,
        [int]$TimeoutSec = 15,
        [string]$Accept = 'application/json'
    )

    $sec = [Math]::Max(1, [int]$TimeoutSec)
    $budgetMs = $sec * 1000

    $req = [System.Net.HttpWebRequest]::Create($Uri)
    $req.Method = 'GET'
    $req.Timeout = $budgetMs
    $req.ReadWriteTimeout = $budgetMs
    $req.AllowAutoRedirect = $true
    $req.KeepAlive = $false
    try {
        $req.AutomaticDecompression = (
            [System.Net.DecompressionMethods]::GZip -bor
            [System.Net.DecompressionMethods]::Deflate
        )
    }
    catch { }
    if ($Accept) {
        $req.Accept = $Accept
    }
    $req.UserAgent = 'BobDigestHttp/1.0'

    $resp = $null
    try {
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $stream = $resp.GetResponseStream()
        if (-not $stream) {
            return [pscustomobject]@{
                StatusCode = $code
                Bytes      = [byte[]]@()
                Text       = ''
            }
        }
        $ms = New-Object System.IO.MemoryStream
        $buffer = New-Object byte[] 8192
        while ($true) {
            $n = $stream.Read($buffer, 0, $buffer.Length)
            if ($n -le 0) { break }
            $ms.Write($buffer, 0, $n)
        }
        $bytes = $ms.ToArray()
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) {
            $text = $text.Substring(1)
        }
        return [pscustomobject]@{
            StatusCode = $code
            Bytes      = $bytes
            Text       = $text
        }
    }
    finally {
        if ($resp) {
            try { $resp.Close() } catch { }
            try { $resp.Dispose() } catch { }
        }
    }
}

function Invoke-BobDigestHttpGetWithRetry {
    <#
    .SYNOPSIS
      FR #8988: one retry when GetResponse throws or the status is 503.
      A WebException ("Exception calling GetResponse with 0 argument(s)") is transient.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Uri,
        [int]$TimeoutSec = 15
    )
    $last = $null
    for ($try = 0; $try -lt 2; $try++) {
        try {
            $got = Invoke-BobDigestHttpGet -Uri $Uri -TimeoutSec $TimeoutSec
            $code = 0
            try { if ($got) { $code = [int]$got.StatusCode } } catch { $code = 0 }
            if ($code -eq 503 -and $try -eq 0) { continue }
            return $got
        }
        catch {
            $last = $_
            if ($try -eq 0) { continue }
            throw
        }
    }
    if ($last) { throw $last }
    return $null
}

function Read-BobTrayDigestPoolsFallback {
    <#
    .SYNOPSIS
      FR #8988: fresh tray-digest-pools.json (digest_ok) becomes a last-good digest.
      Machine percent stays, with age_s, instead of "no digest".
    #>
    [CmdletBinding()]
    param([int]$MaxAgeSec = 900)
    $cands = New-Object System.Collections.Generic.List[string]
    foreach ($root in @($env:BOB_INSTALL_ROOT, $env:BOB_BRIDGE_HOME)) {
        if ($root) { [void]$cands.Add((Join-Path $root 'run\tray-digest-pools.json')) }
    }
    $dir = $PSScriptRoot
    $guard = 0
    while ($dir -and $guard -lt 6) {
        [void]$cands.Add((Join-Path $dir 'run\tray-digest-pools.json'))
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
        $guard++
    }
    $path = $null
    foreach ($p in $cands) {
        if ($p -and (Test-Path -LiteralPath $p -PathType Leaf)) { $path = $p; break }
    }
    if (-not $path) { return $null }
    $doc = $null
    try {
        $raw = [IO.File]::ReadAllText($path, (New-Object System.Text.UTF8Encoding $false))
        $doc = $raw | ConvertFrom-Json
    } catch { return $null }
    if (-not $doc) { return $null }
    $ok = $false
    try { $ok = [bool]$doc.digest_ok } catch { $ok = $false }
    if (-not $ok) { return $null }
    $ts = 0
    try { $ts = [int64]$doc.ts } catch { return $null }
    if ($ts -le 0) { return $null }
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $age = [int]($now - $ts)
    if ($age -lt 0 -or $age -gt $MaxAgeSec) { return $null }
    $fetched = [DateTimeOffset]::FromUnixTimeSeconds($ts).UtcDateTime.ToString('o')
    $map = @{}
    foreach ($row in @($doc.grok)) {
        if (-not $row) { continue }
        $id = ''
        try {
            $heading = [string]$row.heading
            if ($heading -match '^([A-Za-z0-9_-]+)') { $id = $Matches[1] }
        } catch { }
        if (-not $id) { continue }
        $pct = $null
        try { if ($null -ne $row.remaining_pct -and [string]$row.remaining_pct -ne '') { $pct = [int]$row.remaining_pct } } catch { }
        $map[$id] = [pscustomobject]@{
            xai_weekly = [pscustomobject]@{
                remaining_pct = $pct
                fresh         = $false
                fetched_at    = $fetched
                age_s         = $age
            }
        }
    }
    if ($map.Count -eq 0) { return $null }
    $fleet = $null
    try {
        if ($null -ne $doc.opencode_go -and [string]$doc.opencode_go -ne '') {
            $fleet = [pscustomobject]@{
                'opencode-go' = [pscustomobject]@{ remaining = $doc.opencode_go }
            }
        }
    } catch { }
    return [pscustomobject]@{
        machines      = [pscustomobject]$map
        ts            = $ts
        stale         = $false
        fleet_pools   = $fleet
        digest_source = 'tray-digest-pools'
        note          = ('last-good digest age {0}s' -f $age)
    }
}
