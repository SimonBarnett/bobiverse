#Requires -Version 4.0
<#
.SYNOPSIS
  Register NSSM service AircConsole (Automatic). FR #253 / #256 / #305.
.NOTES
  Downloaded packages are unsigned. Prefer Install-AircConsole.cmd (Unblock-File +
  -ExecutionPolicy Bypass). Direct .ps1 invoke fails under AllSigned/Restricted.

  Issue #305: do NOT use a RunAsAdministrator requires-directive (that aborts without UAC).
  Self-elevate via Start-Process -Verb RunAs when the caller is not already admin.
  The MSI release is already elevated (per-machine); this path covers .cmd/.ps1.
#>
[CmdletBinding()]
param(
    # Empty = auto: release third_party\nssm\win64\nssm.exe, then legacy <ai root>\ergo, then PATH (#266).
    [string]$Nssm = '',
    [string]$Launcher = '',
    [Alias('Home')]
    [string]$ConsoleHome = '',
    [string]$PasswordFile = '',
    # Optional explicit Ergo server PASS source file (copied into ConsoleHome\ergo.password).
    [string]$ErgoPasswordFile = '',
    # FR #3639: retired - airc authorises by live control-channel +o/+h only (no operators list).
    # Accepted so older callers still bind; never written to disk.
    [string[]]$Operators = @(),
    [string]$ServiceName = 'AircConsole',
    # Absolute python.exe for LocalSystem (#282). Empty = auto-resolve at install.
    [string]$Python = '',
    # Fleet shop id (ionos/flamingo/...). Empty = BOB_MACHINE_ID / AIRC_CONSOLE_MACHINE.
    # Required on boxes where COMPUTERNAME is not the fleet id (e.g. WIN-...).
    [string]$MachineId = '',
    # #277: default starts the service so Running is the unattended end state.
    [switch]$NoStart,
    # FR #3287: remote capability gates (Install-Airc also writes config\airc.json).
    [ValidateSet('', 'off', 'operators')]
    [string]$ShellMode = '',
    [ValidateSet('', 'off', 'on')]
    [string]$Jobs = '',
    [ValidateSet('', 'off', 'on')]
    [string]$UpdateCap = '',
    [switch]$RequireAccount,
    [string[]]$Accounts = @(),
    # FR #3401 / #3639: every profile authorises by live control-channel +o/+h (irc_ops).
    [ValidateSet('', 'fleet', 'workstation', 'client')]
    [string]$Profile = '',
    # FR #3639: 'operators' is retired and mapped to irc_ops (kept so old callers bind).
    [ValidateSet('', 'operators', 'irc_ops')]
    [string]$AuthMode = ''
)

$ErrorActionPreference = 'Stop'

function Test-AircConsoleIsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-AircConsoleBoundArgumentList {
    <#
      Rebuild -File argv for a UAC re-launch from $PSBoundParameters.
    #>
    $list = New-Object System.Collections.Generic.List[string]
    foreach ($key in $PSBoundParameters.Keys) {
        $val = $PSBoundParameters[$key]
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
    return , $list.ToArray()
}

if (-not (Test-AircConsoleIsAdmin)) {
    $self = $PSCommandPath
    if (-not $self) { $self = $MyInvocation.MyCommand.Path }
    if (-not $self) { throw 'Install-AircConsole: cannot resolve script path for UAC elevation (issue #305)' }
    Write-Host 'INFO not elevated; requesting UAC for Install-AircConsole (issue #305)'
    $relaunch = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $self) + @(Get-AircConsoleBoundArgumentList)
    try {
        $p = Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $relaunch -Wait -PassThru
    } catch {
        throw ("UAC elevation failed or was cancelled: {0}" -f $_.Exception.Message)
    }
    if ($null -eq $p) { throw 'UAC elevation produced no process (cancelled?)' }
    exit [int]$p.ExitCode
}

# FR #1552: load shared helpers when present (Install-Airc always has them; direct invoke may not).
$scriptDirEarly = $PSScriptRoot
if (-not $scriptDirEarly) {
    if ($PSCommandPath) { $scriptDirEarly = Split-Path -Parent $PSCommandPath }
    elseif ($MyInvocation.MyCommand.Path) { $scriptDirEarly = Split-Path -Parent $MyInvocation.MyCommand.Path }
}
$commonPs1 = if ($scriptDirEarly) { Join-Path $scriptDirEarly 'Bobiverse-Common.ps1' } else { '' }
if ($commonPs1 -and (Test-Path -LiteralPath $commonPs1) -and -not (Get-Command Get-BobiverseServiceAppParameters -ErrorAction SilentlyContinue)) {
    . $commonPs1
}

