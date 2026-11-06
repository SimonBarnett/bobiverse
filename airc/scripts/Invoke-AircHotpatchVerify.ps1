# FR #6109: hotpatch verify. Never use $t/$T --- PowerShell folds them, so
# Get-Content into $t then Remove-Item $T deletes a path made of file text.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $ProbeFile
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $ProbeFile)) {
    throw "probe missing: $ProbeFile"
}

$VerifyText = [IO.File]::ReadAllText($ProbeFile)
$VerifyTempDir = Join-Path ([IO.Path]::GetTempPath()) ('airc-hotpatch-verify-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $VerifyTempDir | Out-Null
try {
    $stamp = Join-Path $VerifyTempDir 'ok.txt'
    [IO.File]::WriteAllText($stamp, $VerifyText)
    if (-not (Test-Path -LiteralPath $stamp)) {
        throw 'verify stamp missing'
    }
    Write-Output 'verify-ok'
}
finally {
    Remove-Item -LiteralPath $VerifyTempDir -Recurse -Force -ErrorAction SilentlyContinue
}
