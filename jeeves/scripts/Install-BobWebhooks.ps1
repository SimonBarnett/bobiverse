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
    # FR #8887: backups live under BackupRoot\_backup-www-<site leaf>, never inside the web root.
    [string]$BackupRoot = '',
    [switch]$WhatIf,
    # FR #7465: publish the site kit only. Do not call appcmd and do not touch the Jeeves service.
    [switch]$SiteKit,
    # FR #8803: www/assets publish is opt-in. -SiteKit implies publish. Default run is rules-only.
    [switch]$PublishWww
)
# FR #8803: SiteKit is the site-kit deploy path; it always publishes www.
$doPublishWww = [bool]($PublishWww -or $SiteKit)

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
          <remove fileExtension=".bak" />
          <add fileExtension=".bak" allowed="false" />
        </fileExtensions>
        <denyUrlSequences>
          <remove sequence="_backup-" />
          <add sequence="_backup-" />
          <remove sequence=".bak/" />
          <add sequence=".bak/" />
        </denyUrlSequences>
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


function Test-BobPathIsUnder {
    # FR #8887: true when Child equals Parent or is a descendant (separator-boundary, case-insensitive).
    param(
        [Parameter(Mandatory = $true)][string]$Child,
        [Parameter(Mandatory = $true)][string]$Parent
    )
    $c = [IO.Path]::GetFullPath($Child).TrimEnd('\', '/').ToLowerInvariant()
    $p = [IO.Path]::GetFullPath($Parent).TrimEnd('\', '/').ToLowerInvariant()
    if ($c -eq $p) { return $true }
    $sep = [string][IO.Path]::DirectorySeparatorChar
    return $c.StartsWith($p + $sep)
}

function Ensure-BackupRequestFiltering {
    # FR #8887: deny .bak extension and _backup- / .bak/ URL sequences. Never edit <rewrite>.
    # Idempotent: if already valid, return unchanged.
    param([Parameter(Mandatory = $true)][string]$Cfg)
    $nl = [Environment]::NewLine
    $bakOk = [regex]::IsMatch($Cfg, '(?i)<add\s+fileExtension="\.bak"\s+allowed="false"\s*/>')
    $seq1 = [regex]::IsMatch($Cfg, '(?i)<add\s+sequence="_backup-"\s*/>')
    $seq2 = [regex]::IsMatch($Cfg, '(?i)<add\s+sequence="\.bak/"\s*/>')
    $rfCount = ([regex]::Matches($Cfg, '(?i)<requestFiltering\b')).Count
    if ($bakOk -and $seq1 -and $seq2 -and $rfCount -eq 1) {
        return $Cfg
    }

    $bakRemove = '<remove fileExtension=".bak" />'
    $bakAdd = '<add fileExtension=".bak" allowed="false" />'
    $defSeq = (
        '        <denyUrlSequences>' + $nl +
        '          <remove sequence="_backup-" />' + $nl +
        '          <add sequence="_backup-" />' + $nl +
        '          <remove sequence=".bak/" />' + $nl +
        '          <add sequence=".bak/" />' + $nl +
        '        </denyUrlSequences>'
    )

    # Expand self-closing requestFiltering so children can be added.
    if ($Cfg -match '(?is)<requestFiltering\b[^>]*/>') {
        $Cfg = [regex]::Replace(
            $Cfg,
            '(?is)<requestFiltering\b([^>]*)/>',
            ('<requestFiltering$1>' + $nl +
             '        <fileExtensions allowUnlisted="true">' + $nl +
             '          <add fileExtension=".ico" allowed="true" />' + $nl +
             '          <add fileExtension=".png" allowed="true" />' + $nl +
             '          ' + $bakRemove + $nl +
             '          ' + $bakAdd + $nl +
             '        </fileExtensions>' + $nl +
             $defSeq + $nl +
             '        <hiddenSegments><clear /></hiddenSegments>' + $nl +
             '      </requestFiltering>'),
            1
        )
        return $Cfg
    }

    $feSelf = '(?is)<fileExtensions\b[^>]*/>'
    if ($Cfg -match $feSelf) {
        $Cfg = [regex]::Replace(
            $Cfg,
            $feSelf,
            ('<fileExtensions allowUnlisted="true">' + $nl +
             '          <add fileExtension=".ico" allowed="true" />' + $nl +
             '          <add fileExtension=".png" allowed="true" />' + $nl +
             '          ' + $bakRemove + $nl +
             '          ' + $bakAdd + $nl +
             '        </fileExtensions>'),
            1
        )
    } elseif ($Cfg -match '(?is)<fileExtensions\b[^>]*>') {
        $Cfg = [regex]::Replace(
            $Cfg,
            '(?is)(<fileExtensions\b[^>]*>)(.*?)(</fileExtensions>)',
            {
                param($m)
                $inner = $m.Groups[2].Value
                $inner = [regex]::Replace($inner, '(?im)^\s*<remove\s+fileExtension="\.bak"\s*/>\s*', '')
                $inner = [regex]::Replace($inner, '(?im)^\s*<add\s+fileExtension="\.bak"[^/]*/>\s*', '')
                $inner = $inner.TrimEnd() + $nl + '          ' + $bakRemove + $nl + '          ' + $bakAdd + $nl + '        '
                return $m.Groups[1].Value + $inner + $m.Groups[3].Value
            },
            1
        )
    } elseif ($Cfg -match '(?is)<requestFiltering\b[^>]*>') {
        $block = '        <fileExtensions allowUnlisted="true">' + $nl +
            '          <add fileExtension=".ico" allowed="true" />' + $nl +
            '          <add fileExtension=".png" allowed="true" />' + $nl +
            '          ' + $bakRemove + $nl +
            '          ' + $bakAdd + $nl +
            '        </fileExtensions>' + $nl
        $Cfg = [regex]::Replace($Cfg, '(?is)(<requestFiltering\b[^>]*>)', ('${1}' + $nl + $block), 1)
    } elseif ($Cfg -match '(?is)<security\b[^>]*>') {
        $block = '      <requestFiltering allowDoubleEscaping="true">' + $nl +
            '        <fileExtensions allowUnlisted="true">' + $nl +
            '          <add fileExtension=".ico" allowed="true" />' + $nl +
            '          <add fileExtension=".png" allowed="true" />' + $nl +
            '          ' + $bakRemove + $nl +
            '          ' + $bakAdd + $nl +
            '        </fileExtensions>' + $nl +
            $defSeq + $nl +
            '        <hiddenSegments><clear /></hiddenSegments>' + $nl +
            '      </requestFiltering>' + $nl
        $Cfg = [regex]::Replace($Cfg, '(?is)(<security\b[^>]*>)', ('${1}' + $nl + $block), 1)
        return $Cfg
    } elseif ($Cfg -match '(?is)</system\.webServer>') {
        $block = '    <security>' + $nl +
            '      <requestFiltering allowDoubleEscaping="true">' + $nl +
            '        <fileExtensions allowUnlisted="true">' + $nl +
            '          <add fileExtension=".ico" allowed="true" />' + $nl +
            '          <add fileExtension=".png" allowed="true" />' + $nl +
            '          ' + $bakRemove + $nl +
            '          ' + $bakAdd + $nl +
            '        </fileExtensions>' + $nl +
            $defSeq + $nl +
            '        <hiddenSegments><clear /></hiddenSegments>' + $nl +
            '      </requestFiltering>' + $nl +
            '    </security>' + $nl
        $Cfg = [regex]::Replace($Cfg, '(?is)</system\.webServer>', ($block + '  </system.webServer>'), 1)
        return $Cfg
    }

    # denyUrlSequences: replace existing (consume leading indent) or insert before </requestFiltering>.
    if ($Cfg -match '(?is)<denyUrlSequences\b') {
        $Cfg = [regex]::Replace(
            $Cfg,
            '(?im)^[ \t]*<denyUrlSequences\b[^>]*>.*?</denyUrlSequences>',
            $defSeq,
            1
        )
    } elseif ($Cfg -match '(?is)</requestFiltering>') {
        $Cfg = [regex]::Replace(
            $Cfg,
            '(?im)^[ \t]*</requestFiltering>',
            ($defSeq + $nl + '      </requestFiltering>'),
            1
        )
    }
    return $Cfg
}

function Get-BobOwnedRuleXml {
    # FR #8803: owned rewrite rules only (never websocket / foreign rules).
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$BackendUrl
    )
    switch ($Name) {
        'BobReportWebhook' {
            return @"
        <rule name="BobReportWebhook" stopProcessing="true">
          <match url="^bob/v1/report$" ignoreCase="true" />
          <action type="Rewrite" url="$BackendUrl/bob/v1/report" />
        </rule>
"@
        }
        'BobDigestWebhook' {
            return @"
        <rule name="BobDigestWebhook" stopProcessing="true">
          <match url="^bob/v1/digest$" ignoreCase="true" />
          <action type="Rewrite" url="$BackendUrl/bob/v1/digest" />
        </rule>
"@
        }
        'BobGitWebhook' {
            return @"
        <rule name="BobGitWebhook" stopProcessing="true">
          <match url="^bob/v1/git$" ignoreCase="true" />
          <action type="Rewrite" url="$BackendUrl/bob/v1/git" />
        </rule>
"@
        }
        'BobIntakeWebhook' {
            return @"
        <rule name="BobIntakeWebhook" stopProcessing="true">
          <match url="^bob/v1/intake(.*)" ignoreCase="true" />
          <action type="Rewrite" url="$BackendUrl/bob/v1/intake{R:1}" />
        </rule>
"@
        }
        'BobJiraWebhook' {
            return @"
        <rule name="BobJiraWebhook" stopProcessing="true">
          <match url="^bob/v1/jira(.*)" ignoreCase="true" />
          <action type="Rewrite" url="$BackendUrl/bob/v1/jira{R:1}" />
        </rule>
"@
        }
        'BobHoursWebhook' {
            return @"
        <rule name="BobHoursWebhook" stopProcessing="true">
          <match url="^bob/v1/hours(.*)" ignoreCase="true" />
          <action type="Rewrite" url="$BackendUrl/bob/v1/hours{R:1}" />
        </rule>
"@
        }
        'BobModelsWebhook' {
            # FR #8708: public IIS rewrite is GET|HEAD only (PUT stays direct/LAN).
            return @"
        <rule name="BobModelsWebhook" stopProcessing="true">
          <match url="^bob/v1/models(.*)" ignoreCase="true" />
          <conditions>
            <add input="{REQUEST_METHOD}" pattern="^GET|HEAD$" />
          </conditions>
          <action type="Rewrite" url="$BackendUrl/bob/v1/models{R:1}" />
        </rule>
"@
        }
        'BobJeevesAppliance' {
            return @"
        <rule name="BobJeevesAppliance" stopProcessing="true">
          <match url="^jeeves(/.*)?$" ignoreCase="true" />
          <conditions>
            <add input="{REQUEST_URI}" pattern="/jeeves/assets/" negate="true" />
            <add input="{REQUEST_URI}" pattern="/jeeves/commands" negate="true" />
          </conditions>
          <action type="Rewrite" url="$BackendUrl/jeeves{R:1}" />
        </rule>
"@
        }
        default { throw "unknown Bob owned rule: $Name" }
    }
}

function Format-BobOwnedRuleBlock {
    # Stable nested indent matching the fresh $rewriteXml template (FR #8803 / #8934).
    # Base rule line at 8 spaces; each open element nest +2. Flat 8-on-every-line
    # rewrote template children on the second install and failed byte-stability.
    param([Parameter(Mandatory = $true)][string]$RuleXml)
    $lines = New-Object System.Collections.Generic.List[string]
    $depth = 0
    foreach ($line in (($RuleXml.Trim()) -split "`r?`n")) {
        $t = $line.Trim()
        if (-not $t) { continue }
        if ($t.StartsWith('</')) {
            $depth = [Math]::Max(0, $depth - 1)
        }
        [void]$lines.Add((' ' * (8 + (2 * $depth))) + $t)
        $isOpen = $t.StartsWith('<') -and -not $t.StartsWith('</') -and -not $t.StartsWith('<?')
        $selfClose = $t.EndsWith('/>') -or ($t.Contains('</') -and -not $t.StartsWith('</'))
        if ($isOpen -and -not $selfClose) {
            $depth++
        }
    }
    return [string]::Join("`n", $lines.ToArray())
}

function Set-BobOwnedRewriteRule {
    # Replace or insert one owned rule by name. Leaves every other rule untouched.
    param(
        [Parameter(Mandatory = $true)][string]$Cfg,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$RuleXml
    )
    # Include leading indent on the line so replace does not stack spaces each run.
    $pattern = '(?ms)^[ \t]*<rule\s+name="' + [regex]::Escape($Name) + '"[^>]*>.*?</rule>'
    $formatted = Format-BobOwnedRuleBlock -RuleXml $RuleXml
    if ([regex]::IsMatch($Cfg, $pattern)) {
        $existing = [regex]::Match($Cfg, $pattern).Value
        # FR #8934: skip rewrite when the owned rule is already the canonical block.
        if ($existing -eq $formatted) {
            return $Cfg
        }
        return [regex]::Replace($Cfg, $pattern, $formatted, 1)
    }
    # Replace the whole </rules> line (including indent) so inserts do not stack spaces.
    if ([regex]::IsMatch($Cfg, '(?m)^[ \t]*</rules>')) {
        return [regex]::Replace($Cfg, '(?m)^[ \t]*</rules>', ($formatted + "`n" + '      </rules>'), 1)
    }
    return $Cfg
}

function Write-BobWebhooksRollback {
    param(
        [Parameter(Mandatory = $true)][string]$WebConfigPath,
        [Parameter(Mandatory = $true)][string]$BackupPath,
        [Parameter(Mandatory = $true)][string]$RollbackPath
    )
    $bakEsc = $BackupPath.Replace("'", "''")
    $cfgEsc = $WebConfigPath.Replace("'", "''")
    $body = @"
#Requires -Version 5.1
# FR #8803: restore web.config from Install-BobWebhooks backup.
`$ErrorActionPreference = 'Stop'
`$bak = '$bakEsc'
`$cfg = '$cfgEsc'
if (-not (Test-Path -LiteralPath `$bak)) { throw "backup missing: `$bak" }
Copy-Item -LiteralPath `$bak -Destination `$cfg -Force
Write-Host "INFO restored `$cfg from `$bak"
"@
    [IO.File]::WriteAllText($RollbackPath, $body, [Text.UTF8Encoding]::new($false))
}

