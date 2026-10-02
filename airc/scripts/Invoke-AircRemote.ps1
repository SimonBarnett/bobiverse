#Requires -Version 5.1
<#
.SYNOPSIS
  Driving-box helper for authenticated Airc console remote control (FR #76).
.DESCRIPTION
  Builds IRC-safe PRIVMSG bodies for plain PowerShell, cmd:, psb64:, STATUS,
  PUT chunks (+ SHA-256), RUN/JOB/CANCEL, and UPDATE. Can append lines to an
  outbox file (bob ear / worker outbox) and parse correlated replies
  (out/err/DONE). Secrets are redacted from transcripts. -SelfTest runs offline
  acceptance checks (no IRC).
.NOTES
  PowerShell 5.1 only. Does not invent Ergo/NickServ secrets. PUT/RUN/STATUS
  verbs match docs/airc-remote-control.md; server-side PUT/RUN may land in FR #78.
#>
[CmdletBinding(DefaultParameterSetName = 'Remote')]
param(
    [Parameter(ParameterSetName = 'Remote')]
    [string]$MachineId = '',

    [Parameter(ParameterSetName = 'Remote')]
    [ValidateSet('Command', 'Cmd', 'Psb64', 'Status', 'Put', 'Run', 'Job', 'Cancel', 'Update')]
    [string]$Action = 'Command',

    [Parameter(ParameterSetName = 'Remote')]
    [string]$Text = '',

    [Parameter(ParameterSetName = 'Remote')]
    [string]$Path = '',

    [Parameter(ParameterSetName = 'Remote')]
    [string]$LocalFile = '',

    [Parameter(ParameterSetName = 'Remote')]
    [string]$JobId = '',

    [Parameter(ParameterSetName = 'Remote')]
    [string]$Outbox = '',

    [Parameter(ParameterSetName = 'Remote')]
    [string]$ReplyFile = '',

    [Parameter(ParameterSetName = 'Remote')]
    [int]$TimeoutSec = 60,

    [Parameter(ParameterSetName = 'Remote')]
    [int]$MaxRetries = 2,

    [Parameter(ParameterSetName = 'Remote')]
    [int]$ChunkBytes = 240,

    [Parameter(ParameterSetName = 'Remote')]
    [string]$SandboxRoot = '',

    [Parameter(ParameterSetName = 'Remote')]
    [switch]$WhatIf,

    [Parameter(ParameterSetName = 'SelfTest')]
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- pure helpers (dot-source / SelfTest) ------------------------------------

function Get-AircConsoleNick {
    param([Parameter(Mandatory)][string]$MachineId)
    $mid = ($MachineId.Trim().ToLower() -replace '[^a-z0-9_-]+', '-').Trim('-_')
    if (-not $mid) { throw 'MachineId empty after sanitize' }
    return ('{0}_console' -f $mid)
}

function New-AircCorrelationId {
    return ([guid]::NewGuid().ToString('N').Substring(0, 8))
}

function Protect-AircRemoteSecret {
    <#
      Redact password=/token=/sasl=/nickserv= style assignments and GUID-like secrets.
    #>
    param([AllowNull()][string]$Text)
    if ($null -eq $Text -or $Text -eq '') { return '' }
    $s = $Text
    $s = [regex]::Replace($s, '(?i)\b(password|passwd|token|secret|sasl|nickserv|api[_-]?key)\s*[=:]\s*\S+', '$1=***')
    $s = [regex]::Replace($s, '(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '********-****-****-****-************')
    return $s
}

function ConvertTo-AircPsb64 {
    param([Parameter(Mandatory)][string]$Script)
    $bytes = [System.Text.Encoding]::Unicode.GetBytes($Script)  # UTF-16LE
    return [Convert]::ToBase64String($bytes)
}

function New-AircRemoteBody {
    param(
        [Parameter(Mandatory)][ValidateSet('Command', 'Cmd', 'Psb64', 'Status', 'Put', 'Run', 'Job', 'Cancel', 'Update')]
        [string]$Action,
        [string]$Text = '',
        [string]$Path = '',
        [string]$JobId = '',
        [string]$Product = 'airc'
    )
    switch ($Action) {
        'Command' {
            if (-not $Text) { throw 'Command requires -Text' }
            return $Text
        }
        'Cmd' {
            if (-not $Text) { throw 'Cmd requires -Text' }
            return ('cmd: {0}' -f $Text)
        }
        'Psb64' {
            if (-not $Text) { throw 'Psb64 requires -Text (script)' }
            return ('psb64:{0}' -f (ConvertTo-AircPsb64 -Script $Text))
        }
        'Status' { return 'STATUS' }
        'Put' {
            if (-not $Path) { throw 'Put meta line requires -Path' }
            $id = if ($JobId) { $JobId } else { New-AircCorrelationId }
            return ('PUT path={0} id={1}' -f $Path, $id)
        }
        'Run' {
            if (-not $Path) { throw 'Run requires -Path' }
            $id = if ($JobId) { $JobId } else { New-AircCorrelationId }
            return ('RUN path={0} id={1}' -f $Path, $id)
        }
        'Job' {
            $id = if ($JobId) { $JobId } else { throw 'Job requires -JobId' }
            return ('JOB id={0}' -f $id)
        }
        'Cancel' {
            $id = if ($JobId) { $JobId } else { throw 'Cancel requires -JobId' }
            return ('CANCEL id={0}' -f $id)
        }
        'Update' {
            $p = if ($Text) { $Text } else { $Product }
            return ('UPDATE {0}' -f $p)
        }
    }
}

function Test-AircSandboxPath {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$SandboxRoot
    )
    $root = [System.IO.Path]::GetFullPath($SandboxRoot).TrimEnd('\')
    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full.Equals($root, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    $prefix = $root + '\'
    return $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function New-AircPutChunks {
    param(
        [Parameter(Mandatory)][string]$LocalFile,
        [Parameter(Mandatory)][string]$RemotePath,
        [int]$ChunkBytes = 240,
        [string]$JobId = '',
        [string]$SandboxRoot = ''
    )
    if (-not (Test-Path -LiteralPath $LocalFile)) { throw "LocalFile not found: $LocalFile" }
    if ($ChunkBytes -lt 32 -or $ChunkBytes -gt 350) { throw 'ChunkBytes must be 32..350 (IRC-safe)' }
    if ($SandboxRoot) {
        if (-not (Test-AircSandboxPath -Path $RemotePath -SandboxRoot $SandboxRoot)) {
            throw "RemotePath outside sandbox: $RemotePath"
        }
    }
    $id = if ($JobId) { $JobId } else { New-AircCorrelationId }
    $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $LocalFile))
    $sha = [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)).Replace('-', '').ToLowerInvariant()
    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add(('PUT path={0} id={1} bytes={2} sha256={3}' -f $RemotePath, $id, $bytes.Length, $sha))
    $seq = 0
    $offset = 0
    while ($offset -lt $bytes.Length) {
        $len = [Math]::Min($ChunkBytes, $bytes.Length - $offset)
        $slice = New-Object byte[] $len
        [Array]::Copy($bytes, $offset, $slice, 0, $len)
        $b64 = [Convert]::ToBase64String($slice)
        $seq++
        [void]$lines.Add(('CHUNK id={0} seq={1} data={2}' -f $id, $seq, $b64))
        $offset += $len
    }
    [void]$lines.Add(('PUTEND id={0} seqs={1} sha256={2}' -f $id, $seq, $sha))
    return [pscustomobject]@{
        JobId  = $id
        Sha256 = $sha
        Bytes  = $bytes.Length
        Seqs   = $seq
        Lines  = $lines.ToArray()
    }
}

function ConvertFrom-AircRemoteReply {
    param([Parameter(Mandatory)][string[]]$Lines, [string]$ExpectJobId = '')
    $outs = New-Object System.Collections.Generic.List[object]
    $errs = New-Object System.Collections.Generic.List[object]
    $done = $null
    foreach ($raw in $Lines) {
        $line = Protect-AircRemoteSecret $raw
        if ($line -match '^(?<stream>out|err)\s+id=(?<id>[0-9a-f]+)\s+seq=(?<seq>\d+)\s(?<body>.*)$') {
            $obj = [pscustomobject]@{
                Stream = $Matches.stream
                Id     = $Matches.id
                Seq    = [int]$Matches.seq
                Body   = $Matches.body
            }
            if ($ExpectJobId -and $obj.Id -ne $ExpectJobId) { continue }
            if ($obj.Stream -eq 'out') { [void]$outs.Add($obj) } else { [void]$errs.Add($obj) }
            continue
        }
        if ($line -match '^DONE\s+id=(?<id>[0-9a-f]+)\s+exit=(?<exit>-?\d+)\s*$') {
            $done = [pscustomobject]@{ Id = $Matches.id; ExitCode = [int]$Matches.exit }
        }
    }
    if (-not $done) {
        throw 'malformed replies: missing DONE id=… exit=… (fail closed)'
    }
    if ($ExpectJobId -and $done.Id -ne $ExpectJobId) {
        throw ("correlation mismatch: expected id={0} got id={1}" -f $ExpectJobId, $done.Id)
    }
    $outSorted = @($outs | Sort-Object Seq)
    $errSorted = @($errs | Sort-Object Seq)
    # Fail closed on duplicate seq (seq is global across out/err in FR #75).
    $seen = @{}
    foreach ($row in @($outSorted + $errSorted)) {
        $key = '{0}:{1}' -f $row.Stream, $row.Seq
        if ($seen.ContainsKey($row.Seq)) {
            throw ("malformed replies: duplicate seq={0}" -f $row.Seq)
        }
        $seen[$row.Seq] = $key
    }
    return [pscustomobject]@{
        JobId    = $done.Id
        ExitCode = $done.ExitCode
        Out      = $outSorted
        Err      = $errSorted
        StdOut   = (($outSorted | ForEach-Object { $_.Body }) -join "`n")
        StdErr   = (($errSorted | ForEach-Object { $_.Body }) -join "`n")
    }
}

function New-AircPrivmsgLines {
    param(
        [Parameter(Mandatory)][string]$MachineId,
        [Parameter(Mandatory)][string[]]$Bodies
    )
    $nick = Get-AircConsoleNick -MachineId $MachineId
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($b in $Bodies) {
        $safe = ($b -replace '[\r\n]', ' ')
        if ($safe.Length -gt 400) { throw ("body exceeds IRC soft limit ({0} chars)" -f $safe.Length) }
        [void]$out.Add(('PRIVMSG {0} :{1}' -f $nick, $safe))
    }
    return $out.ToArray()
}

function Write-AircOutbox {
    param(
        [Parameter(Mandatory)][string]$Outbox,
        [Parameter(Mandatory)][string[]]$Lines,
        [switch]$WhatIf
    )
    foreach ($line in $Lines) {
        $redacted = Protect-AircRemoteSecret $line
        if ($WhatIf) {
            Write-Host ("WHATIF {0}" -f $redacted)
            continue
        }
        $dir = Split-Path -Parent $Outbox
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        Add-Content -LiteralPath $Outbox -Value $line -Encoding utf8
    }
}

function Invoke-AircRemoteWithRetry {
    param(
        [scriptblock]$Send,
        [scriptblock]$Wait,
        [int]$MaxRetries = 2
    )
    if ($MaxRetries -lt 0 -or $MaxRetries -gt 5) { throw 'MaxRetries must be 0..5' }
    $attempt = 0
    $last = $null
    while ($attempt -le $MaxRetries) {
        $attempt++
        try {
            & $Send
            return & $Wait
        } catch {
            $last = $_
            if ($attempt -gt $MaxRetries) { break }
        }
    }
    throw ("retry exhausted after {0} attempts: {1}" -f $attempt, (Protect-AircRemoteSecret ([string]$last)))
}

function Invoke-AircRemoteSelfTest {
    $script:SelfTestFailed = 0
    function Assert-True([bool]$Cond, [string]$Msg) {
        if (-not $Cond) {
            Write-Host "FAIL $Msg"
            $script:SelfTestFailed++
        } else {
            Write-Host "ok   $Msg"
        }
    }

    $nick = Get-AircConsoleNick -MachineId 'MarchHare'
    Assert-True ($nick -eq 'marchhare_console') 'console nick sanitize'

    $body = New-AircRemoteBody -Action Command -Text 'Write-Output 1'
    Assert-True ($body -eq 'Write-Output 1') 'plain command body'

    $cmd = New-AircRemoteBody -Action Cmd -Text 'echo %COMSPEC%'
    Assert-True ($cmd -eq 'cmd: echo %COMSPEC%') 'cmd escape'

    $script = 'Write-Output $env:COMPUTERNAME'
    $psb = New-AircRemoteBody -Action Psb64 -Text $script
    Assert-True ($psb.StartsWith('psb64:')) 'psb64 prefix'
    $round = [System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($psb.Substring(6)))
    Assert-True ($round -eq $script) 'psb64 UTF-16LE round-trip'

    Assert-True ((New-AircRemoteBody -Action Status) -eq 'STATUS') 'STATUS verb'

    $tmp = Join-Path $env:TEMP ('airc-put-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $file = Join-Path $tmp 'payload.bin'
        $data = [byte[]](0..199)
        [System.IO.File]::WriteAllBytes($file, $data)
        $remote = Join-Path $tmp 'drop\payload.bin'
        $put = New-AircPutChunks -LocalFile $file -RemotePath $remote -ChunkBytes 64 -SandboxRoot $tmp
        Assert-True ($put.Seqs -eq 4) 'PUT chunk boundary count'
        Assert-True ($put.Lines[0] -match '^PUT path=') 'PUT header'
        Assert-True ($put.Lines[-1] -match '^PUTEND id=') 'PUTEND trailer'
        Assert-True ($put.Sha256.Length -eq 64) 'sha256 length'
        # reassemble
        $buf = New-Object System.Collections.Generic.List[byte]
        foreach ($ln in $put.Lines) {
            if ($ln -match '^CHUNK id=.+ seq=\d+ data=(?<d>.+)$') {
                $part = [Convert]::FromBase64String($Matches.d)
                [void]$buf.AddRange($part)
            }
        }
        $got = $buf.ToArray()
        Assert-True ($got.Length -eq $data.Length) 'PUT reassembly length'
        $same = $true
        for ($i = 0; $i -lt $data.Length; $i++) { if ($got[$i] -ne $data[$i]) { $same = $false; break } }
        Assert-True $same 'PUT reassembly bytes'
        try {
            New-AircPutChunks -LocalFile $file -RemotePath 'C:\Windows\System32\evil.ps1' -SandboxRoot $tmp | Out-Null
            Assert-True $false 'sandbox should reject escape'
        } catch {
            Assert-True $true 'sandbox rejects path escape'
        }
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }

    $id = 'abcd1234'
    $replies = @(
        "out id=$id seq=1 hello",
        "out id=$id seq=2 world",
        "err id=$id seq=3 boom",
        "DONE id=$id exit=7"
    )
    $parsed = ConvertFrom-AircRemoteReply -Lines $replies -ExpectJobId $id
    Assert-True ($parsed.ExitCode -eq 7) 'DONE exit parse'
    Assert-True ($parsed.StdOut -eq "hello`nworld") 'correlated stdout'
    Assert-True ($parsed.StdErr -eq 'boom') 'correlated stderr'

    try {
        ConvertFrom-AircRemoteReply -Lines @('out id=x seq=1 a') | Out-Null
        Assert-True $false 'missing DONE should throw'
    } catch {
        Assert-True $true 'fail closed on missing DONE'
    }

    try {
        ConvertFrom-AircRemoteReply -Lines @("DONE id=deadbeef exit=0") -ExpectJobId 'abcd1234' | Out-Null
        Assert-True $false 'correlation mismatch should throw'
    } catch {
        Assert-True $true 'fail closed on correlation mismatch'
    }

    $secretLine = 'password=super-secret token=abc NickServ GUID 12345678-1234-1234-1234-123456789abc'
    $red = Protect-AircRemoteSecret $secretLine
    Assert-True ($red -notmatch 'super-secret') 'secret redacted password'
    Assert-True ($red -notmatch 'token=abc') 'secret redacted token'
    Assert-True ($red -notmatch '12345678-1234-1234-1234-123456789abc') 'secret redacted guid'

    $script:RetryAttempts = 0
    $result = Invoke-AircRemoteWithRetry -MaxRetries 2 -Send {
        $script:RetryAttempts++
        if ($script:RetryAttempts -lt 3) { throw 'transient' }
    } -Wait { 'ok' }
    Assert-True ($result -eq 'ok') 'retry eventually succeeds'
    Assert-True ($script:RetryAttempts -eq 3) 'retry attempt count'

    try {
        Invoke-AircRemoteWithRetry -MaxRetries 1 -Send { throw 'always' } -Wait { 'x' } | Out-Null
        Assert-True $false 'retry exhaust should throw'
    } catch {
        Assert-True ((Protect-AircRemoteSecret ([string]$_)) -notmatch 'password=') 'retry error redacted'
        Assert-True $true 'retry exhausted'
    }

    $pm = @(New-AircPrivmsgLines -MachineId 'ionos' -Bodies @('STATUS'))
    Assert-True ($pm.Count -eq 1 -and $pm[0] -eq 'PRIVMSG ionos_console :STATUS') 'PRIVMSG framing'

    if ($script:SelfTestFailed -gt 0) {
        Write-Host ("SELFTEST FAILED count={0}" -f $script:SelfTestFailed)
        exit 1
    }
    Write-Host 'SELFTEST PASSED'
    exit 0
}

if ($SelfTest) {
    Invoke-AircRemoteSelfTest
}

# --- remote entry ------------------------------------------------------------

if (-not $MachineId) { throw '-MachineId is required unless -SelfTest' }

$bodies = [string[]]@()
$corr = if ($JobId) { $JobId } else { New-AircCorrelationId }

switch ($Action) {
    'Put' {
        if (-not $LocalFile) { throw 'Put requires -LocalFile' }
        if (-not $Path) { throw 'Put requires -Path (remote)' }
        $sandbox = $SandboxRoot
        if (-not $sandbox) {
            $ai = if ($env:AI_ROOT) { $env:AI_ROOT } else { 'C:\ai' }
            $sandbox = Join-Path $ai 'airc\drop'
        }
        $put = New-AircPutChunks -LocalFile $LocalFile -RemotePath $Path -ChunkBytes $ChunkBytes -JobId $corr -SandboxRoot $sandbox
        $corr = $put.JobId
        $bodies = [string[]]@($put.Lines)
    }
    'Psb64' {
        $bodies = [string[]]@((New-AircRemoteBody -Action Psb64 -Text $Text))
    }
    default {
        $bodies = [string[]]@((New-AircRemoteBody -Action $Action -Text $Text -Path $Path -JobId $corr))
    }
}

$privmsgs = @(New-AircPrivmsgLines -MachineId $MachineId -Bodies $bodies)
Write-Host ("INFO action={0} machine={1} id={2} lines={3}" -f $Action, $MachineId, $corr, $privmsgs.Count)

if ($Outbox) {
    Write-AircOutbox -Outbox $Outbox -Lines $privmsgs -WhatIf:$WhatIf
} elseif ($WhatIf) {
    foreach ($l in $privmsgs) { Write-Host ('WHATIF {0}' -f (Protect-AircRemoteSecret $l)) }
} else {
    Write-Host 'WARN no -Outbox; printing bodies only (not sent)'
    foreach ($l in $privmsgs) { Write-Host (Protect-AircRemoteSecret $l) }
}

if ($ReplyFile -and (Test-Path -LiteralPath $ReplyFile)) {
    $raw = Get-Content -LiteralPath $ReplyFile -Encoding utf8
    $parsed = ConvertFrom-AircRemoteReply -Lines $raw -ExpectJobId $corr
    Write-Output $parsed
    if ($parsed.ExitCode -ne 0) { exit $parsed.ExitCode }
}

exit 0
