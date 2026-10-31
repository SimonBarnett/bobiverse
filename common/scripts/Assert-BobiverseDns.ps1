#Requires -Version 5.1
<#
.SYNOPSIS
  Fail-closed check that fleet-critical hostnames resolve on this Windows box.

.DESCRIPTION
  FR #4345: default Windows DNS can fail to resolve github.com / api.github.com /
  irc.ntsa.uk while public resolvers (8.8.8.8 / 1.1.1.1) still answer. That stalls
  gh, git, and the harvest intake webhook mid-job.

  Assert lists NIC DNS servers, probes RequiredHosts via the default resolver and
  optionally via PreferredPublicDns, and reports hosts-file overrides.

  -RepairDnsServers appends PreferredPublicDns to each IPv4 interface that already
  has servers (keeps the existing first hop for LAN names).
  -ClearStaleHostsPins removes RequiredHosts lines from the hosts file only after
  default Resolve-DnsName succeeds for every required host (avoid permanent pins).

.EXAMPLE
  .\Assert-BobiverseDns.ps1
.EXAMPLE
  .\Assert-BobiverseDns.ps1 -RepairDnsServers -ClearStaleHostsPins
#>
[CmdletBinding()]
param(
    [string[]]$RequiredHosts = @('github.com', 'api.github.com', 'irc.ntsa.uk', 'bob.ntsa.uk'),
    [string[]]$PreferredPublicDns = @('8.8.8.8', '1.1.1.1'),
    [switch]$RepairDnsServers,
    [switch]$ClearStaleHostsPins,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'

function Get-BobiverseHostsOverrides {
    param([string[]]$Names)
    $path = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
    $hits = @()
    if (-not (Test-Path -LiteralPath $path)) { return @() }
    $i = 0
    foreach ($line in Get-Content -LiteralPath $path -ErrorAction SilentlyContinue) {
        $i++
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith('#')) { continue }
        $parts = $trim -split '\s+'
        if ($parts.Count -lt 2) { continue }
        $hostNames = $parts[1..($parts.Count - 1)]
        foreach ($n in $Names) {
            if ($hostNames -contains $n) {
                $hits += ,([pscustomobject]@{ line = $i; address = $parts[0]; name = $n; raw = $trim })
            }
        }
    }
    return $hits
}

function Test-BobiverseResolve {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Server
    )
    try {
        if ($Server) {
            $ans = @(Resolve-DnsName -Name $Name -Type A -Server $Server -ErrorAction Stop |
                Where-Object { $_.Type -eq 'A' -and $_.IPAddress })
        } else {
            $ans = @(Resolve-DnsName -Name $Name -Type A -ErrorAction Stop |
                Where-Object { $_.Type -eq 'A' -and $_.IPAddress })
        }
        if ($ans.Count -lt 1) {
            return [ordered]@{ ok = $false; error = 'no A record'; addresses = @() }
        }
        return [ordered]@{
            ok        = $true
            error     = $null
            addresses = @($ans | ForEach-Object { $_.IPAddress } | Select-Object -Unique)
        }
    } catch {
        return [ordered]@{ ok = $false; error = $_.Exception.Message; addresses = @() }
    }
}

$nicRows = @(Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.ServerAddresses -and @($_.ServerAddresses).Count -gt 0 } |
    ForEach-Object {
        [ordered]@{
            interface = $_.InterfaceAlias
            servers   = @($_.ServerAddresses)
        }
    })

$hostOverrides = Get-BobiverseHostsOverrides -Names $RequiredHosts

$probes = @()
$defaultOk = $true
foreach ($h in $RequiredHosts) {
    $def = Test-BobiverseResolve -Name $h
    $pub = $null
    # Always probe preferred public DNS so operators see "LAN DNS fail / public OK".
    if ($PreferredPublicDns.Count -gt 0) {
        $pub = Test-BobiverseResolve -Name $h -Server $PreferredPublicDns[0]
    }
    if (-not $def.ok) { $defaultOk = $false }
    $probes += ,([pscustomobject]@{
            name         = $h
            defaultOk    = [bool]$def.ok
            defaultError = $def.error
            defaultAddrs = @($def.addresses)
            publicOk     = if ($null -eq $pub) { $null } else { [bool]$pub.ok }
            publicError  = if ($null -eq $pub) { $null } else { $pub.error }
            publicAddrs  = if ($null -eq $pub) { @() } else { @($pub.addresses) }
            publicServer = if ($null -eq $pub) { $null } else { $PreferredPublicDns[0] }
        })
}

