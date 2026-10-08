#Requires -Version 5.1
<#
.SYNOPSIS
  Install git, gh, Python 3.12+, Node LTS IF MISSING (bobiverse).
.NOTES
  Issue #10: LocalSystem MSI QuietExec often cannot see per-user PATH tools
  (e.g. %LOCALAPPDATA%\Programs\gh). Resolve well-known paths before winget;
  soft-fail optional gh when winget is unavailable so the product MSI does
  not 1603.
  FR #1825: winget under SYSTEM cannot use per-user WindowsApps winget alias.
  Prefer a pinned nodejs.org x64 MSI (ALLUSERS=1) for Node; soft-fail git /
  python / node with WARN when install still fails so the product MSI does
  not 1603 on a clean box.
#>
[CmdletBinding()]
param(
    [switch]$ForceTools,
    # FR #3290: MSI BOBIVERSE_SKIP_TOOLS=1 / callers that already decided to skip.
    [switch]$SkipTools
)

$ErrorActionPreference = 'Stop'

if ($SkipTools) {
    Write-Host 'INFO bootstrap-tools skipped (SkipTools) FR #3290'
    return
}

$script:BobiverseToolsInstalled = New-Object System.Collections.Generic.List[string]

# Pinned Node LTS x64 MSI (nodejs.org). Override with BOB_BOOTSTRAP_NODE_MSI_URL / BOB_BOOTSTRAP_NODE_MSI_SHA256.
$script:NodeMsiVersion = '24.21.0'
$script:NodeMsiSha256 = 'bb0eaee134f9357f22aea915ee793343e627aefc1e66488164bac6915bce2cac'
$script:NodeMsiUrl = 'https://nodejs.org/dist/v' + $script:NodeMsiVersion + '/node-v' + $script:NodeMsiVersion + '-x64.msi'

function Add-PathDir([string]$Dir) {
    if (-not $Dir -or -not (Test-Path -LiteralPath $Dir)) { return }
    $parts = $env:Path -split ';' | Where-Object { $_ -and $_.Trim() }
    if ($parts -contains $Dir) { return }
    $env:Path = "$Dir;$env:Path"
}

