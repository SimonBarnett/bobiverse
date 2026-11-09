#Requires -Version 5.1
<#
.SYNOPSIS
  Write a labelled OpenCode Go API key with SYSTEM+Administrators ACL (FR #6301 Part D).

.DESCRIPTION
  Optional helper. Simon may also copy keys by hand into
  <InstallRoot>\config\opencode-keys\<label>.apikey.
  The key is read via a masked SecureString prompt (or -KeySecure) and is never echoed.
  Optionally writes config\opencode-keys\selected.txt with the label.

.PARAMETER Label
  Account label / file stem (e.g. work, personal, default).

.PARAMETER InstallRoot
  Bob install root. Defaults to BOB_INSTALL_ROOT or C:\ai\bob.

.PARAMETER KeySecure
  Optional SecureString key (scriptable). When omitted, prompts masked.

.PARAMETER Select
  Also mark this label as the selected key for the ear.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._@+-]{0,63}$')]
    [string]$Label,

    [string]$InstallRoot = '',

    [SecureString]$KeySecure = $null,

    [switch]$Select
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-BobInstallRoot([string]$Root) {
    $r = ([string]$Root).Trim()
    if (-not $r) { $r = ([string]$env:BOB_INSTALL_ROOT).Trim() }
    if (-not $r) { $r = 'C:\ai\bob' }
    return $r
}

function Set-SystemAdminsAcl([string]$Path) {
    # SYSTEM + Administrators only; strip inheritance.
    & icacls.exe $Path /inheritance:r /grant:r 'NT AUTHORITY\SYSTEM:(F)' 'BUILTIN\Administrators:(F)' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw ("icacls failed on {0} (exit {1})" -f $Path, $LASTEXITCODE)
    }
}

$root = Get-BobInstallRoot $InstallRoot
$keysDir = Join-Path (Join-Path $root 'config') 'opencode-keys'
if (-not (Test-Path -LiteralPath $keysDir -PathType Container)) {
    New-Item -ItemType Directory -Path $keysDir -Force | Out-Null
}
Set-SystemAdminsAcl $keysDir

if (-not $KeySecure) {
    $KeySecure = Read-Host -AsSecureString -Prompt ('OpenCode Go API key for label {0}' -f $Label)
}
if (-not $KeySecure) { throw 'no key provided' }

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($KeySecure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}
if (-not $plain -or -not $plain.Trim()) {
    throw 'empty key'
}
$plain = $plain.Trim()

$dest = Join-Path $keysDir ($Label + '.apikey')
# Write without printing the value.
[System.IO.File]::WriteAllText($dest, $plain, [Text.UTF8Encoding]::new($false))
$plain = $null
Set-SystemAdminsAcl $dest

if ($Select) {
    $sel = Join-Path $keysDir 'selected.txt'
    [System.IO.File]::WriteAllText($sel, $Label + "`n", [Text.UTF8Encoding]::new($false))
    Set-SystemAdminsAcl $sel
}

Write-Host ("Wrote labelled OpenCode key file for label '{0}' (ACL SYSTEM+Administrators)." -f $Label)
if ($Select) {
    Write-Host ("Selected label '{0}'." -f $Label)
}
exit 0
