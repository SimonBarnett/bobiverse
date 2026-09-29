#Requires -Version 5.1
<#
.SYNOPSIS
  Clean-install ircBob + desktop/Start Menu icons. Nick Bob-{MachineId}.
#>
[CmdletBinding()]
param(
    [string]$Nssm = '',
    [string]$InstallRoot = 'C:\ai\bob',
    [string]$ServiceName = 'ircBob',
    [string]$Python = '',
    [string]$MachineId = '',
    [string]$BobHome = '',
    [switch]$NoStart,
    [switch]$ForceTools,
    [switch]$SkipIcons,
    [switch]$SkipWatchAgentHealth,
    [switch]$SkipTray,
    [switch]$PromptServicePassword,
    [switch]$SkipCopy
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'Bobiverse-Common.ps1')

if (-not (Test-BobiverseIsAdmin)) {
    Request-BobiverseUacRelaunch -Bound $PSBoundParameters
}

$repoRoot = Split-Path -Parent $here
$bootstrap = Join-Path $here 'Install-BootstrapTools.ps1'
if (Test-Path -LiteralPath $bootstrap) {
    if ($ForceTools) { & $bootstrap -ForceTools } else { & $bootstrap }
}

if (-not $MachineId) {
    $MachineId = ($env:BOB_MACHINE_ID | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1)
}
if (-not $MachineId) {
    $MachineId = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
} else {
    $MachineId = ($MachineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
}
if (-not $MachineId) { throw 'MachineId required' }
$nick = "Bob-$MachineId"
Write-Host "INFO MachineId=$MachineId nick=$nick"

$Nssm = Resolve-BobiverseNssm -Preferred $Nssm -ScriptDir $here
if (-not $Nssm) { throw 'nssm missing' }
if (-not $Python) { $Python = Resolve-BobiversePython }
$user = Resolve-BobiverseServiceUser
if (-not $BobHome) {
    if (-not $user -or (Test-BobiverseIsLocalSystem)) {
        $BobHome = Join-Path $InstallRoot 'home'
    } else {
        # Profile of service user when known; else current profile
        $BobHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'
    }
}
New-Item -ItemType Directory -Force -Path $BobHome | Out-Null

# Kill conflicting priors (tray/watch left to operator; stop ear service)
Remove-BobiverseService -Nssm $Nssm -Name $ServiceName
Get-Process -Name 'powershell' -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match 'Watch-BobTray|Watch-Bobiverse'
} | ForEach-Object { Write-Host "INFO leave tray/watch PID=$($_.Id) (restart via shortcuts)" }

New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'scripts'), (Join-Path $InstallRoot 'config') | Out-Null
if (-not $SkipCopy) {
    Copy-BobiverseTree -Source $here -Destination (Join-Path $InstallRoot 'scripts') -ContentsOnly
}
Copy-BobiverseVersion -InstallRoot $InstallRoot -RepoRoot $repoRoot
$skillsSrc = Join-Path $repoRoot '.grok\skills'
if (Test-Path $skillsSrc) {
    $skillsDest = Join-Path $InstallRoot '.grok\skills'
    New-Item -ItemType Directory -Force -Path $skillsDest | Out-Null
    if (-not $SkipCopy) {
        Copy-BobiverseTree -Source $skillsSrc -Destination $skillsDest -ContentsOnly
    }
    Install-BobiverseSkills -RepoSkillsRoot $skillsDest -SkillNames @('bobiverse-bob', 'harvest-agent-skills')
}

Install-BobiversePythonDeps -Python $Python
[void](Import-BobiverseErgoPassword -InstallRoot $InstallRoot -HomeDir $BobHome)

# Quote-safe NSSM: no -Python path in AppParameters (issue #3); Start-Bob resolves python.
$launcher = Join-Path $InstallRoot 'scripts\Start-Bob.ps1'

[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('install', $ServiceName, 'powershell.exe'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Application', 'powershell.exe'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppDirectory', (Join-Path $InstallRoot 'scripts')))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'DisplayName', "bobiverse Bob ear ($MachineId)"))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Start', 'SERVICE_AUTO_START'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppExit', 'Default', 'Restart'))