$script:BobOwnedRuleNames = @(
    'BobReportWebhook',
    'BobDigestWebhook',
    'BobGitWebhook',
    'BobIntakeWebhook',
    'BobJiraWebhook',
    'BobHoursWebhook',
    'BobModelsWebhook',
    'BobJeevesAppliance'
)

# FR #7517: extracted kits ship www/ beside the installer; checkouts keep ..\www\irc-ntsa.
$kitWww = Join-Path $PSScriptRoot 'www'
$wwwSrcDefault = if ((-not $WwwSource) -and (Test-Path -LiteralPath (Join-Path $kitWww 'index.html'))) {
    $kitWww
} else {
    Join-Path $PSScriptRoot '..\www\irc-ntsa'
}
$wwwSrc = if ($WwwSource) { $WwwSource } else { $wwwSrcDefault }

# FR #8887: one off-root backup directory for site snapshot + web.config copy.
if (-not $BackupRoot) {
    $BackupRoot = Split-Path -Parent $PhysicalPath
}
$backupDir = Join-Path $BackupRoot ('_backup-www-' + (Split-Path -Leaf $PhysicalPath))
$siteKitBak = Join-Path $backupDir 'site'
$configBak = Join-Path $backupDir 'web.config'
$physFull = [IO.Path]::GetFullPath($PhysicalPath)
$wwwFull = [IO.Path]::GetFullPath($wwwSrc)
$bakFull = [IO.Path]::GetFullPath($backupDir)
if (Test-BobPathIsUnder -Child $bakFull -Parent $physFull) {
    throw "FR #8887 BackupRoot/backup dir must not be inside PhysicalPath: $bakFull"
}
if ((Test-Path -LiteralPath $wwwSrc) -and (Test-BobPathIsUnder -Child $bakFull -Parent $wwwFull)) {
    throw "FR #8887 BackupRoot/backup dir must not be inside WwwSource: $bakFull"
}
if (Test-BobPathIsUnder -Child $physFull -Parent $bakFull) {
    throw "FR #8887 PhysicalPath must not be inside backup dir: $physFull under $bakFull"
}

