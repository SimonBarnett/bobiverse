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

function Invoke-BobiverseNssmChecked {
    <# nssm call that THROWS on a non-zero exit (installer bug: install/set results were ignored). #>
    param([Parameter(Mandatory)][string]$Exe, [Parameter(Mandatory)][string[]]$NssmArgs)
    $r = Invoke-BobiverseNssm -Exe $Exe -NssmArgs $NssmArgs
    if ($r.ExitCode -ne 0) {
        # Never echo parameter VALUES: ObjectName carries the service password and
        # AppEnvironmentExtra carries BOB_IRC_PASSWORD. Show verb/service/parameter only.
        $shown = ($NssmArgs | Select-Object -First 3) -join ' '
        throw "nssm $shown failed ($($r.ExitCode)): $($r.Output -join ' ')"
    }
    return $r
}

function Test-BobiverseServiceDeletePending {
    param([Parameter(Mandatory)][string]$Name)
    $k = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    if (-not (Test-Path -LiteralPath $k)) { return $false }
    $df = (Get-ItemProperty -LiteralPath $k -Name DeleteFlag -ErrorAction SilentlyContinue).DeleteFlag
    return ($df -eq 1)
}

function Wait-BobiverseServiceGone {
    <# True once the SCM entry AND its registry key are gone (a DeleteFlag=1 key means delete is still pending). #>
    param([Parameter(Mandatory)][string]$Name, [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $still = Get-Service -Name $Name -ErrorAction SilentlyContinue
        $key = Test-Path -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
        if (-not $still -and -not $key) { return $true }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Remove-BobiverseService {
    param(
        [Parameter(Mandatory)][string]$Nssm,
        [Parameter(Mandatory)][string]$Name,
        [int]$TimeoutSeconds = 30
    )
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        if (Test-BobiverseServiceDeletePending -Name $Name) {
            throw "service $Name is marked for deletion (DeleteFlag=1) and cannot be recreated yet. Close Services.msc / mmc / Task Manager windows (or reboot) and retry."
        }
        Write-Host "INFO service $Name absent"
        return
    }
    Write-Host "INFO removing service $Name"
    [void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('stop', $Name))
    Start-Sleep -Seconds 2
    [void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('remove', $Name, 'confirm'))
    if (-not (Wait-BobiverseServiceGone -Name $Name -TimeoutSeconds $TimeoutSeconds)) {
        # nssm remove can leave the SCM entry; try sc delete once, then wait again.
        Write-Host "WARN service $Name still present after nssm remove; trying sc delete"
        $null = & sc.exe delete $Name 2>&1
        if (-not (Wait-BobiverseServiceGone -Name $Name -TimeoutSeconds $TimeoutSeconds)) {
            throw "service $Name is still present / marked for deletion after $TimeoutSeconds s x2. A process holds an open handle (Services.msc / mmc / Task Manager / sc). Close them (or reboot) and re-run."
        }
    }
    Write-Host "INFO removed service $Name"
}

function Remove-BobiverseLegacyService {
    <#
      Stop + delete a leftover Windows service by name (NSSM or sc).
      Used to remove agentic_irc AircConsole and gh-Jeeves BobJeeves on bobiverse install.
      Leaves on-disk trees (C:\ai\ergo, C:\ai\airc-console) for manual rollback.
    #>
    param(
        [Parameter(Mandatory)][string]$Name,
        [string]$Nssm = ''
    )
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "INFO legacy service $Name absent"
        return
    }
    Write-Host "INFO removing legacy service $Name"
    if (-not $Nssm) { $Nssm = Resolve-BobiverseNssm }
    if ($Nssm -and (Test-Path -LiteralPath $Nssm)) {
        Remove-BobiverseService -Nssm $Nssm -Name $Name
    }
    # sc delete if nssm remove left the SCM entry (non-nssm or wrong nssm binary)
    $still = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($still) {
        try { Stop-Service -Name $Name -Force -ErrorAction SilentlyContinue } catch { }
        $r = cmd.exe /c "sc stop $Name & sc delete $Name"
        Write-Host ("INFO sc delete $Name -> {0}" -f (($r | Out-String).Trim()))
    }
}

function Disable-BobiverseLegacyBobJeeves {
    # Back-compat alias: remove, do not merely disable (operator asked for SCM cleanup).
    Remove-BobiverseLegacyService -Name 'BobJeeves'
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
        [string]$Description = '',
        [string]$IconLocation = ''
    )
    $dir = Split-Path -Parent $LinkPath
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $w = New-Object -ComObject WScript.Shell
    $sc = $w.CreateShortcut($LinkPath)
    $sc.TargetPath = $TargetPath
    if ($Arguments) { $sc.Arguments = $Arguments }
    if ($WorkingDirectory) { $sc.WorkingDirectory = $WorkingDirectory }
    if ($Description) { $sc.Description = $Description }
    if ($IconLocation) { $sc.IconLocation = $IconLocation }
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
      (MSI heat already laid files under InstallRoot - issue #2).
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
    if ($env:BOB_IRC_PASSWORD) { return $true }
    $path = Get-BobiverseErgoPasswordPath -InstallRoot $InstallRoot -HomeDir $HomeDir
    if (-not $path) { return $false }
    $secret = (Get-Content -LiteralPath $path -Raw).Trim()
    if (-not $secret) { return $false }
    $env:BOB_IRC_PASSWORD = $secret
    Write-Host "INFO loaded BOB_IRC_PASSWORD from $path"
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
    # Never prompt under msiexec / quiet (issue #6) - Get-Credential has no UI and hangs the CA.
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
            Write-Host 'WARN ObjectName left as service default (LocalSystem) - run Complete-BobiverseServiceLogon.ps1 or set BOBIVERSE_SERVICE_PASSWORD'
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

function Get-BobiverseHardlinkCount {
    <# Number of NTFS names for a file (1 = plain file). 0 when it cannot be determined. #>
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return 0 }
    try {
        $names = @(& fsutil.exe hardlink list $Path 2>$null | Where-Object { $_ -and $_.Trim() })
        if ($LASTEXITCODE -ne 0) { return 0 }
        return $names.Count
    } catch { return 0 }
}

function Repair-BobiverseErgoHardlink {
    <#
    .SYNOPSIS
      #70: give a hard-linked ergo.exe its own physical file WITHOUT stopping Ergo.
    .DESCRIPTION
      A running image can be renamed but not overwritten/deleted, so: copy to a temp name, rename the linked
      name aside (the running process keeps the old file), then move the copy into place. The next BobIrcd start
      picks up the independent copy; the pack's ergo\ergo.exe is no longer the same file. Never stops a service.
    #>
    param([Parameter(Mandatory = $true)][string]$ErgoExe)
    $n = Get-BobiverseHardlinkCount -Path $ErgoExe
    if ($n -lt 2) { return $false }
    $stamp = (Get-Date).ToString('yyyyMMddHHmmss')
    $tmp = "$ErgoExe.copy-$stamp"
    $aside = "$ErgoExe.linked-$stamp"
    Copy-Item -LiteralPath $ErgoExe -Destination $tmp -Force
    Move-Item -LiteralPath $ErgoExe -Destination $aside -Force
    Move-Item -LiteralPath $tmp -Destination $ErgoExe -Force
    try { Remove-Item -LiteralPath $aside -Force -ErrorAction Stop } catch { Write-Host "INFO ergo.exe was hard-linked ($n names); independent copy made, old name left at $aside (in use; delete after the next Ergo restart)" }
    Write-Host "INFO ergo.exe was hard-linked ($n names) to the MSI payload: now its own file (#70); Ergo not restarted"
    return $true
}

# ---------------------------------------------------------------------------------------------------------------
# Start Menu: ONE all-users folder "Bobiverse" holds every Bobiverse shortcut (t761u). Older installers / the
# agentic_build tray left top-level "Bob Systray" / "Bobiverse Tray" links and per-user "Bobiverse" folders: those
# are removed on every install/upgrade. Every shortcut here carries the Bobiverse systray icon when it is available.
# ---------------------------------------------------------------------------------------------------------------
function Get-BobiverseProgramsRoot {
    $p = ''
    try { $p = [Environment]::GetFolderPath('CommonPrograms') } catch { }
    if (-not $p) { $p = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs' }
    return $p
}

function Get-BobiverseStartMenuDir {
    param([string]$ProgramsRoot = '')
    if (-not $ProgramsRoot) { $ProgramsRoot = Get-BobiverseProgramsRoot }
    return (Join-Path $ProgramsRoot 'Bobiverse')
}

function Resolve-BobiverseTrayIcon {
    param([string]$InstallRoot = '')
    $cands = @()
    if ($InstallRoot) { $cands += (Join-Path $InstallRoot 'assets\bob-systray.ico') }
    $cands += 'C:\ai\bob\assets\bob-systray.ico', 'C:\ai\jeeves\assets\bob-systray.ico', 'C:\ai\airc\assets\bob-systray.ico'
    foreach ($c in $cands) { if (Test-Path -LiteralPath $c) { return $c } }
    return ''
}

# Pure data: the shortcuts a product contributes to the single Start Menu folder.
function Get-BobiverseShortcutSpec {
    param(
        [Parameter(Mandatory)][ValidateSet('bob', 'jeeves', 'airc')][string]$Product,
        [Parameter(Mandatory)][string]$InstallRoot,
        [string]$MachineId = '',
        [switch]$NeedLogon,
        [switch]$IncludeTray,
        [string]$Icon = ''
    )
    $ico = if ($Icon) { "$Icon,0" } else { '' }
    $ps = 'powershell.exe'
    $scr = Join-Path $InstallRoot 'scripts'
    $list = New-Object System.Collections.Generic.List[object]
    function Add-Spec($name, $target, $cmdArgs, $wd, $desc) {
        $list.Add([pscustomobject]@{ Name = $name; Target = $target; Arguments = $cmdArgs; WorkingDirectory = $wd; Description = $desc; Icon = $ico })
    }
    Add-Spec 'Bob Services' 'services.msc' '' '' 'Windows Services (ircBob, ircJeeves, Airc, BobIrcd)'
    switch ($Product) {
        'bob' {
            if ($IncludeTray) {
                $tray = Join-Path $scr 'Start-BobTray.ps1'
                Add-Spec 'Bobiverse Tray' $ps "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tray`" -InstallRoot `"$InstallRoot`" -MachineId $MachineId -ForceNew" $InstallRoot 'bob TipForm systray (companion to ircBob)'
            }
            Add-Spec 'Restart ircBob' $ps "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $scr 'Restart-BobEar.ps1')`"" $scr 'Restart ircBob (announces departure)'
        }
        'jeeves' {
            Add-Spec 'Restart ircJeeves' $ps "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $scr 'Restart-BobService.ps1')`" -Service ircJeeves" $scr 'Restart ircJeeves only (never BobIrcd/Ergo)'
            Add-Spec 'Jeeves command reference' (Join-Path $InstallRoot 'docs\jeeves-commands.md') '' $InstallRoot 'Jeeves chair command reference and authorization matrix'
        }
        'airc' {
            Add-Spec 'Restart Airc' $ps "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $scr 'Restart-BobService.ps1')`" -Service Airc" $scr 'Restart the Airc console service'
        }
    }
    if ($NeedLogon) {
        Add-Spec "Complete bobiverse service logon ($Product)" $ps "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $scr 'Complete-BobiverseServiceLogon.ps1')`" -Product $Product -InstallRoot `"$InstallRoot`"" $scr "Set the $Product service ObjectName password (required once after MSI)"
    }
    Add-Spec "Logs ($Product)" (Join-Path $InstallRoot 'logs') '' $InstallRoot "$Product service logs"
    Add-Spec "Skill books ($Product)" (Join-Path $InstallRoot '.grok\skills') '' $InstallRoot "$Product agent skill books (cd here and run an agent)"
    Add-Spec "Agent guide ($Product)" (Join-Path $InstallRoot 'AGENTS.md') '' $InstallRoot "$Product AGENTS.md - start-here for agents"
    return $list.ToArray()
}

# Remove the scattered / duplicate Bobiverse Start Menu entries left by older installers. Returns removed paths.
function Remove-BobiverseStartMenuDuplicates {
    param([string[]]$ProgramsRoots = @(), [string]$KeepDir = '')
    if (-not $ProgramsRoots -or $ProgramsRoots.Count -eq 0) {
        $roots = New-Object System.Collections.Generic.List[string]
        $roots.Add((Get-BobiverseProgramsRoot))
        foreach ($u in @(Get-ChildItem 'C:\Users' -Directory -ErrorAction SilentlyContinue)) {
            $p = Join-Path $u.FullName 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs'
            if (Test-Path -LiteralPath $p) { $roots.Add($p) }
        }
        $ProgramsRoots = $roots.ToArray()
    }
    $legacyTop = '^(Bob Systray.*|Bob Tray.*|Bobiverse Tray.*|Bobiverse.*|Bob Fleet.*|Restart ircBob|Restart ircJeeves|Restart Airc|Bob Services|Complete bobiverse service logon.*)\.lnk$'
    $removed = New-Object System.Collections.Generic.List[string]
    foreach ($root in $ProgramsRoots) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        # 1) top-level links (never inside Startup: that is the tray autostart)
        foreach ($f in @(Get-ChildItem -LiteralPath $root -File -Filter '*.lnk' -ErrorAction SilentlyContinue)) {
            if ($f.Name -match $legacyTop) {
                Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
                $removed.Add($f.FullName)
            }
        }
        # 2) legacy folders: "Bob Systray", and a Bobiverse folder that is NOT the kept all-users one
        foreach ($d in @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue)) {
            $isKeep = $KeepDir -and ([IO.Path]::GetFullPath($d.FullName).TrimEnd('\') -ieq [IO.Path]::GetFullPath($KeepDir).TrimEnd('\'))
            if ($isKeep) { continue }
            if ($d.Name -match '^(Bob Systray.*|Bob Tray.*|Bobiverse)$') {
                foreach ($f in @(Get-ChildItem -LiteralPath $d.FullName -File -Filter '*.lnk' -ErrorAction SilentlyContinue)) {
                    Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
                    $removed.Add($f.FullName)
                }
                if (-not @(Get-ChildItem -LiteralPath $d.FullName -Force -ErrorAction SilentlyContinue)) {
                    Remove-Item -LiteralPath $d.FullName -Force -ErrorAction SilentlyContinue
                    $removed.Add($d.FullName)
                }
            }
        }
    }
    foreach ($r in $removed) { Write-Host "INFO start-menu removed duplicate: $r" }
    return $removed.ToArray()
}

# Create/refresh this product's shortcuts in the single all-users "Bobiverse" folder and dedupe the rest.
function Install-BobiverseStartMenu {
    param(
        [Parameter(Mandatory)][ValidateSet('bob', 'jeeves', 'airc')][string]$Product,
        [Parameter(Mandatory)][string]$InstallRoot,
        [string]$MachineId = '',
        [switch]$NeedLogon,
        [switch]$IncludeTray,
        [string]$StartMenuDir = '',
        [string[]]$ProgramsRoots = @()
    )
    if (-not $StartMenuDir) { $StartMenuDir = Get-BobiverseStartMenuDir }
    $icon = Resolve-BobiverseTrayIcon -InstallRoot $InstallRoot
    if (-not $icon) { Write-Host 'WARN bob-systray.ico not found - shortcuts use default icons' }
    [void](Remove-BobiverseStartMenuDuplicates -ProgramsRoots $ProgramsRoots -KeepDir $StartMenuDir)
    New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
    $specs = @(Get-BobiverseShortcutSpec -Product $Product -InstallRoot $InstallRoot -MachineId $MachineId `
            -NeedLogon:$NeedLogon -IncludeTray:$IncludeTray -Icon $icon)
    $want = @{}
    foreach ($s in $specs) {
        $want[($s.Name + '.lnk').ToLowerInvariant()] = $true
        New-BobiverseShortcut -LinkPath (Join-Path $StartMenuDir ($s.Name + '.lnk')) -TargetPath $s.Target `
            -Arguments $s.Arguments -WorkingDirectory $s.WorkingDirectory -Description $s.Description -IconLocation $s.Icon
    }
    # A completed ObjectName logon no longer needs its helper link.
    if (-not $NeedLogon) {
        $stale = Join-Path $StartMenuDir "Complete bobiverse service logon ($Product).lnk"
        if (Test-Path -LiteralPath $stale) { Remove-Item -LiteralPath $stale -Force -ErrorAction SilentlyContinue }
    }
    return $specs
}

# ---------------------------------------------------------------------------------------------------------------
# Agent-start layer (t759u): AGENTS.md / CLAUDE.md / GROK.md / .cursor/rules/bobiverse-<p>.mdc + the product skill book
# live in the install root, so an agent started there has full service information. The MSI lays them; script installs
# (repo -> install root) and the self-updater use these helpers. Files only - never touches secrets or services.
# ---------------------------------------------------------------------------------------------------------------
function Get-BobiverseSkillNames {
    param([Parameter(Mandatory)][string]$SkillsRoot, [Parameter(Mandatory)][string]$Product)
    if (-not (Test-Path -LiteralPath $SkillsRoot)) { return @() }
    return @(Get-ChildItem -LiteralPath $SkillsRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq "bobiverse-$Product" -or $_.Name -like "bobiverse-$Product-*" -or
                $_.Name -in @('bobiverse-fleet-ops', 'harvest', 'harvest-agent-skills') } |
            ForEach-Object { $_.Name })
}

function Sync-BobiverseAgentFolders {
    <#
    .SYNOPSIS
      Build/refresh the bob agent working folders <Destination>\worker and <Destination>\plan from the repo (bob-agents\<n> + shared skills).
    .DESCRIPTION
      Used by Pack-BobiverseRelease (Destination = the MSI stage), Install-Bob (repo installs) and Sync-BobiverseFromRepo (dev sync).
      Writes AGENTS.md + CLAUDE.md + GROK.md + .cursor\rules\bobiverse-<n>.mdc + .grok\skills\* (every skill carries the CAST IRON harvest rule) and
      NEVER deletes anything: plan\work\* (the plans' outputs) and a running worker\bob-worker.exe are left alone. The exe is built by Build-BobWorker.ps1.
    #>
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [Parameter(Mandatory)][string]$Destination
    )
    $skillsRoot = Join-Path $RepoRoot '.grok\skills'
    $enc = New-Object System.Text.UTF8Encoding($false)
    $defs = @(
        @{ Name = 'worker'; Shared = @('bobiverse-bob', 'bobiverse-bob-worker', 'bobiverse-bob-plan', 'bobiverse-bob-job-irc', 'bobiverse-bob-job-fr', 'bobiverse-bob-job-mrb', 'bobiverse-bob-job-uat', 'bobiverse-fleet-ops', 'harvest', 'harvest-agent-skills') },
        @{ Name = 'plan';   Shared = @('harvest', 'harvest-agent-skills') }
    )
    $made = 0
    foreach ($d in $defs) {
        $n = $d.Name
        $src = Join-Path $RepoRoot "bob-agents\$n"
        if (-not (Test-Path -LiteralPath (Join-Path $src 'AGENTS.md'))) { Write-Host "WARN agent folder source missing: bob-agents\$n"; continue }
        $dest = Join-Path $Destination $n
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item -Path (Join-Path $src '*') -Destination $dest -Recurse -Force
        foreach ($sk in $d.Shared) {
            $from = Join-Path $skillsRoot $sk
            if (-not (Test-Path -LiteralPath $from)) { throw "agent folder $n needs .grok\skills\$sk" }
            $to = Join-Path $dest ".grok\skills\$sk"
            New-Item -ItemType Directory -Force -Path $to | Out-Null
            Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force
        }
        # The agent runs with cwd = <install>\$n, so the rule's relative '.\scripts\' must point at the install's scripts.
        Get-ChildItem -LiteralPath (Join-Path $dest '.grok\skills') -Recurse -Filter 'SKILL.md' | ForEach-Object {
            $t = [IO.File]::ReadAllText($_.FullName)
            $t2 = $t.Replace('.\scripts\', 'C:\ai\bob\scripts\')
            if ($t2 -ne $t) { [IO.File]::WriteAllText($_.FullName, $t2, $enc) }
        }
        $agents = [IO.File]::ReadAllText((Join-Path $dest 'AGENTS.md'))
        [IO.File]::WriteAllText((Join-Path $dest 'CLAUDE.md'), $agents, $enc)
        [IO.File]::WriteAllText((Join-Path $dest 'GROK.md'), $agents, $enc)
        $ruleDir = Join-Path $dest '.cursor\rules'
        New-Item -ItemType Directory -Force -Path $ruleDir | Out-Null
        $mdc = "---`ndescription: Bobiverse $n agent folder briefing (CAST IRON harvest rule, always-new agent, skills first)`nalwaysApply: true`n---`n`n" + $agents
        [IO.File]::WriteAllText((Join-Path $ruleDir "bobiverse-$n.mdc"), $mdc, $enc)
        Write-Host ("INFO agent folder {0}\ refreshed ({1} skills)" -f $n, @(Get-ChildItem -LiteralPath (Join-Path $dest '.grok\skills') -Directory).Count)
        $made++
    }
    return $made
}

function Install-BobiverseAgentLayer {
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [Parameter(Mandatory)][string]$InstallRoot,
        [Parameter(Mandatory)][string]$Product
    )
    $same = $false
    try { $same = ([IO.Path]::GetFullPath($RepoRoot).TrimEnd('\') -ieq [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')) } catch { }
    if ($same) { Write-Host "INFO agent layer already in $InstallRoot (laid by the MSI)"; return }
    $n = 0
    foreach ($f in @('AGENTS.md', 'CLAUDE.md', 'GROK.md', ".cursor\rules\bobiverse-$Product.mdc")) {
        $src = Join-Path $RepoRoot $f
        if (-not (Test-Path -LiteralPath $src)) { continue }
        $dst = Join-Path $InstallRoot $f
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $n++
    }
    # script installs stage from the repo: AGENTS.<product>.md is the source of AGENTS.md / CLAUDE.md / GROK.md
    $agentsSrc = Join-Path $RepoRoot "AGENTS.$Product.md"
    if ((-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'AGENTS.md'))) -and (Test-Path -LiteralPath $agentsSrc)) {
        foreach ($d in @('AGENTS.md', 'CLAUDE.md', 'GROK.md')) { Copy-Item -LiteralPath $agentsSrc -Destination (Join-Path $InstallRoot $d) -Force; $n++ }
    }
    Write-Host "INFO agent layer files refreshed in ${InstallRoot}: $n"
}