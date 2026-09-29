# Create (or skip) the Bob git webhook on a SimonBarnett repo.
# Skill: plan-bob-webhooks. Hook target is /bob/v1/git - never /bob/v1/report.
# ASCII-only file (no em-dash / smart quotes) so Windows PowerShell 5.1 parses cleanly.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,

    [string]$HookUrl = 'https://irc.ntsa.uk/bob/v1/git'
)

$ErrorActionPreference = 'Stop'
if ($Repo -notmatch '/') { $Repo = "SimonBarnett/$Repo" }

$existing = gh api "repos/$Repo/hooks" --jq '.[].config.url' 2>$null
if ($existing -split "`n" | Where-Object { $_ -eq $HookUrl }) {
    Write-Host "OK: $HookUrl already on $Repo - skip create."
    exit 0
}

$json = '{"name":"web","active":true,"events":["push","pull_request","issues"],"config":{"url":"' + $HookUrl + '","content_type":"json","insecure_ssl":"0"}}'
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("bob-git-hook-{0}.json" -f [guid]::NewGuid().ToString('n'))
try {
    [IO.File]::WriteAllText($tmp, $json, [Text.UTF8Encoding]::new($false))
    gh api "repos/$Repo/hooks" -X POST --input $tmp
    Write-Host "Created webhook $HookUrl on $Repo (ping delivery expected 204)."
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tmp
}