# FR #1552: capture existing service AppParameters BEFORE tear-down so upgrade/reinstall
# keeps ConsoleHome / MachineId / PasswordFile (never default to the invoking profile).
# Fall back to InstallRoot\config\airc-install.json when the service registry is empty.
$priorAppParams = ''
$priorId = $null
if (Get-Command Get-BobiverseServiceAppParameters -ErrorAction SilentlyContinue) {
    $priorAppParams = Get-BobiverseServiceAppParameters -ServiceName $ServiceName
    $priorId = Get-BobiverseAircIdentityFromAppParameters -AppParameters $priorAppParams
}
if ((-not $priorAppParams) -and $scriptDirEarly) {
    $installRootGuess = Split-Path -Parent $scriptDirEarly
    $snapPath = Join-Path $installRootGuess 'config\airc-install.json'
    if (Test-Path -LiteralPath $snapPath) {
        try {
            $snap = Get-Content -LiteralPath $snapPath -Raw -Encoding utf8 | ConvertFrom-Json
            $priorId = [pscustomobject]@{
                ConsoleHome   = [string]($snap.ConsoleHome)
                MachineId     = [string]($snap.MachineId)
                PasswordFile  = [string]($snap.PasswordFile)
                OperatorsFile = [string]($snap.OperatorsFile)
                Launcher      = [string]($snap.Launcher)
                Raw           = ''
            }
            Write-Host "INFO FR #1552: no AppParameters - using $snapPath"
        } catch {
            Write-Host ("WARN airc-install.json read: {0}" -f $_.Exception.Message)
        }
    }
}
if ($priorId -and ($priorId.ConsoleHome -or $priorId.MachineId -or $priorId.PasswordFile -or $priorId.Launcher -or $priorId.OperatorsFile)) {
    Write-Host "INFO FR #1552: preserving identity from prior $ServiceName install"
    if (-not $ConsoleHome -and $priorId.ConsoleHome) { $ConsoleHome = $priorId.ConsoleHome }
    if (-not $MachineId -and $priorId.MachineId) { $MachineId = $priorId.MachineId }
    if (-not $PasswordFile -and $priorId.PasswordFile -and (Test-Path -LiteralPath $priorId.PasswordFile)) {
        $PasswordFile = $priorId.PasswordFile
    }
    if (-not $Launcher -and $priorId.Launcher -and (Test-Path -LiteralPath $priorId.Launcher)) {
        $Launcher = $priorId.Launcher
    }
}

# Resolve fleet machine id early (NSSM env + Start -MachineId).
if (-not $MachineId) {
    $MachineId = ($env:AIRC_CONSOLE_MACHINE, $env:BOB_MACHINE_ID | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1)
}
if ($MachineId) {
    $MachineId = ($MachineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
}
$script:AircConsoleMachineId = $MachineId
if ($MachineId) {
    Write-Host "INFO MachineId=$MachineId (console will JOIN #$MachineId)"
} else {
    Write-Warning ("Install without -MachineId / BOB_MACHINE_ID uses COMPUTERNAME={0}; console may join #win-... instead of #ionos." -f $env:COMPUTERNAME)
}

# FR #259: $PSScriptRoot can be empty in param() defaults under [CmdletBinding()];
# resolve launcher dir in the body (also prefer local disk over mapped P:).
$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
    if ($PSCommandPath) { $scriptDir = Split-Path -Parent $PSCommandPath }
    elseif ($MyInvocation.MyCommand.Path) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
}
if (-not $Launcher) {
    if (-not $scriptDir) { throw 'cannot resolve Install-AircConsole.ps1 directory (FR #259)' }
    $Launcher = Join-Path $scriptDir 'Start-AircConsole.ps1'
}
$resolveHelper = Join-Path $scriptDir 'Resolve-AircConsoleNssm.ps1'
if (Test-Path -LiteralPath $resolveHelper) { . $resolveHelper }
elseif (Get-Command Resolve-AircConsoleNssmPath -ErrorAction SilentlyContinue) { }
else {
    function Resolve-AircConsoleNssmPath {
        param([string]$Preferred = '', [string]$ScriptDir = '')
        if ($Preferred -and (Test-Path -LiteralPath $Preferred)) { return (Resolve-Path -LiteralPath $Preferred).Path }
        return $null
    }
}
$resolvedNssm = Resolve-AircConsoleNssmPath -Preferred $Nssm -ScriptDir $scriptDir
if (-not $resolvedNssm) {
    throw 'nssm missing: unpack third_party\nssm\win64\nssm.exe from the release zip (issue #266), or pass -Nssm, or install to <ai root>\ergo\nssm.exe'
}
$Nssm = $resolvedNssm
Write-Host "INFO using nssm: $Nssm"
if (-not (Test-Path -LiteralPath $Launcher)) { throw "launcher missing: $Launcher" }
$Launcher = (Resolve-Path -LiteralPath $Launcher).Path
if ($Launcher -match '^[A-Za-z]:\\' ) {
    # Warn when launcher is on a mapped network drive (issue #259 repro on P:).
    $root = ($Launcher.Substring(0, 2))
    $drive = Get-PSDrive -Name $root.TrimEnd(':') -ErrorAction SilentlyContinue
    if ($drive -and $drive.DisplayRoot) {
        Write-Host ("WARN launcher on mapped drive {0} -> {1}; prefer a local copy under C:\\ai\\airc-console (FR #259)" -f $root, $drive.DisplayRoot)
    }
}

