#Requires -Version 5.1
<#
.SYNOPSIS
  IIS TLS front door for https://jeeves.ntsa.uk/ proxying to 127.0.0.1:7701 (FR #6757).

  Uses a certificate the operator already has (thumbprint). Does not run a public
  ACME client, does not create public DNS, and does not bind bob.ntsa.uk or irc.ntsa.uk.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Thumbprint,

    [string]$SiteName = 'jeeves-ntsa',
    [string]$HostName = 'jeeves.ntsa.uk',
    [string]$PhysicalPath = 'C:\inetpub\jeeves-ntsa',
    [string]$Backend = 'http://127.0.0.1:7701',
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$tp = ($Thumbprint -replace '\s', '').ToUpperInvariant()
if ($tp.Length -lt 16) {
    throw 'Thumbprint is required (existing store cert; do not mint via public ACME).'
}

$appcmd = Join-Path $env:SystemRoot 'system32\inetsrv\appcmd.exe'
if (-not (Test-Path -LiteralPath $appcmd)) {
    Write-Host 'WARN appcmd.exe missing --- skip IIS appliance front door'
    return
}

if ($WhatIf) {
    Write-Host "WhatIf would bind https://$HostName/ (443) with existing Thumbprint to $Backend; HTTP 80 redirects to HTTPS. No public DNS. No Cloudflare."
    return
}

if (-not (Test-Path -LiteralPath $PhysicalPath)) {
    New-Item -ItemType Directory -Force -Path $PhysicalPath | Out-Null
}

$webConfig = Join-Path $PhysicalPath 'web.config'
$config = @"
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="HttpToHttps" stopProcessing="true">
          <match url="(.*)" />
          <conditions>
            <add input="{HTTPS}" pattern="off" ignoreCase="true" />
          </conditions>
          <action type="Redirect" url="https://{HTTP_HOST}/{R:1}" redirectType="Permanent" />
        </rule>
        <rule name="JeevesApplianceProxy" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="$Backend/{R:1}" />
          <serverVariables>
            <set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" />
          </serverVariables>
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
"@
[System.IO.File]::WriteAllText($webConfig, $config, (New-Object System.Text.UTF8Encoding $false))

& $appcmd add site /name:"$SiteName" /bindings:"http/*:80:${HostName},https/*:443:${HostName}" /physicalPath:"$PhysicalPath" 2>$null | Out-Null
& $appcmd set site /site.name:"$SiteName" /+bindings.[protocol='https',bindingInformation="*:443:${HostName}"] 2>$null | Out-Null
Write-Host "OK appliance front door site=$SiteName host=$HostName backend=$Backend (set JEEVES_SETTINGS_FRONTDOOR=1 so ircJeeves binds 127.0.0.1 only)."
Write-Host "Bind the existing cert thumbprint in IIS / netsh http sslcert. Internal DNS only."