$repaired = @()
$needsElevation = $false
$repairErrors = @()
# (needsElevation / repairErrors stay false/empty when -RepairDnsServers is omitted)
if ($RepairDnsServers) {
    foreach ($row in $nicRows) {
        $alias = [string]$row.interface
        $cur = @($row.servers)
        $merged = @()
        foreach ($s in $cur) { if ($s -and ($merged -notcontains $s)) { $merged += $s } }
        foreach ($s in $PreferredPublicDns) {
            if ($s -and ($merged -notcontains $s)) { $merged += $s }
        }
        if (($merged -join ',') -ne ($cur -join ',')) {
            try {
                Set-DnsClientServerAddress -InterfaceAlias $alias -ServerAddresses $merged -ErrorAction Stop
                $repaired += ,([pscustomobject]@{ interface = $alias; before = $cur; after = $merged; ok = $true })
            } catch {
                $needsElevation = $true
                $repairErrors += ,([pscustomobject]@{
                        interface = $alias
                        error     = $_.Exception.Message
                    })
            }
        }
    }
    # refresh NIC snapshot after repair
    $nicRows = @(Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.ServerAddresses -and @($_.ServerAddresses).Count -gt 0 } |
        ForEach-Object {
            [pscustomobject]@{
                interface = $_.InterfaceAlias
                servers   = @($_.ServerAddresses)
            }
        })
    # re-probe default after repair
    $defaultOk = $true
    $probes = @()
    foreach ($h in $RequiredHosts) {
        $def = Test-BobiverseResolve -Name $h
        $pub = Test-BobiverseResolve -Name $h -Server $PreferredPublicDns[0]
        if (-not $def.ok) { $defaultOk = $false }
        $probes += ,([pscustomobject]@{
                name         = $h
                defaultOk    = [bool]$def.ok
                defaultError = $def.error
                defaultAddrs = @($def.addresses)
                publicOk     = [bool]$pub.ok
                publicError  = $pub.error
                publicAddrs  = @($pub.addresses)
                publicServer = $PreferredPublicDns[0]
            })
    }
}

$clearedHosts = @()
if ($ClearStaleHostsPins) {
    if (-not $defaultOk) {
        Write-Warning 'ClearStaleHostsPins skipped: default Resolve-DnsName still failing for one or more RequiredHosts'
    } else {
        $path = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
        $raw = @(Get-Content -LiteralPath $path -ErrorAction Stop)
        $keep = New-Object System.Collections.Generic.List[string]
        foreach ($line in $raw) {
            $trim = $line.Trim()
            $drop = $false
            if ($trim -and -not $trim.StartsWith('#')) {
                $parts = $trim -split '\s+'
                if ($parts.Count -ge 2) {
                    $names = $parts[1..($parts.Count - 1)]
                    foreach ($n in $RequiredHosts) {
                        if ($names -contains $n) { $drop = $true; break }
                    }
                }
            }
            if ($drop) {
                $clearedHosts += $trim
            } else {
                [void]$keep.Add($line)
            }
        }
        if ($clearedHosts.Count -gt 0) {
            $utf8 = New-Object System.Text.UTF8Encoding $false
            [System.IO.File]::WriteAllLines($path, @($keep), $utf8)
            Clear-DnsClientCache -ErrorAction SilentlyContinue
            # confirm still green without hosts pins
            $defaultOk = $true
            foreach ($h in $RequiredHosts) {
                $def = Test-BobiverseResolve -Name $h
                if (-not $def.ok) { $defaultOk = $false; break }
            }
            $hostOverrides = Get-BobiverseHostsOverrides -Names $RequiredHosts
        }
    }
}

$result = [ordered]@{
    ok                 = $defaultOk
    fr                 = 'FR #4345'
    nicDns             = $nicRows
    preferredPublicDns = $PreferredPublicDns
    requiredHosts      = $RequiredHosts
    probes             = @($probes)
    hostsOverrides     = @($hostOverrides)
    repaired           = @($repaired)
    repairErrors       = @($repairErrors)
    needsElevation     = $needsElevation
    clearedHostsPins   = @($clearedHosts)
}

# Always emit JSON (operator + agent parse). -Json is accepted for explicit callers.
$result | ConvertTo-Json -Depth 6 -Compress


if ($needsElevation -and $RepairDnsServers) {
    Write-Warning 'FR #4345: -RepairDnsServers needs an elevated Admin shell (Set-DnsClientServerAddress AccessDenied at Medium IL). Re-run elevated: Assert-BobiverseDns.ps1 -RepairDnsServers -ClearStaleHostsPins'
}

if (-not $result.ok) {
    $failing = @($probes | Where-Object { -not $_.defaultOk } | ForEach-Object { $_.name })
    $msg = "FR #4345 DNS fail (remote name could not be resolved) for: $($failing -join ', '). NIC DNS=$($nicRows | ConvertTo-Json -Compress). Run elevated with -RepairDnsServers (append 8.8.8.8/1.1.1.1) then -ClearStaleHostsPins after green."
    Write-Error $msg
    exit 1
}

Write-Host 'Assert-BobiverseDns: OK'
exit 0