function Test-AircDefaultProfileHome {
    param([string]$Path)
    return [bool](($Path) -and ($Path -match '(?i)(?:^|[\\/])Users[\\/]Default(?:[\\/]|$)'))
}

function Test-AircUserProfileHome {
    <# FR #3288: any Users\<profile>\... home is unsafe for a LocalSystem console service. #>
    param([string]$Path)
    return [bool](($Path) -and ($Path -match '(?i)(?:^|[\\/])Users[\\/][^\\/]+(?:[\\/]|$)'))
}

function Resolve-AircSafeConsoleHome {
    <#
      FR #2355: never keep ConsoleHome under Users\Default (prior-identity restore / FR #1552
      can re-bake the orphan NickServ home). Migrate files to <install>\home and rewrite paths.
      FR #3288: also migrate any Users\<profile> home to <install>\home for LocalSystem Airc.
    #>
    param(
        # FR #2499: never name this $Home - automatic $Home is read-only under bind.
        [Parameter(Mandatory)]
        [Alias('Home')]
        [string]$HomePath,
        [Parameter(Mandatory)][string]$SafeHome,
        [string]$PasswordFilePath = '',
        [switch]$MigrateAnyUserProfile
    )
    $mustMove = Test-AircDefaultProfileHome -Path $HomePath
    if (-not $mustMove -and $MigrateAnyUserProfile -and (Test-AircUserProfileHome -Path $HomePath)) {
        $mustMove = $true
    }
    if (-not $mustMove) {
        return [pscustomobject]@{ ConsoleHome = $HomePath; PasswordFile = $PasswordFilePath; Migrated = $false; SourceHome = $HomePath }
    }
    Write-Host "WARN FR #2355/#3288: ConsoleHome under user profile ($HomePath) - migrating to $SafeHome"
    New-Item -ItemType Directory -Force -Path $SafeHome | Out-Null
    if (Test-Path -LiteralPath $HomePath) {
        Copy-Item -LiteralPath (Join-Path $HomePath '*') -Destination $SafeHome -Recurse -Force -ErrorAction SilentlyContinue
    }
    $pf = $PasswordFilePath
    if ($pf -and (Test-AircUserProfileHome -Path $pf)) {
        $leaf = Split-Path -Leaf $pf
        if (-not $leaf) { $leaf = 'console.password' }
        $pf = Join-Path $SafeHome $leaf
    }
    return [pscustomobject]@{ ConsoleHome = $SafeHome; PasswordFile = $pf; Migrated = $true; SourceHome = $HomePath }
}

function Remove-AircDefaultProfileSecrets {
    <# FR #3288: delete Users\Default\.airc* so new local profiles do not inherit secrets. #>
    param([string]$SystemDrive = $env:SystemDrive)
    if (-not $SystemDrive) { $SystemDrive = 'C:' }
    $defaultRoot = Join-Path $SystemDrive 'Users\Default'
    foreach ($name in @('.airc', '.airc-console')) {
        $p = Join-Path $defaultRoot $name
        if (Test-Path -LiteralPath $p) {
            try {
                Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction Stop
                Write-Host "INFO FR #3288 removed $p"
            } catch {
                Write-Host ("WARN FR #3288 could not remove {0}: {1}" -f $p, $_.Exception.Message)
                if (Get-Command Protect-BobiverseSecretPath -ErrorAction SilentlyContinue) {
                    Protect-BobiverseSecretPath -Path $p -Recurse
                }
            }
        }
    }
}

