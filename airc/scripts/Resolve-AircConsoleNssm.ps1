#Requires -Version 5.1
# Dot-source only. Issue #266: prefer release-bundled NSSM over C:\ai\ergo\nssm.exe.
function Resolve-AircConsoleNssmPath {
    param(
        [string]$Preferred = '',
        [string]$ScriptDir = ''
    )
    if ($Preferred -and (Test-Path -LiteralPath $Preferred)) {
        return (Resolve-Path -LiteralPath $Preferred).Path
    }
    if (-not $ScriptDir) {
        if ($PSScriptRoot) { $ScriptDir = $PSScriptRoot }
        elseif ($PSCommandPath) { $ScriptDir = Split-Path -Parent $PSCommandPath }
        elseif ($MyInvocation.MyCommand.Path) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
    }
    $candidates = @()
    if ($ScriptDir) {
        $root = Split-Path -Parent $ScriptDir
        $candidates += @(
            (Join-Path $root 'third_party\nssm\win64\nssm.exe'),
            (Join-Path $root 'third_party\nssm\nssm.exe'),
            (Join-Path $ScriptDir 'nssm.exe'),
            (Join-Path $ScriptDir 'nssm\nssm.exe')
        )
    }
    $candidates += @(
        'C:\ai\ergo\nssm.exe',
        'C:\ai\nssm\nssm.exe'
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) {
            return (Resolve-Path -LiteralPath $c).Path
        }
    }
    $cmd = Get-Command nssm.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return [string]$cmd.Source }
    return $null
}