function Resolve-KnownTool([string]$Name) {
    $c = Get-Command $Name -ErrorAction SilentlyContinue
    if ($c -and $c.Source) { return $c.Source }

    $candidates = @()
    switch ($Name.ToLowerInvariant()) {
        'gh' {
            $candidates = @(
                (Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe'),
                (Join-Path ${env:ProgramFiles(x86)} 'GitHub CLI\gh.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\gh\bin\gh.exe'),
                (Join-Path $env:USERPROFILE 'bin\gh\gh.exe'),
                (Join-Path $env:LOCALAPPDATA 'gh-cli\bin\gh.exe')
            )
        }
        'git' {
            $candidates = @(
                (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'),
                (Join-Path ${env:ProgramFiles(x86)} 'Git\cmd\git.exe')
            )
        }
        'python' {
            $candidates = @(
                'C:\Python312\python.exe',
                'C:\Python313\python.exe',
                (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
                (Join-Path $env:ProgramFiles 'Python312\python.exe')
            )
        }
        'node' {
            $candidates = @(
                (Join-Path $env:ProgramFiles 'nodejs\node.exe'),
                (Join-Path ${env:ProgramFiles(x86)} 'nodejs\node.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\node\node.exe')
            )
        }
        'winget' {
            $candidates = @(
                (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe'),
                (Join-Path $env:ProgramFiles 'WindowsApps\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\winget.exe')
            )
        }
    }
    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            Add-PathDir (Split-Path -Parent $p)
            return $p
        }
    }
    return $null
}

function Test-CmdVersion([string]$Name) {
    return [bool](Resolve-KnownTool $Name)
}

function Install-WingetPackage([string]$Id) {
    $winget = Resolve-KnownTool 'winget'
    if (-not $winget) { return $false }
    # Per-user WindowsApps winget alias is often unusable under SYSTEM (FR #1825).
    if ($winget -match '[\\/]WindowsApps[\\/]winget\.exe$') {
        Write-Host "WARN winget alias is WindowsApps path ($winget) - may fail under SYSTEM; trying anyway"
    }
    & $winget install --id $Id -e --accept-package-agreements --accept-source-agreements --disable-interactivity
    return ($LASTEXITCODE -eq 0)
}

function Install-NodeOfficialMsi {
    <#
      FR #1825: machine-wide Node via pinned nodejs.org MSI (not winget under SYSTEM).
      Returns $true if node is present after attempt.
    #>
    if (Test-CmdVersion 'node') { return $true }
    $url = if ($env:BOB_BOOTSTRAP_NODE_MSI_URL) { $env:BOB_BOOTSTRAP_NODE_MSI_URL.Trim() } else { $script:NodeMsiUrl }
    $sha = if ($env:BOB_BOOTSTRAP_NODE_MSI_SHA256) { $env:BOB_BOOTSTRAP_NODE_MSI_SHA256.Trim().ToLowerInvariant() } else { $script:NodeMsiSha256 }
    if (-not $url) { return $false }
    $cacheRoot = Join-Path $env:TEMP 'bobiverse-bootstrap'
    New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null
    $msi = Join-Path $cacheRoot ("node-v$($script:NodeMsiVersion)-x64.msi")
    try {
        Write-Host "INFO tool-install node via official MSI $url"
        if (-not (Test-Path -LiteralPath $msi)) {
            Invoke-WebRequest -Uri $url -OutFile $msi -UseBasicParsing -TimeoutSec 300
        }
        if ($sha) {
            $hash = (Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($hash -ne $sha) {
                Write-Host "WARN node MSI sha256 mismatch (got $hash want $sha) - deleting cache"
                Remove-Item -LiteralPath $msi -Force -ErrorAction SilentlyContinue
                return $false
            }
        }
        $p = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i', $msi, '/qn', 'ALLUSERS=1', '/norestart') -Wait -PassThru
        if ($p.ExitCode -ne 0) {
            Write-Host "WARN node MSI msiexec exit $($p.ExitCode)"
            return $false
        }
        # msiexec may not refresh this process PATH; probe well-known locations.
        return [bool](Resolve-KnownTool 'node')
    } catch {
        Write-Host "WARN node official MSI failed: $($_.Exception.Message)"
        return $false
    }
}

function Ensure-Tool {
    param(
        [string]$Label,
        [string]$Cmd,
        [string]$WingetId,
        [scriptblock]$Present,
        [switch]$Optional,
        [scriptblock]$DirectInstall
    )
    if (-not $ForceTools -and (& $Present)) {
        $resolved = Resolve-KnownTool $Cmd
        if ($resolved) {
            Write-Host "INFO tool-present $Label ($resolved)"
        } else {
            Write-Host "INFO tool-present $Label"
        }
        return
    }
    $installed = $false
    if ($DirectInstall) {
        try { $installed = [bool](& $DirectInstall) } catch {
            Write-Host "WARN direct-install $Label failed: $($_.Exception.Message)"
            $installed = $false
        }
    }
    if (-not $installed) {
        Write-Host "INFO tool-install $Label via winget $WingetId"
        $installed = Install-WingetPackage $WingetId
    }
    if (-not $installed) {
        if ($Optional) {
            Write-Host "WARN tool-missing $Label (winget unavailable or failed) - continuing (issue #10 / FR #1825)"
            return
        }
        throw "failed to install $Label (winget $WingetId). Install manually or cache under third_party/bootstrap."
    }
    if (-not (& $Present)) {
        if ($Optional) {
            Write-Host "WARN tool-missing $Label after install - continuing (issue #10 / FR #1825)"
            return
        }
        throw "$Label still missing after winget install"
    }
    # FR #3290: record tools this run actually installed (for uninstall offer).
    if ($installed -and $script:BobiverseToolsInstalled -and -not ($script:BobiverseToolsInstalled -contains $Label)) {
        [void]$script:BobiverseToolsInstalled.Add($Label)
    }
}

# Soft-fail under LocalSystem quiet MSI when winget cannot install (FR #1825 / issue #10).
Ensure-Tool 'git' 'git' 'Git.Git' { Test-CmdVersion 'git' } -Optional
Ensure-Tool 'gh' 'gh' 'GitHub.cli' { Test-CmdVersion 'gh' } -Optional
Ensure-Tool 'python' 'python' 'Python.Python.3.12' {
    $py = Resolve-KnownTool 'python'
    if (-not $py) { return $false }
    $v = & $py -c "import sys; print('%d.%d'%sys.version_info[:2])"
    return ([version]$v -ge [version]'3.12')
} -Optional
Ensure-Tool 'node' 'node' 'OpenJS.NodeJS.LTS' { Test-CmdVersion 'node' } -Optional -DirectInstall { Install-NodeOfficialMsi }

# Runtime deps for irc_agent / seal (issue #3)
$pyPath = Resolve-KnownTool 'python'
if ($pyPath) {
    $here = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    . (Join-Path $here 'Bobiverse-Common.ps1')
    try { Install-BobiversePythonDeps -Python $pyPath } catch {
        Write-Host "WARN python deps: $($_.Exception.Message)"
    }
} else {
    Write-Host 'WARN tool-missing python - skip python deps (FR #1825)'
}

# FR #3290: durable list of tools this bootstrap installed (uninstall can offer to remove).
try {
    if ($script:BobiverseToolsInstalled -and $script:BobiverseToolsInstalled.Count -gt 0) {
        $pd = Join-Path $env:ProgramData 'Bobiverse'
        New-Item -ItemType Directory -Force -Path $pd | Out-Null
        $recPath = Join-Path $pd 'installed-tools.json'
        $prior = @()
        if (Test-Path -LiteralPath $recPath) {
            try {
                $old = Get-Content -LiteralPath $recPath -Raw -Encoding utf8 | ConvertFrom-Json
                if ($old.tools) { $prior = @($old.tools) }
            } catch { }
        }
        $merged = @($prior + @($script:BobiverseToolsInstalled) | Select-Object -Unique)
        $rec = [ordered]@{
            v       = 1
            updated = (Get-Date).ToUniversalTime().ToString('o')
            tools   = @($merged)
        }
        ($rec | ConvertTo-Json) | Set-Content -LiteralPath $recPath -Encoding utf8
        Write-Host ("INFO wrote {0} tools={1}" -f $recPath, ($merged -join ','))
    }
} catch {
    Write-Host ("WARN installed-tools.json: {0}" -f $_.Exception.Message)
}
Write-Host 'INFO bootstrap-tools done'