# LocalSystem / quiet MSI: never bake C:\Users\Default\.airc* (NickServ GUID orphan).
# FR #3288: LocalSystem ConsoleHome defaults to <install>\home (never a user profile).
if (-not $ConsoleHome) {
    $isSystem = $false
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $isSystem = ($id.User.Value -eq 'S-1-5-18') -or ($id.Name -match 'SYSTEM$')
    } catch { }
    if ($isSystem) {
        $installGuess = Split-Path -Parent (Split-Path -Parent $Launcher)
        if (-not $installGuess) { $installGuess = if (Get-Command Get-BobiverseAiRoot -ErrorAction SilentlyContinue) { Join-Path (Get-BobiverseAiRoot) 'airc' } else { throw 'cannot derive the airc install dir (dot-source Bobiverse-Common.ps1 or pass -ConsoleHome)' } }
        $ConsoleHome = Join-Path $installGuess 'home'
        Write-Host "INFO LocalSystem ConsoleHome=$ConsoleHome (FR #3288 install\home)"
    } else {
        $ConsoleHome = Join-Path $env:USERPROFILE '.airc-console'
    }
}
New-Item -ItemType Directory -Force -Path $ConsoleHome | Out-Null

# FR #2355 / #3288: remap user-profile homes (Default or Admin) to <install>\home.
$installRootForHome = Split-Path -Parent (Split-Path -Parent $Launcher)
if (-not $installRootForHome) { $installRootForHome = Split-Path -Parent $scriptDir }
$safeConsoleHome = Join-Path $installRootForHome 'home'
$migrateProfiles = $true
$homeFix = Resolve-AircSafeConsoleHome -Home $ConsoleHome -SafeHome $safeConsoleHome -PasswordFilePath $PasswordFile -MigrateAnyUserProfile:$migrateProfiles
$ConsoleHome = $homeFix.ConsoleHome
if ($homeFix.PasswordFile) { $PasswordFile = $homeFix.PasswordFile }
Remove-AircDefaultProfileSecrets
New-Item -ItemType Directory -Force -Path $ConsoleHome | Out-Null

function Write-AircSecretFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Secret
    )
    $text = ($Secret -replace '[\r\n]+$', '').Trim()
    if (-not $text) { throw "refusing empty secret for $Path" }
    # ASCII one-line; no BOM - same shape as connect.password / NickServ GUID.
    [IO.File]::WriteAllText($Path, $text + "`n", (New-Object System.Text.UTF8Encoding $false))
    # FR #3288: SYSTEM + Administrators only - never grant the installing user.
    if (Get-Command Protect-BobiverseSecretPath -ErrorAction SilentlyContinue) {
        Protect-BobiverseSecretPath -Path $Path
    } else {
        icacls $Path /inheritance:r /grant:r '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' 2>$null | Out-Null
    }
}

