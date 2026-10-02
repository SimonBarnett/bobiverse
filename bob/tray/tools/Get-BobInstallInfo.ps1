#Requires -Version 5.1
# t797u: what is installed on this machine, per product (bob, jeeves, airc, ergo): every install folder found by scanning the
# ai roots AND the Windows services, each with version, release/build date, commit and path. Products that are not installed are
# simply absent (no error, no empty row). Pure functions: the service and git lookups are injectable so tests need neither.
# ASCII-only for Windows PowerShell 5.1.

$script:BobInfoProducts = @(
    [pscustomobject]@{ Product = 'bob';    Service = 'ircBob';    Dir = 'bob' }
    [pscustomobject]@{ Product = 'jeeves'; Service = 'ircJeeves'; Dir = 'jeeves' }
    [pscustomobject]@{ Product = 'airc';   Service = 'Airc';      Dir = 'airc' }
    [pscustomobject]@{ Product = 'ergo';   Service = 'BobIrcd';   Dir = 'ergo' }
)

function Get-BobInfoAiRoots {
    param([string]$RepoRoot = '')
    $roots = New-Object System.Collections.Generic.List[string]
    $e = ([string]$env:BOB_AI_ROOT).Trim()
    if ($e) { $roots.Add($e) }
    if ($RepoRoot -and (Split-Path -Leaf $RepoRoot) -ieq 'bob') { $roots.Add((Split-Path -Parent $RepoRoot)) }
    try {
        foreach ($d in @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' -ErrorAction Stop)) { $roots.Add(($d.DeviceID + '\ai')) }
    } catch {
        try { foreach ($d in [IO.DriveInfo]::GetDrives()) { if ($d.DriveType -eq 'Fixed') { $roots.Add(($d.Name + 'ai')) } } } catch { }
    }
    return @($roots | Where-Object { $_ } | Select-Object -Unique)
}

function Get-BobInfoServices {
    # Default service probe: existing services among the product services + the install dir NSSM was given.
    param([string[]]$Names)
    $out = New-Object System.Collections.Generic.List[object]
    foreach ($n in $Names) {
        $svc = $null
        try { $svc = Get-CimInstance Win32_Service -Filter ("Name='{0}'" -f $n) -ErrorAction Stop } catch { }
        if (-not $svc) { continue }
        $dir = ''
        try {
            $pk = 'HKLM:\SYSTEM\CurrentControlSet\Services\{0}\Parameters' -f $n
            $app = [string](Get-ItemProperty -LiteralPath $pk -Name Application -ErrorAction SilentlyContinue).Application
            $ad = [string](Get-ItemProperty -LiteralPath $pk -Name AppDirectory -ErrorAction SilentlyContinue).AppDirectory
            if ($ad -and (Split-Path -Leaf $ad) -ieq 'scripts') { $dir = Split-Path -Parent $ad }
            elseif ($app -and $app -match '\.exe$' -and $app -notmatch '(?i)powershell|python') { $dir = Split-Path -Parent $app }
            elseif ($ad) { $dir = $ad }
        } catch { }
        $out.Add([pscustomobject]@{ Name = $n; State = [string]$svc.State; Dir = $dir })
    }
    return $out.ToArray()
}

function Invoke-BobInfoGit {
    param([string]$Dir, [string[]]$GitArgs)
    try {
        if (-not (Test-Path -LiteralPath (Join-Path $Dir '.git'))) { return '' }
        $git = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
        if (-not $git) { foreach ($c in 'C:\Program Files\Git\cmd\git.exe', 'C:\Program Files\Git\bin\git.exe') { if (Test-Path -LiteralPath $c) { $git = $c; break } } }
        if (-not $git) { return '' }
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $git
        $psi.Arguments = ('-c safe.directory=* -C "{0}" {1}' -f $Dir, ($GitArgs -join ' '))
        $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
        $p = [Diagnostics.Process]::Start($psi)
        if (-not $p.WaitForExit(5000)) { try { $p.Kill() } catch { }; return '' }
        if ($p.ExitCode -ne 0) { return '' }
        return $p.StandardOutput.ReadToEnd().Trim()
    } catch { return '' }
}

function Test-BobInfoProductDir {
    param([string]$Product, [string]$Dir)
    if (-not $Dir -or -not (Test-Path -LiteralPath $Dir -PathType Container)) { return $false }
    if ($Product -eq 'ergo') {
        foreach ($x in 'ergo.exe', 'ircd.exe', 'bin\ergo.exe') { if (Test-Path -LiteralPath (Join-Path $Dir $x)) { return $true } }
        return $false
    }
    return ((Test-Path -LiteralPath (Join-Path $Dir 'VERSION')) -or (Test-Path -LiteralPath (Join-Path $Dir 'scripts') -PathType Container))
}

function Get-BobInfoOne {
    param([string]$Product, [string]$Dir, [scriptblock]$GitProbe)
    $ver = ''; $rel = ''; $relSrc = ''; $commit = ''
    $vf = Join-Path $Dir 'VERSION'
    if (Test-Path -LiteralPath $vf) {
        try { $ver = ([string](Get-Content -LiteralPath $vf -TotalCount 1 -ErrorAction Stop)).Trim() } catch { }
    }
    if (-not $ver -and $Product -eq 'ergo') {
        foreach ($x in 'ergo.exe', 'ircd.exe', 'bin\ergo.exe') {
            $ep = Join-Path $Dir $x
            if (Test-Path -LiteralPath $ep) { try { $ver = [string](Get-Item -LiteralPath $ep).VersionInfo.ProductVersion } catch { }; break }
        }
    }
    $bj = Join-Path $Dir 'BUILD.json'
    if (Test-Path -LiteralPath $bj) {
        try {
            $b = Get-Content -LiteralPath $bj -Raw -ErrorAction Stop | ConvertFrom-Json
            if ($b.built_utc) { $rel = ([datetime]::Parse([string]$b.built_utc).ToUniversalTime()).ToString('yyyy-MM-dd HH:mm') + ' UTC'; $relSrc = 'built' }
            if ($b.commit) { $commit = ([string]$b.commit).Trim() }
        } catch { }
    }
    if (-not $commit) { $commit = [string](& $GitProbe $Dir @('rev-parse', '--short', 'HEAD')) }
    if (-not $rel) {
        $cd = [string](& $GitProbe $Dir @('log', '-1', '--format=%cI'))
        if ($cd) { try { $rel = ([datetime]::Parse($cd).ToUniversalTime()).ToString('yyyy-MM-dd HH:mm') + ' UTC'; $relSrc = 'commit' } catch { } }
    }
    if (-not $rel) {
        $anchor = $vf; if (-not (Test-Path -LiteralPath $anchor)) { $anchor = $Dir }
        try { $rel = (Get-Item -LiteralPath $anchor).LastWriteTimeUtc.ToString('yyyy-MM-dd HH:mm') + ' UTC'; $relSrc = 'installed' } catch { }
    }
    return [pscustomobject]@{ Version = $(if ($ver) { $ver } else { '-' }); Released = $(if ($rel) { $rel } else { '-' }); ReleasedSource = $relSrc; Commit = $(if ($commit) { $commit } else { '-' }) }
}

function Get-BobInstallInfo {
    <#
      One row per install folder found, per product, in bob, jeeves, airc, ergo order. A product with no folder and no service
      gives no row. A service whose folder cannot be resolved gives one row with Path '(unknown)'.
    #>
    param(
        [string[]]$AiRoots = $null,
        [string]$RepoRoot = '',
        [scriptblock]$ServiceProbe = $null,
        [scriptblock]$GitProbe = $null
    )
    if ($null -eq $AiRoots) { $AiRoots = @(Get-BobInfoAiRoots -RepoRoot $RepoRoot) }
    if (-not $GitProbe) { $GitProbe = { param($d, $a) Invoke-BobInfoGit -Dir $d -GitArgs $a } }
    $svcs = @()
    try {
        if ($ServiceProbe) { $svcs = @(& $ServiceProbe @($script:BobInfoProducts | ForEach-Object { $_.Service })) }
        else { $svcs = @(Get-BobInfoServices -Names @($script:BobInfoProducts | ForEach-Object { $_.Service })) }
    } catch { $svcs = @() }
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($pd in $script:BobInfoProducts) {
        $svc = @($svcs | Where-Object { $_ -and $_.Name -ieq $pd.Service } | Select-Object -First 1)
        $dirs = New-Object System.Collections.Generic.List[string]
        foreach ($r in $AiRoots) {
            if (-not $r) { continue }
            $d = Join-Path $r $pd.Dir
            if (Test-BobInfoProductDir -Product $pd.Product -Dir $d) { $dirs.Add([IO.Path]::GetFullPath($d)) }
        }
        $svcDir = ''
        if ($svc.Count -gt 0 -and $svc[0].Dir) {
            try { $svcDir = [IO.Path]::GetFullPath([string]$svc[0].Dir) } catch { $svcDir = [string]$svc[0].Dir }
            if (Test-BobInfoProductDir -Product $pd.Product -Dir $svcDir) { $dirs.Add($svcDir) } else { $svcDir = '' }
        }
        $seen = @{}
        $uniq = New-Object System.Collections.Generic.List[string]
        foreach ($d in $dirs) { $k = $d.TrimEnd('\').ToLowerInvariant(); if (-not $seen.ContainsKey($k)) { $seen[$k] = $true; $uniq.Add($d) } }
        foreach ($d in $uniq) {
            $info = Get-BobInfoOne -Product $pd.Product -Dir $d -GitProbe $GitProbe
            $isSvc = ($svc.Count -gt 0) -and $svcDir -and ($svcDir.TrimEnd('\') -ieq $d.TrimEnd('\'))
            $rows.Add([pscustomobject]@{
                    Product = $pd.Product; Path = $d; Version = $info.Version; Released = $info.Released; ReleasedSource = $info.ReleasedSource
                    Commit = $info.Commit; Service = $(if ($svc.Count -gt 0) { $pd.Service } else { '' })
                    ServiceState = $(if ($svc.Count -gt 0) { [string]$svc[0].State } else { '' }); RunsService = [bool]$isSvc
                })
        }
        if ($uniq.Count -eq 0 -and $svc.Count -gt 0) {
            $rows.Add([pscustomobject]@{
                    Product = $pd.Product; Path = '(unknown)'; Version = '-'; Released = '-'; ReleasedSource = ''; Commit = '-'
                    Service = $pd.Service; ServiceState = [string]$svc[0].State; RunsService = $true
                })
        }
    }
    return $rows.ToArray()
}

function Format-BobInstallInfo {
    param([object[]]$Rows)
    $Rows = @($Rows)
    if ($Rows.Count -eq 0) { return 'No Bobiverse products found on this machine.' }
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($r in $Rows) {
        $lines.Add(('{0}  {1}' -f $r.Product, $r.Version))
        $src = if ($r.ReleasedSource) { ' (' + $r.ReleasedSource + ')' } else { '' }
        $lines.Add(('    released: {0}{1}' -f $r.Released, $src))
        $lines.Add(('    commit:   {0}' -f $r.Commit))
        $lines.Add(('    path:     {0}' -f $r.Path))
        if ($r.Service) { $lines.Add(('    service:  {0} ({1})' -f $r.Service, $(if ($r.ServiceState) { $r.ServiceState } else { 'unknown' }))) }
    }
    return ($lines -join "`r`n")
}