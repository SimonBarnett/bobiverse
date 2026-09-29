# Jeeves digest chair. Do not share --home with bob-ionos.
# --home / AGENTIC_IRC_HOME = ~\.agentic-irc-jeeves
# BOB_DIGEST_HOME           = ~\.agentic-irc-bobiverse  (digest.json, chair-outbox.txt)
# Without BOB_DIGEST_HOME, fleet_digest_home() uses --home and GIT lines stay stuck.
# BobIrcd NSSM and the hook that starts Jeeves with the IRC server live in
# agentic_build (chairNick Jeeves). This script does not install that service.
# See docs/bobiverse-ionos-ircd.md and skill bob-irc.
#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
if (-not $env:USERPROFILE) {
    Write-Error 'USERPROFILE is not set'
}
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $here 'irc_agent.py'
# Never inherit AGENTIC_IRC_HOME. Watch/bob-ionos sets that to the digest home.
$chairHome = Join-Path $env:USERPROFILE '.agentic-irc-jeeves'
$digestHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'
$chairFull = [IO.Path]::GetFullPath($chairHome).TrimEnd('\').ToLowerInvariant()
$digestFull = [IO.Path]::GetFullPath($digestHome).TrimEnd('\').ToLowerInvariant()
if ($chairFull -eq $digestFull) {
    Write-Error "Jeeves --home must not be the bob-ionos digest home ($digestHome)"
}
$nick = if ($env:AGENTIC_IRC_CHAIR_NICK) { $env:AGENTIC_IRC_CHAIR_NICK } else { 'Jeeves' }
$env:AGENTIC_IRC_CHAIR_NICK = $nick
$env:AGENTIC_IRC_HOME = $chairHome
$env:BOB_DIGEST_HOME = $digestHome

$pwFile = Join-Path $env:USERPROFILE '.grok\ergo\connect.password'
if (Test-Path -LiteralPath $pwFile) {
    $env:AGENTIC_IRC_PASSWORD = (Get-Content -LiteralPath $pwFile -Raw).Trim()
} elseif (-not $env:AGENTIC_IRC_PASSWORD) {
    Write-Error 'missing connect.password (set AGENTIC_IRC_PASSWORD or the file)'
}

$forward = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    $a = [string]$args[$i]
    if ($a -eq '--password') {
        $i++
        continue
    }
    if ($a -like '--password=*') { continue }
    $forward += $a
}

function Get-PriorChairProcesses {
    param([string]$Nick)
    $nickEsc = [regex]::Escape($Nick)
    $nickRe = '(?i)(^|\s)--nick(?:=|\s+)"?' + $nickEsc + '"?(\s|$)'
    $chairRe = '(?i)(^|\s)--chair(\s|$)'
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return $false }
        if ($cmd -notmatch 'irc_agent\.py') { return $false }
        if ($cmd -match $chairRe) { return $true }
        if ($cmd -match $nickRe) { return $true }
        return $false
    })
}

function Request-ChairQuit {
    param([string]$ProcHome)
    $full = [IO.Path]::GetFullPath($ProcHome).TrimEnd('\').ToLowerInvariant()
    # A quit file on the digest home would also stop bob-ionos.
    if ($full -eq $digestFull) { return }
    if (-not (Test-Path -LiteralPath $ProcHome)) { return }
    $quit = Join-Path $ProcHome 'agent.quit.request'
    [IO.File]::WriteAllText($quit, "0 jeeves-restart`n")
}

function Stop-PriorChair {
    param([string]$Nick)
    $procs = @(Get-PriorChairProcesses -Nick $Nick)
    if ($procs.Count -eq 0) { return }
    $grace = $false
    foreach ($p in $procs) {
        $cmd = [string]$p.CommandLine
        $procHome = $null
        if ($cmd -match '(?i)(^|\s)--home(?:=|\s+)"([^"]+)"') {
            $procHome = $Matches[2]
        } elseif ($cmd -match "(?i)(^|\s)--home(?:=|\s+)'([^']+)'") {
            $procHome = $Matches[2]
        } elseif ($cmd -match '(?i)(^|\s)--home(?:=|\s+)(\S+)') {
            $procHome = $Matches[2]
        }
        if ($procHome) {
            Request-ChairQuit -ProcHome $procHome
            $full = [IO.Path]::GetFullPath($procHome).TrimEnd('\').ToLowerInvariant()
            if ($full -ne $digestFull) { $grace = $true }
        }
    }
    if ($grace) {
        $deadline = (Get-Date).AddSeconds(8)
        do {
            $procs = @(Get-PriorChairProcesses -Nick $Nick)
            if ($procs.Count -eq 0) { return }
            if ((Get-Date) -ge $deadline) { break }
            Start-Sleep -Milliseconds 400
        } while ($true)
    }
    $procs = @(Get-PriorChairProcesses -Nick $Nick)
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
    $left = @(Get-PriorChairProcesses -Nick $Nick)
    if ($left.Count -gt 0) {
        $ids = ($left | ForEach-Object { $_.ProcessId }) -join ','
        Write-Error "prior Jeeves/--chair still running (pid $ids)"
    }
}

Stop-PriorChair -Nick $nick
if (-not (Test-Path -LiteralPath $chairHome)) {
    New-Item -ItemType Directory -Force -Path $chairHome | Out-Null
}
# Stop-PriorChair writes agent.quit.request for the old chair. If that chair
# ignored it and was force-killed, the file stays and the NEW chair consumes it
# on its first tick and quits ("agent quit request (jeeves-restart)").
$staleQuit = Join-Path $chairHome 'agent.quit.request'
if (Test-Path -LiteralPath $staleQuit) {
    Remove-Item -LiteralPath $staleQuit -Force -ErrorAction SilentlyContinue
}
& python -c "import sys; sys.path.insert(0, r'$here'); import bobreport; bobreport.persist_chair_nick(r'$chairHome', r'$nick')"
& python $py --nick $nick --channel '#bobiverse' --home $chairHome --chair @forward
if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }
