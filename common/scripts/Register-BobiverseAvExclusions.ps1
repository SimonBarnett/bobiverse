#Requires -Version 4.0
<#
.SYNOPSIS
  Best-effort antivirus path/process exclusions before laying product binaries (FR #4215).

.DESCRIPTION
  Consumer AV (Avast, Defender, AVG, ...) often quarantines or blocks creating
  unsigned airc.exe / bob-ear.exe during install. Call this AFTER elevation and
  BEFORE New-Item / Copy / Build of the exe.

  - Windows Defender: Add-MpPreference ExclusionPath + ExclusionProcess (+ CFA allow).
  - Avast / AVG: detect install tree; append folder exclusions to known FileShield
    registry lists when present (best-effort; consumer UI may still need a manual
    exception when the key layout differs).
  - Never throws: failures become WARN lines so install can continue.

.PARAMETER Paths
  Folders to exclude (install root, airc subdir, ai root). Missing paths are still
  registered so Defender allows the first create.

.PARAMETER Processes
  Process image names (e.g. airc.exe) for Defender ExclusionProcess.

.PARAMETER Product
  Short product tag for log lines (airc / bob / jeeves).

.EXAMPLE
  .\Register-BobiverseAvExclusions.ps1 -Paths @('C:\ai\airc') -Processes @('airc.exe') -Product airc
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string[]]$Paths = @(),
    [string[]]$Processes = @(),
    [string]$Product = 'bobiverse',
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

