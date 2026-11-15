#Requires -Version 5.1
<#
.SYNOPSIS
  Idempotent IIS URL Rewrite rules for bobcallback on 127.0.0.1:7700
  (report, digest, git, intake, jira, hours, jeeves appliance). Site default: irc-ntsa.
#>
[CmdletBinding()]
param(
    [string]$SiteName = 'irc-ntsa',
    [string]$PhysicalPath = 'C:\inetpub\irc-ntsa',
    [string]$Backend = 'http://127.0.0.1:7700',
    # FR #7414: override www source (tests / alternate trees). Default: jeeves/www/irc-ntsa beside this script.
    [string]$WwwSource = '',
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$appcmd = Join-Path $env:SystemRoot 'system32\inetsrv\appcmd.exe'
$hasAppcmd = Test-Path -LiteralPath $appcmd
if (-not $hasAppcmd) {
    Write-Host 'WARN appcmd.exe missing --- write web.config only; skip ARR enable'
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
    @{ Name = 'BobJiraWebhook'; Match = '^bob/v1/jira'; Url = "$Backend/bob/v1/jira" },
    @{ Name = 'BobHoursWebhook'; Match = '^bob/v1/hours'; Url = "$Backend/bob/v1/hours" },
    @{ Name = 'BobJeevesAppliance'; Match = '^jeeves(/.*)?$'; Url = "$Backend/jeeves" }
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
        <rule name="BobHoursWebhook" stopProcessing="true">
          <match url="^bob/v1/hours(.*)" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/hours{R:1}" />
        </rule>
        <rule name="BobJeevesAppliance" stopProcessing="true">
          <match url="^jeeves(/.*)?$" ignoreCase="true" />
          <conditions>
            <add input="{REQUEST_URI}" pattern="/jeeves/assets/" negate="true" />
            <add input="{REQUEST_URI}" pattern="/jeeves/commands" negate="true" />
          </conditions>
          <action type="Rewrite" url="$Backend/jeeves{R:1}" />
        </rule>
      </rules>
    </rewrite>
    <security>
      <requestFiltering allowDoubleEscaping="true">
        <fileExtensions allowUnlisted="true">
          <add fileExtension=".ico" allowed="true" />
          <add fileExtension=".png" allowed="true" />
        </fileExtensions>
        <hiddenSegments><clear /></hiddenSegments>
      </requestFiltering>
    </security>
  </system.webServer>
</configuration>
"@

$wwwSrcDefault = Join-Path $PSScriptRoot '..\www\irc-ntsa'
$wwwSrc = if ($WwwSource) { $WwwSource } else { $wwwSrcDefault }
if ($WhatIf) {
    Write-Host "WhatIf would write rewrite rules to $webConfig backend=$Backend"
    Write-Host "WhatIf FR #7414 www publish from $wwwSrc -> $PhysicalPath : site.css, downloads/, jeeves/commands/, docs/, index.html"
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
    if ($updated -notmatch 'bob/v1/hours' -and $updated -match '</rules>') {
        # FR #3450: hours webhook (create/list/summary/export + heartbeat/close/withdraw).
        $hoursRule = @"
        <rule name="BobHoursWebhook" stopProcessing="true">
          <match url="^bob/v1/hours(.*)" ignoreCase="true" />
          <action type="Rewrite" url="$Backend/bob/v1/hours{R:1}" />
        </rule>
"@
        $updated = $updated -replace '</rules>', ($hoursRule + '</rules>')
    }
    if ($updated -notmatch 'BobJeevesAppliance' -and $updated -match '</rules>') {
        # FR #6903: /jeeves appliance login -> bobcallback (FR #6815/6818).
        # FR #7414 / #7413: skip static /jeeves/commands (and assets) for IIS.
        $jeevesRule = @"
        <rule name="BobJeevesAppliance" stopProcessing="true">
          <match url="^jeeves(/.*)?$" ignoreCase="true" />
          <conditions>
            <add input="{REQUEST_URI}" pattern="/jeeves/assets/" negate="true" />
            <add input="{REQUEST_URI}" pattern="/jeeves/commands" negate="true" />
          </conditions>
          <action type="Rewrite" url="$Backend/jeeves{R:1}" />
        </rule>
"@
        $updated = $updated -replace '</rules>', ($jeevesRule + '</rules>')
    }
    if ($updated -match 'BobJeevesAppliance' -and ($updated -notmatch 'jeeves/assets/' -or $updated -notmatch 'jeeves/commands')) {
        $jeevesRuleUp = @"
        <rule name="BobJeevesAppliance" stopProcessing="true">
          <match url="^jeeves(/.*)?$" ignoreCase="true" />
          <conditions>
            <add input="{REQUEST_URI}" pattern="/jeeves/assets/" negate="true" />
            <add input="{REQUEST_URI}" pattern="/jeeves/commands" negate="true" />
          </conditions>
          <action type="Rewrite" url="$Backend/jeeves{R:1}" />
        </rule>
"@
        $updated = [regex]::Replace(
            $updated,
            '(?s)<rule name="BobJeevesAppliance".*?</rule>',
            $jeevesRuleUp.TrimEnd()
        )
    }
    if ($updated -notmatch 'fileExtension="\.ico"') {
        $icoAllow = '<add fileExtension=".ico" allowed="true" />'
        if ($updated -match '<fileExtensions allowUnlisted="true"\s*/>') {
            $updated = $updated -replace '<fileExtensions allowUnlisted="true"\s*/>',
                ("<fileExtensions allowUnlisted=`"true`">$icoAllow<add fileExtension=`".png`" allowed=`"true`" /></fileExtensions>")
        } elseif ($updated -match '<fileExtensions allowUnlisted="true">') {
            $updated = $updated -replace '<fileExtensions allowUnlisted="true">',
                ("<fileExtensions allowUnlisted=`"true`">$icoAllow")
        }
    }
    [IO.File]::WriteAllText($webConfig, $updated, [Text.UTF8Encoding]::new($false))
    Write-Host "INFO updated $webConfig"
} else {
    [IO.File]::WriteAllText($webConfig, $rewriteXml, [Text.UTF8Encoding]::new($false))
    Write-Host "INFO created $webConfig"
}

# Ensure ARR proxy enabled (best-effort; needs appcmd)
if ($hasAppcmd) {
    try {
        & $appcmd set config -section:system.webServer/proxy /enabled:true /commit:apphost | Out-Null
    } catch {
        Write-Host "WARN could not enable ARR proxy: $($_.Exception.Message)"
    }
}
# FR #6453 / #7410 / #7414: sync static www (CSS, downloads, commands, docs) into IIS physical path.
# Operators: re-run Install-BobWebhooks.ps1 (or compose/sync) after git pull to refresh bob.ntsa.uk www.
if (Test-Path -LiteralPath $wwwSrc) {
    $null = New-Item -ItemType Directory -Force -Path $PhysicalPath
    $indexSrc = Join-Path $wwwSrc 'index.html'
    if (Test-Path -LiteralPath $indexSrc) {
        Copy-Item -LiteralPath $indexSrc -Destination (Join-Path $PhysicalPath 'index.html') -Force
    }
    $siteCss = Join-Path $wwwSrc 'site.css'
    if (Test-Path -LiteralPath $siteCss) {
        Copy-Item -LiteralPath $siteCss -Destination (Join-Path $PhysicalPath 'site.css') -Force
    }
    $docsSrc = Join-Path $wwwSrc 'docs'
    if (Test-Path -LiteralPath $docsSrc) {
        $docsDst = Join-Path $PhysicalPath 'docs'
        if (Test-Path -LiteralPath $docsDst) {
            Remove-Item -LiteralPath $docsDst -Recurse -Force
        }
        Copy-Item -LiteralPath $docsSrc -Destination $docsDst -Recurse -Force
    }
    $downloadsSrc = Join-Path $wwwSrc 'downloads'
    if (Test-Path -LiteralPath $downloadsSrc) {
        $downloadsDst = Join-Path $PhysicalPath 'downloads'
        if (Test-Path -LiteralPath $downloadsDst) {
            Remove-Item -LiteralPath $downloadsDst -Recurse -Force
        }
        Copy-Item -LiteralPath $downloadsSrc -Destination $downloadsDst -Recurse -Force
    }
    # FR #7414 / #7413: public /jeeves/commands (rewrite skips this prefix).
    $commandsSrc = Join-Path $wwwSrc 'jeeves\commands'
    if (Test-Path -LiteralPath $commandsSrc) {
        $commandsDst = Join-Path $PhysicalPath 'jeeves\commands'
        if (Test-Path -LiteralPath $commandsDst) {
            Remove-Item -LiteralPath $commandsDst -Recurse -Force
        }
        $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $commandsDst)
        Copy-Item -LiteralPath $commandsSrc -Destination $commandsDst -Recurse -Force
    }
    Write-Host "INFO synced FR #6453/#7410/#7414 www (site.css, downloads, jeeves/commands, docs) from $wwwSrc -> $PhysicalPath"
} else {
    Write-Host "WARN FR #7414 www source missing: $wwwSrc"
}

# FR #7411: IIS static map /jeeves/assets/* (rewrite skips this prefix).
$assetDst = Join-Path $PhysicalPath 'jeeves\assets'
$null = New-Item -ItemType Directory -Force -Path $assetDst
$butlerCands = @(
    (Join-Path $PSScriptRoot '..\assets\jeeves-butler.ico'),
    (Join-Path $PSScriptRoot '..\..\jeeves\assets\jeeves-butler.ico')
)
$logoCands = @(
    (Join-Path $PSScriptRoot '..\assets\ntsa-gut-logo.png'),
    (Join-Path $PSScriptRoot '..\..\bob\tray\assets\ntsa-gut-logo.png'),
    (Join-Path $PSScriptRoot '..\docs\appliance-ui-20261112\mocks\ntsa-gut-logo.png')
)
foreach ($src in $butlerCands) {
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $assetDst 'jeeves-butler.ico') -Force
        Write-Host "INFO FR #7411 staged jeeves\assets\jeeves-butler.ico"
        break
    }
}
foreach ($src in $logoCands) {
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $assetDst 'ntsa-gut-logo.png') -Force
        Write-Host "INFO FR #7411 staged jeeves\assets\ntsa-gut-logo.png"
        break
    }
}

Write-Host 'INFO Install-BobWebhooks done'
