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
