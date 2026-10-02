#Requires -Version 5.1
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
    # Simon + bob-{COMPUTERNAME} seeded; runtime also allows any bob-* fleet nick (#302).
    [string[]]$Operators = @('Simon'),
    [string]$ServiceName = 'AircConsole',
    # Absolute python.exe for LocalSystem (#282). Empty = auto-resolve at install.
    [string]$Python = '',
    # Fleet shop id (ionos/flamingo/…). Empty = BOB_MACHINE_ID / AIRC_CONSOLE_MACHINE.
    # Required on boxes where COMPUTERNAME is not the fleet id (e.g. WIN-…).
    [string]$MachineId = '',
    # #277: default starts the service so Running is the unattended end state.
    [switch]$NoStart
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

# Resolve fleet machine id early (operators seed + NSSM env + Start -MachineId).
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
    Write-Warning ("Install without -MachineId / BOB_MACHINE_ID uses COMPUTERNAME={0}; console may join #win-… instead of #ionos." -f $env:COMPUTERNAME)
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

# LocalSystem / quiet MSI: never bake C:\Users\Default\.airc* (NickServ GUID orphan).
if (-not $ConsoleHome) {
    $adminHome = Join-Path $env:SystemDrive 'Users\Administrator\.airc'
    $isSystem = $false
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $isSystem = ($id.User.Value -eq 'S-1-5-18') -or ($id.Name -match 'SYSTEM$')
    } catch { }
    if ($isSystem) {
        if (Test-Path -LiteralPath $adminHome) {
            $ConsoleHome = $adminHome
            Write-Host "INFO LocalSystem using existing Admin ConsoleHome=$ConsoleHome"
        } else {
            $installGuess = Split-Path -Parent (Split-Path -Parent $Launcher)
            if (-not $installGuess) { $installGuess = if (Get-Command Get-BobiverseAiRoot -ErrorAction SilentlyContinue) { Join-Path (Get-BobiverseAiRoot) 'airc' } else { throw 'cannot derive the airc install dir (dot-source Bobiverse-Common.ps1 or pass -ConsoleHome)' } }
            $ConsoleHome = Join-Path $installGuess 'home'
            Write-Host "INFO LocalSystem ConsoleHome=$ConsoleHome (avoid Default profile)"
        }
    } else {
        $ConsoleHome = Join-Path $env:USERPROFILE '.airc-console'
    }
}
New-Item -ItemType Directory -Force -Path $ConsoleHome | Out-Null

function Write-AircSecretFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Secret
    )
    $text = ($Secret -replace '[\r\n]+$', '').Trim()
    if (-not $text) { throw "refusing empty secret for $Path" }
    # ASCII one-line; no BOM — same shape as connect.password / NickServ GUID.
    [IO.File]::WriteAllText($Path, $text + "`n", [Text.UTF8Encoding]::new($false))
    icacls $Path /grant 'SYSTEM:(R)' 2>$null | Out-Null
    if ($env:USERNAME) {
        icacls $Path /grant ("{0}:(R)" -f $env:USERNAME) 2>$null | Out-Null
    }
}

function Initialize-AircConsoleHomeSecrets {
    param(
        # Never name this $Home — PowerShell automatic $Home is read-only (FR #259).
        [Parameter(Mandatory)][string]$ConsoleHomeDir,
        [string[]]$OperatorNicks,
        [string]$NickServPasswordFile = '',
        [string]$ErgoSourceFile = '',
        # Issue #294: packaged release config\ergo.password (not target ~/.grok).
        [string]$PackagedErgoFile = ''
    )
    $opsFile = Join-Path $ConsoleHomeDir 'operators.txt'
    # Issue #289: never UTF-8 BOM. Issue #302: always include bob-{machinename}.
    # Prefer fleet id (BOB_MACHINE_ID) over Windows COMPUTERNAME.
    $machineId = ($script:AircConsoleMachineId)
    if (-not $machineId) {
        $machineId = ($env:AIRC_CONSOLE_MACHINE, $env:BOB_MACHINE_ID | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1)
    }
    if (-not $machineId) {
        $machineId = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
    }
    if (-not $machineId) { $machineId = 'unknown' }
    $machineId = ($machineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
    $bobNick = "bob-$machineId"
    $seedOps = [System.Collections.Generic.List[string]]::new()
    foreach ($o in @($OperatorNicks)) {
        if ($o -and $o.Trim()) { [void]$seedOps.Add($o.Trim()) }
    }
    if (-not ($seedOps | Where-Object { $_.ToLowerInvariant() -eq $bobNick })) {
        [void]$seedOps.Add($bobNick)
    }
    if ($seedOps.Count -gt 0 -and -not (Test-Path -LiteralPath $opsFile)) {
        $body = ($seedOps -join "`n") + "`n"
        [IO.File]::WriteAllText($opsFile, $body, [Text.UTF8Encoding]::new($false))
        Write-Host "INFO wrote $opsFile (no BOM; includes $bobNick)"
    } elseif (Test-Path -LiteralPath $opsFile) {
        $raw = [IO.File]::ReadAllText($opsFile)
        $clean = $raw.TrimStart([char]0xFEFF)
        $lines = @($clean -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -notmatch '^#' })
        $changed = ($clean -ne $raw)
        if (-not ($lines | Where-Object { $_.ToLowerInvariant() -eq $bobNick })) {
            $lines = @($lines + $bobNick)
            $changed = $true
        }
        if ($changed) {
            $body = (($lines | Select-Object -Unique) -join "`n") + "`n"
            [IO.File]::WriteAllText($opsFile, $body, [Text.UTF8Encoding]::new($false))
            Write-Host "INFO updated $opsFile (BOM strip / ensure $bobNick) (#289/#302)"
        } else {
            Write-Host "INFO keep $opsFile"
        }
    } else {
        throw 'operators.txt missing and -Operators empty (FR #253)'
    }

    # #271 NickServ GUID — mint here so first service start is unattended.
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

    # #294: Ergo server PASS comes from the *release zip* (config\ergo.password),
    # not from the target machine's ~/.grok (most clients have none).
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
    if (-not $secret) {
        throw "Ergo server PASS missing in release: expected config\ergo.password beside the unpack tree (issue #294). Re-download airc-console zip packed with the fleet secret."
    }
    Write-AircSecretFile -Path $ergoDest -Secret $secret
    Write-Host "INFO seeded ergo.password from package ($source) -> $ergoDest"
    return [pscustomobject]@{
        OperatorsFile       = $opsFile
        NickServPasswordFile = $NickServPasswordFile
        ErgoPasswordFile    = $ergoDest
    }
}