function Initialize-AircConsoleHomeSecrets {
    param(
        # Never name this $Home - PowerShell automatic $Home is read-only (FR #259).
        [Parameter(Mandatory)][string]$ConsoleHomeDir,
        [string[]]$OperatorNicks,
        [string]$NickServPasswordFile = '',
        [string]$ErgoSourceFile = '',
        # Issue #294: packaged release config\ergo.password (not target ~/.grok).
        [string]$PackagedErgoFile = ''
    )
    # FR #3401 / #3639: no profile creates, updates or reads operators.txt. Auth is live
    # control-channel +o/+h. A leftover file from an older install is left in place
    # (rollback to a pre-#3639 build still finds it) but nothing reads it.
    $legacyOps = Join-Path $ConsoleHomeDir 'operators.txt'
    if (Test-Path -LiteralPath $legacyOps) {
        Write-Host "INFO FR #3639 legacy $legacyOps left unused (auth is control-channel +o/+h)"
    } else {
        Write-Host 'INFO FR #3639 no operators.txt (auth is control-channel +o/+h)'
    }
    $opsFile = $null

    # #271 NickServ GUID - mint here so first service start is unattended.
    if (-not $NickServPasswordFile) {
        $NickServPasswordFile = Join-Path $ConsoleHomeDir 'console.password'
    }
    if (-not (Test-Path -LiteralPath $NickServPasswordFile) -or -not (Get-Content -LiteralPath $NickServPasswordFile -Raw -ErrorAction SilentlyContinue).Trim()) {
        $guid = [guid]::NewGuid().ToString()
        Write-AircSecretFile -Path $NickServPasswordFile -Secret $guid
        Write-Host "INFO minted NickServ GUID -> $NickServPasswordFile"
    } else {
        Write-Host "INFO keep $NickServPasswordFile"
    }

    # #294 / FR #3756: Ergo server PASS comes from the *release zip*
    # (config\ergo.password), -ErgoPasswordFile, env, or an existing home file -
    # not from the target machine's ~/.grok (most clients have none). Public MSIs
    # do not embed the PASS (issue #4); private fleet zips may.
    $ergoDest = Join-Path $ConsoleHomeDir 'ergo.password'
    $secret = $null
    $source = $null
    if ($ErgoSourceFile -and (Test-Path -LiteralPath $ErgoSourceFile)) {
        $secret = (Get-Content -LiteralPath $ErgoSourceFile -Raw).Trim()
        $source = $ErgoSourceFile
    }
    if (-not $secret -and $PackagedErgoFile -and (Test-Path -LiteralPath $PackagedErgoFile)) {
        $secret = (Get-Content -LiteralPath $PackagedErgoFile -Raw).Trim()
        $source = $PackagedErgoFile
    }
    if (-not $secret -and (Test-Path -LiteralPath $ergoDest)) {
        $secret = (Get-Content -LiteralPath $ergoDest -Raw).Trim()
        $source = $ergoDest
    }
    # FR #3756: same env keys as Pack-AircConsoleRelease / Start-AircConsole.
    if (-not $secret) {
        foreach ($key in @(
                'AIRC_PACK_ERGO_PASSWORD',
                'AGENTIC_IRC_PASSWORD',
                'AIRC_CONSOLE_SERVER_PASSWORD',
                'BOB_IRC_PASSWORD'
            )) {
            $v = [Environment]::GetEnvironmentVariable($key)
            if ($v -and $v.Trim()) {
                $secret = $v.Trim()
                $source = "env:$key"
                break
            }
        }
    }
    if (-not $secret) {
        throw @"
Ergo server PASS missing (FR #3756 / issue #294). Provide one of:
  1) release unpack config\ergo.password (private zip packed with fleet secret),
  2) -ErgoPasswordFile <path>,
  3) env AIRC_PACK_ERGO_PASSWORD / AGENTIC_IRC_PASSWORD / AIRC_CONSOLE_SERVER_PASSWORD / BOB_IRC_PASSWORD,
  4) pre-seed ConsoleHome\ergo.password.
Public MSIs never embed the PASS (issue #4). Never invent the secret.
"@
    }
    Write-AircSecretFile -Path $ergoDest -Secret $secret
    Write-Host "INFO seeded ergo.password from package ($source) -> $ergoDest"
    return [pscustomobject]@{
        OperatorsFile       = $(if ($opsFile) { $opsFile } else { '' })
        NickServPasswordFile = $NickServPasswordFile
        ErgoPasswordFile    = $ergoDest
    }
}

# Packaged secret lives at <unpack>\config\ergo.password (scripts\.. = unpack root).
$packRoot = Split-Path -Parent $scriptDir
$packagedErgo = Join-Path $packRoot 'config\ergo.password'
# FR #3401 / #3639: every profile is irc_ops (control-channel +o/+h); no operators list.
if (([string]$AuthMode).Trim().ToLowerInvariant() -eq 'operators') {
    Write-Host 'INFO FR #3639 AuthMode=operators is retired; using irc_ops'
}
$AuthMode = 'irc_ops'
$script:AircConsoleAuthMode = $AuthMode
if (@($Operators | Where-Object { $_ -and ([string]$_).Trim() }).Count -gt 0) {
    Write-Host 'INFO FR #3639 ignoring -Operators (no operators list; control-channel +o/+h auth)'
}
$Operators = @()

