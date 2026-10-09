#Requires -Version 4.0
# Dot-source only. Issue #266: prefer release-bundled NSSM over <ai root>\ergo\nssm.exe.
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
    # t780u: legacy shared nssm locations live under the discovered <drive>:\ai (Common is dot-sourced by every installer).
    if (Get-Command Get-BobiverseAiRoot -ErrorAction SilentlyContinue) {
        $aiRoot = Get-BobiverseAiRoot
        $candidates += @((Join-Path $aiRoot 'ergo\nssm.exe'), (Join-Path $aiRoot 'nssm\nssm.exe'))
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) {
            return (Resolve-Path -LiteralPath $c).Path
        }
    }
    $cmd = Get-Command nssm.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return [string]$cmd.Source }
    return $null
}
