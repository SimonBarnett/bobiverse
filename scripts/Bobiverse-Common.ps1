#Requires -Version 5.1
<#
.SYNOPSIS
  Shared helpers for bobiverse Install-*.ps1 (clean reinstall, NSSM, skills, shortcuts).
#>

function Test-BobiverseIsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-BobiverseScriptDir {
    if ($PSScriptRoot) { return $PSScriptRoot }
    if ($PSCommandPath) { return (Split-Path -Parent $PSCommandPath) }
    if ($MyInvocation.MyCommand.Path) { return (Split-Path -Parent $MyInvocation.MyCommand.Path) }
    throw 'cannot resolve bobiverse scripts directory'
}

function Invoke-BobiverseNssm {
    param([Parameter(Mandatory)][string]$Exe, [Parameter(Mandatory)][string[]]$NssmArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $Exe @NssmArgs 2>&1
        $code = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    return [pscustomobject]@{ ExitCode = $code; Output = @($out | ForEach-Object { "$_" }) }
}

function Remove-BobiverseService {
    param([Parameter(Mandatory)][string]$Nssm, [Parameter(Mandatory)][string]$Name)
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "INFO service $Name absent"
        return
    }
    Write-Host "INFO removing service $Name"
    [void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('stop', $Name))
    Start-Sleep -Seconds 2
    [void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('remove', $Name, 'confirm'))
    Start-Sleep -Seconds 1
}

function Resolve-BobiverseNssm {
    param([string]$Preferred = '', [string]$ScriptDir = '')
    if ($Preferred -and (Test-Path -LiteralPath $Preferred)) {
        return (Resolve-Path -LiteralPath $Preferred).Path
    }
    if (-not $ScriptDir) { $ScriptDir = Get-BobiverseScriptDir }
    $pack = Join-Path (Split-Path -Parent $ScriptDir) 'third_party\nssm\win64\nssm.exe'
    foreach ($c in @(
            $pack,
            'C:\ai\ergo\nssm.exe',
            'C:\ai\bob\third_party\nssm\win64\nssm.exe',
            'C:\ai\jeeves\third_party\nssm\win64\nssm.exe'
        )) {
        if (Test-Path -LiteralPath $c) { return (Resolve-Path -LiteralPath $c).Path }
    }
    $onPath = Get-Command nssm.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

function Resolve-BobiversePython {
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    foreach ($c in @(
            "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
            'C:\Python312\python.exe',
            'C:\Program Files\Python312\python.exe'
        )) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    throw 'python.exe not found (run Install-BootstrapTools.ps1)'
}

function Install-BobiverseSkills {
    param(
        [Parameter(Mandatory)][string]$RepoSkillsRoot,
        [Parameter(Mandatory)][string[]]$SkillNames
    )
    $destRoot = Join-Path $env:USERPROFILE '.grok\skills'
    New-Item -ItemType Directory -Force -Path $destRoot | Out-Null
    foreach ($name in $SkillNames) {
        $src = Join-Path $RepoSkillsRoot $name
        if (-not (Test-Path -LiteralPath $src)) {
            Write-Host "WARN skill missing in pack: $name"
            continue
        }
        $dest = Join-Path $destRoot $name
        if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
        Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force
        Write-Host "INFO installed skill $name -> $dest"
    }
}

function New-BobiverseShortcut {
    param(
        [Parameter(Mandatory)][string]$LinkPath,
        [Parameter(Mandatory)][string]$TargetPath,
        [string]$Arguments = '',
        [string]$WorkingDirectory = '',
        [string]$Description = ''
    )
    $dir = Split-Path -Parent $LinkPath
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $w = New-Object -ComObject WScript.Shell
    $sc = $w.CreateShortcut($LinkPath)
    $sc.TargetPath = $TargetPath
    if ($Arguments) { $sc.Arguments = $Arguments }
    if ($WorkingDirectory) { $sc.WorkingDirectory = $WorkingDirectory }
    if ($Description) { $sc.Description = $Description }
    $sc.Save()
    Write-Host "INFO shortcut $LinkPath"
}

function Copy-BobiverseVersion {
    param([Parameter(Mandatory)][string]$InstallRoot, [Parameter(Mandatory)][string]$RepoRoot)
    $src = Join-Path $RepoRoot 'src\VERSION'
    if (-not (Test-Path -LiteralPath $src)) { throw "missing $src" }
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    Copy-Item -LiteralPath $src -Destination (Join-Path $InstallRoot 'VERSION') -Force
}

function Request-BobiverseUacRelaunch {
    param([Parameter(Mandatory)][System.Management.Automation.PSBoundParameters]$Bound)
    $self = $PSCommandPath
    if (-not $self) { $self = $MyInvocation.MyCommand.Path }
    if (-not $self) { throw 'cannot resolve script path for UAC' }
    Write-Host 'INFO not elevated; requesting UAC'
    $list = New-Object System.Collections.Generic.List[string]
    [void]$list.Add('-NoProfile'); [void]$list.Add('-ExecutionPolicy'); [void]$list.Add('Bypass')
    [void]$list.Add('-File'); [void]$list.Add($self)
    foreach ($key in $Bound.Keys) {
        $val = $Bound[$key]
        if ($val -is [System.Management.Automation.SwitchParameter]) {
            if ($val.IsPresent) { [void]$list.Add("-$key") }
            continue
        }
        [void]$list.Add("-$key")
        if ($val -is [System.Array]) {
            foreach ($item in $val) { [void]$list.Add([string]$item) }
        } else {
            [void]$list.Add([string]$val)
        }
    }
    $p = Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $list.ToArray() -Wait -PassThru
    if ($null -eq $p) { throw 'UAC cancelled' }
    exit [int]$p.ExitCode
}
