#Requires -Version 5.1
<#
.SYNOPSIS
  Idempotent IIS URL Rewrite rules for bobcallback on 127.0.0.1:7700
  (report, digest, git, intake, jira, hours, models, jeeves appliance). Site default: irc-ntsa.
#>
[CmdletBinding()]
param(
    [string]$SiteName = 'irc-ntsa',
    [string]$PhysicalPath = 'C:\inetpub\irc-ntsa',
    [string]$Backend = 'http://127.0.0.1:7700',
    # FR #7414: override www source (tests / alternate trees). Default: jeeves/www/irc-ntsa beside this script.
    [string]$WwwSource = '',
    [switch]$WhatIf,
    # FR #7465: publish the site kit only. Do not call appcmd and do not touch the Jeeves service.
    [switch]$SiteKit
)

$ErrorActionPreference = 'Stop'
$appcmd = Join-Path $env:SystemRoot 'system32\inetsrv\appcmd.exe'
$hasAppcmd = Test-Path -LiteralPath $appcmd
if ($SiteKit) {
    $hasAppcmd = $false
}
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
    @{ Name = 'BobModelsWebhook'; Match = '^bob/v1/models'; Url = "$Backend/bob/v1/models" },
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
        <rule name="BobModelsWebhook" stopProcessing="true">
          <match url="^bob/v1/models(.*)" ignoreCase="true" />
          <conditions>
            <add input="{REQUEST_METHOD}" pattern="^GET|HEAD$" />
          </conditions>
          <action type="Rewrite" url="$Backend/bob/v1/models{R:1}" />
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
    <!-- FR #7442: serve site-root favicon without proxying to Jeeves -->
    <staticContent>
      <remove fileExtension=".ico" />
      <mimeMap fileExtension=".ico" mimeType="image/x-icon" />
    </staticContent>
  </system.webServer>
</configuration>
"@

function Ensure-IcoStaticContent {
    # FR #7460: exactly one <staticContent>; merge .ico remove+mimeMap; never append a second section.
    param([Parameter(Mandatory = $true)][string]$Cfg)
    $count = ([regex]::Matches($Cfg, '(?i)<staticContent\b')).Count
    $hasIcoMap = $Cfg -match '(?i)<mimeMap\b[^>]*fileExtension="\.ico"[^>]*mimeType="image/x-icon"|(?i)<mimeMap\b[^>]*mimeType="image/x-icon"[^>]*fileExtension="\.ico"'
    $hasIcoRemove = $Cfg -match '(?i)<remove\s+fileExtension="\.ico"'
    if ($count -eq 1 -and $hasIcoMap -and $hasIcoRemove) {
        return $Cfg
    }
    $preserved = New-Object System.Collections.Generic.List[string]
    $Cfg2 = [regex]::Replace(
        $Cfg,
        '(?is)\s*<staticContent\b[^>]*>(.*?)</staticContent>',
        {
            param($m)
            $inner = $m.Groups[1].Value
            foreach ($line in ($inner -split "`r?`n")) {
                $t = $line.Trim()
                if (-not $t) { continue }
                if ($t -match '(?i)fileExtension="\.ico"') { continue }
                if (-not $preserved.Contains($t)) { [void]$preserved.Add($t) }
            }
            return ''
        }
    )
    $kids = New-Object System.Collections.Generic.List[string]
    foreach ($p in $preserved) { [void]$kids.Add(('      ' + $p)) }
    [void]$kids.Add('      <remove fileExtension=".ico" />')
    [void]$kids.Add('      <mimeMap fileExtension=".ico" mimeType="image/x-icon" />')
    $nl = [Environment]::NewLine
    $block = '    <staticContent>' + $nl + [string]::Join($nl, $kids.ToArray()) + $nl + '    </staticContent>' + $nl
    if ($Cfg2 -match '</system\.webServer>') {
        return [regex]::Replace($Cfg2, '</system\.webServer>', ($block + '  </system.webServer>'), 1)
    }
    return ($Cfg2 + $block)
}

