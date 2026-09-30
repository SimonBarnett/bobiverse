function Get-BridgeRoot {
    if ($env:BOB_BRIDGE_HOME -and $env:BOB_BRIDGE_HOME.Trim()) {
        return [IO.Path]::GetFullPath($env:BOB_BRIDGE_HOME)
    }
    return [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.grok\bob-bridge'))
}

function Initialize-BridgeRoot {
    $root = Get-BridgeRoot
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $root 'workers') | Out-Null
    $overlayPath = Join-Path $root 'overlay.json'
    if (-not (Test-Path $overlayPath)) {
        Write-JsonFile $overlayPath @{ workers = @() }
    }
    $cfgPath = Join-Path $root 'config.json'
    if (-not (Test-Path $cfgPath)) {
        $bundled = Join-Path (Get-ModuleRoot) 'config\default.json'
        if (-not (Test-Path $bundled)) {
            $bundled = Join-Path (Split-Path (Get-ModuleRoot) -Parent) 'config\default.json'
        }
        if (Test-Path $bundled) {
            Copy-Item $bundled $cfgPath
        }
        else {
            Write-JsonFile $cfgPath @{ max_workers_per_machine = 0; profiles = @{} }
        }
    }
    if (-not (Test-Path (Join-Path $root 'audit.jsonl'))) {
        [IO.File]::WriteAllText((Join-Path $root 'audit.jsonl'), '')
    }
    if (-not (Test-Path (Join-Path $root 'job-audit.jsonl'))) {
        [IO.File]::WriteAllText((Join-Path $root 'job-audit.jsonl'), '')
    }
    return $root
}

function Get-ModuleRoot {
    # src/ when loaded as module; repo root is parent of src
    $src = $PSScriptRoot
    if ((Split-Path $src -Leaf) -eq 'Private') {
        $src = Split-Path $src -Parent
    }
    return (Split-Path $src -Parent)
}

function Get-WorkerDir {
    param([Parameter(Mandatory)][string]$SessionId)
    Join-Path (Get-BridgeRoot) (Join-Path 'workers' $SessionId)
}

function Read-JsonFile {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $raw = $null
    for ($i = 0; $i -lt 8; $i++) {
        try {
            $raw = [IO.File]::ReadAllText($Path)
            break
        }
        catch {
            if ($i -ge 7) { throw }
            Start-Sleep -Milliseconds 60
        }
    }
    if (-not $raw -or -not $raw.Trim()) { return $null }
    # NUL-smashed or truncated files must not throw into tray poll.
    if ($raw.IndexOf([char]0) -ge 0) { return $null }
    $trim = $raw.TrimStart()
    if (-not ($trim.StartsWith('{') -or $trim.StartsWith('['))) { return $null }
    try {
        return $raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)]$Object
    )
    $dir = Split-Path $Path -Parent
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $json = $Object | ConvertTo-Json -Depth 12
    [IO.File]::WriteAllText($Path, $json)
}

function Read-Overlay {
    Initialize-BridgeRoot | Out-Null
    $path = Join-Path (Get-BridgeRoot) 'overlay.json'
    $o = Read-JsonFile $path
    if (-not $o) { $o = [pscustomobject]@{ workers = @() } }
    if (-not $o.workers) { $o | Add-Member -NotePropertyName workers -NotePropertyValue @() -Force }
    # Normalize to array
    $w = @($o.workers)
    $o | Add-Member -NotePropertyName workers -NotePropertyValue $w -Force
    return $o
}

function Write-Overlay {
    param($Overlay)
    Write-JsonFile (Join-Path (Get-BridgeRoot) 'overlay.json') $Overlay
}

function Get-GrokExe {
    if ($env:BOB_GROK_EXE -and $env:BOB_GROK_EXE.Trim()) {
        return $env:BOB_GROK_EXE.Trim()
    }
    $cmd = Get-Command grok -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path $env:USERPROFILE '.grok\bin\grok.exe'
    if (Test-Path $fallback) { return $fallback }
    return $null
}