$secrets = Initialize-AircConsoleHomeSecrets -ConsoleHomeDir $ConsoleHome -OperatorNicks $Operators `
    -NickServPasswordFile $PasswordFile -ErgoSourceFile $ErgoPasswordFile -PackagedErgoFile $packagedErgo
$opsFile = $secrets.OperatorsFile
$PasswordFile = $secrets.NickServPasswordFile
$ergoFile = $secrets.ErgoPasswordFile

function Invoke-AircNssm {
    param(
        [Parameter(Mandatory)][string]$Exe,
        [Parameter(Mandatory)][string[]]$NssmArgs
    )
    # nssm writes status to stderr even on success ("STOP: The service has not been
    # started"). Under $ErrorActionPreference=Stop that becomes NativeCommandError (#273).
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $Exe @NssmArgs 2>&1
        $code = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEa
    }
    return [pscustomobject]@{
        ExitCode = $code
        Output   = @($out | ForEach-Object { "$_" })
    }
}

function Remove-AircConsoleService {
    param(
        [Parameter(Mandatory)][string]$Exe,
        [Parameter(Mandatory)][string]$Name
    )
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "INFO no existing $Name service"
        return
    }
    Write-Host "INFO removing existing $Name (status=$($svc.Status))"
    $null = Invoke-AircNssm -Exe $Exe -NssmArgs @('stop', $Name)
    Start-Sleep -Seconds 2
    # confirm = non-interactive remove
    $rm = Invoke-AircNssm -Exe $Exe -NssmArgs @('remove', $Name, 'confirm')
    Start-Sleep -Seconds 1
    $left = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($left) {
        # Fallback when nssm remove is sticky
        sc.exe delete $Name 2>&1 | Out-Null
        Start-Sleep -Seconds 1
        $left = Get-Service -Name $Name -ErrorAction SilentlyContinue
    }
    if ($left) {
        throw ("failed to remove existing service {0}; nssm exit={1} out={2}" -f $Name, $rm.ExitCode, ($rm.Output -join ' '))
    }
    Write-Host "INFO removed $Name"
}

# Issue #273: always tear down any prior install, then register from this tree.
Remove-AircConsoleService -Exe $Nssm -Name $ServiceName
Write-Host "INFO Installing $ServiceName"

# FR #3639: no --operators-file / -OperatorsFile in AppParameters (prior OperatorsFile is not carried).

# FR #2397: prefer one-file airc.exe (no system Python). Legacy: powershell + Start-AircConsole.ps1.
$aircExe = Join-Path $packRoot 'airc\airc.exe'
$useAircExe = Test-Path -LiteralPath $aircExe
if ($useAircExe) {
    $aircExe = (Resolve-Path -LiteralPath $aircExe).Path
    $inst = Invoke-AircNssm -Exe $Nssm -NssmArgs @('install', $ServiceName, $aircExe)
    if ($inst.ExitCode -ne 0) {
        throw ("nssm install failed: {0} ({1})" -f $inst.ExitCode, ($inst.Output -join ' '))
    }
    $appParams = "--home `"$ConsoleHome`" --password-file `"$PasswordFile`" --sasl"
    if ($MachineId) { $appParams += " --machine `"$MachineId`"" }
    # FR #3639: always irc_ops; never --operators-file.
    $appParams += " --auth-mode $AuthMode"
    # FR #3287: bake capability flags into AppParameters (survive NSSM re-register on upgrade).
    if (-not $ShellMode -and $priorId -and $priorId.PSObject.Properties['ShellMode'] -and $priorId.ShellMode) {
        $ShellMode = [string]$priorId.ShellMode
    }
    if (-not $Jobs -and $priorId -and $priorId.PSObject.Properties['Jobs'] -and $priorId.Jobs) {
        $Jobs = [string]$priorId.Jobs
    }
    if (-not $UpdateCap -and $priorId -and $priorId.PSObject.Properties['UpdateCap'] -and $priorId.UpdateCap) {
        $UpdateCap = [string]$priorId.UpdateCap
    }
    if ($ShellMode -in @('off', 'operators')) { $appParams += " --shell-mode $ShellMode" }
    if ($Jobs -in @('off', 'on')) { $appParams += " --jobs $Jobs" }
    if ($UpdateCap -in @('off', 'on')) { $appParams += " --update $UpdateCap" }
    if ($RequireAccount -or ($priorId -and $priorId.PSObject.Properties['RequireAccount'] -and $priorId.RequireAccount)) {
        $appParams += ' --require-account'
        $RequireAccount = $true
    }
    if ($Accounts.Count -eq 0 -and $priorId -and $priorId.PSObject.Properties['Accounts'] -and $priorId.Accounts) {
        $Accounts = @(([string]$priorId.Accounts) -split '[,;\s]+' | Where-Object { $_ })
    }
    if ($Accounts.Count -gt 0) {
        $appParams += ' --accounts'
        foreach ($a in $Accounts) { $appParams += " $a" }
    }
    Write-Host ("INFO FR #3287 AppParameters capabilities shell={0} jobs={1} update={2} require_account={3} accounts={4}" -f $(if ($ShellMode) { $ShellMode } else { '-' }), $(if ($Jobs) { $Jobs } else { '-' }), $(if ($UpdateCap) { $UpdateCap } else { '-' }), [int][bool]$RequireAccount, $Accounts.Count)
    $appTarget = $aircExe
    $appDirectory = $packRoot
    Write-Host "INFO Airc Application=airc.exe (FR #2397 cutover)"
} else {
    $inst = Invoke-AircNssm -Exe $Nssm -NssmArgs @('install', $ServiceName, 'powershell.exe')
    if ($inst.ExitCode -ne 0) {
        throw ("nssm install failed: {0} ({1})" -f $inst.ExitCode, ($inst.Output -join ' '))
    }
    # Issue #282: bake absolute python.exe into AppParameters (LocalSystem has no PATH).
    $resolvePy = Join-Path $scriptDir 'Resolve-AircConsolePython.ps1'
    if (Test-Path -LiteralPath $resolvePy) { . $resolvePy }
    if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
        if (Get-Command Resolve-AircConsolePythonPath -ErrorAction SilentlyContinue) {
            $Python = Resolve-AircConsolePythonPath -Preferred $Python -HintUserProfile $env:USERPROFILE
        }
    }
    if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
        throw 'python.exe not found for service install. Install Python (all-users) or pass -Python. Issue #282.'
    }
    $Python = (Resolve-Path -LiteralPath $Python).Path
    Write-Host "INFO service python=$Python"
    # Application MUST be powershell.exe (never the .ps1 Path - see NSSM GUI / issue #259).
    $appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`" -ServiceMode -ConsoleHome `"$ConsoleHome`""
    $appParams += " -Python `"$Python`""
    $appParams += " -PasswordFile `"$PasswordFile`""
    if ($MachineId) { $appParams += " -MachineId `"$MachineId`"" }
    # FR #3639: always irc_ops; never -OperatorsFile.
    $appParams += " -AuthMode $AuthMode"
    # FR #3287: legacy Start-AircConsole.ps1 capability params.
    if (-not $ShellMode -and $priorId -and $priorId.PSObject.Properties['ShellMode'] -and $priorId.ShellMode) {
        $ShellMode = [string]$priorId.ShellMode
    }
    if (-not $Jobs -and $priorId -and $priorId.PSObject.Properties['Jobs'] -and $priorId.Jobs) {
        $Jobs = [string]$priorId.Jobs
    }
    if (-not $UpdateCap -and $priorId -and $priorId.PSObject.Properties['UpdateCap'] -and $priorId.UpdateCap) {
        $UpdateCap = [string]$priorId.UpdateCap
    }
    if ($ShellMode -in @('off', 'operators')) { $appParams += " -ShellMode $ShellMode" }
    if ($Jobs -in @('off', 'on')) { $appParams += " -Jobs $Jobs" }
    if ($UpdateCap -in @('off', 'on')) { $appParams += " -UpdateCap $UpdateCap" }
    if ($RequireAccount -or ($priorId -and $priorId.PSObject.Properties['RequireAccount'] -and $priorId.RequireAccount)) {
        $appParams += ' -RequireAccount'
        $RequireAccount = $true
    }
    if ($Accounts.Count -eq 0 -and $priorId -and $priorId.PSObject.Properties['Accounts'] -and $priorId.Accounts) {
        $Accounts = @(([string]$priorId.Accounts) -split '[,;\s]+' | Where-Object { $_ })
    }
    if ($Accounts.Count -gt 0) {
        $appParams += ' -Accounts'
        foreach ($a in $Accounts) { $appParams += " $a" }
    }
    $appTarget = 'powershell.exe'
    $appDirectory = (Split-Path $Launcher -Parent)
    Write-Host 'INFO Airc Application=powershell Start-AircConsole.ps1 (legacy; no airc\airc.exe)'
}

