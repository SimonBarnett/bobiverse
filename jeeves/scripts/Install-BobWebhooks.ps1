#Requires -Version 5.1
<#
.SYNOPSIS
  Idempotent IIS URL Rewrite rules for bobcallback on 127.0.0.1:7700
  (report, digest, git, intake, jira). Site default: irc-ntsa.
#>
[CmdletBinding()]
param(
    [string]$SiteName = 'irc-ntsa',
    [string]$PhysicalPath = 'C:\inetpub\irc-ntsa',
    [string]$Backend = 'http://127.0.0.1:7700',
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$appcmd = Join-Path $env:SystemRoot 'system32\inetsrv\appcmd.exe'
if (-not (Test-Path -LiteralPath $appcmd)) {
    Write-Host 'WARN appcmd.exe missing — skip IIS webhook install'
    return
}

$webConfig = Join-Path $PhysicalPath 'web.config'
if (-not (Test-Path -LiteralPath $PhysicalPath)) {
    New-Item -ItemType Directory -Force -Path $PhysicalPath | Out-Null
}

$rules = @(
    @{ Name = 'BobReportWebhook'; Match = '^bob/v1/report$'; Url = "$Backend/bob/v1/report" },
    @{ Name = 'BobDigestWebhook'; Match = '^bob/v1/digest$'; Url = "$Backend/bob/v1/digest" },
    @{ Name = 'BobGitWebhook'; Match = '^bob/v1/git$'; Url = "$Backend/bob/v1/git" },
    @{ Name = 'BobIntakeWebhook'; Match = '^bob/v1/intake'; Url = "$Backend/bob/v1/intake" },
    @{ Name = 'BobJiraWebhook'; Match = '^bob/v1/jira'; Url = "$Backend/bob/v1/jira" }
)

# Prefer editing web.config rewrite section if present; else write minimal config
$rewriteXml = @"
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="BobReportWebhook" stopProcessing="true">
          <match url="^bob/v1/report$" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/report" />
        </rule>
        <rule name="BobDigestWebhook" stopProcessing="true">
          <match url="^bob/v1/digest$" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/digest" />
        </rule>
        <rule name="BobGitWebhook" stopProcessing="true">
          <match url="^bob/v1/git$" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/git" />
        </rule>
        <rule name="BobIntakeWebhook" stopProcessing="true">
          <match url="^bob/v1/intake(.*)" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/intake{R:1}" />
        </rule>
        <rule name="BobJiraWebhook" stopProcessing="true">
          <match url="^bob/v1/jira(.*)" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/jira{R:1}" />
        </rule>
      </rules>
    </rewrite>
    <security>
      <requestFiltering allowDoubleEscaping="true">
        <fileExtensions allowUnlisted="true" />
        <hiddenSegments><clear /></hiddenSegments>
      </requestFiltering>
    </security>
  </system.webServer>
</configuration>
"@

if ($WhatIf) {
    Write-Host "WhatIf would write rewrite rules to $webConfig backend=$Backend"
    return
}

if (Test-Path -LiteralPath $webConfig) {
    $raw = Get-Content -LiteralPath $webConfig -Raw -ErrorAction Stop
    # Force backend port alignment away from ephemeral 19781
    $updated = $raw -replace '127\.0\.0\.1:\d+', ([uri]$Backend).Authority
    if ($updated -notmatch 'bob/v1/intake') {
        # Insert intake/jira rules before closing </rules> if rewrite exists
        if ($updated -match '</rules>') {
            $extra = @"
        <rule name="BobIntakeWebhook" stopProcessing="true">
          <match url="^bob/v1/intake(.*)" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/intake{R:1}" />
        </rule>
        <rule name="BobJiraWebhook" stopProcessing="true">
          <match url="^bob/v1/jira(.*)" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/jira{R:1}" />
        </rule>
"@
            $updated = $updated -replace '</rules>', ($extra + '</rules>')
        } else {
            $updated = $rewriteXml
        }
    }
    if ($updated -notmatch 'bob/v1/digest' -and $updated -match '</rules>') {
        # Public GET /bob/v1/digest (same body as /bob/v1/report). Idempotent: only added when missing.
        $digestRule = @"
        <rule name="BobDigestWebhook" stopProcessing="true">
          <match url="^bob/v1/digest$" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/digest" />
        </rule>
"@
        $updated = $updated -replace '</rules>', ($digestRule + '</rules>')
    }
    [IO.File]::WriteAllText($webConfig, $updated, [Text.UTF8Encoding]::new($false))
    Write-Host "INFO updated $webConfig"
} else {
    [IO.File]::WriteAllText($webConfig, $rewriteXml, [Text.UTF8Encoding]::new($false))
    Write-Host "INFO created $webConfig"
}

# Ensure ARR proxy enabled (best-effort)
try {
    & $appcmd set config -section:system.webServer/proxy /enabled:true /commit:apphost | Out-Null
} catch {
    Write-Host "WARN could not enable ARR proxy: $($_.Exception.Message)"
}
Write-Host 'INFO Install-BobWebhooks done'