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

function Get-BobiverseFullPath([string]$Path) {
    if (-not $Path) { return $null }
    try { return [IO.Path]::GetFullPath($Path) } catch { return $Path }
}

function Test-BobiverseSamePath([string]$A, [string]$B) {
    $fa = Get-BobiverseFullPath $A
    $fb = Get-BobiverseFullPath $B
    if (-not $fa -or -not $fb) { return $false }
    return ($fa.TrimEnd('\') -ieq $fb.TrimEnd('\'))
}

function Copy-BobiverseTree {
    <#
      Copy source tree to dest. No-op when source and dest are the same path
      (MSI heat already laid files under InstallRoot — issue #2).
    #>
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Destination,
        [switch]$ContentsOnly
    )
    if (-not (Test-Path -LiteralPath $Source)) {
        Write-Host "WARN copy-skip missing source $Source"
        return
    }
    $srcFull = Get-BobiverseFullPath $Source
    $dstFull = Get-BobiverseFullPath $Destination
    if (Test-BobiverseSamePath $srcFull $dstFull) {
        Write-Host "INFO copy-skip same-path $srcFull (MSI staged)"
        return
    }
    # Also skip when Source is Dest\* already (scripts → InstallRoot\scripts and $here is that scripts dir)
    if ($ContentsOnly) {
        $parentOfSrc = Split-Path -Parent $srcFull
        if (Test-BobiverseSamePath $parentOfSrc $dstFull) {
            Write-Host "INFO copy-skip source already under dest $dstFull"
            return
        }
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    if ($ContentsOnly) {
        Copy-Item -Path (Join-Path $Source '*') -Destination $Destination -Recurse -Force
    } else {
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
    }
}

function Test-BobiverseIsLocalSystem {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $sid = $id.User.Value
    return ($sid -eq 'S-1-5-18') -or ($id.Name -match 'SYSTEM$')
}

function Test-BobiverseMsiOrQuiet {
    <#
      True under msiexec custom actions / quiet installs (issue #6).
      MSI Impersonate=yes still reports UserInteractive=$true, so Get-Credential hangs forever under /qn.
    #>
    if ($env:BOBIVERSE_NONINTERACTIVE -eq '1') { return $true }
    if ($env:MsiLogFileLocation) { return $true }
    if ($env:WINDOWS_INSTALLER -eq '1') { return $true }
    try {
        $pidWalk = $PID
        for ($i = 0; $i -lt 8 -and $pidWalk; $i++) {
            $p = Get-CimInstance Win32_Process -Filter "ProcessId=$pidWalk" -ErrorAction Stop
            if ($p.Name -match '(?i)^msiexec') { return $true }
            $pidWalk = $p.ParentProcessId
            if (-not $pidWalk -or $pidWalk -eq 0) { break }
        }
    } catch { }
    return $false
}

function Resolve-BobiverseServiceUser {
    <# Prefer interactive / install user over LocalSystem (MSI deferred CA). #>
    if (-not (Test-BobiverseIsLocalSystem)) {
        return [Security.Principal.WindowsIdentity]::GetCurrent().Name
    }
    if ($env:BOBIVERSE_SERVICE_USER) { return $env:BOBIVERSE_SERVICE_USER.Trim() }
    try {
        $cs = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
        if ($cs.UserName) { return $cs.UserName }
    } catch { }
    try {
        $explorer = Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($explorer) {
            $owner = Invoke-CimMethod -InputObject $explorer -MethodName GetOwner -ErrorAction SilentlyContinue
            if ($owner -and $owner.User) {
                if ($owner.Domain) { return "$($owner.Domain)\$($owner.User)" }
                return $owner.User
            }
        }
    } catch { }
    return $null
}

function Get-BobiverseErgoPasswordPath {
    param([string]$InstallRoot = '', [string]$HomeDir = '')
    foreach ($c in @(
            $(if ($HomeDir) { Join-Path $HomeDir 'ergo.password' } else { $null }),
            $(if ($InstallRoot) { Join-Path $InstallRoot 'config\ergo.password' } else { $null }),
            (Join-Path $env:USERPROFILE '.grok\ergo\connect.password'),
            (Join-Path $env:USERPROFILE '.grok\ergo\ergo.password')
        )) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Import-BobiverseErgoPassword {
    param([string]$InstallRoot = '', [string]$HomeDir = '')
    if ($env:AGENTIC_IRC_PASSWORD) { return $true }
    $path = Get-BobiverseErgoPasswordPath -InstallRoot $InstallRoot -HomeDir $HomeDir
    if (-not $path) { return $false }
    $secret = (Get-Content -LiteralPath $path -Raw).Trim()
    if (-not $secret) { return $false }
    $env:AGENTIC_IRC_PASSWORD = $secret
    Write-Host "INFO loaded AGENTIC_IRC_PASSWORD from $path"
    return $true
}

function Get-BobiverseServicePasswordSecure {
    param(
        [string]$InstallRoot = '',
        [SecureString]$Password = $null,
        [switch]$PromptIfMissing,
        [string]$User = ''
    )
    if ($Password) { return $Password }
    if ($env:BOBIVERSE_SERVICE_PASSWORD) {
        return (ConvertTo-SecureString -String $env:BOBIVERSE_SERVICE_PASSWORD -AsPlainText -Force)
    }
    $fileCandidates = @(
        $env:BOBIVERSE_SERVICE_PASSWORD_FILE,
        $(if ($InstallRoot) { Join-Path $InstallRoot 'config\service.password' } else { $null })
    )
    foreach ($f in $fileCandidates) {
        if ($f -and (Test-Path -LiteralPath $f)) {
            $raw = (Get-Content -LiteralPath $f -Raw).Trim()
            if ($raw) {
                Write-Host "INFO loaded service password from file $f"
                return (ConvertTo-SecureString -String $raw -AsPlainText -Force)
            }
        }
    }
    $dpapi = if ($InstallRoot) { Join-Path $InstallRoot 'config\service.cred' } else { $null }
    if ($dpapi -and (Test-Path -LiteralPath $dpapi)) {
        try {
            $enc = Get-Content -LiteralPath $dpapi -Raw
            $ss = ConvertTo-SecureString -String $enc
            Write-Host "INFO loaded service password from DPAPI $dpapi"
            return $ss
        } catch {
            Write-Host "WARN DPAPI service.cred unreadable: $($_.Exception.Message)"
        }
    }
    # Never prompt under msiexec / quiet (issue #6) — Get-Credential has no UI and hangs the CA.
    if ($PromptIfMissing -and -not (Test-BobiverseMsiOrQuiet) -and [Environment]::UserInteractive -and -not (Test-BobiverseIsLocalSystem)) {
        $who = if ($User) { $User } else { [Security.Principal.WindowsIdentity]::GetCurrent().Name }
        $cred = Get-Credential -UserName $who -Message 'Password for bobiverse Windows service (ObjectName / DPAPI user)'
        if ($cred) { return $cred.Password }
    }
    return $null
}

function Save-BobiverseServicePassword {
    param([Parameter(Mandatory)][string]$InstallRoot, [Parameter(Mandatory)][SecureString]$Password)
    $cfg = Join-Path $InstallRoot 'config'
    New-Item -ItemType Directory -Force -Path $cfg | Out-Null
    $dpapi = Join-Path $cfg 'service.cred'
    $enc = ConvertFrom-SecureString -SecureString $Password
    [IO.File]::WriteAllText($dpapi, $enc)
    Write-Host "INFO saved DPAPI service.cred under config\"
}

function Request-BobiverseUacRelaunch {
    param([Parameter(Mandatory)]$Bound)
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
        # Never re-pass plaintext passwords on the UAC command line.
        if ($key -eq 'ServicePassword') { continue }
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

function Set-BobiverseServiceObjectName {
    <#
      Set NSSM ObjectName to the fleet user (DPAPI). Password from:
        1) -Password SecureString
        2) env BOBIVERSE_SERVICE_PASSWORD
        3) BOBIVERSE_SERVICE_PASSWORD_FILE or InstallRoot\config\service.password
        4) InstallRoot\config\service.cred (DPAPI)
        5) interactive Get-Credential when -PromptIfMissing
      Without a password, leaves LocalSystem and writes Complete-BobiverseServiceLogon shortcut path.
    #>
    param(
        [Parameter(Mandatory)][string]$Nssm,
        [Parameter(Mandatory)][string]$ServiceName,
        [string]$User = '',
        [SecureString]$Password = $null,
        [string]$InstallRoot = '',
        [switch]$PromptIfMissing,
        [switch]$AllowLocalSystem
    )
    if (-not $User) { $User = Resolve-BobiverseServiceUser }
    $Password = Get-BobiverseServicePasswordSecure -InstallRoot $InstallRoot -Password $Password -PromptIfMissing:$PromptIfMissing -User $User
    $plain = $null
    try {
        if ($Password -and $User) {
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
            try {
                $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
            } finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
            }
            $r = Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'ObjectName', $User, $plain)
            if ($r.ExitCode -ne 0) {
                throw "nssm set ObjectName failed ($($r.ExitCode)): $($r.Output -join ' ')"
            }
            Write-Host "INFO ObjectName=$User (password set)"
            if ($InstallRoot) {
                try { Save-BobiverseServicePassword -InstallRoot $InstallRoot -Password $Password } catch {
                    Write-Host "WARN could not save service.cred: $($_.Exception.Message)"
                }
            }
            return $true
        }
        if ($AllowLocalSystem -or -not $User) {
            Write-Host 'WARN ObjectName left as service default (LocalSystem) — run Complete-BobiverseServiceLogon.ps1 or set BOBIVERSE_SERVICE_PASSWORD'
            return $false
        }
        [void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'ObjectName', $User))
        Write-Host ('WARN ObjectName={0} without password - service may fail logon. Run Complete-BobiverseServiceLogon.ps1 or set BOBIVERSE_SERVICE_PASSWORD' -f $User)
        return $false
    } finally {
        $plain = $null
    }
}

function Install-BobiversePythonDeps {
    param([Parameter(Mandatory)][string]$Python)
    $pkgs = @('cryptography')
    foreach ($pkg in $pkgs) {
        $code = & $Python -c "import $pkg" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "INFO python-dep-present $pkg"
            continue
        }
        Write-Host "INFO python-dep-install $pkg"
        & $Python -m pip install --upgrade $pkg
        if ($LASTEXITCODE -ne 0) { throw "pip install $pkg failed ($LASTEXITCODE)" }
    }
}