# Packaged secret lives at <unpack>\config\ergo.password (scripts\.. = unpack root).
$packRoot = Split-Path -Parent $scriptDir
$packagedErgo = Join-Path $packRoot 'config\ergo.password'
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

# Application MUST be powershell.exe (never the .ps1 Path — see NSSM GUI / issue #259).
$appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`" -ServiceMode -ConsoleHome `"$ConsoleHome`""
$appParams += " -Python `"$Python`""
$appParams += " -PasswordFile `"$PasswordFile`""
if ($MachineId) { $appParams += " -MachineId `"$MachineId`"" }
if (Test-Path -LiteralPath $opsFile) { $appParams += " -OperatorsFile `"$opsFile`"" }

$setPairs = @(
    @('Application', 'powershell.exe'),
    @('AppDirectory', (Split-Path $Launcher -Parent)),
    @('AppParameters', $appParams),
    @('DisplayName', 'airc console (#{machine} IRC shell)'),
    @('Description', 'FR #253: nick console on #{machinename}; auth PRIVMSG -> shell; silent in channel.'),
    @('Start', 'SERVICE_AUTO_START'),
    @('AppExit', 'Default', 'Restart'),
    @('AppRestartDelay', '5000'),
    @('AppThrottle', '1500'),
    @('ObjectName', 'LocalSystem')
)
# Fleet id is passed via AppParameters -MachineId (LocalSystem has no user env).
# Do not set AppEnvironmentExtra here — NSSM MULTI_SZ quoting is fragile on WinPS 5.1.
$logDir = Join-Path $env:USERPROFILE '.grok\long-running-background-tasks'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'airc-console-service.log'
$setPairs += @(
    @('AppStdout', $log),
    @('AppStderr', $log),
    @('AppStdoutCreationDisposition', '4'),
    @('AppStderrCreationDisposition', '4'),
    @('AppRotateFiles', '1'),
    @('AppRotateBytes', '1048576')
)
foreach ($pair in $setPairs) {
    $argsN = @('set', $ServiceName) + $pair
    $r = Invoke-AircNssm -Exe $Nssm -NssmArgs $argsN
    if ($r.ExitCode -ne 0) {
        throw ("nssm set failed ({0}): {1}" -f ($pair -join ' '), ($r.Output -join ' '))
    }
}

icacls $ConsoleHome /grant 'SYSTEM:(OI)(CI)(M)' /T 2>$null | Out-Null
foreach ($sec in @($PasswordFile, $ergoFile, $opsFile)) {
    if ($sec -and (Test-Path -LiteralPath $sec)) {
        icacls $sec /grant 'SYSTEM:(R)' 2>$null | Out-Null
    }
}

$appGet = Invoke-AircNssm -Exe $Nssm -NssmArgs @('get', $ServiceName, 'Application')
$parGet = Invoke-AircNssm -Exe $Nssm -NssmArgs @('get', $ServiceName, 'AppParameters')
Write-Host ("Application=" + ($appGet.Output -join ' ').Trim())
Write-Host ("AppParameters=" + ($parGet.Output -join ' ').Trim())

if ($NoStart) {
    Write-Host 'INFO Install done; -NoStart set — not starting service.'
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
        $logHint = Join-Path $env:USERPROFILE '.grok\long-running-background-tasks\airc-console-service.log'
        throw ("$ServiceName failed to reach Running (status=$($svc.Status)). Check $logHint")
    }
    Write-Host "INFO $ServiceName Running"
}

Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
Write-Host 'INFO Install complete (unattended #277).'
Write-Host "INFO home=$ConsoleHome operators + console.password (NickServ GUID) + ergo.password (from release config\\ergo.password)"
