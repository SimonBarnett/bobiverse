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

function Protect-BobiverseSecretPath {
    <#
      FR #3288: lock a secret file or directory to SYSTEM + Administrators only.
      Removes inheritance and drops Users / Authenticated Users / Everyone / CREATOR OWNER /
      installing-user ACEs. Optional -ServiceAccount gets Read when it is not LocalSystem.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$ServiceAccount = '',
        [switch]$Recurse
    )
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return }
    $item = Get-Item -LiteralPath $Path -Force
    # Snapshot paths first. Apply files before directories so a locked parent cannot
    # block Get-Item on children (and so Medium-IL tokens finish the walk).
    $entries = New-Object System.Collections.Generic.List[object]
    [void]$entries.Add([pscustomobject]@{ FullName = $item.FullName; IsDir = [bool]$item.PSIsContainer })
    if ($Recurse -and $item.PSIsContainer) {
        Get-ChildItem -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
            [void]$entries.Add([pscustomobject]@{ FullName = $_.FullName; IsDir = [bool]$_.PSIsContainer })
        }
    }
    $ordered = @($entries | Sort-Object @{ Expression = { if ($_.IsDir) { 1 } else { 0 } } }, @{ Expression = { $_.FullName.Length }; Descending = $true })
    $sys = New-Object System.Security.Principal.SecurityIdentifier 'S-1-5-18'
    $adm = New-Object System.Security.Principal.SecurityIdentifier 'S-1-5-32-544'
    $full = [System.Security.AccessControl.FileSystemRights]::FullControl
    $read = [System.Security.AccessControl.FileSystemRights]::ReadAndExecute
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    $svcSid = $null
    if ($ServiceAccount -and ($ServiceAccount -notmatch '(?i)^(NT AUTHORITY\\)?SYSTEM$|^S-1-5-18$')) {
        try {
            $svcSid = (New-Object System.Security.Principal.NTAccount($ServiceAccount)).Translate(
                [type]'System.Security.Principal.SecurityIdentifier'
            )
        } catch {
            Write-Host ("WARN Protect-BobiverseSecretPath: cannot resolve ServiceAccount={0}: {1}" -f $ServiceAccount, $_.Exception.Message)
        }
    }
    foreach ($e in $ordered) {
        $t = [string]$e.FullName
        $isDir = [bool]$e.IsDir
        if ($isDir) {
            $acl = New-Object System.Security.AccessControl.DirectorySecurity
            $inherit = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor `
                [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
        } else {
            $acl = New-Object System.Security.AccessControl.FileSecurity
            $inherit = [System.Security.AccessControl.InheritanceFlags]::None
        }
        $prop = [System.Security.AccessControl.PropagationFlags]::None
        $acl.SetAccessRuleProtection($true, $false)
        $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($sys, $full, $inherit, $prop, $allow)))
        $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($adm, $full, $inherit, $prop, $allow)))
        if ($svcSid) {
            $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($svcSid, $read, $inherit, $prop, $allow)))
        }
        Set-Acl -LiteralPath $t -AclObject $acl
    }
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

function Get-BobiverseNssmApplication {
    <# FR #2475: read NSSM Application from the service registry (path only; no secrets). #>
    param([Parameter(Mandatory)][string]$ServiceName)
    try {
        $k = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
        if (Test-Path -LiteralPath $k) {
            return [string](Get-ItemProperty -LiteralPath $k -Name Application -ErrorAction Stop).Application
        }
    } catch { }
    return ''
}

function Get-BobiverseEarServiceHome {
    <#
      FR #2943 / VISION S3: home the live ircBob ear drains (LocalSystem Start-Bob -> InstallRoot\home).
      Interactive tray / Restart-BobEar must write depart-request + departure PRIVMSG here - not
      %USERPROFILE%\.bobiverse - or the announce never reaches IRC.
      Override: BOB_EAR_HOME. Else InstallRoot\home, else NSSM AppDirectory parent\home, else product root\home.
    #>
    param(
        [string]$ServiceName = 'ircBob',
        [string]$InstallRoot = ''
    )
    $ov = ([string]$env:BOB_EAR_HOME).Trim()
    if ($ov) {
        try { return [IO.Path]::GetFullPath($ov) } catch { return $ov }
    }
    $root = ([string]$InstallRoot).Trim()
    if ($root) {
        try { return [IO.Path]::GetFullPath((Join-Path $root 'home')) } catch { return (Join-Path $root 'home') }
    }
    try {
        $k = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
        if (Test-Path -LiteralPath $k) {
            $ad = [string](Get-ItemProperty -LiteralPath $k -Name AppDirectory -ErrorAction SilentlyContinue).AppDirectory
            if ($ad) {
                $svcRoot = $ad
                if ((Split-Path -Leaf $ad) -ieq 'scripts') { $svcRoot = Split-Path -Parent $ad }
                return [IO.Path]::GetFullPath((Join-Path $svcRoot 'home'))
            }
        }
    } catch { }
    try {
        if (Get-Command Get-BobiverseProductRoot -ErrorAction SilentlyContinue) {
            $pr = [string](Get-BobiverseProductRoot -Product bob)
            if ($pr) { return [IO.Path]::GetFullPath((Join-Path $pr 'home')) }
        }
    } catch { }
    return ''
}

function Set-BobiverseNssmApplicationSafe {
    <#
      FR #2475: never point NSSM Application at a missing exe.
      If NewApplication is a filesystem path that does not exist, keep the previous Application
      (or throw when -RequireExe and nothing valid remains). powershell.exe / cmd.exe are allowed.
    #>
    param(
        [Parameter(Mandatory)][string]$Nssm,
        [Parameter(Mandatory)][string]$ServiceName,
        [Parameter(Mandatory)][string]$NewApplication,
        [string]$AppDirectory = '',
        [switch]$RequireExe
    )
    $prev = Get-BobiverseNssmApplication -ServiceName $ServiceName
    $new = [string]$NewApplication
    $isShell = ($new -match '(?i)(^|[\\/])(powershell|pwsh|cmd)\.exe$') -or ($new -ieq 'powershell.exe') -or ($new -ieq 'pwsh.exe') -or ($new -ieq 'cmd.exe')
    if (-not $isShell) {
        if (-not (Test-Path -LiteralPath $new)) {
            Write-Host "WARN FR#2475 refuse NSSM Application=$new (missing); keeping previous=$prev"
            if ($RequireExe -and -not ($prev -and (Test-Path -LiteralPath $prev))) {
                throw "FR#2475: refused to set Application to missing path and no valid previous Application for $ServiceName"
            }
            return [pscustomobject]@{ Ok = $false; KeptPrevious = $true; Application = $prev; Refused = $new }
        }
    }
    [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Application', $new))
    if ($AppDirectory) {
        [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppDirectory', $AppDirectory))
    }
    if (-not $isShell -and -not (Test-Path -LiteralPath $new)) {
        Write-Host "WARN FR#2475 Application vanished after set ($new); restoring previous=$prev"
        if ($prev) {
            [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Application', $prev))
            return [pscustomobject]@{ Ok = $false; KeptPrevious = $true; Application = $prev; Refused = $new }
        }
        throw "FR#2475: Application missing after nssm set and no previous path to restore ($ServiceName)"
    }
    return [pscustomobject]@{ Ok = $true; KeptPrevious = $false; Application = $new; Refused = '' }
}

function Invoke-BobiverseMsiexecSerialized {
    <#
      FR #2475: serialise msiexec via Global\bobiverse-msiexec mutex; retry exit 1618
      (ERROR_INSTALL_ALREADY_RUNNING) a few times instead of leaving services half-upgraded.
    #>
    param(
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [string]$LogPath = '',
        [int]$TimeoutMs = 1200000,
        [int]$MaxAttempts = 6,
        [int]$RetryDelaySec = 15
    )
    $msiexec = Join-Path $env:SystemRoot 'System32\msiexec.exe'
    $mutex = New-Object System.Threading.Mutex($false, 'Global\bobiverse-msiexec')
    $held = $false
    try {
        try { $held = $mutex.WaitOne(1800000) } catch [System.Threading.AbandonedMutexException] { $held = $true }
        if (-not $held) { throw 'FR#2475: timed out waiting for Global\bobiverse-msiexec mutex' }
        $code = -1
        for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
            $others = @(Get-Process -Name msiexec -ErrorAction SilentlyContinue)
            if ($others.Count -gt 0 -and $attempt -lt $MaxAttempts) {
                Write-Host "WARN FR#2475 msiexec busy (procs=$($others.Count)); wait $RetryDelaySec s attempt=$attempt"
                Start-Sleep -Seconds $RetryDelaySec
                continue
            }
            $p = Start-Process -FilePath $msiexec -ArgumentList $ArgumentList -PassThru -WindowStyle Hidden
            if (-not $p.WaitForExit([Math]::Max(1000, [int]$TimeoutMs))) {
                try { $p.Kill() } catch { }
                throw ("FR#2475: msiexec timed out after {0} ms (attempt {1})" -f $TimeoutMs, $attempt)
            }
            $code = [int]$p.ExitCode
            if ($code -ne 1618) { break }
            Write-Host "WARN FR#2475 msiexec exit 1618 (already running); retry in $RetryDelaySec s attempt=$attempt"
            Start-Sleep -Seconds $RetryDelaySec
        }
        return [pscustomobject]@{ ExitCode = $code; LogPath = $LogPath }
    } finally {
        if ($held) { try { $mutex.ReleaseMutex() } catch { } }
        try { $mutex.Dispose() } catch { }
    }
}


function Get-BobiverseServiceAppParameters {
    <# FR #1552: read NSSM AppParameters from the service registry (no secret values logged). #>
    param([Parameter(Mandatory)][string]$ServiceName)
    try {
        $k = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
        if (Test-Path -LiteralPath $k) {
            return [string](Get-ItemProperty -LiteralPath $k -Name AppParameters -ErrorAction Stop).AppParameters
        }
    } catch { }
    return ''
}

function Get-BobiverseAppParam {
    <# Parse -Name "value" or -Name value from an NSSM AppParameters string. #>
    param([string]$AppParameters, [Parameter(Mandatory)][string]$Name)
    if (-not $AppParameters) { return '' }
    if ($AppParameters -match ("-{0}\s+`"([^`"]+)`"" -f [regex]::Escape($Name))) { return $Matches[1] }
    if ($AppParameters -match ("-{0}\s+([A-Za-z0-9_.:\\/-]+)" -f [regex]::Escape($Name))) { return $Matches[1] }
    return ''
}

function Get-BobiverseAircIdentityFromAppParameters {
    <# FR #1552: extract ConsoleHome / MachineId / PasswordFile / OperatorsFile / Launcher from AppParameters.
       FR #2397: also accept airc.exe argparse forms (--home / --machine / --password-file / --operators-file). #>
    param([string]$AppParameters)
    $launcher = ''
    if ($AppParameters -match '-File\s+"([^"]+\.ps1)"') { $launcher = $Matches[1] }
    elseif ($AppParameters -match '-File\s+([A-Za-z0-9_.:\\/-]+\.ps1)') { $launcher = $Matches[1] }
    $consoleHome = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'ConsoleHome'
    if (-not $consoleHome) { $consoleHome = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'home' }
    $machineId = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'MachineId'
    if (-not $machineId) { $machineId = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'machine' }
    $passwordFile = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'PasswordFile'
    if (-not $passwordFile) { $passwordFile = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'password-file' }
    $operatorsFile = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'OperatorsFile'
    if (-not $operatorsFile) { $operatorsFile = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'operators-file' }
    # FR #3287: capability / account flags (argparse --shell-mode / --jobs / --update / --require-account / --accounts).
    $shellMode = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'shell-mode'
    if (-not $shellMode) { $shellMode = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'ShellMode' }
    $jobs = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'jobs'
    $updateCap = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'update'
    $requireAccount = $false
    if ($AppParameters -match '(^|\s)--require-account(\s|$)') { $requireAccount = $true }
    elseif ((Get-BobiverseAppParam -AppParameters $AppParameters -Name 'RequireAccount') -eq '1') { $requireAccount = $true }
    $accounts = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'accounts'
    if (-not $accounts) { $accounts = Get-BobiverseAppParam -AppParameters $AppParameters -Name 'Accounts' }
    return [pscustomobject]@{
        ConsoleHome     = $consoleHome
        MachineId       = $machineId
        PasswordFile    = $passwordFile
        OperatorsFile   = $operatorsFile
        Launcher        = $launcher
        ShellMode       = $shellMode
        Jobs            = $jobs
        UpdateCap       = $updateCap
        RequireAccount  = $requireAccount
        Accounts        = $accounts
        Raw             = [string]$AppParameters
    }
}

function Protect-BobiverseInstallTree {
    <#
      FR #3289: lock an airc (or other product) install tree so standard users cannot
      create/modify scripts that LocalSystem will run. Removes inheritance; grants
      SYSTEM + Administrators FullControl and BUILTIN\Users ReadAndExecute only.
      Does not grant Authenticated Users modify.
      FR #3394: -FailClosed rethrows so Install-Airc cannot leave a user-writable tree
      that LocalSystem is about to run. Default remains best-effort (WARN only).
      FR #3516: takeown /A (Administrators) so a pre-created user-owned
      ProgramData\Bobiverse (or install tree) cannot keep WRITE_DAC after re-ACL.
      FR #3581: SetOwner Administrators after DACL Set-Acl (never on the same ACL
      object - unelevated SetOwner breaks Set-Acl); takeown /R /D Y only when
      -Recurse (LogsOnly must not walk update\ via takeown /R). Directory ACEs keep
      ContainerInherit|ObjectInherit: inherit=None on a parent empties child DACLs.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [switch]$Recurse,
        [switch]$FailClosed
    )
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        if ($FailClosed -and $Path) {
            throw ("Protect-BobiverseInstallTree FailClosed: path missing '{0}'" -f $Path)
        }
        return
    }
    try {
        $item = Get-Item -LiteralPath $Path -Force
        $entries = New-Object System.Collections.Generic.List[object]
        [void]$entries.Add([pscustomobject]@{ FullName = $item.FullName; IsDir = [bool]$item.PSIsContainer })
        if ($Recurse -and $item.PSIsContainer) {
            Get-ChildItem -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
                [void]$entries.Add([pscustomobject]@{ FullName = $_.FullName; IsDir = [bool]$_.PSIsContainer })
            }
        }
        # Files before dirs so a locked parent cannot block children (same order as FR #3288).
        $ordered = @($entries | Sort-Object @{ Expression = { if ($_.IsDir) { 1 } else { 0 } } }, @{ Expression = { $_.FullName.Length }; Descending = $true })
        $sys = New-Object System.Security.Principal.SecurityIdentifier 'S-1-5-18'
        $adm = New-Object System.Security.Principal.SecurityIdentifier 'S-1-5-32-544'
        $usr = New-Object System.Security.Principal.SecurityIdentifier 'S-1-5-32-545'
        $full = [System.Security.AccessControl.FileSystemRights]::FullControl
        $rx = [System.Security.AccessControl.FileSystemRights]::ReadAndExecute
        $allow = [System.Security.AccessControl.AccessControlType]::Allow
        foreach ($e in $ordered) {
            $t = [string]$e.FullName
            $isDir = [bool]$e.IsDir
            if ($isDir) {
                $acl = New-Object System.Security.AccessControl.DirectorySecurity
                # Always CI|OI on dirs. inherit=None + SetAccessRuleProtection empties
                # child DACLs (update\ becomes Access denied) - FR #3581.
                $inherit = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor `
                    [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
            } else {
                $acl = New-Object System.Security.AccessControl.FileSecurity
                $inherit = [System.Security.AccessControl.InheritanceFlags]::None
            }
            $prop = [System.Security.AccessControl.PropagationFlags]::None
            $acl.SetAccessRuleProtection($true, $false)
            $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($sys, $full, $inherit, $prop, $allow)))
            $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($adm, $full, $inherit, $prop, $allow)))
            $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($usr, $rx, $inherit, $prop, $allow)))
            # DACL first - do not SetOwner on this object (unelevated Set-Acl fails).
            Set-Acl -LiteralPath $t -AclObject $acl
            # FR #3581: in-process owner reset after DACL (elevated MSI); best-effort.
            try {
                $aclOwner = Get-Acl -LiteralPath $t
                $aclOwner.SetOwner($adm)
                Set-Acl -LiteralPath $t -AclObject $aclOwner
            } catch { }
        }
        # FR #3516 / #3581: best-effort takeown /A fallback. /R /D Y only when -Recurse
        # (directory alone must not recurse - LogsOnly protects root+logs without
        # walking update\). Install/uninstall run elevated; unit tests may lack
        # elevation - owner reset never FailClosed-throws (DACL lock is the gate).
        try {
            $takeown = Join-Path $env:SystemRoot 'System32\takeown.exe'
            if (Test-Path -LiteralPath $takeown) {
                # cmd swallows stderr so unelevated unit tests do not NativeCommandError.
                if ($Recurse -and $item.PSIsContainer) {
                    $tc = 'takeown /F "' + $item.FullName + '" /A /R /D Y >nul 2>&1'
                } else {
                    $tc = 'takeown /F "' + $item.FullName + '" /A >nul 2>&1'
                }
                cmd.exe /c $tc | Out-Null
                if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
                    Write-Host ("WARN FR #3516 takeown exit={0} path={1}" -f $LASTEXITCODE, $item.FullName)
                }
            }
        } catch {
            Write-Host ("WARN FR #3516 Protect owner reset: {0}" -f $_.Exception.Message)
        }
        Write-Host ("INFO Protect-BobiverseInstallTree locked {0}" -f $Path)
    } catch {
        Write-Host ("WARN Protect-BobiverseInstallTree: {0}" -f $_.Exception.Message)
        if ($FailClosed) { throw }
    }
}