# FR #7517: extracted kits ship www/ beside the installer; checkouts keep ..\www\irc-ntsa.
$kitWww = Join-Path $PSScriptRoot 'www'
$wwwSrcDefault = if ((-not $WwwSource) -and (Test-Path -LiteralPath (Join-Path $kitWww 'index.html'))) {
    $kitWww
} else {
    Join-Path $PSScriptRoot '..\www\irc-ntsa'
}
$wwwSrc = if ($WwwSource) { $WwwSource } else { $wwwSrcDefault }
if ($WhatIf) {
    Write-Host "WhatIf would write rewrite rules to $webConfig backend=$Backend"
    Write-Host "WhatIf FR #7414/#7442 www publish from $wwwSrc -> $PhysicalPath : site.css, favicon.ico, downloads/, jeeves/commands/, docs/, index.html"
    return
}

# FR #7465: backup the published tree before this run so a failed site-kit deploy can roll back.
$siteKitBak = Join-Path (Split-Path -Parent $PhysicalPath) ((Split-Path -Leaf $PhysicalPath) + '.site-kit-bak')
if (Test-Path -LiteralPath $siteKitBak) {
    Remove-Item -LiteralPath $siteKitBak -Recurse -Force
}
if (Test-Path -LiteralPath $PhysicalPath) {
    Copy-Item -LiteralPath $PhysicalPath -Destination $siteKitBak -Recurse -Force
} else {
    New-Item -ItemType Directory -Force -Path $siteKitBak | Out-Null
}
try {
if ($env:BOB_WEBHOOKS_FAIL_AFTER_BACKUP -eq '1') {
    throw 'FR #7465 forced site-kit failure'
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
    if ($updated -notmatch 'bob/v1/models' -and $updated -match '</rules>') {
        # FR #8707 / MRB #8766 / FR #8708: GET|HEAD /bob/v1/models public IIS (PUT stays direct/LAN only).
        $modelsRule = @"
        <rule name="BobModelsWebhook" stopProcessing="true">
          <match url="^bob/v1/models(.*)" ignoreCase="true" />
          <conditions>
            <add input="{REQUEST_METHOD}" pattern="^GET|HEAD$" />
          </conditions>
          <action type="Rewrite" url="$Backend/bob/v1/models{R:1}" />
        </rule>
"@
        $updated = $updated -replace '</rules>', ($modelsRule + '</rules>')
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
    # FR #7442 / #7460: .ico MIME via a single <staticContent> (merge; never append a second).
    $backup = "$webConfig.fr7460.bak"
    Copy-Item -LiteralPath $webConfig -Destination $backup -Force
    try {
        $updated = Ensure-IcoStaticContent -Cfg $updated
        $probe = New-Object System.Xml.XmlDocument
        $probe.XmlResolver = $null
        $probe.LoadXml($updated)
        $sc = $probe.SelectNodes('//*[local-name()="staticContent"]')
        if ($sc.Count -gt 1) {
            throw "FR #7460 validation failed: $($sc.Count) staticContent sections"
        }
        $icoMaps = $probe.SelectNodes('//*[local-name()="mimeMap" and @fileExtension=".ico"]')
        if ($icoMaps.Count -gt 1) {
            throw "FR #7460 validation failed: $($icoMaps.Count) .ico mimeMap entries"
        }
        [IO.File]::WriteAllText($webConfig, $updated, [Text.UTF8Encoding]::new($false))
        Write-Host "INFO updated $webConfig"
    } catch {
        if (Test-Path -LiteralPath $backup) {
            Copy-Item -LiteralPath $backup -Destination $webConfig -Force
            Write-Host "WARN FR #7460 rolled back web.config from backup: $($_.Exception.Message)"
        }
        throw
    }
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
# FR #6453 / #7410 / #7414 / #7442: sync static www (CSS, favicon, downloads, commands, docs) into IIS physical path.
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
    # FR #7442: site-root favicon (Bob tray icon). Prefer checked-in jeeves/www/favicon.ico beside irc-ntsa.
    $faviconCands = @(
        (Join-Path $wwwSrc 'favicon.ico'),
        (Join-Path $wwwSrc '..\favicon.ico'),
        (Join-Path $PSScriptRoot '..\www\favicon.ico'),
        (Join-Path $PSScriptRoot '..\..\bob\tray\assets\bob-systray.ico')
    )
    $faviconStaged = $false
    foreach ($fav in $faviconCands) {
        if (Test-Path -LiteralPath $fav) {
            Copy-Item -LiteralPath $fav -Destination (Join-Path $PhysicalPath 'favicon.ico') -Force
            Write-Host "INFO FR #7442 staged favicon.ico from $fav"
            $faviconStaged = $true
            break
        }
    }
    if (-not $faviconStaged) {
        Write-Warning 'FR #7517 favicon.ico source not found'
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
        # FR #7643: stamp concrete PriorityAgent.exe hrefs (prerelease OK when that is where the installer is).
        $stamp = Join-Path $PSScriptRoot 'Stamp-PriorityAgentDownloads.ps1'
        $paHtml = Join-Path $downloadsDst 'index.html'
        if ((Test-Path -LiteralPath $stamp) -and (Test-Path -LiteralPath $paHtml)) {
            try {
                & $stamp -HtmlPath $paHtml
            } catch {
                Write-Warning ("FR #7643 stamp Priority Agent downloads failed: " + $_.Exception.Message)
            }
        }
    }
    # FR #7414 / #7413: public /jeeves/commands (rewrite skips this prefix; not behind settings cookie).
    $commandsSrc = Join-Path $wwwSrc 'jeeves\commands'
    if (Test-Path -LiteralPath $commandsSrc) {
        $commandsDst = Join-Path $PhysicalPath 'jeeves\commands'
        if (Test-Path -LiteralPath $commandsDst) {
            Remove-Item -LiteralPath $commandsDst -Recurse -Force
        }
        $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $commandsDst)
        Copy-Item -LiteralPath $commandsSrc -Destination $commandsDst -Recurse -Force
    }
    Write-Host "INFO synced FR #6453/#7410/#7413/#7414/#7442 www (site.css, favicon.ico, downloads, jeeves/commands, docs) from $wwwSrc -> $PhysicalPath"
} else {
    Write-Host "WARN FR #7414 www source missing: $wwwSrc"
}

# FR #7411: IIS static map /jeeves/assets/* (rewrite skips this prefix).
$assetDst = Join-Path $PhysicalPath 'jeeves\assets'
$null = New-Item -ItemType Directory -Force -Path $assetDst
# FR #7517: kit-local assets\ first so an extracted kit does not pick stray ..\assets.
$butlerCands = @(
    (Join-Path $PSScriptRoot 'assets\jeeves-butler.ico'),
    (Join-Path $PSScriptRoot '..\assets\jeeves-butler.ico'),
    (Join-Path $PSScriptRoot '..\..\jeeves\assets\jeeves-butler.ico')
)
$logoCands = @(
    (Join-Path $PSScriptRoot 'assets\ntsa-gut-logo.png'),
    (Join-Path $PSScriptRoot '..\assets\ntsa-gut-logo.png'),
    (Join-Path $PSScriptRoot '..\..\bob\tray\assets\ntsa-gut-logo.png'),
    (Join-Path $PSScriptRoot '..\docs\appliance-ui-20261112\mocks\ntsa-gut-logo.png')
)
$butlerStaged = $false
foreach ($src in $butlerCands) {
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $assetDst 'jeeves-butler.ico') -Force
        Write-Host "INFO FR #7411 staged jeeves\assets\jeeves-butler.ico"
        $butlerStaged = $true
        break
    }
}
if (-not $butlerStaged) {
    Write-Warning 'FR #7517 jeeves-butler.ico source not found'
}
$logoStaged = $false
foreach ($src in $logoCands) {
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $assetDst 'ntsa-gut-logo.png') -Force
        Write-Host "INFO FR #7411 staged jeeves\assets\ntsa-gut-logo.png"
        $logoStaged = $true
        break
    }
}
if (-not $logoStaged) {
    Write-Warning 'FR #7517 ntsa-gut-logo.png source not found'
}

Write-Host 'INFO Install-BobWebhooks done'
} catch {
    if (Test-Path -LiteralPath $siteKitBak) {
        if (Test-Path -LiteralPath $PhysicalPath) {
            Remove-Item -LiteralPath $PhysicalPath -Recurse -Force
        }
        Copy-Item -LiteralPath $siteKitBak -Destination $PhysicalPath -Recurse -Force
        Write-Host "WARN FR #7465 rolled back site kit from $siteKitBak : $($_.Exception.Message)"
    }
    throw
}
