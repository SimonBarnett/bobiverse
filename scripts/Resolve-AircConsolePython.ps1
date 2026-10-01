#Requires -Version 5.1
# Dot-source only. Issue #282: LocalSystem has no python on PATH — resolve absolute exe.
function Test-AircRealPythonExe {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    # Skip WindowsApps stub (opens Store).
    if ($Path -match '\\WindowsApps\\') { return $false }
    try {
        $v = & $Path -c "import sys; print(sys.version)" 2>$null
        return [bool]$v
    } catch {
        return $false
    }
}

function Resolve-AircConsolePythonPath {
    param(
        [string]$Preferred = '',
        [string]$HintUserProfile = ''
    )
    if ($Preferred -and (Test-AircRealPythonExe $Preferred)) {
        return (Resolve-Path -LiteralPath $Preferred).Path
    }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd -and (Test-AircRealPythonExe $cmd.Source)) {
        return $cmd.Source
    }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $exe = (& $py.Source -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
            if ($exe -and (Test-AircRealPythonExe $exe.Trim())) { return $exe.Trim() }
        } catch { }
    }
    $roots = @()
    if ($HintUserProfile) {
        $roots += (Join-Path $HintUserProfile 'AppData\Local\Programs\Python')
    }
    if ($env:LOCALAPPDATA) {
        $roots += (Join-Path $env:LOCALAPPDATA 'Programs\Python')
    }
    $roots += @(
        'C:\Program Files\Python312',
        'C:\Program Files\Python311',
        'C:\Program Files\Python310',
        'C:\Python312',
        'C:\Python311',
        'C:\Python310'
    )
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $hits = @(Get-ChildItem -LiteralPath $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch '\\WindowsApps\\' -and $_.FullName -notmatch '\\venv\\' } |
            Select-Object -First 5)
        foreach ($h in $hits) {
            if (Test-AircRealPythonExe $h.FullName) { return $h.FullName }
        }
    }
    return $null
}