function Test-BobiverseAircPurgePrefixIsSafe {
    <#
      FR #3516: refuse drive roots and single-segment paths (C:\, C:\Windows) so a
      planted manifest install_root=C:\ cannot make every path "under" the allow-list.
      Require at least two path segments under the drive (e.g. C:\ai\airc).
    #>
    param([Parameter(Mandatory)][string]$Prefix)
    $raw = ([string]$Prefix).Trim()
    if (-not $raw) { return $false }
    try {
        $full = [IO.Path]::GetFullPath($raw).TrimEnd('\')
    } catch {
        return $false
    }
    if ($full -match '^[A-Za-z]:$') { return $false }
    $driveRoot = [IO.Path]::GetPathRoot($full)
    if (-not $driveRoot) { return $false }
    $driveTrim = $driveRoot.TrimEnd('\')
    if ($full.Equals($driveTrim, [StringComparison]::OrdinalIgnoreCase)) { return $false }
    $rel = $full.Substring([Math]::Min($full.Length, $driveRoot.Length)).TrimStart('\')
    $parts = @($rel -split '[\\/]' | Where-Object { $_ })
    if ($parts.Count -lt 2) { return $false }
    return $true
}

function Test-BobiverseAircPurgePathAllowed {
    <#
      FR #3394: uninstall purge may only delete paths under known prefixes so a
      user-owned airc-install-manifest.json cannot point SYSTEM at arbitrary deletes.
      FR #3516: InstallRoot / ConsoleHome / ProgramDataRoot must pass
      Test-BobiverseAircPurgePrefixIsSafe (no drive-root allow-list base).
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$InstallRoot = '',
        [string]$ConsoleHome = '',
        [string]$ProgramDataRoot = ''
    )
    $raw = ([string]$Path).Trim()
    if (-not $raw) { return $false }
    if ($raw -match '(?i)^removed:') { return $false }
    try {
        $full = [IO.Path]::GetFullPath($raw)
    } catch {
        return $false
    }
    if (-not $ProgramDataRoot) {
        $pd = if ($env:ProgramData) { $env:ProgramData } else { 'C:\ProgramData' }
        $ProgramDataRoot = Join-Path $pd 'Bobiverse'
    }
    $prefixes = New-Object System.Collections.Generic.List[string]
    foreach ($p in @($InstallRoot, $ConsoleHome, $ProgramDataRoot)) {
        if (-not $p) { continue }
        if (-not (Test-BobiverseAircPurgePrefixIsSafe -Prefix ([string]$p))) { continue }
        try {
            [void]$prefixes.Add(([IO.Path]::GetFullPath([string]$p)).TrimEnd('\') + '\')
            [void]$prefixes.Add(([IO.Path]::GetFullPath([string]$p)).TrimEnd('\'))
        } catch { }
    }
    $sysBob = Join-Path $env:SystemRoot 'System32\config\systemprofile\AppData\Local\Bobiverse'
    try {
        [void]$prefixes.Add(([IO.Path]::GetFullPath($sysBob)).TrimEnd('\') + '\')
        [void]$prefixes.Add(([IO.Path]::GetFullPath($sysBob)).TrimEnd('\'))
    } catch { }
    foreach ($leaf in @('.airc', '.airc-console')) {
        $def = Join-Path $env:SystemDrive ('Users\Default\' + $leaf)
        $defLocal = Join-Path $env:SystemDrive ('Users\Default\AppData\Local\' + $leaf)
        foreach ($d in @($def, $defLocal)) {
            try {
                [void]$prefixes.Add(([IO.Path]::GetFullPath($d)).TrimEnd('\') + '\')
                [void]$prefixes.Add(([IO.Path]::GetFullPath($d)).TrimEnd('\'))
            } catch { }
        }
    }
    foreach ($pre in $prefixes) {
        if (-not $pre) { continue }
        if ($full.Equals($pre.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) { return $true }
        if ($full.StartsWith($pre, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

# FR #3554: once-per-process Protect cache keyed by root|mode (avoid re-ACLing a huge
# ProgramData\Bobiverse tree on every MSI log line).
if (-not (Get-Variable -Name BobiverseProgramDataProtectCache -Scope Script -ErrorAction SilentlyContinue)) {
    $script:BobiverseProgramDataProtectCache = @{}
}

function Ensure-BobiverseProgramDataRoot {
    <#
      FR #3394: create/lock %ProgramData%\Bobiverse (+ logs) so Users cannot own the
      purge manifest or MSI install log. SYSTEM + Administrators Full; Users RX.
      Pre-existing user-owned trees are re-locked (WARN) when possible; -FailClosed throws.
      FR #3516: Protect takeown /A Administrators so CREATOR OWNER cannot keep WRITE_DAC.
      FR #3554: -ProtectMode Full|LogsOnly|None; process cache skips repeat Protect;
      env BOBIVERSE_PROGRAMDATA_ROOT (or -Root) redirects for tests so pytest never
      touches the live C:\ProgramData\Bobiverse tree.
    #>
    param(
        [string]$Root = '',
        [switch]$FailClosed,
        [ValidateSet('Full', 'LogsOnly', 'None')][string]$ProtectMode = 'Full'
    )
    try {
        if (-not $Root) {
            if ($env:BOBIVERSE_PROGRAMDATA_ROOT -and ([string]$env:BOBIVERSE_PROGRAMDATA_ROOT).Trim()) {
                $Root = ([string]$env:BOBIVERSE_PROGRAMDATA_ROOT).Trim()
            } else {
                $pd = if ($env:ProgramData) { $env:ProgramData } else { 'C:\ProgramData' }
                $Root = Join-Path $pd 'Bobiverse'
            }
        }
        $rootFull = [IO.Path]::GetFullPath($Root)
        $existed = Test-Path -LiteralPath $rootFull
        New-Item -ItemType Directory -Force -Path $rootFull | Out-Null
        $logs = Join-Path $rootFull 'logs'
        New-Item -ItemType Directory -Force -Path $logs | Out-Null

        if ($ProtectMode -eq 'None') {
            return $rootFull
        }

        $cacheKey = ($rootFull.ToLowerInvariant() + '|' + $ProtectMode)
        if ($script:BobiverseProgramDataProtectCache.ContainsKey($cacheKey)) {
            Write-Host ("INFO FR #3554 ProgramData protect skipped (cached) mode={0} root={1}" -f $ProtectMode, $rootFull)
            return $rootFull
        }

        if ($existed) {
            Write-Host ("WARN FR #3394 Ensure-BobiverseProgramDataRoot re-locking pre-existing {0}" -f $rootFull)
        }
        if ($ProtectMode -eq 'LogsOnly') {
            # FR #3554 / #3581: lock root + logs without -Recurse on root so takeown
            # does not /R the GB-scale update\ tree. Root Set-Acl keeps CI|OI (fast
            # inherited ACE refresh); takeown /A only on the path itself. Recurse
            # logs\ (small) so install-*.log files get Admin Full + Users RX.
            Protect-BobiverseInstallTree -Path $rootFull -FailClosed:$FailClosed
            Protect-BobiverseInstallTree -Path $logs -Recurse -FailClosed:$FailClosed
            Write-Host ("INFO FR #3554 ProgramData Bobiverse locked LogsOnly {0}" -f $rootFull)
        } else {
            # One -Recurse pass covers logs\; install-time FailClosed keeps Full.
            Protect-BobiverseInstallTree -Path $rootFull -Recurse -FailClosed:$FailClosed
            Write-Host ("INFO FR #3394 ProgramData Bobiverse locked {0}" -f $rootFull)
        }
        $script:BobiverseProgramDataProtectCache[$cacheKey] = $true
        return $rootFull
    } catch {
        Write-Host ("WARN Ensure-BobiverseProgramDataRoot: {0}" -f $_.Exception.Message)
        if ($FailClosed) { throw }
        return ''
    }
}

function Test-BobiverseCrashReportAllowsIntake {
    <#
      FR #3395: whether installer/crash paths may POST to public intake.
      Precedence (mirrors crash_report.load_crash_report_policy): BOB_CRASH_REPORT /
      BOBIVERSE_CRASH_REPORT env > InstallRoot\config\crash-report.json > allow (fleet default).
      enabled=false / mode off|local-only => $false.
    #>
    param(
        [string]$InstallRoot = ''
    )
    $envRaw = ''
    if ($env:BOB_CRASH_REPORT -and ([string]$env:BOB_CRASH_REPORT).Trim()) {
        $envRaw = ([string]$env:BOB_CRASH_REPORT).Trim().ToLowerInvariant()
    } elseif ($env:BOBIVERSE_CRASH_REPORT -and ([string]$env:BOBIVERSE_CRASH_REPORT).Trim()) {
        $envRaw = ([string]$env:BOBIVERSE_CRASH_REPORT).Trim().ToLowerInvariant()
    }
    if ($envRaw) {
        if ($envRaw -in @('0', 'false', 'no', 'off', 'local', 'local-only', 'local_only', 'spool')) {
            return $false
        }
        if ($envRaw -in @('1', 'true', 'yes', 'on', 'full', 'no-log-tail', 'nologtail', 'no_log_tail')) {
            return $true
        }
    }
    if ($InstallRoot) {
        $cfg = Join-Path $InstallRoot 'config\crash-report.json'
        if (-not (Test-Path -LiteralPath $cfg)) {
            $cfg = Join-Path $InstallRoot 'crash-report.json'
        }
        if (Test-Path -LiteralPath $cfg) {
            try {
                $obj = Get-Content -LiteralPath $cfg -Raw -Encoding utf8 | ConvertFrom-Json
                $mode = ''
                if ($null -ne $obj.mode) { $mode = ([string]$obj.mode).Trim().ToLowerInvariant() }
                if ($mode -in @('local', 'local-only', 'local_only', 'spool', 'off')) {
                    return $false
                }
                if ($null -ne $obj.enabled) {
                    return [bool]$obj.enabled
                }
            } catch {
                # MRB #3440: unreadable/corrupt crash-report.json => deny intake.
                return $false
            }
        }
    }
    return $true
}


function Redact-BobiverseCrashText {
    <#
      FR #3515: mirror crash_report.redact for PowerShell install-failure intake
      (Bearer/Basic, NickServ, PASS, URL userinfo, secret KV, token blobs).
    #>
    param(
        [AllowNull()][string]$Text = ''
    )
    $s = if ($null -eq $Text) { '' } else { [string]$Text }
    if (-not $s) { return '' }
    $s = [regex]::Replace($s, '(?i)\b(?:Authorization\s*[:=]\s*)?(Bearer|Basic)\s+\S+', '$1=<redacted>')
    $s = [regex]::Replace(
        $s,
        '(?i)(?:PRIVMSG\s+NickServ\s+:)?(?:NickServ\s+)?(IDENTIFY|REGISTER)\s+\S+(?:\s+\S+)?',
        { param($m) "NickServ $($m.Groups[1].Value) <redacted>" }
    )
    $s = [regex]::Replace($s, '(?i)\bPASS\s+\S+', 'PASS <redacted>')
    $s = [regex]::Replace($s, '(?i)(https?://)[^/\s:@]+:[^/\s@]+@', '$1<redacted>@')
    $s = [regex]::Replace(
        $s,
        '(?i)"?(?<key>password|passwd|\bpass\b|secret|token|api[_-]?key|xai_api_key|cursor_api_key|BOB_IRC_PASSWORD|GH_TOKEN|GITHUB_TOKEN|Authorization|NickServ|SASL)"?\s*[:=]\s*(?:"[^"]*"|[^\s",}]+)',
        { param($m) "$($m.Groups['key'].Value)=<redacted>" }
    )
    $s = [regex]::Replace(
        $s,
        '(?i)\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{10,}|xox[baprs]-[A-Za-z0-9-]+)\b',
        '<redacted-token>'
    )
    return $s
}


function Resolve-BobiverseAircIntakeReportScript {
    <#
      FR #3515: find Report-BobiverseIntakeIssue.ps1 after client allow-list purge.
      Prefer InstallRoot\scripts (kept by FR #3514), then ScriptsDir / beside Common.
    #>
    param(
        [string]$InstallRoot = '',
        [string]$ScriptsDir = ''
    )
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($InstallRoot) {
        [void]$candidates.Add((Join-Path $InstallRoot 'scripts\Report-BobiverseIntakeIssue.ps1'))
    }
    if ($ScriptsDir) {
        [void]$candidates.Add((Join-Path $ScriptsDir 'Report-BobiverseIntakeIssue.ps1'))
        [void]$candidates.Add((Join-Path (Split-Path -Parent $ScriptsDir) 'common\scripts\Report-BobiverseIntakeIssue.ps1'))
    }
    if ($PSScriptRoot) {
        [void]$candidates.Add((Join-Path $PSScriptRoot 'Report-BobiverseIntakeIssue.ps1'))
    }
    foreach ($p in @($candidates)) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    return $null
}


function Send-BobiverseAircInstallFailureIntake {
    <#
      FR #3515 / #3395: local MSI log always; redacted intake when crash-report allows.
      Returns a small object: skipped / dry_run / title / body / report (or $null on hard skip).
    #>
    param(
        [string]$InstallRoot = '',
        [string]$ScriptsDir = '',
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$Body,
        [string]$Repo = 'SimonBarnett/bobiverse',
        [string]$IntakeUrl = '',
        [switch]$DryRun
    )
    $safeTitle = Redact-BobiverseCrashText -Text $Title
    $safeBody = Redact-BobiverseCrashText -Text $Body
    try {
        Write-BobiverseMsiInstallLog -Product airc -Message ("install-fail-intake: {0}" -f $safeBody)
    } catch { }

    $allowIntake = $false
    try {
        $allowIntake = [bool](Test-BobiverseCrashReportAllowsIntake -InstallRoot $InstallRoot)
    } catch {
        $allowIntake = $false
        Write-Host ("WARN FR #3515 crash-report policy check failed; skip intake: {0}" -f $_.Exception.Message)
    }
    if (-not $allowIntake) {
        Write-Host 'INFO FR #3515 skip intake (crash-report opt-out / local-only); failure logged locally'
        return [pscustomobject]@{
            skipped = $true
            dry_run = [bool]$DryRun
            title   = $safeTitle
            body    = $safeBody
            report  = $null
        }
    }

    $report = Resolve-BobiverseAircIntakeReportScript -InstallRoot $InstallRoot -ScriptsDir $ScriptsDir
    if (-not $report) {
        Write-Host 'WARN FR #3515 Report-BobiverseIntakeIssue.ps1 missing after purge; intake skipped'
        return [pscustomobject]@{
            skipped = $true
            dry_run = [bool]$DryRun
            title   = $safeTitle
            body    = $safeBody
            report  = $null
            missing_report = $true
        }
    }

    try {
        $splat = @{
            Title       = $safeTitle
            Body        = $safeBody
            Repo        = $Repo
            InstallRoot = $InstallRoot
        }
        if ($DryRun) { $splat.DryRun = $true }
        if ($IntakeUrl) { $splat.IntakeUrl = $IntakeUrl }
        $r = & $report @splat
        if ($r -and ($r.PSObject.Properties.Name -contains 'dry_run' -or $r.PSObject.Properties.Name -contains 'title')) {
            # Prefer report payload fields when present; always expose redacted title/body.
            return [pscustomobject]@{
                skipped = [bool]($(if ($r.PSObject.Properties['skipped_crash_opt_out']) { $r.skipped_crash_opt_out } else { $false }))
                dry_run = [bool]($(if ($r.PSObject.Properties['dry_run']) { $r.dry_run } else { [bool]$DryRun }))
                title   = $safeTitle
                body    = $safeBody
                report  = $report
                raw     = $r
            }
        }
        return [pscustomobject]@{
            skipped = $false
            dry_run = [bool]$DryRun
            title   = $safeTitle
            body    = $safeBody
            report  = $report
            raw     = $r
        }
    } catch {
        Write-Host ("WARN FR #3515 intake report failed: {0}" -f $_.Exception.Message)
        return [pscustomobject]@{
            skipped = $true
            dry_run = [bool]$DryRun
            title   = $safeTitle
            body    = $safeBody
            report  = $report
            error   = $_.Exception.Message
        }
    }
}


function Get-BobiverseAircFleetOperatorRoster {
    <#
      FR #3513: nick list for fleet cross-machine ears (one nick per line, # comments ok).
      Reads InstallRoot\config\fleet-operators.txt then %ProgramData%\Bobiverse\fleet-operators.txt.
      Workstation/client callers should ignore the result.
    #>
    param(
        [string]$InstallRoot = '',
        [string[]]$ExtraPaths = @()
    )
    $paths = New-Object System.Collections.Generic.List[string]
    if ($InstallRoot) {
        [void]$paths.Add((Join-Path $InstallRoot 'config\fleet-operators.txt'))
    }
    $pd = [string]$env:ProgramData
    if ($pd) {
        [void]$paths.Add((Join-Path $pd 'Bobiverse\fleet-operators.txt'))
    }
    foreach ($p in @($ExtraPaths)) {
        if ($p -and ([string]$p).Trim()) { [void]$paths.Add(([string]$p).Trim()) }
    }
    $seen = @{}
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($path in $paths) {
        if (-not $path -or -not (Test-Path -LiteralPath $path)) { continue }
        try {
            $raw = [IO.File]::ReadAllText($path)
        } catch {
            Write-Host ("WARN FR #3513 roster read {0}: {1}" -f $path, $_.Exception.Message)
            continue
        }
        $clean = $raw.TrimStart([char]0xFEFF)
        foreach ($ln in @($clean -split "`r?`n")) {
            $n = ([string]$ln).Trim()
            if (-not $n -or $n.StartsWith('#')) { continue }
            # Allow comma-separated leftovers on one line without treating as one nick (FR #3512).
            foreach ($piece in @($n -split '[,;\s]+' | Where-Object { $_ })) {
                $nick = ([string]$piece).Trim()
                if (-not $nick) { continue }
                $k = $nick.ToLowerInvariant()
                if ($seen.ContainsKey($k)) { continue }
                $seen[$k] = $true
                [void]$out.Add($nick)
            }
        }
    }
    Write-Output -NoEnumerate ($out.ToArray())
}

function Resolve-BobiverseAircOperatorNicks {
    <#
      FR #3397 / #3513 / #3639: build the operator nick list for Install-Airc / operators.txt.
      FR #3639: fleet + client never seed operators.txt (IRC +o/+h auth; ignore roster/extra).
      Workstation: use -Operators only; ignore OperatorsExtra and roster.
      FR #3512: return a flat string[] via Write-Output -NoEnumerate (never nest under @(...)).
    #>
    param(
        [string]$Profile = '',
        [string[]]$Operators = @(),
        [string]$OperatorsExtra = '',
        [string]$InstallRoot = '',
        [string[]]$RosterExtra = @()
    )
    $ops = New-Object System.Collections.Generic.List[string]
    foreach ($o in @($Operators)) {
        if ($o -and ([string]$o).Trim()) { [void]$ops.Add(([string]$o).Trim()) }
    }
    $prof = ([string]$Profile).Trim().ToLowerInvariant()
    # FR #3401 / #3639: client + fleet never seed operators.txt (IRC +o/+h auth).
    if ($prof -in @('client', 'fleet')) {
        Write-Output -NoEnumerate @()
        return
    }
    if ($prof -ne 'workstation') {
        $extra = ([string]$OperatorsExtra).Trim()
        if ($extra) {
            foreach ($o in @($extra -split '[,;\s]+' | Where-Object { $_ })) {
                $n = ([string]$o).Trim()
                if ($n) { [void]$ops.Add($n) }
            }
        }
        # Legacy empty-profile path only (fleet/client already returned).
        foreach ($o in @(Get-BobiverseAircFleetOperatorRoster -InstallRoot $InstallRoot)) {
            if ($o -and ([string]$o).Trim()) { [void]$ops.Add(([string]$o).Trim()) }
        }
        foreach ($o in @($RosterExtra)) {
            if ($o -and ([string]$o).Trim()) { [void]$ops.Add(([string]$o).Trim()) }
        }
    }
    $seen = @{}
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($n in $ops) {
        $k = $n.ToLowerInvariant()
        if ($seen.ContainsKey($k)) { continue }
        $seen[$k] = $true
        [void]$out.Add($n)
    }
    Write-Output -NoEnumerate ($out.ToArray())
}

function Merge-BobiverseAircOperatorsFile {
    <#
      FR #3397: create or union-update operators.txt (UTF-8 no BOM). Case-insensitive unique.
      Ensures bob-<machineId> unless -NoEnsureBobLocal.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [string[]]$Nicks = @(),
        [string]$MachineId = '',
        [switch]$NoEnsureBobLocal
    )
    if (-not $MachineId) {
        $MachineId = ($env:AIRC_CONSOLE_MACHINE, $env:BOB_MACHINE_ID | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1)
    }
    if (-not $MachineId) {
        $MachineId = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
    }
    if (-not $MachineId) { $MachineId = 'unknown' }
    $MachineId = ($MachineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
    $bobNick = "bob-$MachineId"
    $want = New-Object System.Collections.Generic.List[string]
    # FR #3512: split space/comma-joined tokens so a nested @() nick array cannot
    # land as a single operators.txt line ("Simon bob-other"). Absorbed from PR #3555.
    foreach ($o in @($Nicks)) {
        if ($null -eq $o) { continue }
        if (($o -is [System.Array]) -and -not ($o -is [string])) {
            foreach ($n in $o) {
                foreach ($p in @(([string]$n) -split '[,;\s]+' | Where-Object { $_ })) {
                    [void]$want.Add($p.Trim())
                }
            }
            continue
        }
        foreach ($p in @(([string]$o) -split '[,;\s]+' | Where-Object { $_ })) {
            [void]$want.Add($p.Trim())
        }
    }
    if (-not $NoEnsureBobLocal) {
        if (-not ($want | Where-Object { $_.ToLowerInvariant() -eq $bobNick })) {
            [void]$want.Add($bobNick)
        }
    }
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $existing = @()
    if (Test-Path -LiteralPath $Path) {
        $raw = [IO.File]::ReadAllText($Path)
        $clean = $raw.TrimStart([char]0xFEFF)
        $existing = @($clean -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -notmatch '^#' })
    }
    $seen = @{}
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($n in @($existing + @($want))) {
        if (-not $n) { continue }
        $k = $n.ToLowerInvariant()
        if ($seen.ContainsKey($k)) { continue }
        $seen[$k] = $true
        [void]$lines.Add($n)
    }
    if ($lines.Count -eq 0) {
        throw 'Merge-BobiverseAircOperatorsFile: no operator nicks'
    }
    $body = (($lines.ToArray()) -join "`n") + "`n"
    [IO.File]::WriteAllText($Path, $body, [Text.UTF8Encoding]::new($false))
    Write-Host ("INFO FR #3397 operators.txt union {0} ({1} nicks)" -f $Path, $lines.Count)
    return $Path
}


function Set-BobiverseNssmAppExitRestart {
    <#
    FR #1055: pin NSSM to Restart on Default AND exit code 0.
    Graceful chair quit exits 0; without an explicit AppExit 0=Restart some installs
    leave ircJeeves Stopped after a clean exit even when Default=Restart.
    #>
    param(
        [Parameter(Mandatory)][string]$Nssm,
        [Parameter(Mandatory)][string]$ServiceName,
        [int]$RestartDelayMs = 2000
    )
    [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppExit', 'Default', 'Restart'))
    [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppExit', '0', 'Restart'))
    if ($RestartDelayMs -gt 0) {
        [void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppRestartDelay', ([string]$RestartDelayMs)))
    }
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
      Leaves on-disk trees (<ai root>\ergo, <ai root>\airc-console) for manual rollback.
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
    $aiRoot = Get-BobiverseAiRoot   # t780u: discovered <drive>:\ai, never a hard-coded C:\ai
    foreach ($c in @(
            $pack,
            (Join-Path $aiRoot 'ergo\nssm.exe'),
            (Join-Path $aiRoot 'bob\third_party\nssm\win64\nssm.exe'),
            (Join-Path $aiRoot 'jeeves\third_party\nssm\win64\nssm.exe')
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

# ---------------------------------------------------------------------------------------------------------------------------
# Repo layout (t773u). The git repo is split per service (common\ jeeves\ bob\ airc\, each with scripts\ .grok\skills\ docs\ ...)
# but every STAGED / INSTALLED tree stays FLAT (<root>\scripts, <root>\.grok\skills, <root>\docs ...). These helpers let one
# piece of code read either: a split repo checkout, or a flat tree (a stage dir / an install root). Callers keep using the
# legacy flat relative paths ('scripts\x.ps1', 'src\VERSION', 'bob-agents\worker', 'AGENTS.bob.md', 'third_party\nssm' ...).
# ---------------------------------------------------------------------------------------------------------------------------
$script:BobiverseServiceDirs = @('common', 'jeeves', 'bob', 'airc')

# ---------------------------------------------------------------------------------------------------------------------------
# The "<drive>:\ai" root (t780u). Fleet boxes keep services/trees under <drive>:\ai, but the drive is NOT always C: (MarchHare had
# repos + agent homes on D:\ai). Never assume C:\ai: scan the FIXED physical disks (Win32_LogicalDisk DriveType 3; removable,
# network and CD/DVD are ignored) and use the \ai folder that exists. Several -> prefer the one already holding bob/jeeves/airc/
# ergo installs, then the one the fleet services (ircBob/ircJeeves/BobIrcd/Airc) already point at, then the system drive, then
# drive-letter order. None -> <SystemDrive>\ai, created ONLY by -Create. Env BOB_AI_ROOT overrides everything.
# ---------------------------------------------------------------------------------------------------------------------------
$script:BobiverseAiProducts = @('bob', 'jeeves', 'airc', 'ergo')
$script:BobiverseAiServices = @('ircBob', 'ircJeeves', 'BobIrcd', 'Airc')

function Select-BobiverseAiRoot {
    # Pure selection (tests inject Disks / ServiceDirs). Disks: objects with .Root (e.g. 'D:\') and .DriveType (3 = fixed).
    param(
        [object[]]$Disks = @(),
        [string[]]$ServiceDirs = @(),
        [string]$SystemDrive = 'C:',
        [string]$Override = ''
    )
    if ($Override) {
        return [pscustomobject]@{ Path = $Override.TrimEnd('\'); Found = $true; Reason = 'BOB_AI_ROOT override'; Candidates = @() }
    }
    $sysRoot = ($SystemDrive.TrimEnd('\') + '\')
    $fixed = @($Disks | Where-Object { $_ -and [int]$_.DriveType -eq 3 })
    $cands = @()
    foreach ($d in $fixed) {
        $root = ([string]$d.Root)
        if (-not $root.EndsWith('\')) { $root += '\' }
        $ai = Join-Path $root 'ai'
        if (Test-Path -LiteralPath $ai -PathType Container) { $cands += $ai }
    }
    if ($cands.Count -eq 0) {
        return [pscustomobject]@{ Path = ($sysRoot + 'ai'); Found = $false; Reason = 'no fixed disk has an ai folder; default is <SystemDrive>\ai'; Candidates = @() }
    }
    if ($cands.Count -eq 1) {
        return [pscustomobject]@{ Path = $cands[0]; Found = $true; Reason = 'only fixed disk with an ai folder'; Candidates = $cands }
    }
    $scored = foreach ($c in $cands) {
        $inst = @($script:BobiverseAiProducts | Where-Object { Test-Path -LiteralPath (Join-Path $c $_) -PathType Container }).Count
        $svc = @($ServiceDirs | Where-Object { $_ -and ($_.TrimEnd('\') -ieq $c.TrimEnd('\') -or $_.StartsWith($c.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) }).Count
        $isSys = [int]((Split-Path -Qualifier $c) -ieq $SystemDrive.TrimEnd('\'))
        [pscustomobject]@{ Path = $c; Inst = $inst; Svc = $svc; Sys = $isSys }
    }
    $best = $scored | Sort-Object @{Expression = 'Inst'; Descending = $true }, @{Expression = 'Svc'; Descending = $true }, @{Expression = 'Sys'; Descending = $true }, @{Expression = 'Path'; Descending = $false } | Select-Object -First 1
    $why = if ($best.Inst -gt 0) { "holds $($best.Inst) bob/jeeves/airc/ergo install folder(s)" } elseif ($best.Svc -gt 0) { 'fleet services point at it' } elseif ($best.Sys) { 'system drive' } else { 'first by drive letter' }
    return [pscustomobject]@{ Path = $best.Path; Found = $true; Reason = "several fixed disks have ai; chose: $why"; Candidates = $cands }
}

function Get-BobiverseFixedDisks {
    # Fixed physical disks only (DriveType 3). Falls back to [IO.DriveInfo] when CIM is unavailable.
    $out = @()
    try {
        $out = @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3' -ErrorAction Stop | ForEach-Object { [pscustomobject]@{ Root = ($_.DeviceID + '\'); DriveType = 3 } })
    } catch { }
    if ($out.Count -eq 0) {
        try { $out = @([IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq 'Fixed' } | ForEach-Object { [pscustomobject]@{ Root = $_.Name; DriveType = 3 } }) } catch { }
    }
    return $out
}

function Get-BobiverseServiceAiDirs {
    # Directories the fleet services already run from (NSSM AppDirectory / service image path), for the tie-break.
    $dirs = @()
    foreach ($n in $script:BobiverseAiServices) {
        try {
            $k = "HKLM:\SYSTEM\CurrentControlSet\Services\$n"
            $img = (Get-ItemProperty -LiteralPath $k -ErrorAction Stop).ImagePath
            if ($img) { $dirs += ([string]$img).Trim('"') }
            $ad = (Get-ItemProperty -LiteralPath "$k\Parameters" -ErrorAction SilentlyContinue).AppDirectory
            if ($ad) { $dirs += [string]$ad }
        } catch { }
    }
    return $dirs
}

function Get-BobiverseAiRoot {
    # The <drive>:\ai root to use. -Create makes <SystemDrive>\ai ONLY when no fixed disk has one (never when found).
    param(
        [switch]$Create,
        [object[]]$Disks = $null,
        [string[]]$ServiceDirs = $null,
        [string]$SystemDrive = '',
        [string]$Override = $null
    )
    # [string]$Override = $null binds as '' (not $null), so test whether the caller passed it.
    if (-not $PSBoundParameters.ContainsKey('Override')) { $Override = [string]$env:BOB_AI_ROOT }
    if (-not $SystemDrive) { $SystemDrive = if ($env:SystemDrive) { $env:SystemDrive } else { 'C:' } }
    if ($null -eq $Disks) { $Disks = if ($Override) { @() } else { @(Get-BobiverseFixedDisks) } }
    if ($null -eq $ServiceDirs) { $ServiceDirs = if ($Override) { @() } else { @(Get-BobiverseServiceAiDirs) } }
    $sel = Select-BobiverseAiRoot -Disks $Disks -ServiceDirs $ServiceDirs -SystemDrive $SystemDrive -Override $Override
    if ($Create -and -not (Test-Path -LiteralPath $sel.Path)) {
        New-Item -ItemType Directory -Force -Path $sel.Path | Out-Null
    }
    return $sel.Path
}

function Get-BobiverseProductRoot {
    # <ai root>\<product>  (bob | jeeves | airc | ergo ...). Does not create anything.
    param([Parameter(Mandatory)][string]$Product)
    return [IO.Path]::Combine((Get-BobiverseAiRoot), $Product)   # not Join-Path: it throws for a drive that does not exist (yet)
}

# ---------------------------------------------------------------------------------------------------------------------------
# The install dir as a git work tree (t781u/t782u). On every service start (Start-Bob / Start-Jeeves / Start-AircConsole ->
# Sync-BobiverseFromRepo.ps1 -> Sync-BobiverseWorkTree) <ai root>\<product> is made a SPARSE checkout of the bobiverse repo that holds
# ONLY that product's subtree plus common\ (bob -> bob\ + common\; jeeves -> jeeves\ + common\; airc -> airc\ + common\) and is
# fast-forwarded to origin/main. Rules: ff-only; never reset/stash/checkout -f/clean (local edits, commits and branches survive);
# never blocks or fails the start (timeouts, every error is a WARN and the installed files keep running); the flat runtime files
# (scripts\ third_party\ docs\ ...) are composed FROM the work tree by Sync-BobiverseFromRepo.ps1 and hidden from git via
# .git\info\exclude, so `git status` shows only real edits under <product>\ and common\.
# FR #1157: clean leftover fix/* tips (merged / upstream gone) auto-switch back to main before ff; BOBIVERSE_KEEP_BRANCH=1 opts out.
# ---------------------------------------------------------------------------------------------------------------------------
$script:BobiverseDefaultRemote = 'https://github.com/SimonBarnett/bobiverse.git'

function Resolve-BobiverseGitExe {
    foreach ($c in @(
            (Get-Command git.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
            (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'),
            (Join-Path $env:ProgramFiles 'Git\bin\git.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'Git\cmd\git.exe'),
            (Join-Path $env:LOCALAPPDATA 'grok\git\2.55.0.windows.5\cmd\git.exe')
        )) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Invoke-BobiverseGit {
    # Run git with a hard timeout and no prompts. Returns Code / Out / TimedOut. Never throws.
    param(
        [Parameter(Mandatory)][string]$Git,
        [Parameter(Mandatory)][string[]]$GitArgs,
        [string]$WorkDir = '',
        [int]$TimeoutSec = 60
    )
    $q = ($GitArgs | ForEach-Object { if ($_ -match '[\s"]' -or $_ -eq '') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' '
    $so = [IO.Path]::GetTempFileName(); $se = [IO.Path]::GetTempFileName()
    $prevPrompt = $env:GIT_TERMINAL_PROMPT; $env:GIT_TERMINAL_PROMPT = '0'
    try {
        $sp = @{ FilePath = $Git; ArgumentList = $q; NoNewWindow = $true; PassThru = $true; RedirectStandardOutput = $so; RedirectStandardError = $se }
        if ($WorkDir) { $sp.WorkingDirectory = $WorkDir }
        $p = Start-Process @sp
        $null = $p.Handle   # keep the handle so ExitCode is readable after WaitForExit
        $timedOut = $false
        if (-not $p.WaitForExit($TimeoutSec * 1000)) {
            $timedOut = $true
            try { & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null } catch { }
        } else { $p.WaitForExit() }
        $out = @((Get-Content -LiteralPath $so -ErrorAction SilentlyContinue) + (Get-Content -LiteralPath $se -ErrorAction SilentlyContinue)) | Where-Object { "$_".Trim() }
        return [pscustomobject]@{ Code = $(if ($timedOut) { 124 } else { [int]$p.ExitCode }); Out = @($out); TimedOut = $timedOut }
    } catch {
        return [pscustomobject]@{ Code = 125; Out = @($_.Exception.Message); TimedOut = $false }
    } finally {
        $env:GIT_TERMINAL_PROMPT = $prevPrompt
        Remove-Item -LiteralPath $so, $se -Force -ErrorAction SilentlyContinue
    }
}

function Sync-BobiverseWorkTree {
    <#
    .SYNOPSIS
      Make <InstallRoot> a sparse git work tree of the repo (product subtree + common\) and fast-forward it. Never throws.
    .OUTPUTS
      Ok (the work tree is usable as the file source), Pulled (HEAD moved), Bootstrapped, Branch, Reason, Log (lines to print).
    #>
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        [Parameter(Mandatory)][ValidateSet('bob', 'jeeves', 'airc')][string]$Product,
        [string]$Branch = 'main',
        [string]$Remote = '',
        [string]$GitExe = '',
        [int]$FetchTimeoutSec = 120,
        [int]$FetchRetries = 2,
        [switch]$DryRun
    )
    # FR #1074: allow ops override without editing the script (seconds / retry count).
    if ($env:BOBIVERSE_FETCH_TIMEOUT_SEC -match '^\d+$') {
        $FetchTimeoutSec = [int]$env:BOBIVERSE_FETCH_TIMEOUT_SEC
    }
    if ($env:BOBIVERSE_FETCH_RETRIES -match '^\d+$') {
        $FetchRetries = [int]$env:BOBIVERSE_FETCH_RETRIES
    }
    $log = New-Object System.Collections.Generic.List[string]
    $res = [ordered]@{ Ok = $false; Pulled = $false; Bootstrapped = $false; Branch = ''; Reason = ''; Log = $log }
    function Done([string]$why) { $res.Reason = $why; return [pscustomobject]$res }
    try {
        if ($env:BOBIVERSE_NO_UPDATE -eq '1') { return (Done 'BOBIVERSE_NO_UPDATE=1') }
        $git = if ($GitExe) { $GitExe } else { Resolve-BobiverseGitExe }
        if (-not $git) { return (Done 'git.exe missing') }
        if (-not $Remote) { $Remote = [string]$env:BOBIVERSE_REMOTE }
        if (-not $Remote) { $Remote = $script:BobiverseDefaultRemote }
        $root = [IO.Path]::GetFullPath($InstallRoot)
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { return (Done "install root missing: $root") }
        $G = @('-c', 'safe.directory=*', '-c', 'core.autocrlf=false', '-C', $root)   # services run as another account than the repo owner
        $hasGit = Test-Path -LiteralPath (Join-Path $root '.git')
        $created = $false
        if (-not $hasGit) {
            if ($DryRun) { $log.Add("INFO worktree-dry-run would bootstrap $root (sparse: $Product + common) from $Remote"); return (Done 'dry-run') }
            $r = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('init', '-q')) -TimeoutSec 30
            if ($r.Code -ne 0) { return (Done ("git init failed: " + ($r.Out -join ' '))) }
            $created = $true
            foreach ($step in @(
                    @('remote', 'add', 'origin', $Remote),
                    @('config', 'core.longpaths', 'true'),
                    @('sparse-checkout', 'set', '--no-cone', "/$Product/", '/common/'))) {
                $r = Invoke-BobiverseGit -Git $git -GitArgs ($G + $step) -TimeoutSec 30
                if ($r.Code -ne 0) { Remove-Item -LiteralPath (Join-Path $root '.git') -Recurse -Force -ErrorAction SilentlyContinue; return (Done ("git $($step[0]) failed: " + ($r.Out -join ' '))) }
            }
            Write-BobiverseInstallGitExclude -InstallRoot $root -Product $Product
            $log.Add("INFO worktree-bootstrap $root sparse=$Product,common origin=$Remote")
        } else {
            # Refresh exclude on existing installs so FR #132 un-ignores land without re-bootstrap.
            try { Write-BobiverseInstallGitExclude -InstallRoot $root -Product $Product } catch { }
        }
        if ($DryRun) { $log.Add('INFO worktree-dry-run skip fetch/merge'); $res.Ok = $true; return (Done 'dry-run') }

        # a merge/rebase/cherry-pick/bisect in progress is somebody's work - leave it completely alone
        foreach ($m in 'MERGE_HEAD', 'rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD', 'REVERT_HEAD') {
            if (Test-Path -LiteralPath (Join-Path $root ".git\$m")) { $res.Ok = $true; return (Done "operation in progress ($m); not touching the work tree") }
        }
        # FR #1074: longer default timeout + retries so transient GitHub slowness does not leave offer gates stale.
        $attempts = 1 + [Math]::Max(0, $FetchRetries)
        $f = $null
        for ($attempt = 1; $attempt -le $attempts; $attempt++) {
            $f = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('-c', 'http.lowSpeedLimit=1000', '-c', 'http.lowSpeedTime=45', 'fetch', '--prune', '-q', 'origin')) -TimeoutSec $FetchTimeoutSec
            if ($f.Code -eq 0) { break }
            foreach ($l in ($f.Out | Select-Object -First 3)) { $log.Add("  $l") }
            if ($f.TimedOut -and $attempt -lt $attempts) {
                $log.Add("WARN sync-fetch timed out after ${FetchTimeoutSec}s (attempt $attempt/$attempts); retrying")
                Start-Sleep -Seconds ([Math]::Min(5 * $attempt, 15))
                continue
            }
            break
        }
        if ($f.Code -ne 0) {
            if ($created) { Remove-Item -LiteralPath (Join-Path $root '.git') -Recurse -Force -ErrorAction SilentlyContinue }
            else { $res.Ok = $true }
            $why = if ($f.TimedOut) { "fetch timed out after ${FetchTimeoutSec}s x$attempts" } else { "fetch failed (exit $($f.Code)); keeping the installed version" }
            $log.Add("ALERT sync-fetch-failed: $why; live tree not refreshed from origin")
            return (Done $why)
        }
        if ($created) {
            $c = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('checkout', '-q', '-B', $Branch, '--track', "origin/$Branch")) -TimeoutSec 120
            if ($c.Code -ne 0) {
                foreach ($l in ($c.Out | Select-Object -First 3)) { $log.Add("  $l") }
                Remove-Item -LiteralPath (Join-Path $root '.git') -Recurse -Force -ErrorAction SilentlyContinue
                return (Done "initial checkout failed (exit $($c.Code)); keeping the installed version")
            }
            $res.Bootstrapped = $true; $res.Pulled = $true; $res.Ok = $true; $res.Branch = $Branch
            return (Done "bootstrapped on $Branch")
        }
        # FR #2944: existing .git with unborn/empty HEAD (e.g. leftover `master` with "No commits yet")
        # never enters the bootstrap checkout path above. Heal like first bootstrap when origin/$Branch
        # is reachable - empty HEAD is not agent work, so KEEP_BRANCH does not preserve it.
        $hv = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('rev-parse', '--verify', 'HEAD')) -TimeoutSec 20
        if ($hv.Code -ne 0) {
            $sc = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('sparse-checkout', 'set', '--no-cone', "/$Product/", '/common/')) -TimeoutSec 30
            if ($sc.Code -ne 0) {
                foreach ($l in ($sc.Out | Select-Object -First 3)) { $log.Add("  $l") }
                $res.Ok = $true
                return (Done ("unborn HEAD heal sparse-checkout failed (exit $($sc.Code)); keeping the installed version"))
            }
            try { Write-BobiverseInstallGitExclude -InstallRoot $root -Product $Product } catch { }
            $c = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('checkout', '-q', '-B', $Branch, '--track', "origin/$Branch")) -TimeoutSec 120
            if ($c.Code -ne 0) {
                foreach ($l in ($c.Out | Select-Object -First 3)) { $log.Add("  $l") }
                $res.Ok = $true
                $log.Add("ALERT worktree-heal-unborn failed (exit $($c.Code)); keeping the installed version")
                return (Done ("unborn HEAD heal checkout failed (exit $($c.Code)); keeping the installed version"))
            }
            $res.Bootstrapped = $true; $res.Pulled = $true; $res.Ok = $true; $res.Branch = $Branch
            $log.Add("INFO worktree-heal-unborn HEAD -> $Branch (FR #2944)")
            return (Done "healed unborn HEAD onto $Branch")
        }
        $res.Ok = $true
        $br = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('symbolic-ref', '--short', '-q', 'HEAD')) -TimeoutSec 20
        $cur = if ($br.Code -eq 0 -and $br.Out.Count) { "$($br.Out[0])".Trim() } else { '' }
        $res.Branch = $cur
        if ($cur -ne $Branch) {
            # FR #1157: install trees left on a merged/deleted feature branch skip ff forever and robocopy
            # drifts from that tip. When safe, return to main (never destroys dirty work or never-pushed branches).
            # Opt out: BOBIVERSE_KEEP_BRANCH=1 (or BOBIVERSE_NO_UPDATE=1 already returned above).
            $keepBranch = ($env:BOBIVERSE_KEEP_BRANCH -eq '1')
            $st = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('status', '--porcelain')) -TimeoutSec 20
            $dirty = ($st.Code -eq 0 -and (@($st.Out | Where-Object { "$_".Trim() }).Count -gt 0))
            $anc = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('merge-base', '--is-ancestor', 'HEAD', "origin/$Branch")) -TimeoutSec 20
            $mergedOrBehind = ($anc.Code -eq 0)
            $cfgRemote = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('config', '--get', "branch.$cur.remote")) -TimeoutSec 15
            $hadUpstream = ($cfgRemote.Code -eq 0 -and @($cfgRemote.Out | Where-Object { "$_".Trim() }).Count -gt 0)
            $up = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('rev-parse', '--abbrev-ref', '@{u}')) -TimeoutSec 15
            $upstreamGone = ($hadUpstream -and $up.Code -ne 0)
            if (-not $keepBranch -and -not $dirty -and ($mergedOrBehind -or $upstreamGone)) {
                $whyReturn = if ($upstreamGone) { "upstream gone" } else { "HEAD ancestor of origin/$Branch" }
                $log.Add("INFO worktree-return-$Branch from '$cur' (clean; $whyReturn) FR#1157")
                $sw = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('switch', '-q', $Branch)) -TimeoutSec 60
                if ($sw.Code -eq 0) {
                    $res.Branch = $Branch
                    $cur = $Branch
                } else {
                    foreach ($l in ($sw.Out | Select-Object -First 3)) { $log.Add("  $l") }
                    $log.Add("WARN worktree-return-$Branch switch failed; staying on '$cur'")
                }
            }
            if ($cur -ne $Branch) {
                # FR #1074: still off-main after #1157 gates - alert so operators notice offer gates may lag.
                # FR #3622: append "; dirty" when porcelain is non-empty so Sync-BobiverseFromRepo can
                # tip-ok compose a clean agent branch while still sync-skip-stale for dirty trees (FR #2982).
                $why = if ($cur) { "on branch '$cur' (not $Branch); fetched only, work tree untouched" } else { 'detached HEAD; fetched only, work tree untouched' }
                if ($dirty) { $why = "$why; dirty" }
                $behindOff = Get-BobiverseWorkTreeBehindCount -Git $git -GitArgsBase $G -Branch $Branch
                if ($behindOff -gt 0) {
                    $why = "$why; HEAD behind origin/$Branch by $behindOff commit(s)"
                }
                $log.Add("ALERT sync-worktree-off-main: $why")
                return (Done $why)
            }
        }
        $before = (Invoke-BobiverseGit -Git $git -GitArgs ($G + @('rev-parse', 'HEAD')) -TimeoutSec 20).Out | Select-Object -First 1
        $behindPre = Get-BobiverseWorkTreeBehindCount -Git $git -GitArgsBase $G -Branch $Branch
        if ($behindPre -gt 0) {
            $log.Add("INFO sync-behind-pre: HEAD behind origin/$Branch by $behindPre commit(s); attempting ff-only")
        }
        $m = Invoke-BobiverseGit -Git $git -GitArgs ($G + @('merge', '--ff-only', '-q', "origin/$Branch")) -TimeoutSec 60
        if ($m.Code -ne 0) {
            foreach ($l in ($m.Out | Select-Object -First 3)) { $log.Add("  $l") }
            $behindFail = Get-BobiverseWorkTreeBehindCount -Git $git -GitArgsBase $G -Branch $Branch
            $behindMsg = if ($behindFail -gt 0) { "; HEAD behind origin/$Branch by $behindFail commit(s)" } else { '' }
            $log.Add("ALERT sync-ff-failed: ff-only not possible (local commits or edits in the way); live flat scripts may lag origin/$Branch until resolved$behindMsg")
            return (Done ("ff-only not possible (local commits or edits in the way); local work kept as is$behindMsg"))
        }
        $after = (Invoke-BobiverseGit -Git $git -GitArgs ($G + @('rev-parse', 'HEAD')) -TimeoutSec 20).Out | Select-Object -First 1
        $res.Pulled = ("$before" -ne "$after")
        # FR #2470: verify tip after ff - a silent miss left marchhare common/scripts 403 commits behind origin/main.
        $behind = Get-BobiverseWorkTreeBehindCount -Git $git -GitArgsBase $G -Branch $Branch
        if ($behind -gt 0) {
            $log.Add("ALERT sync-behind: HEAD behind origin/$Branch by $behind commit(s) after ff-only; live common/scripts may lag tip (FR #2470)")
            return (Done "still behind origin/$Branch by $behind")
        }
        return (Done $(if ($res.Pulled) { "fast-forwarded origin/$Branch" } else { 'already up to date' }))
    } catch {
        $res.Reason = "work tree sync error: $($_.Exception.Message)"
        return [pscustomobject]$res
    }
}

function Get-BobiverseWorkTreeBehindCount {
    # FR #2470: commits on origin/<Branch> not in HEAD (0 = tip; -1 = git error).
    param(
        [Parameter(Mandatory)][string]$Git,
        [Parameter(Mandatory)][string[]]$GitArgsBase,
        [Parameter(Mandatory)][string]$Branch
    )
    $c = Invoke-BobiverseGit -Git $Git -GitArgs ($GitArgsBase + @('rev-list', '--count', "HEAD..origin/$Branch")) -TimeoutSec 30
    if ($c.Code -ne 0) { return -1 }
    $raw = if ($c.Out.Count) { "$($c.Out[0])".Trim() } else { '' }
    if ($raw -match '^\d+$') { return [int]$raw }
    return -1
}

function Sync-BobiverseUpdaterFromOrigin {
    # FR #2581: dirty install trees block ff-only, so robocopy composes a stale
    # Update-BobiverseService.ps1 (pre-#2563 soft-fail). After fetch, overlay the
    # origin/<Branch> tip blob into flat scripts\ and common\scripts\ so Apply
    # soft-fail lands without waiting for a clean worktree.
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        [string]$Branch = 'main',
        [string]$GitExe = ''
    )
    $git = if ($GitExe) { $GitExe } else {
        $cmd = Get-Command git -ErrorAction SilentlyContinue
        if ($cmd) { $cmd.Source } else { '' }
    }
    if (-not $git) { return [pscustomobject]@{ Ok = $false; Reason = 'no git' } }
    if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot '.git'))) {
        return [pscustomobject]@{ Ok = $false; Reason = 'install is not a git work tree' }
    }
    $spec = "origin/${Branch}:common/scripts/Update-BobiverseService.ps1"
    $tmp = Join-Path $env:TEMP ("bobiverse-upd-tip-" + [guid]::NewGuid().ToString('n') + '.ps1')
    try {
        $p = Start-Process -FilePath $git -ArgumentList @('-C', $InstallRoot, 'show', $spec) `
            -RedirectStandardOutput $tmp -RedirectStandardError ($tmp + '.err') `
            -NoNewWindow -Wait -PassThru
        if ($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $tmp)) {
            $err = ''
            if (Test-Path -LiteralPath ($tmp + '.err')) {
                $err = (Get-Content -LiteralPath ($tmp + '.err') -Raw -ErrorAction SilentlyContinue)
            }
            return [pscustomobject]@{ Ok = $false; Reason = "git show $spec failed: $err" }
        }
        $bytes = [IO.File]::ReadAllBytes($tmp)
        if ($bytes.Length -lt 40) {
            return [pscustomobject]@{ Ok = $false; Reason = "tip blob too small ($($bytes.Length))" }
        }
        $text = [Text.Encoding]::UTF8.GetString($bytes)
        if ($text -notmatch 'MaxAttempts|FR #2563|Update-Bobiverse|NoCount') {
            return [pscustomobject]@{ Ok = $false; Reason = 'tip blob unexpected content' }
        }
        $utf8 = New-Object Text.UTF8Encoding $false
        $targets = @(
            (Join-Path $InstallRoot 'scripts\Update-BobiverseService.ps1'),
            (Join-Path $InstallRoot 'common\scripts\Update-BobiverseService.ps1')
        )
        foreach ($t in $targets) {
            $dir = Split-Path -Parent $t
            if (-not (Test-Path -LiteralPath $dir)) {
                New-Item -ItemType Directory -Force -Path $dir | Out-Null
            }
            [IO.File]::WriteAllText($t, $text.TrimEnd("`r", "`n") + "`n", $utf8)
        }
        return [pscustomobject]@{
            Ok     = $true
            Reason = "overlay $spec"
            Bytes  = $bytes.Length
        }
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath ($tmp + '.err') -Force -ErrorAction SilentlyContinue
    }
}
function Get-BobiverseInstallGitExcludeText {
    # Shared by install bootstrap and sync refresh (FR #132). Linked FR worktrees use this exclude.
    param([Parameter(Mandatory)][string]$Product)
    return (
        "# bobiverse install work tree (t781u): runtime files are composed from <product>/ and common/`n" +
        "# FR worktrees sharing this git dir: sibling products un-ignored; else git add -f (FR #132)`n" +
        "/*`n!/$Product/`n!/common/`n!/airc/`n!/jeeves/`n"
    )
}

function Write-BobiverseInstallGitExclude {
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        [Parameter(Mandatory)][string]$Product
    )
    $ex = Join-Path $InstallRoot '.git\info\exclude'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ex) | Out-Null
    [IO.File]::WriteAllText($ex, (Get-BobiverseInstallGitExcludeText -Product $Product), (New-Object Text.UTF8Encoding($false)))
}

function Test-BobiverseSplitRepo {
    param([Parameter(Mandatory)][string]$Root)
    return [bool](Test-Path -LiteralPath (Join-Path $Root 'common\VERSION'))
}

function Get-BobiverseRepoRoot {
    # <repo>\<service>\scripts -> <repo> (split checkout);  <root>\scripts -> <root> (flat stage / install tree).
    param([Parameter(Mandatory)][string]$ScriptDir)
    $p = Split-Path -Parent $ScriptDir
    $g = if ($p) { Split-Path -Parent $p } else { '' }
    if ($g -and (Test-BobiverseSplitRepo -Root $g)) { return $g }
    return $p
}

function Get-BobiverseRepoDirs {
    # Every existing <service>\<Sub> directory of a split repo (common first), or the single <Root>\<Sub> of a flat tree.
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Sub)
    if (Test-BobiverseSplitRepo -Root $Root) {
        foreach ($s in $script:BobiverseServiceDirs) {
            $d = Join-Path $Root (Join-Path $s $Sub)
            if (Test-Path -LiteralPath $d -PathType Container) { $d }
        }
    } else {
        $d = Join-Path $Root $Sub
        if (Test-Path -LiteralPath $d -PathType Container) { $d }
    }
}

function Copy-BobiverseRepoDirs {
    # Compose <Dest> from every <service>\<Sub> (the staged flat layout is exactly this union).
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Sub, [Parameter(Mandatory)][string]$Dest)
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    foreach ($d in @(Get-BobiverseRepoDirs -Root $Root -Sub $Sub)) {
        Copy-Item -Path (Join-Path $d '*') -Destination $Dest -Recurse -Force
    }
}

function Get-BobiverseRepoPath {
    # Resolve a LEGACY flat relative path to where it lives now. Flat trees: plain Join-Path. Split repo: alias table, else the
    # first <service>\<Rel> that exists, else <Root>\<Rel> (config\, dist\ ... stay at the repo root).
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Rel)
    $r = $Rel.TrimStart('\', '/').Replace('/', '\')
    if (-not (Test-BobiverseSplitRepo -Root $Root)) { return (Join-Path $Root $r) }
    $alias = $null
    if ($r -ieq 'src\VERSION' -or $r -ieq 'VERSION') { $alias = 'common\VERSION' }
    elseif ($r -imatch '^bob-agents(\\.*)?$') { $alias = 'bob\agents' + $Matches[1] }
    elseif ($r -imatch '^AGENTS\.(jeeves|bob|airc)\.md$') { $alias = $Matches[1] + '\AGENTS.md' }
    elseif ($r -imatch '^packaging\\airc\\(.+)$') { $alias = 'airc\packaging\' + $Matches[1] }
    # t829u: the systray and the agent watcher are first-class bob sources (bob\tray, bob\agentwatcher); the legacy flat spellings keep resolving.
    elseif ($r -imatch '^third_party\\bob-tray(\\.*)?$') { $alias = 'bob\tray' + $Matches[1] }
    elseif ($r -imatch '^third_party\\Watch-AgentHealth(\\.*)?$') { $alias = 'bob\agentwatcher' + $Matches[1] }
    elseif ($r -imatch '^(tray|agentwatcher)(\\.*)?$') { $alias = 'bob\' + $Matches[1] + $Matches[2] }
    elseif ($r -imatch '^third_party\\(nssm|ergo|wix|bootstrap)(\\.*)?$') { $alias = 'common\third_party\' + $Matches[1] + $Matches[2] }
    if ($alias) { return (Join-Path $Root $alias) }
    foreach ($s in $script:BobiverseServiceDirs) {
        $c = Join-Path $Root (Join-Path $s $r)
        if (Test-Path -LiteralPath $c) { return $c }
    }
    return (Join-Path $Root $r)
}

function Get-BobiverseRepoMergedDir {
    # A flat tree: <Root>\<Sub>.  A split repo: a temp dir holding the union of every <service>\<Sub>.
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Sub)
    if (-not (Test-BobiverseSplitRepo -Root $Root)) { return (Join-Path $Root $Sub) }
    $t = Join-Path ([IO.Path]::GetTempPath()) ('bobiverse-' + ($Sub -replace '[^A-Za-z0-9]', '-') + '-' + [Guid]::NewGuid().ToString('N'))
    Copy-BobiverseRepoDirs -Root $Root -Sub $Sub -Dest $t
    return $t
}

function Copy-BobiverseVersion {
    <#
      Lay InstallRoot\VERSION from the repo/stage VERSION source.
      FR #2948: MSI RunInstall must not overwrite the MSI-laid VERSION with a stale
      InstallRoot\common\VERSION when RepoRoot == InstallRoot (sparse work tree that
      could not ff). When -MsiProductVersion is set, that value wins. When RepoRoot
      is the install tree and VERSION already exists, keep it (do not copy common\VERSION).
    #>
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        [Parameter(Mandatory)][string]$RepoRoot,
        [string]$MsiProductVersion = ''
    )
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    $dest = Join-Path $InstallRoot 'VERSION'
    $want = ([string]$MsiProductVersion).Trim()
    if ($want -match '^\d+\.\d+\.\d+') {
        [IO.File]::WriteAllText($dest, $want + [Environment]::NewLine, (New-Object Text.UTF8Encoding $false))
        Write-Host ("INFO Copy-BobiverseVersion MSI ProductVersion={0} -> {1}" -f $want, $dest)
        return
    }
    if (Test-BobiverseSamePath $InstallRoot $RepoRoot) {
        if (Test-Path -LiteralPath $dest) {
            $laid = ''
            try { $laid = (Get-Content -LiteralPath $dest -Raw -ErrorAction Stop).Trim() } catch { }
            $srcSame = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'src\VERSION'
            $gitV = ''
            if (Test-Path -LiteralPath $srcSame) {
                try { $gitV = (Get-Content -LiteralPath $srcSame -Raw -ErrorAction Stop).Trim() } catch { }
            }
            if ($laid -and $gitV -and ($laid -ne $gitV)) {
                Write-Host ("INFO Copy-BobiverseVersion skip stale git VERSION={0} keep laid={1} (RepoRoot==InstallRoot; FR #2948)" -f $gitV, $laid)
                return
            }
            if ($laid) {
                Write-Host ("INFO Copy-BobiverseVersion skip: VERSION already present at InstallRoot ({0}; FR #2948)" -f $laid)
                return
            }
        }
    }
    $src = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'src\VERSION'
    if (-not (Test-Path -LiteralPath $src)) { throw "missing $src" }
    Copy-Item -LiteralPath $src -Destination $dest -Force
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
    # Also skip when Source is Dest\* already (scripts -> InstallRoot\scripts and $here is that scripts dir)
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

# --- FR #2564: MSI UI 1603 / rollback logging + service recover ---

function Get-BobiverseMsiLogDir {
    <#
      Canonical verbose / CA log directory for UI and quiet msiexec (FR #2564).
      Prefer %ProgramData%\Bobiverse\logs so a UI install without /l*v still leaves a known trail.
      FR #3394 / #3554: Ensure locks root+logs once per process (LogsOnly), not Full -Recurse
      on every append (fleet ProgramData trees are GB-scale).
      Honours BOBIVERSE_PROGRAMDATA_ROOT for tests.
    #>
    # FR #3554: pytest sets BOBIVERSE_PROGRAMDATA_ROOT - create dirs only (Protect would
    # Users-RX the tmp tree and unelevated AppendAllText fails). Live MSI uses LogsOnly.
    $mode = 'LogsOnly'
    if ($env:BOBIVERSE_PROGRAMDATA_ROOT -and ([string]$env:BOBIVERSE_PROGRAMDATA_ROOT).Trim()) {
        $mode = 'None'
    }
    $root = Ensure-BobiverseProgramDataRoot -ProtectMode $mode
    if ($root) {
        return (Join-Path $root 'logs')
    }
    $pd = if ($env:ProgramData) { $env:ProgramData } else { 'C:\ProgramData' }
    $dir = Join-Path $pd 'Bobiverse\logs'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Write-BobiverseMsiInstallLog {
    <#
      Append one UTF-8 (no BOM) line to ProgramData\Bobiverse\logs\install-<product>.log (FR #2564).
      FR #3554: uses Get-BobiverseMsiLogDir (LogsOnly + process Protect cache).
    #>
    param(
        [Parameter(Mandatory)][ValidateSet('bob', 'jeeves', 'airc')][string]$Product,
        [Parameter(Mandatory)][string]$Message,
        [string]$Leaf = ''
    )
    try {
        $dir = Get-BobiverseMsiLogDir
        if (-not $Leaf) { $Leaf = "install-$Product.log" }
        $path = Join-Path $dir $Leaf
        $line = '{0:o} {1}' -f [datetime]::UtcNow, ($Message -replace '[\r\n]+', ' ')
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [IO.File]::AppendAllText($path, $line + [Environment]::NewLine, $utf8)
        Write-Host ("INFO msi-log {0}: {1}" -f $Leaf, $Message)
    } catch {
        Write-Host ("WARN msi-log-write-failed: {0}" -f $_.Exception.Message)
    }
}

function Assert-BobiverseInstallVersion {
    <#
      FR #2564: when MSI forwards ProductVersion, InstallRoot\VERSION must match.
      Prevents a "success" that left binaries / ARP on a different build.
      Empty ExpectedVersion = no-op (repo/script installs without the MSI property).
    #>
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        [string]$ExpectedVersion = '',
        [ValidateSet('bob', 'jeeves', 'airc', '')][string]$Product = ''
    )
    if (-not $ExpectedVersion -or -not $ExpectedVersion.Trim()) { return }
    $want = $ExpectedVersion.Trim()
    if ($want -notmatch '^\d+\.\d+\.\d+') {
        Write-Host ("WARN Assert-BobiverseInstallVersion skip bad ExpectedVersion '{0}'" -f $want)
        return
    }
    $verPath = Join-Path $InstallRoot 'VERSION'
    if (-not (Test-Path -LiteralPath $verPath)) {
        throw "Assert-BobiverseInstallVersion: missing $verPath (expected $want)"
    }
    $got = (Get-Content -LiteralPath $verPath -Raw -ErrorAction Stop).Trim()
    if ($got -ne $want) {
        throw "Assert-BobiverseInstallVersion: InstallRoot VERSION='$got' expected '$want' (FR #2564)"
    }
    if ($Product) {
        Write-BobiverseMsiInstallLog -Product $Product -Message ("version-ok file={0}" -f $got)
    }
}

function Restore-BobiverseServiceAfterFailedInstall {
    <#
      FR #2564: after Install-*.ps1 / MSI RunInstall failure or WiX rollback, best-effort Start-Service
      so a failed upgrade does not leave ircBob/Airc/ircJeeves Stopped and wipe seats.
      Does not recreate a fully removed service (needs a full Install-*.ps1); only starts if SCM entry exists.
    #>
    param(
        [Parameter(Mandatory)][string]$ServiceName,
        [ValidateSet('bob', 'jeeves', 'airc')][string]$Product = 'bob',
        [string]$Why = 'install-failed'
    )
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-BobiverseMsiInstallLog -Product $Product -Message ("recover-skip service=$ServiceName absent why=$Why") -Leaf ("recover-$Product.log")
        Write-Host "WARN recover: service $ServiceName absent after failed install ($Why) - re-run Install or sanctioned self-update"
        return $false
    }
    if ($svc.Status -eq 'Running') {
        Write-BobiverseMsiInstallLog -Product $Product -Message ("recover-ok already-running $ServiceName why=$Why") -Leaf ("recover-$Product.log")
        return $true
    }
    try {
        if ($svc.StartType -eq 'Disabled') {
            try { Set-Service -Name $ServiceName -StartupType Automatic -ErrorAction SilentlyContinue } catch { }
        }
        Start-Service -Name $ServiceName -ErrorAction Stop
        Start-Sleep -Seconds 2
        $after = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        $ok = $after -and $after.Status -eq 'Running'
        Write-BobiverseMsiInstallLog -Product $Product -Message ("recover-start service=$ServiceName ok=$ok status=$($after.Status) why=$Why") -Leaf ("recover-$Product.log")
        if ($ok) { Write-Host "INFO recover: started $ServiceName after failed install ($Why)" }
        else { Write-Host "WARN recover: Start-Service $ServiceName did not reach Running ($($after.Status))" }
        return [bool]$ok
    } catch {
        Write-BobiverseMsiInstallLog -Product $Product -Message ("recover-fail service=$ServiceName err=$($_.Exception.Message) why=$Why") -Leaf ("recover-$Product.log")
        Write-Host "WARN recover: Start-Service $ServiceName failed: $($_.Exception.Message)"
        return $false
    }
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
    $aiRoot = Get-BobiverseAiRoot   # t780u
    foreach ($p in 'bob', 'jeeves', 'airc') { $cands += (Join-Path $aiRoot "$p\assets\bob-systray.ico") }
    foreach ($c in $cands) { if (Test-Path -LiteralPath $c) { return $c } }
    return ''
}

# Pure data: the shortcuts a product contributes to the single Start Menu folder.
# t794u / FR #787: Bobiverse folder holds "Start Systray" (bob) and "Start Jeeves Monitor" (jeeves, butler icon).
# The only other link is the transient "Complete bobiverse service logon (<product>)" helper while a service still needs its password.
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
    $butler = Join-Path $InstallRoot 'assets\jeeves-butler.ico'
    if (-not (Test-Path -LiteralPath $butler)) {
        $aiRoot = Split-Path -Parent $InstallRoot
        $alt = Join-Path $aiRoot 'jeeves\assets\jeeves-butler.ico'
        if (Test-Path -LiteralPath $alt) { $butler = $alt }
    }
    $butlerIco = if (Test-Path -LiteralPath $butler) { "$butler,0" } else { $ico }
    $ps = 'powershell.exe'
    $scr = Join-Path $InstallRoot 'scripts'
    $list = New-Object System.Collections.Generic.List[object]
    function Add-Spec($name, $target, $cmdArgs, $wd, $desc, $iconLoc = $ico) {
        $list.Add([pscustomobject]@{ Name = $name; Target = $target; Arguments = $cmdArgs; WorkingDirectory = $wd; Description = $desc; Icon = $iconLoc })
    }
    if ($Product -eq 'bob' -and $IncludeTray) {
        $tray = Join-Path $scr 'Start-BobTray.ps1'
        # FR #1636: Start Menu shortcut uses -SkipTidy so operators do not wipe seats/Grok Bot.
        # TipForm menu Restart remains the explicit tidy path (Start-BobFleetTray -ForceNew without SkipTidy).
        Add-Spec 'Start Systray' $ps "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tray`" -InstallRoot `"$InstallRoot`" -MachineId $MachineId -ForceNew -SkipTidy" $InstallRoot 'Start the Bobiverse systray (ForceNew tray only; SkipTidy keeps seats)' $ico
    }
    if ($Product -eq 'jeeves') {
        $mon = Join-Path $scr 'Start-JeevesMonitor.ps1'
        Add-Spec 'Start Jeeves Monitor' $ps "-NoProfile -ExecutionPolicy Bypass -File `"$mon`" -InstallRoot `"$InstallRoot`"" $InstallRoot 'Start a NEW Jeeves MONITORING agent (never resume; CWD = Jeeves install; runs monitor-start immediately)' $butlerIco
    }
    if ($NeedLogon) {
        Add-Spec "Complete bobiverse service logon ($Product)" $ps "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $scr 'Complete-BobiverseServiceLogon.ps1')`" -Product $Product -InstallRoot `"$InstallRoot`"" $scr "Set the $Product service ObjectName password (required once after MSI)" $ico
    }
    return $list.ToArray()
}

# t794u: the systray runs as the interactive user and must be able to stop/start ircBob (Exit stops it, Start Systray restarts
# it). Services default to read-only for interactive users, so the installer adds start/stop/pause/interrogate for IU to the SDDL.
# Pure: Sddl in, Sddl out (unchanged when IU already has the rights).
function Get-BobiverseServiceSddlWithUserControl {
    param([Parameter(Mandatory)][string]$Sddl)
    $need = @('RP', 'WP', 'DT', 'LO', 'LC', 'CR')   # start, stop, pause/continue, interrogate, query status, read control
    $m = [regex]::Match($Sddl, '\(A;;([A-Z]+);;;IU\)')
    if ($m.Success) {
        $have = @(); $r = $m.Groups[1].Value
        for ($i = 0; $i + 1 -lt $r.Length; $i += 2) { $have += $r.Substring($i, 2) }
        $all = @($have)
        foreach ($n in $need) { if ($all -notcontains $n) { $all += $n } }
        if ($all.Count -eq $have.Count) { return $Sddl }
        return $Sddl.Substring(0, $m.Index) + '(A;;' + ($all -join '') + ';;;IU)' + $Sddl.Substring($m.Index + $m.Length)
    }
    $ace = '(A;;' + ($need -join '') + ';;;IU)'
    $s = $Sddl.IndexOf('S:')
    if ($s -ge 0) { return $Sddl.Substring(0, $s) + $ace + $Sddl.Substring($s) }
    return $Sddl + $ace
}

# Needs an elevated caller (installer / hotpatch). Returns $true when the service now grants the interactive user start/stop.
function Grant-BobiverseServiceUserControl {
    param([Parameter(Mandatory)][string]$Name)
    try {
        if ($Name -notmatch '^[A-Za-z0-9_.-]{1,64}$') { return $false }
        $sc = Join-Path $env:SystemRoot 'System32\sc.exe'
        $cur = (@(& $sc sdshow $Name 2>&1) | Where-Object { $_ -match '^D:' } | Select-Object -First 1)
        if (-not $cur) { return $false }
        $new = Get-BobiverseServiceSddlWithUserControl -Sddl ([string]$cur).Trim()
        if ($new -ceq ([string]$cur).Trim()) { return $true }
        $out = & $sc sdset $Name $new 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) { Write-Host ("WARN service ACL for {0}: {1}" -f $Name, ($out -replace '\s+', ' ').Trim()); return $false }
        Write-Host "INFO $Name : interactive users may start/stop the service (systray Exit / Start Systray)"
        return $true
    } catch {
        Write-Host ("WARN service ACL for {0}: {1}" -f $Name, $_.Exception.Message)
        return $false
    }
}

# Remove the scattered / duplicate Bobiverse Start Menu entries left by older installers. Returns removed paths.
function Remove-BobiverseStartMenuDuplicates {
    param([string[]]$ProgramsRoots = @(), [string]$KeepDir = '')
    if (-not $ProgramsRoots -or $ProgramsRoots.Count -eq 0) {
        $roots = New-Object System.Collections.Generic.List[string]
        $roots.Add((Get-BobiverseProgramsRoot))
        # t794u: profiles are not always on C: (MarchHare: D:\Users). Take every ProfileList entry, the current user's Programs folder
        # and C:\Users, de-duplicated.
        $profileDirs = New-Object System.Collections.Generic.List[string]
        try {
            foreach ($k in @(Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList' -ErrorAction SilentlyContinue)) {
                $pi = [string](Get-ItemProperty -LiteralPath $k.PSPath -Name ProfileImagePath -ErrorAction SilentlyContinue).ProfileImagePath
                if ($pi) { $profileDirs.Add([Environment]::ExpandEnvironmentVariables($pi)) }
            }
        } catch { }
        foreach ($u in @(Get-ChildItem 'C:\Users' -Directory -ErrorAction SilentlyContinue)) { $profileDirs.Add($u.FullName) }
        foreach ($pd in @($profileDirs | Select-Object -Unique)) {
            $p = Join-Path $pd 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs'
            if ((Test-Path -LiteralPath $p) -and -not $roots.Contains($p)) { $roots.Add($p) }
        }
        try { $cu = [Environment]::GetFolderPath('Programs'); if ($cu -and (Test-Path -LiteralPath $cu) -and -not $roots.Contains($cu)) { $roots.Add($cu) } } catch { }
        $ProgramsRoots = $roots.ToArray()
    }
    $legacyTop = '^(Bob Systray.*|Bob Tray.*|Bobiverse Tray.*|Bobiverse.*|Bob Fleet.*|Restart ircBob|Restart ircJeeves|Restart Airc|Bob Services|Start Systray|Start Jeeves Monitor|Complete bobiverse service logon.*)\.lnk$'
    $legacyInKeep = '^(Bob Services|Bobiverse Tray|Bob Systray.*|Restart (ircBob|ircJeeves|Airc)|Jeeves command reference|Logs \(.+\)|Skill books \(.+\)|Agent guide \(.+\))\.lnk$'
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
            if ($isKeep) {
                # t794u: the kept folder holds ONE entry; drop every older per-product / duplicate link inside it
                foreach ($f in @(Get-ChildItem -LiteralPath $d.FullName -File -Filter '*.lnk' -ErrorAction SilentlyContinue)) {
                    if ($f.Name -match $legacyInKeep) {
                        Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
                        $removed.Add($f.FullName)
                    }
                }
                continue
            }
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
    $skillsDirs = @(Get-BobiverseRepoDirs -Root $RepoRoot -Sub '.grok\skills')
    $enc = New-Object System.Text.UTF8Encoding($false)
    $defs = @(
        @{ Name = 'worker'; Shared = @('bobiverse-bob', 'bobiverse-bob-worker', 'bobiverse-bob-plan', 'bobiverse-bob-job-irc', 'bobiverse-bob-job-fr', 'bobiverse-bob-job-mrb', 'bobiverse-bob-job-uat', 'bobiverse-fleet-ops', 'harvest', 'harvest-agent-skills') },
        @{ Name = 'plan';   Shared = @('harvest', 'harvest-agent-skills') }
    )
    $made = 0
    foreach ($d in $defs) {
        $n = $d.Name
        $src = Get-BobiverseRepoPath -Root $RepoRoot -Rel "bob-agents\$n"
        if (-not (Test-Path -LiteralPath (Join-Path $src 'AGENTS.md'))) { Write-Host "WARN agent folder source missing: bob-agents\$n"; continue }
        $dest = Join-Path $Destination $n
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item -Path (Join-Path $src '*') -Destination $dest -Recurse -Force
        foreach ($sk in $d.Shared) {
            $from = @($skillsDirs | ForEach-Object { Join-Path $_ $sk } | Where-Object { Test-Path -LiteralPath $_ })[0]
            if (-not $from) { throw "agent folder $n needs .grok\skills\$sk" }
            $to = Join-Path $dest ".grok\skills\$sk"
            New-Item -ItemType Directory -Force -Path $to | Out-Null
            Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force
            # FR #2835: nested skill-dba\.grok\skills is a foreign skill-book snapshot (SimonBarnett/skill-dba),
            # not a bobiverse agent instruction copy. Drop it from the staged agent folder so CAST IRON /
            # Report-BobiverseIntakeIssue pins stay on real bob books only.
            $nestedDbaGrok = Join-Path $to 'skill-dba\.grok'
            if (Test-Path -LiteralPath $nestedDbaGrok) {
                Remove-Item -LiteralPath $nestedDbaGrok -Recurse -Force
            }
        }
        # The agent runs with cwd = <install>\$n, so the rule's relative '.\scripts\' becomes '..\scripts\' (install-root independent - t780u: no C:\ai baked into the MSI stage).
        Get-ChildItem -LiteralPath (Join-Path $dest '.grok\skills') -Recurse -Filter 'SKILL.md' | ForEach-Object {
            $t = [IO.File]::ReadAllText($_.FullName)
            $t2 = [regex]::Replace($t, '(?<!\.)\.\\scripts\\', '..\scripts\')   # bare '.\scripts\' only; a plain Replace also hit '..\scripts\' -> '...\scripts\' (FR #1704)
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
    $agentsSrc = Get-BobiverseRepoPath -Root $RepoRoot -Rel "AGENTS.$Product.md"
    if ((-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'AGENTS.md'))) -and (Test-Path -LiteralPath $agentsSrc)) {
        foreach ($d in @('AGENTS.md', 'CLAUDE.md', 'GROK.md')) { Copy-Item -LiteralPath $agentsSrc -Destination (Join-Path $InstallRoot $d) -Force; $n++ }
    }
    Write-Host "INFO agent layer files refreshed in ${InstallRoot}: $n"
}

# FR #3392: MSI Stage-Product always lays AGENTS/CLAUDE/GROK/.cursor/.grok and the union of
# common/bob/jeeves agent scripts. Workstation / AIRC_AGENT_LAYER=0 must strip that payload
# after copy (Install-Airc) so the box stays agent-free. Returns paths removed (for manifest).
function Remove-BobiverseAircWorkstationAgentPayload {
    param(
        [Parameter(Mandatory)][string]$InstallRoot
    )
    $removed = New-Object System.Collections.Generic.List[string]
    if (-not $InstallRoot -or -not (Test-Path -LiteralPath $InstallRoot)) {
        return @($removed)
    }
    $root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
    $targets = New-Object System.Collections.Generic.List[string]
    foreach ($f in @('AGENTS.md', 'CLAUDE.md', 'GROK.md')) {
        [void]$targets.Add((Join-Path $root $f))
    }
    [void]$targets.Add((Join-Path $root '.cursor'))
    [void]$targets.Add((Join-Path $root '.grok'))
    # Fleet / agent launcher scripts laid by Pack union of common+bob+jeeves scripts.
    $agentScripts = @(
        'agent_control.py',
        'startworker.py',
        'grok_talk.py',
        'bobtalk.py',
        'irc_agent.py',
        'chan_workers.py',
        'talk_seat_ghost.py',
        'talk_seat_pid.py',
        'worker_irc_seats.py',
        'Install-BootstrapTools.ps1',
        'Invoke-BobiverseHarvest.ps1',
        'Report-BobiverseIntakeIssue.ps1',
        'Sync-BobiverseFromRepo.ps1',
        'Start-BobCallbackSupervised.ps1',
        'Restart-BobService.ps1'
    )
    $scriptsDir = Join-Path $root 'scripts'
    foreach ($name in $agentScripts) {
        [void]$targets.Add((Join-Path $scriptsDir $name))
    }
    foreach ($path in $targets) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        try {
            Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
            [void]$removed.Add($path)
            Write-Host ("INFO FR #3392 removed workstation agent payload: {0}" -f $path)
        } catch {
            Write-Host ("WARN FR #3392 remove {0}: {1}" -f $path, $_.Exception.Message)
        }
    }
    Write-Host ("INFO FR #3392 workstation agent payload purged count={0}" -f $removed.Count)
    return @($removed)
}

function Get-BobiverseAircClientAllowedScriptNames {
    <#
    .SYNOPSIS
      FR #3514: scripts kept under AIRC_PROFILE=client (allow-list, not deny-list).
    #>
    return @(
        'Bobiverse-Common.ps1',
        'Install-Airc.ps1',
        'Install-Airc.cmd',
        'Install-AircConsole.ps1',
        'Install-AircConsole.cmd',
        'Uninstall-Airc.ps1',
        'Uninstall-Airc.cmd',
        'Recover-BobiverseService.ps1',
        'Recover-BobiverseService.cmd',
        'Resolve-AircConsoleNssm.ps1',
        'Resolve-AircConsolePython.ps1',
        'Start-AircConsole.ps1',
        'Start-AircConsole.cmd',
        'Start-AircConsole-Fleet.ps1',
        'Update-BobiverseService.ps1',
        # FR #3514 / #3515: install-failure intake + python crash path
        'Report-BobiverseIntakeIssue.ps1',
        'crash_report.py',
        # Legacy host when airc\airc.exe is absent (SkipAircExe / pre-exe trees)
        'airc_console.py',
        'airc_console_service.py',
        'airc_jobs.py'
    )
}

function Remove-BobiverseAircClientExtraPayload {
    <#
    .SYNOPSIS
      FR #3514 / #3582: AIRC_PROFILE=client keep-only tree (airc.exe + service + install tooling).

    .DESCRIPTION
      The MSI stages the 4-product script union. Workstation uses a deny-list strip
      (Remove-BobiverseAircWorkstationAgentPayload) that still leaves Jeeves/Bob/docs.
      Client uses this allow-list: keep VERSION/BUILD.json, config\ (install-generated
      only), logs\, airc\, third_party\nssm\, and Get-BobiverseAircClientAllowedScriptNames;
      delete the rest. FR #3582: always drop config\fleet-operators.txt - client never
      reads the fleet roster (Install sets Operators=@(); file header says client ignores it).
    #>
    param(
        [Parameter(Mandatory)][string]$InstallRoot
    )
    $removed = New-Object System.Collections.Generic.List[string]
    if (-not $InstallRoot -or -not (Test-Path -LiteralPath $InstallRoot)) {
        return @($removed)
    }
    $root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')

    function Add-RemovedPath([string]$Path) {
        if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return }
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            [void]$removed.Add($Path)
            Write-Host ("INFO FR #3514 removed client extra: {0}" -f $Path)
        } catch {
            Write-Host ("WARN FR #3514 remove {0}: {1}" -f $Path, $_.Exception.Message)
        }
    }

    # Top-level files/dirs that must go (docs/src/assets/agent briefings).
    foreach ($name in @(
            'AGENTS.md', 'CLAUDE.md', 'GROK.md',
            '.cursor', '.grok',
            'docs', 'src', 'assets'
        )) {
        Add-RemovedPath (Join-Path $root $name)
    }

    # Any other unexpected top-level entry outside the keep set.
    $keepTop = @{
        'version'      = $true
        'build.json'   = $true
        'config'       = $true
        'logs'         = $true
        'scripts'      = $true
        'airc'         = $true
        'third_party'  = $true
        'home'         = $true  # rare; ConsoleHome is usually separate
    }
    Get-ChildItem -LiteralPath $root -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $key = $_.Name.ToLowerInvariant()
        if (-not $keepTop.ContainsKey($key)) {
            Add-RemovedPath $_.FullName
        }
    }

    # third_party: keep only nssm (win64\nssm.exe tree).
    $tp = Join-Path $root 'third_party'
    if (Test-Path -LiteralPath $tp) {
        Get-ChildItem -LiteralPath $tp -Force -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.Name -ne 'nssm') {
                Add-RemovedPath $_.FullName
            }
        }
    }

    # scripts: allow-list only.
    $allowed = @{}
    foreach ($n in @(Get-BobiverseAircClientAllowedScriptNames)) {
        $allowed[$n.ToLowerInvariant()] = $true
    }
    $scriptsDir = Join-Path $root 'scripts'
    if (Test-Path -LiteralPath $scriptsDir) {
        Get-ChildItem -LiteralPath $scriptsDir -Force -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.PSIsContainer) {
                Add-RemovedPath $_.FullName
                return
            }
            if (-not $allowed.ContainsKey($_.Name.ToLowerInvariant())) {
                Add-RemovedPath $_.FullName
            }
        }
    }

    # FR #3582: fleet roster is dead weight on client (never read; leaks seat nicks).
    Add-RemovedPath (Join-Path $root 'config\fleet-operators.txt')

    Write-Host ("INFO FR #3514 client allow-list purge count={0}" -f $removed.Count)
    return @($removed)
}
