<#
.SYNOPSIS
  FR #3685: outer install-failure reporter for Install-Airc.cmd.

.DESCRIPTION
  Runs when Install-Airc.ps1 never started (#Requires refuse, parse error) or exited
  nonzero without writing the fail-reported flag. No #Requires so Windows PowerShell
  4.0 / Server 2012 R2 can still log + redact + POST (or honour crash-report opt-out).
#>
[CmdletBinding()]
param(
    [int]$ExitCode = 1,
    [string]$ScriptsDir = '',
    [string]$ArgsText = '',
    [string]$InstallRoot = '',
    [string]$Profile = '',
    [string]$IntakeUrl = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'

function Get-Fr3685ArgValue {
    param([string]$Text, [string]$Name)
    if (-not $Text) { return '' }
    $m = [regex]::Match($Text, ('(?i)\-{0}\s+\"([^\"]*)\"' -f [regex]::Escape($Name)))
    if ($m.Success) { return $m.Groups[1].Value }
    $m = [regex]::Match($Text, ('(?i)\-{0}\s+(\S+)' -f [regex]::Escape($Name)))
    if ($m.Success) { return $m.Groups[1].Value }
    return ''
}

function Test-Fr3685CrashReportAllowsIntake {
    param([string]$Root)
    $raw = [string]$env:BOBIVERSE_CRASH_REPORT
    if (-not $raw) { $raw = [string]$env:BOB_CRASH_REPORT }
    if ($raw -and ($raw.Trim() -match '^(?i)0|off|false|no|local-only|local_only|spool$')) {
        return $false
    }
    if ($raw -and ($raw.Trim() -match '^(?i)1|full|on|true|yes|no-log-tail$')) {
        return $true
    }
    if ($Root) {
        $cfg = Join-Path $Root 'config\crash-report.json'
        if (Test-Path -LiteralPath $cfg) {
            try {
                $j = Get-Content -LiteralPath $cfg -Raw -ErrorAction Stop
                if ($j -match '(?i)"enabled"\s*:\s*false') { return $false }
                if ($j -match '(?i)"mode"\s*:\s*"(off|local-only|local_only|spool)"') { return $false }
            } catch { }
        }
    }
    # Fleet / client default: allow (matches FR #3401 client ON).
    return $true
}

function Redact-Fr3685CrashText {
    param([string]$Text = '')
    if (-not $Text) { return '' }
    $s = [string]$Text
    $s = [regex]::Replace($s, '(?i)\b(?:Authorization\s*[:=]\s*)?(Bearer|Basic)\s+\S+', '$1=<redacted>')
    $s = [regex]::Replace($s, '(?i)\bPASS\s+\S+', 'PASS <redacted>')
    $s = [regex]::Replace($s, '(?i)(https?://)[^/\s:@]+:[^/\s@]+@', '$1<redacted>@')
    $s = [regex]::Replace(
        $s,
        '(?i)"?(password|passwd|secret|token|api[_-]?key|BOB_IRC_PASSWORD|GH_TOKEN|GITHUB_TOKEN)"?\s*[:=]\s*(?:"[^"]*"|\S+)',
        '$1=<redacted>'
    )
    $s = [regex]::Replace(
        $s,
        '(?i)\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{10,})\b',
        '<redacted-token>'
    )
    return $s
}

function Write-Fr3685InstallLog {
    param([string]$Message)
    try {
        $dir = Join-Path $env:ProgramData 'Bobiverse\logs'
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        $path = Join-Path $dir 'install-airc.log'
        $line = '{0:o} {1}' -f [datetime]::UtcNow, ($Message -replace '[\r\n]+', ' ')
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [IO.File]::AppendAllText($path, $line + [Environment]::NewLine, $utf8)
    } catch { }
}

if (-not $ScriptsDir) { $ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $InstallRoot) { $InstallRoot = Get-Fr3685ArgValue -Text $ArgsText -Name 'InstallRoot' }
if (-not $Profile) { $Profile = Get-Fr3685ArgValue -Text $ArgsText -Name 'Profile' }
if (-not $Profile) { $Profile = 'unknown' }

$msg = ('cmd-outer install-fail exit={0} profile={1} args={2}' -f $ExitCode, $Profile, $ArgsText)
Write-Fr3685InstallLog -Message $msg

# Prefer Common helper on PS 5.1+ when present (redact + policy + Report script).
$psMajor = 0
try { $psMajor = [int]$PSVersionTable.PSVersion.Major } catch { $psMajor = 0 }
$common = Join-Path $ScriptsDir 'Bobiverse-Common.ps1'
if (-not (Test-Path -LiteralPath $common)) {
    $common = Join-Path (Split-Path -Parent $ScriptsDir) 'common\scripts\Bobiverse-Common.ps1'
}
if ($psMajor -ge 5 -and (Test-Path -LiteralPath $common)) {
    try {
        . $common
        $title = 'airc install: Install-Airc.cmd failed (outer)'
        $body = ('exit={0} profile={1} {2}' -f $ExitCode, $Profile, $ArgsText)
        $splat = @{
            InstallRoot = $InstallRoot
            ScriptsDir  = $ScriptsDir
            Title       = $title
            Body        = $body
        }
        if ($DryRun) { $splat.DryRun = $true }
        if ($IntakeUrl) { $splat.IntakeUrl = $IntakeUrl }
        [void](Send-BobiverseAircInstallFailureIntake @splat)
        exit 0
    } catch {
        Write-Fr3685InstallLog -Message ('cmd-outer Common Send failed: {0}' -f $_.Exception.Message)
        # fall through to minimal path
    }
}

$allow = Test-Fr3685CrashReportAllowsIntake -Root $InstallRoot
$safeBody = Redact-Fr3685CrashText -Text $msg
Write-Fr3685InstallLog -Message ('cmd-outer install-fail-intake: {0}' -f $safeBody)

if (-not $allow) {
    Write-Host 'INFO FR #3685 skip intake (crash-report opt-out); failure logged locally'
    exit 0
}

$url = $IntakeUrl
if (-not $url) { $url = [string]$env:BOB_INTAKE_URL }
if (-not $url) { $url = 'https://irc.ntsa.uk/bob/v1/intake' }

$title = Redact-Fr3685CrashText -Text ('airc install: Install-Airc.cmd failed exit={0} profile={1}' -f $ExitCode, $Profile)
$payload = @{
    kind            = 'issue'
    repo            = 'SimonBarnett/bobiverse'
    title           = $title
    body            = $safeBody
    machine         = $env:COMPUTERNAME
    agent           = 'Report-AircInstallCmdFailure'
    idempotency_key = ('airc-install-cmd-fail-{0}-{1}' -f $env:COMPUTERNAME, $ExitCode)
} | ConvertTo-Json -Compress

if ($DryRun) {
    Write-Host ('INFO FR #3685 DryRun intake title={0}' -f $title)
    exit 0
}

try {
    # PS 2/4-safe POST (no Invoke-RestMethod required).
    $wc = New-Object System.Net.WebClient
    $wc.Headers.Add('Content-Type', 'application/json; charset=utf-8')
    $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
    [void]$wc.UploadData($url, 'POST', $bytes)
    Write-Host 'INFO FR #3685 outer install-fail intake posted'
} catch {
    Write-Fr3685InstallLog -Message ('cmd-outer intake POST failed: {0}' -f $_.Exception.Message)
    try {
        $obox = Join-Path $env:ProgramData 'Bobiverse\report-outbox'
        if (-not (Test-Path -LiteralPath $obox)) {
            New-Item -ItemType Directory -Force -Path $obox | Out-Null
        }
        $leaf = ('airc-install-cmd-fail-{0}.json' -f [guid]::NewGuid().ToString('N'))
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [IO.File]::WriteAllText((Join-Path $obox $leaf), $payload, $utf8)
    } catch { }
}

exit 0