# FR #1546: expand DisplayName/Description (never leave literal #{machine}); log under install tree.
$dnMachine = if ($MachineId) { $MachineId } elseif ($script:AircConsoleMachineId) { $script:AircConsoleMachineId } else { 'machine' }
$displayName = "airc console (#${dnMachine} IRC shell)"
$description = "FR #253: nick console on #${dnMachine}; auth PRIVMSG -> shell; silent in channel."
$setPairs = @(
    @('Application', $appTarget),
    @('AppDirectory', $appDirectory),
    @('AppParameters', $appParams),
    @('DisplayName', $displayName),
    @('Description', $description),
    @('Start', 'SERVICE_AUTO_START'),
    @('AppExit', 'Default', 'Restart'),
    @('AppRestartDelay', '5000'),
    @('AppThrottle', '1500'),
    @('ObjectName', 'LocalSystem')
)
# Fleet id is passed via AppParameters -MachineId (LocalSystem has no user env).
# Do not set AppEnvironmentExtra here - NSSM MULTI_SZ quoting is fragile on WinPS 5.1.
$logDir = Join-Path $packRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'airc-console.log'
$setPairs += @(
    @('AppStdout', $log),
    @('AppStderr', $log),
    @('AppStdoutCreationDisposition', '4'),
    @('AppStderrCreationDisposition', '4'),
    @('AppRotateFiles', '1'),
    @('AppRotateBytes', '1048576')
)
Write-Host "INFO service DisplayName=$displayName"
Write-Host "INFO service log=$log"
foreach ($pair in $setPairs) {
    $argsN = @('set', $ServiceName) + $pair
    $r = Invoke-AircNssm -Exe $Nssm -NssmArgs $argsN
    if ($r.ExitCode -ne 0) {
        throw ("nssm set failed ({0}): {1}" -f ($pair -join ' '), ($r.Output -join ' '))
    }
}

