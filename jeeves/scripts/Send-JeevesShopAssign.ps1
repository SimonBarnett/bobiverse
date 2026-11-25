<#
.SYNOPSIS
  Append Jeeves shop-wire assign lines to chair outbox (FR #9878).
.DESCRIPTION
  Durable helper for MONITORING / ops when ear !assign is mute and cmd-trace is
  stale. Writes UTF-8 no-BOM lines to BOB_CHAIR_OUTBOX or ~/.jeeves/outbox.txt:

    PRIVMSG #<machine> :<nick>: MRB|FIX|FR owner/repo#N <url>
    PRIVMSG #bobiverse :assign: sent <nick>: TASK owner/repo#N <url>

  Live mute incidents that must hit the walrus chair outbox require
  require_machine=walrus. Path override lets any host tip/test without walrus.
.PARAMETER Nick
  Shop seat nick (machine-pid).
.PARAMETER Repo
  owner/name
.PARAMETER Task
  FR|MRB|UAT|FIX
.PARAMETER Number
  Issue or PR number (no #).
.PARAMETER Url
  Assign URL (invented from repo/task/number when omitted).
.PARAMETER ChairOutbox
  Override outbox path (else BOB_CHAIR_OUTBOX / %USERPROFILE%\.jeeves\outbox.txt).
.PARAMETER DryRun
  Print lines; do not write.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Nick,
    [Parameter(Mandatory = $true)][string]$Repo,
    [Parameter(Mandatory = $true)][ValidateSet('FR', 'MRB', 'UAT', 'FIX', 'PR', 'BUILD')][string]$Task,
    [Parameter(Mandatory = $true)][string]$Number,
    [string]$Url = '',
    [string]$ChairOutbox = '',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

$num = ($Number -replace '^#', '').Trim()
if (-not $Url) {
    if ($Task -in @('MRB', 'FIX', 'PR')) {
        $Url = "https://github.com/$Repo/pull/$num"
    } else {
        $Url = "https://github.com/$Repo/issues/$num"
    }
}

$outbox = $ChairOutbox
if (-not $outbox) { $outbox = $env:BOB_CHAIR_OUTBOX }
if (-not $outbox) {
    $homeJ = if ($env:JEEVES_HOME) { $env:JEEVES_HOME } elseif ($env:BOB_JEEVES_HOME) { $env:BOB_JEEVES_HOME } else { Join-Path $env:USERPROFILE '.jeeves' }
    $outbox = Join-Path $homeJ 'outbox.txt'
}

$machine = if ($Nick -match '^(.*)-\d+$') { $Matches[1].ToLowerInvariant() } else { $Nick.ToLowerInvariant() }
$body = ("{0}: {1} {2}#{3} {4}" -f $Nick, $Task.ToUpperInvariant(), $Repo, $num, $Url)
$body = ($body -replace '\s+', ' ').Trim()
$shop = "PRIVMSG #$machine :$body"
$announce = "PRIVMSG #bobiverse :assign: sent $body"

if ($DryRun) {
    Write-Output $shop
    Write-Output $announce
    Write-Output ("dry_run=1 outbox=" + $outbox)
    exit 0
}

$parent = Split-Path -Parent $outbox
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}

# UTF-8 no BOM append (WinPS Set-Content -Encoding utf8 writes BOM).
$utf8 = New-Object System.Text.UTF8Encoding $false
foreach ($line in @($shop, $announce)) {
    $text = if ($line.EndsWith("`n")) { $line } else { $line + "`n" }
    [System.IO.File]::AppendAllText($outbox, $text, $utf8)
}
Write-Output ("wrote=2 mode=shop_wire outbox=" + $outbox)
exit 0
