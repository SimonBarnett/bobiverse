#Requires -Version 5.1
<#
.SYNOPSIS
  Console-side CRED persist via=irc sender (FR #5825).
.DESCRIPTION
  Reads a credential from local CredMan or a SecureString prompt, then drives
  CRED persist via=irc + CRED-SEAL over the Bob ear outbox / airc-replies.jsonl
  path (same nick that opened HELLO). Never accepts a plaintext password on the
  command line or from a file. Exit 0 only on cred-persisted.
.NOTES
  PowerShell 5.1 only. Relies on airc_cred_send.py + cryptography.
#>
[CmdletBinding(DefaultParameterSetName = 'CredMan')]
param(
    [Parameter(Mandatory)]
    [string]$MachineId,

    [Parameter(Mandatory)]
    [string]$Target,

    [Parameter(ParameterSetName = 'CredMan', Mandatory)]
    [string]$CredManSource,

    [Parameter(ParameterSetName = 'Prompt', Mandatory)]
    [string]$Username,

    [Parameter(ParameterSetName = 'Prompt')]
    [securestring]$Password,

    [Parameter(ParameterSetName = 'Prompt')]
    [switch]$Prompt,

    [string]$Outbox = '',

    [string]$ReplyFile = '',

    [int]$TimeoutSec = 90,

    [string]$Python = '',

    [string]$Qid = '',

    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-AircCredSendScript {
    $here = $PSScriptRoot
    $cand = Join-Path $here 'airc_cred_send.py'
    if (Test-Path -LiteralPath $cand) { return $cand }
    throw 'airc_cred_send.py not found beside Send-AircCred.ps1'
}

function Resolve-AircCredPython {
    param([string]$Preferred)
    if ($Preferred -and (Test-Path -LiteralPath $Preferred)) { return $Preferred }
    foreach ($c in @(
            (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
            'C:\Program Files\Python312\python.exe',
            'C:\Python312\python.exe'
        )) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    throw 'python.exe not found (needed for airc_cred_send.py)'
}

function ConvertFrom-AircSecureStringPlain {
    param([Parameter(Mandatory)][securestring]$Secure)
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
        }
    }
}

function Invoke-AircCredSendSelfTest {
    $py = Resolve-AircCredPython -Preferred $Python
    $script = Get-AircCredSendScript
    $code = @'
import airc_cred_send as s
assert s.parse_cred_hello("out CRED-HELLO token=aabbccddeeff0011 pub=x exp=9999999999 alg=x25519-chacha20poly1305 target=T")
assert "via=irc" in s.format_persist_command(qid="c5825001", target="T")
assert s.extract_cred_result_code("DONE exit=0 cred-persisted target=T account=U") == "cred-persisted"
print("ok")
'@
    $env:PYTHONPATH = (Split-Path -Parent $script)
    & $py -c $code
    if ($LASTEXITCODE -ne 0) { throw "SelfTest failed exit=$LASTEXITCODE" }
    Write-Host 'Send-AircCred SelfTest OK'
}

if ($SelfTest) {
    Invoke-AircCredSendSelfTest
    return
}

if (-not $Outbox) {
    throw 'Outbox is required (Bob ear/worker outbox.txt)'
}
if (-not (Test-Path -LiteralPath $Outbox)) {
    # allow create-on-write by Python; ensure parent exists
    $parent = Split-Path -Parent $Outbox
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        throw "Outbox parent missing: $parent"
    }
}

$py = Resolve-AircCredPython -Preferred $Python
$script = Get-AircCredSendScript
$env:PYTHONPATH = (Split-Path -Parent $script)

$argList = @(
    $script,
    '--machine', $MachineId,
    '--target', $Target,
    '--outbox', $Outbox,
    '--timeout-s', ([string][Math]::Max(1, $TimeoutSec))
)
if ($ReplyFile) { $argList += @('--replies', $ReplyFile) }
if ($Qid) { $argList += @('--qid', $Qid) }

$plain = $null
try {
    if ($PSCmdlet.ParameterSetName -eq 'CredMan') {
        $argList += @('--credman-source', $CredManSource)
        & $py @argList
        exit $LASTEXITCODE
    }

    $user = ($Username | ForEach-Object { $_.Trim() })
    if (-not $user) { throw 'Username required for Prompt set' }
    $sec = $Password
    if ($Prompt -or -not $sec) {
        $sec = Read-Host -AsSecureString -Prompt 'Password'
    }
    $plain = ConvertFrom-AircSecureStringPlain -Secure $sec
    $argList += @('--username', $user, '--stdin-password')
    $plain | & $py @argList
    exit $LASTEXITCODE
}
finally {
    if ($null -ne $plain) {
        $plain = $null
        [GC]::Collect()
    }
}
