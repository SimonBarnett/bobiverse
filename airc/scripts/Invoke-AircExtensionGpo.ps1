#Requires -Version 5.1
<#
.SYNOPSIS
  FR #5291: create/update domain GPO Priority-web-extension ForceInstall for Chrome+Edge.

.DESCRIPTION
  Discovers a DC (nltest / Get-ADDomain); fails closed when none. Prefers local
  GroupPolicy module; if missing, runs New-GPO / Set-GPRegistryValue / New-GPLink
  on the DC via Invoke-Command (lab seats often lack RSAT). -WhatIf: read-only.
  Emits one JSON object on stdout. Never prints passwords.
  Out of scope: LDAP registry fallback (FR-C), DCC (FR-D).
#>
[CmdletBinding()]
param(
  [ValidateSet('install', 'status')]
  [string]$Action = 'install',
  [string]$ExtensionId = 'cgmpadejahkaggjpffnhaoiafbnicgpa',
  [string]$UpdateUrl = 'https://clients2.google.com/service/update2/crx',
  [string]$GpoName = 'Priority-web-extension',
  [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Result([hashtable]$h) {
  $h['extension_id'] = $ExtensionId
  $h['update_url'] = $UpdateUrl
  $h['gpo_name'] = $GpoName
  $h['force_install'] = ('{0};{1}' -f $ExtensionId, $UpdateUrl)
  $h['whatif'] = [bool]$WhatIf
  $h['action'] = $Action
  ($h | ConvertTo-Json -Compress -Depth 6)
}

function Find-DomainController {
  try {
    $nl = & nltest.exe /dsgetdc: 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0 -and $nl -match 'DC:\s*\\\\(\S+)') {
      $dc = $Matches[1].Trim()
      $domainDns = $null
      $domainDn = $null
      if ($nl -match 'Dom Name:\s*(\S+)') { $domainDns = $Matches[1].Trim() }
      return @{ ok = $true; dc = $dc; domain_dns = $domainDns; domain_dn = $domainDn; source = 'nltest' }
    }
  } catch { }
  try {
    Import-Module ActiveDirectory -ErrorAction Stop
    $d = Get-ADDomain -ErrorAction Stop
    $dc = [string]$d.PDCEmulator
    if (-not $dc) { $dc = [string]$d.InfrastructureMaster }
    if ($dc) {
      return @{
        ok = $true
        dc = ($dc -replace '\.$', '')
        domain_dn = [string]$d.DistinguishedName
        domain_dns = [string]$d.DNSRoot
        source = 'Get-ADDomain'
      }
    }
  } catch { }
  return @{ ok = $false; reason = 'no_dc' }
}

function Test-LocalGroupPolicy {
  try {
    Import-Module GroupPolicy -ErrorAction Stop
    return $true
  } catch {
    return $false
  }
}

$force = '{0};{1}' -f $ExtensionId, $UpdateUrl
$chromeKey = 'HKLM\Software\Policies\Google\Chrome\ExtensionInstallForcelist'
$edgeKey = 'HKLM\Software\Policies\Microsoft\Edge\ExtensionInstallForcelist'

$dcInfo = Find-DomainController
if (-not $dcInfo.ok) {
  Write-Result @{
    ok = $false
    gpo = 'fail'
    reason = 'no_dc'
    wrote_gpo = $false
    browsers = @()
    policy_names = @()
  }
  exit 2
}

$useRemote = -not (Test-LocalGroupPolicy)
$dcHost = $dcInfo.dc

$work = {
  param(
    [string]$Action,
    [string]$GpoName,
    [string]$Force,
    [string]$ChromeKey,
    [string]$EdgeKey,
    [bool]$WhatIfFlag,
    [string]$DomainDnHint,
    [string]$DomainDnsHint
  )
  $ErrorActionPreference = 'Stop'
  Import-Module GroupPolicy -ErrorAction Stop
  Import-Module ActiveDirectory -ErrorAction Stop
  $d = Get-ADDomain -ErrorAction Stop
  $domainDn = if ($DomainDnHint) { $DomainDnHint } else { [string]$d.DistinguishedName }
  $domainDns = if ($DomainDnsHint) { $DomainDnsHint } else { [string]$d.DNSRoot }
  $existing = $null
  try { $existing = Get-GPO -Name $GpoName -ErrorAction Stop } catch { $existing = $null }
  $chromeVal = $null
  $edgeVal = $null
  if ($existing) {
    try { $chromeVal = Get-GPRegistryValue -Name $GpoName -Key $ChromeKey -ValueName '1' -ErrorAction SilentlyContinue } catch { }
    try { $edgeVal = Get-GPRegistryValue -Name $GpoName -Key $EdgeKey -ValueName '1' -ErrorAction SilentlyContinue } catch { }
  }
  if ($WhatIfFlag -or $Action -eq 'status') {
    return @{
      ok = $true
      gpo = $(if ($existing) { 'present' } else { 'absent' })
      reason = 'whatif_plan'
      domain_dns = $domainDns
      domain_dn = $domainDn
      wrote_gpo = $false
      browsers = @('chrome', 'edge')
      policy_names = @($GpoName)
      chrome_force = $(if ($chromeVal) { [string]$chromeVal.Value } else { $null })
      edge_force = $(if ($edgeVal) { [string]$edgeVal.Value } else { $null })
      would_set = $Force
    }
  }
  if (-not $existing) {
    $null = New-GPO -Name $GpoName -Comment 'Airc EXTENSION Priority web ForceInstall (FR #5291)' -ErrorAction Stop
  }
  Set-GPRegistryValue -Name $GpoName -Key $ChromeKey -ValueName '1' -Type String -Value $Force -ErrorAction Stop | Out-Null
  Set-GPRegistryValue -Name $GpoName -Key $EdgeKey -ValueName '1' -Type String -Value $Force -ErrorAction Stop | Out-Null
  $linked = $false
  try {
    foreach ($l in @((Get-GPInheritance -Target $domainDn -ErrorAction Stop).GpoLinks)) {
      if ($l.DisplayName -eq $GpoName) { $linked = $true; break }
    }
  } catch { $linked = $false }
  if (-not $linked) {
    New-GPLink -Name $GpoName -Target $domainDn -LinkEnabled Yes -ErrorAction Stop | Out-Null
  }
  return @{
    ok = $true
    gpo = 'ok'
    reason = 'prepared'
    domain_dns = $domainDns
    domain_dn = $domainDn
    wrote_gpo = $true
    browsers = @('chrome', 'edge')
    policy_names = @($GpoName)
    linked = $true
    force_install_written = $Force
  }
}

try {
  if ($useRemote) {
    $body = Invoke-Command -ComputerName $dcHost -ScriptBlock $work -ArgumentList @(
      $Action, $GpoName, $force, $chromeKey, $edgeKey, [bool]$WhatIf,
      [string]$dcInfo.domain_dn, [string]$dcInfo.domain_dns
    )
  } else {
    $body = & $work $Action $GpoName $force $chromeKey $edgeKey ([bool]$WhatIf) ([string]$dcInfo.domain_dn) ([string]$dcInfo.domain_dns)
  }
  if ($body -is [System.Collections.IDictionary]) {
    $ht = @{}
    foreach ($k in $body.Keys) { $ht[[string]$k] = $body[$k] }
  } else {
    $ht = @{}
    foreach ($p in $body.PSObject.Properties) { $ht[$p.Name] = $p.Value }
  }
  $ht['dc'] = $dcHost
  $ht['gpo_via'] = $(if ($useRemote) { 'invoke_command_dc' } else { 'local_grouppolicy' })
  Write-Result $ht
  if ($ht['ok']) { exit 0 } else { exit 5 }
} catch {
  Write-Result @{
    ok = $false
    gpo = 'fail'
    reason = $(if ($useRemote) { 'gpo_remote_failed' } else { 'gpo_write_failed' })
    dc = $dcHost
    gpo_via = $(if ($useRemote) { 'invoke_command_dc' } else { 'local_grouppolicy' })
    error = $_.Exception.Message
    wrote_gpo = $false
    browsers = @('chrome', 'edge')
    policy_names = @($GpoName)
  }
  exit 5
}
