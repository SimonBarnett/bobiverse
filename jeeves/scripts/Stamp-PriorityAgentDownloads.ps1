<#
.SYNOPSIS
  FR #7643: stamp concrete PriorityAgent.exe (+ sha256) download hrefs into the
  /downloads Priority Agent card HTML. Prefer newest non-draft non-prerelease with
  the installer; otherwise newest non-draft prerelease that has it.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$HtmlPath,

    [string]$ReleasesJsonPath,

    [string]$ApiUrl = 'https://api.github.com/repos/SimonBarnett/priority-mcp/releases?per_page=100',

    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-PaInstallerName([string]$Name) {
    return $Name -match '^PriorityAgent(-\d+\.\d+\.\d+)?\.exe$'
}

function Test-PaShaName([string]$Name) {
    return $Name -match '^PriorityAgent(-\d+\.\d+\.\d+)?\.exe\.sha256$'
}

function Select-PaRelease {
    param([object[]]$Releases)
    foreach ($rel in @($Releases)) {
        if (-not $rel -or $rel.draft) { continue }
        if ($rel.prerelease) { continue }
        $names = @($rel.assets | ForEach-Object { [string]$_.name })
        if ($names | Where-Object { Test-PaInstallerName $_ }) { return $rel }
    }
    foreach ($rel in @($Releases)) {
        if (-not $rel -or $rel.draft) { continue }
        $names = @($rel.assets | ForEach-Object { [string]$_.name })
        if ($names | Where-Object { Test-PaInstallerName $_ }) { return $rel }
    }
    return $null
}

if (-not (Test-Path -LiteralPath $HtmlPath)) {
    throw "HTML not found: $HtmlPath"
}

# PS 5.1: never `return @($array)` from a helper (pipeline unrolls / re-packs wrong).
if ($ReleasesJsonPath) {
    $parsed = Get-Content -LiteralPath $ReleasesJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
} else {
    $headers = @{
        Accept = 'application/vnd.github+json'
        'User-Agent' = 'bobiverse-stamp-pa-downloads'
    }
    $parsed = Invoke-RestMethod -Uri $ApiUrl -Headers $headers -TimeoutSec 45
}
$releases = @($parsed)
$picked = Select-PaRelease -Releases $releases
$html = [System.IO.File]::ReadAllText($HtmlPath)

if (-not $picked) {
    Write-Host 'WARN FR #7643: no PriorityAgent.exe on any non-draft release; leaving card unstamped'
    exit 0
}

$tag = [string]$picked.tag_name
$title = [string]$picked.name
if ([string]::IsNullOrWhiteSpace($title)) { $title = $tag }
$assetNames = @($picked.assets | ForEach-Object { [string]$_.name })
$installer = @($assetNames | Where-Object { Test-PaInstallerName $_ } | Select-Object -First 1)[0]
$sha = @($assetNames | Where-Object { Test-PaShaName $_ } | Select-Object -First 1)[0]
if ([string]::IsNullOrWhiteSpace($installer)) {
    Write-Host 'WARN FR #7643: picked release missing installer name'
    exit 0
}

$prefix = 'https://github.com/SimonBarnett/priority-mcp/releases/download/'
$exeHref = $prefix + $tag + '/' + $installer
$shaHref = if ($sha) { $prefix + $tag + '/' + $sha } else { '' }
$notesHref = 'https://github.com/SimonBarnett/priority-mcp/releases/tag/' + $tag

$assetInner = '        <a class="btn btn-gold" data-role="installer" href="' + $exeHref + '">' + $installer + '</a>'
if ($shaHref) {
    $assetInner += "`r`n        <a class=`"btn btn-ghost`" data-role=`"sha256`" href=`"$shaHref`">sha256</a>"
}

$versionRx = [regex]'(?s)(<article class="card" data-product="priority-agent">.*?<p data-role="version">)(.*?)(</p>)'
if (-not $versionRx.IsMatch($html)) { throw 'FR #7643: version element missing on priority-agent card' }
$html = $versionRx.Replace($html, { param($m) $m.Groups[1].Value + $title + $m.Groups[3].Value }, 1)

$assetsRx = [regex]'(?s)(<div data-role="assets">)(.*?)(</div>)'
# Only the first assets div after priority-agent — page has one priority-agent card.
$paStart = $html.IndexOf('data-product="priority-agent"')
if ($paStart -lt 0) { throw 'FR #7643: priority-agent card missing' }
$before = $html.Substring(0, $paStart)
$after = $html.Substring($paStart)
$mAssets = $assetsRx.Match($after)
if (-not $mAssets.Success) { throw 'FR #7643: assets div missing on priority-agent card' }
$after2 = $assetsRx.Replace($after, { param($m) $m.Groups[1].Value + "`r`n" + $assetInner + "`r`n      " + $m.Groups[3].Value }, 1)
$html = $before + $after2

$notesRx = [regex]'(data-role="release-notes" href=")([^"]*)(")'
$mNotes = $notesRx.Match($html.Substring($html.IndexOf('data-product="priority-agent"')))
if (-not $mNotes.Success) { throw 'FR #7643: release-notes link missing' }
# Replace only within the priority-agent article slice
$artStart = $html.IndexOf('<article class="card" data-product="priority-agent">')
$artEnd = $html.IndexOf('</article>', $artStart)
if ($artStart -lt 0 -or $artEnd -lt 0) { throw 'FR #7643: article bounds missing' }
$artEnd += '</article>'.Length
$article = $html.Substring($artStart, $artEnd - $artStart)
$article2 = $notesRx.Replace($article, '${1}' + $notesHref + '${3}', 1)
$html = $html.Substring(0, $artStart) + $article2 + $html.Substring($artEnd)

if ($WhatIf) {
    Write-Host "WhatIf would stamp tag=$tag installer=$installer"
    exit 0
}

[System.IO.File]::WriteAllText($HtmlPath, $html, [System.Text.UTF8Encoding]::new($false))
Write-Host "INFO FR #7643 stamped Priority Agent download tag=$tag asset=$installer"
