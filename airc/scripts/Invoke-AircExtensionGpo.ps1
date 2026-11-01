#Requires -Version 5.1
<#
.SYNOPSIS
  FR #5291: create/update domain GPO Priority-web-extension ForceInstall for Chrome+Edge.

.DESCRIPTION
  Discovers a DC (nltest / Get-ADDomain); fails closed when none. Prefers local
  GroupPolicy module; if missing, runs New-GPO / Set-GPRegistryValue / New-GPLink
  on the DC via Invoke-Command (lab seats often lack RSAT). -WhatIf: read-only.
  FR #5645: LocalSystem computer account is denied WinRM on the DC by design.
  On Access Denied, retry Invoke-Command -Credential from CredMan
  PriorityAirc/ExtensionAdmin; if still denied or CredMan missing, emit
  reason=gpo_access_denied with need= guidance (never print the password).
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
  [string]$CredmanTarget = 'PriorityAirc/ExtensionAdmin',
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


function Get-ExtensionAdminCredential {
  # FR #5645: CredMan PriorityAirc/ExtensionAdmin for DC Invoke-Command hop.
  # Returns PSCredential or $null. Never writes password to host/log/JSON.
  param([string]$Target = 'PriorityAirc/ExtensionAdmin')
  try {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class AircExtCredRead {
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
  public struct CREDENTIAL {
    public uint Flags; public uint Type; public string TargetName; public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public uint CredentialBlobSize; public IntPtr CredentialBlob; public uint Persist;
    public uint AttributeCount; public IntPtr Attributes; public string TargetAlias; public string UserName;
  }
  [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern bool CredRead(string target, uint type, int reserved, out IntPtr cred);
  [DllImport("advapi32.dll", SetLastError=true)]
  public static extern void CredFree(IntPtr cred);
  public static string[] ReadPair(string target) {
    IntPtr p;
    if (!CredRead(target, 1, 0, out p) || p == IntPtr.Zero) return null;
    try {
      var c = (CREDENTIAL)Marshal.PtrToStructure(p, typeof(CREDENTIAL));
      string user = c.UserName ?? "";
      string pw = "";
      if (c.CredentialBlob != IntPtr.Zero && c.CredentialBlobSize > 0)
        pw = Marshal.PtrToStringUni(c.CredentialBlob, (int)c.CredentialBlobSize / 2) ?? "";
      return new string[] { user, pw };
    } finally { CredFree(p); }
  }
}
"@ -ErrorAction SilentlyContinue
  } catch { }
  try {
    $pair = [AircExtCredRead]::ReadPair($Target)
    if ($null -eq $pair) { return $null }
    $user = [string]$pair[0]
    $pw = [string]$pair[1]
    if (-not $user -or -not $pw) { return $null }
    $sec = ConvertTo-SecureString -String $pw -AsPlainText -Force
    return New-Object System.Management.Automation.PSCredential ($user, $sec)
  } catch {
    return $null
  }
}

function Test-AccessDeniedMessage([string]$msg) {
  if (-not $msg) { return $false }
  return [bool]($msg -match '(?i)access\s+is\s+denied|AccessDenied|0x80070005|WinRM.*denied')
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

$argList = @(
  $Action, $GpoName, $force, $chromeKey, $edgeKey, [bool]$WhatIf,
  [string]$dcInfo.domain_dn, [string]$dcInfo.domain_dns
)
$credmanTried = $false
$credmanPresent = $false
try {
  if ($useRemote) {
    try {
      $body = Invoke-Command -ComputerName $dcHost -ScriptBlock $work -ArgumentList $argList
    } catch {
      $err1 = [string]$_.Exception.Message
      if (-not (Test-AccessDeniedMessage $err1)) { throw }
      # FR #5645: machine/computer account denied - retry with ExtensionAdmin CredMan.
      $cred = Get-ExtensionAdminCredential -Target $CredmanTarget
      $credmanTried = $true
      $credmanPresent = [bool]$cred
      if (-not $cred) {
        Write-Result @{
          ok = $false
          gpo = 'fail'
          reason = 'gpo_access_denied'
          dc = $dcHost
          gpo_via = 'invoke_command_dc'
          error = $err1
          need = 'credman:PriorityAirc/ExtensionAdmin (GPO edit / Remote Management on DC); computer account LocalSystem cannot Invoke-Command to DC'
          credman_tried = $true
          credman_present = $false
          wrote_gpo = $false
          browsers = @('chrome', 'edge')
          policy_names = @($GpoName)
        }
        exit 5
      }
      try {
        $body = Invoke-Command -ComputerName $dcHost -Credential $cred -ScriptBlock $work -ArgumentList $argList
      } catch {
        $err2 = [string]$_.Exception.Message
        $reason2 = if (Test-AccessDeniedMessage $err2) { 'gpo_access_denied' } else { 'gpo_remote_failed' }
        Write-Result @{
          ok = $false
          gpo = 'fail'
          reason = $reason2
          dc = $dcHost
          gpo_via = 'invoke_command_dc_credman'
          error = $err2
          need = 'credman:PriorityAirc/ExtensionAdmin must be a domain principal allowed to manage GPOs on the DC (Remote Management Users / GPO edit)'
          credman_tried = $true
          credman_present = $true
          wrote_gpo = $false
          browsers = @('chrome', 'edge')
          policy_names = @($GpoName)
        }
        exit 5
      }
    }
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
  if ($credmanTried) { $ht['gpo_via'] = 'invoke_command_dc_credman'; $ht['credman_tried'] = $true }
  Write-Result $ht
  if ($ht['ok']) { exit 0 } else { exit 5 }
} catch {
  $emsg = [string]$_.Exception.Message
  $denied = $useRemote -and (Test-AccessDeniedMessage $emsg)
  Write-Result @{
    ok = $false
    gpo = 'fail'
    reason = $(if ($denied) { 'gpo_access_denied' } elseif ($useRemote) { 'gpo_remote_failed' } else { 'gpo_write_failed' })
    dc = $dcHost
    gpo_via = $(if ($useRemote) { 'invoke_command_dc' } else { 'local_grouppolicy' })
    error = $emsg
    need = $(if ($denied) { 'credman:PriorityAirc/ExtensionAdmin (GPO edit / Remote Management on DC); computer account LocalSystem cannot Invoke-Command to DC' } else { $null })
    credman_tried = $credmanTried
    wrote_gpo = $false
    browsers = @('chrome', 'edge')
    policy_names = @($GpoName)
  }
  exit 5
}
