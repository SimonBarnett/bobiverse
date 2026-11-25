#Requires -Version 5.1
<#
.SYNOPSIS
  FR #9879: tail inbound-transcript at 1s; emit READY / DONE / BORED push events.
.DESCRIPTION
  !bored (and worker ready / DONE) are push events. This notifier tails
  home/inbound-transcript.log every PollSec (default 1) and prints one line per
  match so a MONITORING agent (monitor tool) can dispatch the same turn.
  A 5-minute health scheduler must not own assign.

  Singleton: a second instance exits 0 with ALREADY_RUNNING unless
  -AllowSecondInstance (tests). Also appends the same lines to
  StateDir/bored-push-events.log so a Hidden Ensure start remains visible.
#>
[CmdletBinding()]
param(
    [string]$Inbound = '',
    [string]$StateDir = '',
    [int]$PollSec = 1,
    [int]$MaxEvents = 0,
    [switch]$StartAtBeginning,
    [switch]$AllowSecondInstance,
    [string[]]$ShopChannels = @('flamingo', 'redqueen', 'marchhare', 'walrus', 'wonderland')
)

$ErrorActionPreference = 'Continue'
$scriptName = 'watch_bored_push_notify.ps1'

function Get-BoredPushNotifyPids {
    param([switch]$ExcludeCurrentPid)
    $ids = @()
    try {
        foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" -ErrorAction SilentlyContinue)) {
            $cmd = [string]$p.CommandLine
            if (-not $cmd) { continue }
            if ($cmd -notmatch 'watch_bored_push_notify\.ps1') { continue }
            if ($ExcludeCurrentPid -and [int]$p.ProcessId -eq $PID) { continue }
            $ids += [int]$p.ProcessId
        }
    } catch { }
    return @($ids | Select-Object -Unique)
}

if (-not $AllowSecondInstance) {
    $others = @(Get-BoredPushNotifyPids -ExcludeCurrentPid)
    if ($others.Count -ge 1) {
        Write-Output ("ALREADY_RUNNING pid(s)={0} (FR #9879 dedupe)" -f ($others -join ','))
        exit 0
    }
}

if (-not $Inbound) {
    if ($env:BOB_INBOUND_TRANSCRIPT) {
        $Inbound = $env:BOB_INBOUND_TRANSCRIPT
    } else {
        $bobHome = if ($env:BOB_HOME) { $env:BOB_HOME } else { 'C:\ai\bob\home' }
        $Inbound = Join-Path $bobHome 'inbound-transcript.log'
    }
}
if (-not $StateDir) {
    $base = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE 'AppData\Local' }
    $StateDir = Join-Path $base 'Bobiverse\monitor'
}
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$StateFile = Join-Path $StateDir 'bored_push_state.json'
$EventsFile = Join-Path $StateDir 'bored-push-events.log'
if ($PollSec -lt 1) { $PollSec = 1 }

$shopAlt = ($ShopChannels | ForEach-Object { [regex]::Escape($_) }) -join '|'
$rxReady = "(?i)#($shopAlt)\s+([a-z0-9]+-\d+)\s+worker ready\b"
$rxDone = "(?i)#($shopAlt)\s+([a-z0-9]+-\d+)\s+DONE\b"
$rxBored = "(?i)#($shopAlt)\s+([a-z0-9]+-\d+)\s+!bored\b"

function Write-BoredPushEvent([string]$line) {
    Write-Output $line
    try {
        $enc = New-Object System.Text.UTF8Encoding $false
        [IO.File]::AppendAllText($EventsFile, $line + [Environment]::NewLine, $enc)
    } catch { }
}

function Save-BoredPushOffset([int64]$offset) {
    try {
        $obj = @{ offset = $offset; updated = (Get-Date).ToString('o') } | ConvertTo-Json -Compress
        $enc = New-Object System.Text.UTF8Encoding $false
        [IO.File]::WriteAllText($StateFile, $obj, $enc)
    } catch { }
}

$offset = [int64]0
if (-not $StartAtBeginning -and (Test-Path -LiteralPath $StateFile)) {
    try {
        $st = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -ne $st.offset) { $offset = [int64]$st.offset }
    } catch { }
}
if (-not $StartAtBeginning -and $offset -le 0 -and (Test-Path -LiteralPath $Inbound)) {
    $offset = [int64](Get-Item -LiteralPath $Inbound).Length
}

Write-Output ("START bored-push-notify FR #9879 offset={0} inbound={1} poll={2}s" -f $offset, $Inbound, $PollSec)
$emitted = 0

while ($true) {
    if (-not (Test-Path -LiteralPath $Inbound)) {
        if ($MaxEvents -gt 0) { break }
        Start-Sleep -Seconds $PollSec
        continue
    }
    $len = [int64](Get-Item -LiteralPath $Inbound).Length
    if ($len -lt $offset) { $offset = [int64]0 }
    if ($len -gt $offset) {
        $fs = [IO.File]::Open($Inbound, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try {
            [void]$fs.Seek($offset, [IO.SeekOrigin]::Begin)
            $sr = New-Object IO.StreamReader($fs)
            while ($null -ne ($line = $sr.ReadLine())) {
                $offset = [int64]$fs.Position
                if ($line -match $rxReady) {
                    Write-BoredPushEvent ("READY nick={0} channel=#{1}" -f $Matches[2], $Matches[1])
                    $emitted++
                } elseif ($line -match $rxDone) {
                    Write-BoredPushEvent ("DONE nick={0} channel=#{1}" -f $Matches[2], $Matches[1])
                    $emitted++
                } elseif ($line -match $rxBored) {
                    Write-BoredPushEvent ("BORED nick={0} channel=#{1} (fallback)" -f $Matches[2], $Matches[1])
                    $emitted++
                }
                if ($MaxEvents -gt 0 -and $emitted -ge $MaxEvents) { break }
            }
        } finally {
            $fs.Close()
        }
        Save-BoredPushOffset $offset
    }
    # -MaxEvents > 0: one-shot / fixture mode (tests); never sleep into a timer loop.
    if ($MaxEvents -gt 0) { break }
    Start-Sleep -Seconds $PollSec
}

Write-Output ("STOP bored-push-notify events={0} offset={1}" -f $emitted, $offset)
exit 0