if ($WhatIf) {
    Write-Host "WhatIf would write Bob* rewrite rules in $webConfig backend=$Backend (websocket rules untouched)"
    Write-Host "WhatIf FR #8887 backup dir $bakFull (site + web.config)"
    if ($doPublishWww) {
        Write-Host "WhatIf FR #7414/#7442 www publish from $wwwSrc -> $PhysicalPath : site.css, favicon.ico, downloads/, jeeves/commands/, docs/, index.html"
    } else {
        Write-Host "WhatIf FR #8803 skipping www publish (pass -PublishWww or -SiteKit)"
    }
    return
}

# FR #7465 / #8887: full tree backup only when publishing www/site-kit (off-root).
if ($doPublishWww) {
    if (Test-Path -LiteralPath $siteKitBak) {
        Remove-Item -LiteralPath $siteKitBak -Recurse -Force
    }
    if (Test-Path -LiteralPath $PhysicalPath) {
        Copy-Item -LiteralPath $PhysicalPath -Destination $siteKitBak -Recurse -Force
    } else {
        New-Item -ItemType Directory -Force -Path $siteKitBak | Out-Null
    }
}
try {
if ($env:BOB_WEBHOOKS_FAIL_AFTER_BACKUP -eq '1') {
    throw 'FR #7465 forced site-kit failure'
}

$rollbackPs1 = Join-Path $PhysicalPath 'ROLLBACK-BobWebhooks.ps1'
if (Test-Path -LiteralPath $webConfig) {
    $raw = Get-Content -LiteralPath $webConfig -Raw -ErrorAction Stop
    # FR #8803: never blanket-replace 127.0.0.1:<port> (that retargeted WsircWebSocket7999 / IrcWebSocket7999).
    $updated = $raw
    if ($updated -notmatch '<rewrite>' -or $updated -notmatch '</rules>') {
        $updated = $rewriteXml
    } else {
        foreach ($rn in $script:BobOwnedRuleNames) {
            $ruleXml = Get-BobOwnedRuleXml -Name $rn -BackendUrl $Backend
            $updated = Set-BobOwnedRewriteRule -Cfg $updated -Name $rn -RuleXml $ruleXml
        }
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
    $updated = Ensure-IcoStaticContent -Cfg $updated
    # FR #8887: deny .bak / _backup- in requestFiltering (rewrite section untouched).
    $updated = Ensure-BackupRequestFiltering -Cfg $updated
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
    $rf = $probe.SelectNodes('//*[local-name()="requestFiltering"]')
    if ($rf.Count -ne 1) {
        throw "FR #8887 validation failed: $($rf.Count) requestFiltering sections"
    }
    $bakDenied = $probe.SelectNodes('//*[local-name()="fileExtensions"]/*[local-name()="add" and @fileExtension=".bak" and @allowed="false"]')
    if ($bakDenied.Count -ne 1) {
        throw "FR #8887 validation failed: expected one .bak allowed=false add"
    }
    $seqBackup = $probe.SelectNodes('//*[local-name()="denyUrlSequences"]/*[local-name()="add" and @sequence="_backup-"]')
    $seqBakDir = $probe.SelectNodes('//*[local-name()="denyUrlSequences"]/*[local-name()="add" and @sequence=".bak/"]')
    if ($seqBackup.Count -ne 1 -or $seqBakDir.Count -ne 1) {
        throw "FR #8887 validation failed: denyUrlSequences must add _backup- and .bak/"
    }
    # Canonicalize newlines so a second run is a no-op (FR #8803 idempotent).
    $normText = {
        param($t)
        $s = [string]$t
        $s = $s -replace "`r`n", "`n"
        $s = $s -replace "`r", "`n"
        # Collapse runs of spaces before newlines introduced by rule upsert formatting.
        $s = [regex]::Replace($s, '[ \t]+\n', "`n")
        return $s.TrimEnd() + "`n"
    }
    $updated = & $normText $updated
    $rawNorm = & $normText $raw
    if ($updated -eq $rawNorm) {
        Write-Host "INFO web.config Bob* rules already current (no write)"
    } else {
        $null = New-Item -ItemType Directory -Force -Path $backupDir
        Copy-Item -LiteralPath $webConfig -Destination $configBak -Force
        Write-BobWebhooksRollback -WebConfigPath $webConfig -BackupPath $configBak -RollbackPath $rollbackPs1
        try {
            # Write LF-canonical text; IIS accepts LF in web.config.
            [IO.File]::WriteAllText($webConfig, $updated, [Text.UTF8Encoding]::new($false))
            Write-Host "INFO updated $webConfig (backup $configBak; ROLLBACK $rollbackPs1)"
        } catch {
            if (Test-Path -LiteralPath $configBak) {
                Copy-Item -LiteralPath $configBak -Destination $webConfig -Force
                Write-Host "WARN FR #8803 rolled back web.config from backup: $($_.Exception.Message)"
            }
            throw
        }
    }
} else {
    # FR #8887: template already includes backup requestFiltering; write then off-root backup.
    # FR #8934: LF-canonicalize on create so the second install is a byte no-op.
    $fresh = [string]$rewriteXml
    $fresh = $fresh -replace "`r`n", "`n"
    $fresh = $fresh -replace "`r", "`n"
    $fresh = [regex]::Replace($fresh, '[ \t]+\n', "`n")
    $fresh = $fresh.TrimEnd() + "`n"
    [IO.File]::WriteAllText($webConfig, $fresh, [Text.UTF8Encoding]::new($false))
    $null = New-Item -ItemType Directory -Force -Path $backupDir
    Copy-Item -LiteralPath $webConfig -Destination $configBak -Force
    Write-BobWebhooksRollback -WebConfigPath $webConfig -BackupPath $configBak -RollbackPath $rollbackPs1
    Write-Host "INFO created $webConfig (backup $configBak; ROLLBACK $rollbackPs1)"
}

# Ensure ARR proxy enabled (best-effort; needs appcmd)
if ($hasAppcmd) {
    try {
        & $appcmd set config -section:system.webServer/proxy /enabled:true /commit:apphost | Out-Null
    } catch {
        Write-Host "WARN could not enable ARR proxy: $($_.Exception.Message)"
    }
}
if ($doPublishWww) {
# FR #6453 / #7410 / #7414 / #7442: sync static www (CSS, favicon, downloads, commands, docs) into IIS physical path.
# Operators: Install-BobWebhooks.ps1 -PublishWww (or -SiteKit) after git pull to refresh bob.ntsa.uk www.
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
        $stampScript = Join-Path $PSScriptRoot 'Stamp-PriorityAgentDownloads.ps1'
        $paHtml = Join-Path $downloadsDst 'index.html'
        if ((Test-Path -LiteralPath $stampScript) -and (Test-Path -LiteralPath $paHtml)) {
            try {
                & $stampScript -HtmlPath $paHtml
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
} else {
    Write-Host 'INFO FR #8803 skipping www/assets publish (pass -PublishWww or -SiteKit to enable)'
}

Write-Host 'INFO Install-BobWebhooks done'
} catch {
    if ($doPublishWww -and (Test-Path -LiteralPath $siteKitBak)) {
        if (Test-Path -LiteralPath $PhysicalPath) {
            Remove-Item -LiteralPath $PhysicalPath -Recurse -Force
        }
        Copy-Item -LiteralPath $siteKitBak -Destination $PhysicalPath -Recurse -Force
        Write-Host "WARN FR #7465 rolled back site kit from $siteKitBak : $($_.Exception.Message)"
    }
    throw
}