function Test-BobiverseAvAdmin {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $p = New-Object Security.Principal.WindowsPrincipal($id)
        return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Get-BobiverseAvNormalizedPaths([string[]]$Raw) {
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($p in @($Raw)) {
        if (-not $p) { continue }
        $t = ([string]$p).Trim()
        if (-not $t) { continue }
        try { $t = [IO.Path]::GetFullPath($t) } catch { }
        if (-not $out.Contains($t)) { [void]$out.Add($t) }
    }
    return , $out.ToArray()
}

function Register-BobiverseDefenderExclusions {
    param([string[]]$PathList, [string[]]$ProcList)
    if (-not (Get-Command Add-MpPreference -ErrorAction SilentlyContinue)) {
        Write-Host 'INFO FR #4215 Defender Add-MpPreference not available (skipped)'
        return 0
    }
    $n = 0
    foreach ($path in $PathList) {
        if ($WhatIf) {
            Write-Host ("WhatIf: Defender ExclusionPath={0}" -f $path)
            $n++
            continue
        }
        try {
            Add-MpPreference -ExclusionPath $path -ErrorAction Stop
            Write-Host ("INFO FR #4215 Defender ExclusionPath ok: {0}" -f $path)
            $n++
        } catch {
            Write-Warning ("FR #4215 Defender ExclusionPath failed ({0}): {1}" -f $path, $_.Exception.Message)
        }
    }
    foreach ($proc in @($ProcList)) {
        if (-not $proc) { continue }
        $name = [IO.Path]::GetFileName($proc)
        if (-not $name) { continue }
        if ($WhatIf) {
            Write-Host ("WhatIf: Defender ExclusionProcess={0}" -f $name)
            $n++
            continue
        }
        try {
            Add-MpPreference -ExclusionProcess $name -ErrorAction Stop
            Write-Host ("INFO FR #4215 Defender ExclusionProcess ok: {0}" -f $name)
            $n++
        } catch {
            Write-Warning ("FR #4215 Defender ExclusionProcess failed ({0}): {1}" -f $name, $_.Exception.Message)
        }
        # Controlled Folder Access: allow the image when CFA is on (best-effort).
        foreach ($full in $PathList) {
            $candidate = Join-Path $full $name
            if ($WhatIf) { continue }
            try {
                Add-MpPreference -ControlledFolderAccessAllowedApplications $candidate -ErrorAction SilentlyContinue
            } catch { }
        }
    }
    return $n
}

function Register-BobiverseAvastFamilyExclusions {
    param([string[]]$PathList)
    # Detect Avast / AVG install roots (consumer + business layouts).
    $roots = @(
        ${env:ProgramFiles} + '\AVAST Software\Avast',
        ${env:ProgramFiles} + '\AVG\Antivirus',
        ${env:ProgramFiles(x86)} + '\AVAST Software\Avast',
        ${env:ProgramFiles(x86)} + '\AVG\Antivirus'
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    if (-not $roots -or $roots.Count -eq 0) {
        Write-Host 'INFO FR #4215 Avast/AVG not detected (skipped)'
        return 0
    }

    $n = 0
    # Known FileShield exclusion list value names (layout varies by build).
    $regCandidates = @(
        'HKLM:\SOFTWARE\AVAST Software\Avast\properties\settings\Shield\FileShield',
        'HKLM:\SOFTWARE\WOW6432Node\AVAST Software\Avast\properties\settings\Shield\FileShield',
        'HKLM:\SOFTWARE\AVG\Antivirus\properties\settings\Shield\FileShield',
        'HKLM:\SOFTWARE\WOW6432Node\AVG\Antivirus\properties\settings\Shield\FileShield'
    )

    foreach ($keyPath in $regCandidates) {
        if (-not (Test-Path -LiteralPath $keyPath)) { continue }
        foreach ($valueName in @('ExcludedFolders', 'ExcludedPaths', 'ExcludeFolders')) {
            try {
                $prop = Get-ItemProperty -LiteralPath $keyPath -ErrorAction SilentlyContinue
                if (-not $prop) { continue }
                $names = @($prop.PSObject.Properties | ForEach-Object { $_.Name })
                if ($names -notcontains $valueName) { continue }
                $existing = [string]$prop.$valueName
                if ($null -eq $existing) { $existing = '' }
                $changed = $false
                foreach ($path in $PathList) {
                    if ($existing -and ($existing.IndexOf($path, [StringComparison]::OrdinalIgnoreCase) -ge 0)) {
                        continue
                    }
                    if ($WhatIf) {
                        Write-Host ("WhatIf: Avast/AVG {0}\{1} += {2}" -f $keyPath, $valueName, $path)
                        $n++
                        $changed = $true
                        continue
                    }
                    if ($existing) { $existing = $existing.TrimEnd(';', ' ') + ';' + $path }
                    else { $existing = $path }
                    $changed = $true
                    $n++
                }
                if ($changed -and -not $WhatIf) {
                    Set-ItemProperty -LiteralPath $keyPath -Name $valueName -Value $existing -ErrorAction Stop
                    Write-Host ("INFO FR #4215 Avast/AVG registry exclusion via {0}\{1}" -f $keyPath, $valueName)
                }
            } catch {
                Write-Warning ("FR #4215 Avast/AVG registry exclusion failed ({0}): {1}" -f $keyPath, $_.Exception.Message)
            }
        }
    }

    if ($n -eq 0) {
        $hint = ($PathList | Select-Object -First 3) -join '; '
        Write-Warning ("FR #4215 Avast/AVG detected under {0} but no writable FileShield exclusion key. Add a manual File/Folder exception for: {1}" -f ($roots[0]), $hint)
    }
    return $n
}

# --- main ---
if (-not (Test-BobiverseAvAdmin)) {
    Write-Warning 'FR #4215 AV exclusions require elevation; skipped (caller should UAC first)'
    return
}

$pathList = @(Get-BobiverseAvNormalizedPaths $Paths)
$procList = @($Processes | Where-Object { $_ } | ForEach-Object { [string]$_ })

if ($pathList.Count -eq 0 -and $procList.Count -eq 0) {
    Write-Host 'INFO FR #4215 no Paths/Processes supplied; nothing to register'
    return
}

Write-Host ("INFO FR #4215 Register-BobiverseAvExclusions product={0} paths={1} processes={2}" -f $Product, $pathList.Count, $procList.Count)
$d = Register-BobiverseDefenderExclusions -PathList $pathList -ProcList $procList
$a = Register-BobiverseAvastFamilyExclusions -PathList $pathList
Write-Host ("INFO FR #4215 AV exclusion ops defender={0} avast_family={1}" -f $d, $a)