# Issue #6: msiexec /qn is UserInteractive=$true but has no console - never Get-Credential unless -PromptServicePassword
# and not under MSI/quiet.
$doPrompt = $PromptServicePassword -or (
    -not (Test-BobiverseMsiOrQuiet) -and [Environment]::UserInteractive -and -not (Test-BobiverseIsLocalSystem)
)
$objectOk = Set-BobiverseServiceObjectName -Nssm $Nssm -ServiceName $ServiceName -User $user `
    -InstallRoot $InstallRoot -PromptIfMissing:$doPrompt -AllowLocalSystem

# Issue #7: LocalSystem must not bake the installing user's -BobHome; Start-Bob then picks InstallRoot\home.
$appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -MachineId $MachineId -InstallRoot `"$InstallRoot`""
if ($objectOk) {
    $appParams += " -BobHome `"$BobHome`""
} else {
    Write-Host "INFO LocalSystem ObjectName: omit -BobHome (issue #7; Start-Bob uses $InstallRoot\home)"
}
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppParameters', $appParams))

$envExtra = @(
    "BOB_MACHINE_ID=$MachineId"
)
if ($env:AGENTIC_IRC_PASSWORD) {
    # NSSM AppEnvironmentExtra multi-line: KEY=VAL each line
    $envExtra += "AGENTIC_IRC_PASSWORD=$($env:AGENTIC_IRC_PASSWORD)"
}
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppEnvironmentExtra', ($envExtra -join "`n")))
# Watch-AgentHealth bundle → Desktop (IF MISSING folder, or refresh scripts when pack present)
if (-not $SkipWatchAgentHealth) {
    $wahSrc = Join-Path $InstallRoot 'Watch-AgentHealth'
    if (-not (Test-Path -LiteralPath (Join-Path $wahSrc 'Watch-AgentHealth.ps1'))) {
        $wahSrc = Join-Path $repoRoot 'Watch-AgentHealth'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $wahSrc 'Watch-AgentHealth.ps1'))) {
        $wahSrc = Join-Path $repoRoot 'third_party\Watch-AgentHealth'
    }
    $wahDesk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Watch-AgentHealth'
    if (Test-Path -LiteralPath (Join-Path $wahSrc 'Watch-AgentHealth.ps1')) {
        if (-not (Test-Path -LiteralPath $wahDesk) -or $ForceTools) {
            New-Item -ItemType Directory -Force -Path $wahDesk | Out-Null
            Copy-Item -Path (Join-Path $wahSrc '*') -Destination $wahDesk -Recurse -Force
            Write-Host "INFO Watch-AgentHealth -> $wahDesk"
        } else {
            Write-Host "INFO Watch-AgentHealth already on Desktop (pass -ForceTools to refresh)"
        }
    } else {
        Write-Host 'WARN Watch-AgentHealth not in pack; skip Desktop install'
    }
}

if (-not $SkipIcons) {
    $desk = [Environment]::GetFolderPath('Desktop')
    $start = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Bobiverse'
    $restartPs1 = Join-Path $InstallRoot 'scripts\Restart-BobEar.ps1'
    $trayPs1 = Join-Path $InstallRoot 'scripts\Start-BobTray.ps1'
    New-BobiverseShortcut -LinkPath (Join-Path $desk 'Bob Fleet Restart.lnk') `
        -TargetPath 'powershell.exe' `
        -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$restartPs1`"" `
        -WorkingDirectory (Join-Path $InstallRoot 'scripts') `
        -Description 'Restart ircBob (announces departure)'
    New-BobiverseShortcut -LinkPath (Join-Path $start 'Restart ircBob.lnk') `
        -TargetPath 'powershell.exe' `
        -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$restartPs1`"" `
        -WorkingDirectory (Join-Path $InstallRoot 'scripts') `
        -Description 'Restart ircBob service'
    New-BobiverseShortcut -LinkPath (Join-Path $start 'Bob Services.lnk') `
        -TargetPath 'services.msc' `
        -Description 'Windows Services'
    if ((-not $SkipTray) -and (Test-Path -LiteralPath $trayPs1)) {
        New-BobiverseShortcut -LinkPath (Join-Path $desk 'Bobiverse Tray.lnk') `
            -TargetPath 'powershell.exe' `
            -Arguments "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayPs1`" -InstallRoot `"$InstallRoot`"" `
            -WorkingDirectory (Join-Path $InstallRoot 'scripts') `
            -Description 'bobiverse tray (Restart ircBob)'
        New-BobiverseShortcut -LinkPath (Join-Path $start 'Bobiverse Tray.lnk') `
            -TargetPath 'powershell.exe' `
            -Arguments "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayPs1`" -InstallRoot `"$InstallRoot`"" `
            -WorkingDirectory (Join-Path $InstallRoot 'scripts') `
            -Description 'bobiverse tray (Restart ircBob)'
    }
    $logonPs1 = Join-Path $InstallRoot 'scripts\Complete-BobiverseServiceLogon.ps1'
    if ((-not $objectOk) -and (Test-Path -LiteralPath $logonPs1)) {
        New-BobiverseShortcut -LinkPath (Join-Path $desk 'Complete bobiverse service logon.lnk') `
            -TargetPath 'powershell.exe' `
            -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$logonPs1`" -Product bob -InstallRoot `"$InstallRoot`"" `
            -WorkingDirectory (Join-Path $InstallRoot 'scripts') `
            -Description 'Set ircBob ObjectName password (required once after MSI)'
        New-BobiverseShortcut -LinkPath (Join-Path $start 'Complete bobiverse service logon.lnk') `
            -TargetPath 'powershell.exe' `
            -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$logonPs1`" -Product bob -InstallRoot `"$InstallRoot`"" `
            -WorkingDirectory (Join-Path $InstallRoot 'scripts') `
            -Description 'Set ircBob ObjectName password'
    }
}

if ((-not $SkipTray) -and (-not $NoStart)) {
    $trayPs1 = Join-Path $InstallRoot 'scripts\Start-BobTray.ps1'
    $fleetTray = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'Watch-BobTray\.ps1' }
    if ($fleetTray) {
        Write-Host 'INFO Watch-BobTray already running - skip Start-BobTray (one tray)'
    } elseif (Test-Path -LiteralPath $trayPs1) {
        Start-Process -FilePath 'powershell.exe' -ArgumentList @(
            '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
            '-File', $trayPs1, '-InstallRoot', $InstallRoot
        ) | Out-Null
        Write-Host 'INFO started Start-BobTray'
    }
}

if (-not $NoStart) {
    # Soft-fail start so missing ObjectName password does not 1603 the MSI (issue #6).
    try {
        Start-Service $ServiceName -ErrorAction Stop
        Start-Sleep -Seconds 2
    } catch {
        Write-Host "WARN Start-Service $ServiceName failed: $($_.Exception.Message) - complete service logon then start"
    }
}
Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
Write-Host "INFO Install-Bob done nick=$nick"