# FR #3288: lock ConsoleHome + secret files to SYSTEM + Administrators (no Users inheritance).
if (Get-Command Protect-BobiverseSecretPath -ErrorAction SilentlyContinue) {
    Protect-BobiverseSecretPath -Path $ConsoleHome -Recurse
    $acctJson = Join-Path $ConsoleHome 'accounts.json'
    foreach ($sec in @($PasswordFile, $ergoFile, $opsFile, $acctJson)) {
        if ($sec -and (Test-Path -LiteralPath $sec)) {
            Protect-BobiverseSecretPath -Path $sec
        }
    }
    $cfgDir = Join-Path $installRootForHome 'config'
    if (Test-Path -LiteralPath $cfgDir) {
        Protect-BobiverseSecretPath -Path $cfgDir -Recurse
    }
} else {
    icacls $ConsoleHome /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /T 2>$null | Out-Null
    foreach ($sec in @($PasswordFile, $ergoFile, $opsFile)) {
        if ($sec -and (Test-Path -LiteralPath $sec)) {
            icacls $sec /inheritance:r /grant:r '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' 2>$null | Out-Null
        }
    }
}
Remove-AircDefaultProfileSecrets

$appGet = Invoke-AircNssm -Exe $Nssm -NssmArgs @('get', $ServiceName, 'Application')
$parGet = Invoke-AircNssm -Exe $Nssm -NssmArgs @('get', $ServiceName, 'AppParameters')
Write-Host ("Application=" + ($appGet.Output -join ' ').Trim())
Write-Host ("AppParameters=" + ($parGet.Output -join ' ').Trim())

if ($NoStart) {
    Write-Host 'INFO Install done; -NoStart set - not starting service.'
} else {
    # #277 unattended end state: service Running.
    Write-Host "INFO starting $ServiceName"
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        Start-Service -Name $ServiceName -ErrorAction Continue
    } finally {
        $ErrorActionPreference = $prevEa
    }
    $deadline = (Get-Date).AddSeconds(45)
    do {
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -eq 'Running') { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if (-not $svc -or $svc.Status -ne 'Running') {
        $logHint = Join-Path $packRoot 'logs\airc-console.log'
        throw ("$ServiceName failed to reach Running (status=$($svc.Status)). Check $logHint")
    }
    Write-Host "INFO $ServiceName Running"
}

Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
Write-Host 'INFO Install complete (unattended #277).'
Write-Host "INFO home=$ConsoleHome auth=control-channel +o/+h (FR #3639) + console.password (NickServ GUID) + ergo.password (from release config\\ergo.password)"
