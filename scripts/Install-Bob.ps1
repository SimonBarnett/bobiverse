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
# #32: start the tray WITHOUT Stop-BobSystrayPriorAgents (which kills grok.exe seats, Grok Bot,
# Watch-AgentHealth). Implied under msiexec/quiet installs; or set env BOBIVERSE_NO_TIDY=1.
[switch]$SkipTidy,
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
        $BobHome = Join-Path $env:USERPROFILE '.bobiverse'
    }
}
New-Item -ItemType Directory -Force -Path $BobHome | Out-Null

# Stop ear service; TipForm tray is restarted after icons (companion, not BobFleet task)
Remove-BobiverseService -Nssm $Nssm -Name $ServiceName

New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'scripts'), (Join-Path $InstallRoot 'config') | Out-Null
if (-not $SkipCopy) {
    Copy-BobiverseTree -Source $here -Destination (Join-Path $InstallRoot 'scripts') -ContentsOnly
}
Copy-BobiverseVersion -InstallRoot $InstallRoot -RepoRoot $repoRoot

# TipForm tray payload (tools/src/assets/PIN) when installing from repo (MSI heat already staged)
$trayVendor = Join-Path $repoRoot 'third_party\bob-tray'
if (-not (Test-Path -LiteralPath (Join-Path $trayVendor 'tools\Watch-BobTray.ps1'))) {
    $trayVendor = $null
}
if ($trayVendor) {
    if (-not $SkipCopy -and -not (Test-BobiverseSamePath $trayVendor $InstallRoot)) {
        foreach ($sub in @('tools', 'assets')) {
            $from = Join-Path $trayVendor $sub
            if (Test-Path -LiteralPath $from) {
                $to = Join-Path $InstallRoot $sub
                New-Item -ItemType Directory -Force -Path $to | Out-Null
                Copy-BobiverseTree -Source $from -Destination $to -ContentsOnly
            }
        }
        $traySrcMod = Join-Path $trayVendor 'src'
        if (Test-Path -LiteralPath (Join-Path $traySrcMod 'BobBridge.psd1')) {
            $srcDest = Join-Path $InstallRoot 'src'
            New-Item -ItemType Directory -Force -Path $srcDest | Out-Null
            Copy-Item -LiteralPath (Join-Path $traySrcMod 'BobBridge.psd1') -Destination (Join-Path $srcDest 'BobBridge.psd1') -Force
            Copy-Item -LiteralPath (Join-Path $traySrcMod 'BobBridge.psm1') -Destination (Join-Path $srcDest 'BobBridge.psm1') -Force
            foreach ($sub in @('Public', 'Private')) {
                $from = Join-Path $traySrcMod $sub
                if (Test-Path -LiteralPath $from) {
                    $to = Join-Path $srcDest $sub
                    New-Item -ItemType Directory -Force -Path $to | Out-Null
                    Copy-BobiverseTree -Source $from -Destination $to -ContentsOnly
                }
            }
        }
        foreach ($leaf in @('PIN.txt')) {
            $from = Join-Path $trayVendor $leaf
            if (Test-Path -LiteralPath $from) {
                Copy-Item -LiteralPath $from -Destination (Join-Path $InstallRoot $leaf) -Force
            }
        }
        foreach ($cfg in @('bobiverse.json', 'bob-seats.json', 'default.json', 'fleet-registry.json')) {
            $from = Join-Path $trayVendor "config\$cfg"
            if (Test-Path -LiteralPath $from) {
                Copy-Item -LiteralPath $from -Destination (Join-Path $InstallRoot "config\$cfg") -Force
            }
        }
        Write-Host "INFO TipForm tray -> $InstallRoot (tools/src/assets)"
    }
} elseif (-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'tools\Watch-BobTray.ps1'))) {
    Write-Host 'WARN TipForm Watch-BobTray missing under InstallRoot (pack/sync bob-tray)'
}
$skillsSrc = Join-Path $repoRoot '.grok\skills'
if (Test-Path $skillsSrc) {
    $skillsDest = Join-Path $InstallRoot '.grok\skills'
    New-Item -ItemType Directory -Force -Path $skillsDest | Out-Null
    if (-not $SkipCopy) {
        Copy-BobiverseTree -Source $skillsSrc -Destination $skillsDest -ContentsOnly
    }
    Install-BobiverseSkills -RepoSkillsRoot $skillsDest -SkillNames @('bobiverse-bob', 'harvest', 'harvest-agent-skills')
}

Install-BobiversePythonDeps -Python $Python
[void](Import-BobiverseErgoPassword -InstallRoot $InstallRoot -HomeDir $BobHome)

# Quote-safe NSSM: no -Python path in AppParameters (issue #3); Start-Bob resolves python.
$launcher = Join-Path $InstallRoot 'scripts\Start-Bob.ps1'

[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('install', $ServiceName, 'powershell.exe'))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Application', 'powershell.exe'))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppDirectory', (Join-Path $InstallRoot 'scripts')))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'DisplayName', "bobiverse Bob ear ($MachineId)"))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Start', 'SERVICE_AUTO_START'))
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppExit', 'Default', 'Restart'))

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
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppParameters', $appParams))

$envExtra = @(
    "BOB_MACHINE_ID=$MachineId"
)
if ($env:BOB_IRC_PASSWORD) {
    # NSSM AppEnvironmentExtra multi-line: KEY=VAL each line
    $envExtra += "BOB_IRC_PASSWORD=$($env:BOB_IRC_PASSWORD)"
}
[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppEnvironmentExtra', ($envExtra -join "`n")))
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
    $trayIco = Join-Path $InstallRoot 'assets\bob-systray.ico'
    if (-not (Test-Path -LiteralPath $trayIco)) { $trayIco = '' }
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
        $trayArgs = "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayPs1`" -InstallRoot `"$InstallRoot`" -MachineId $MachineId -ForceNew"
        $trayDesc = 'bob TipForm systray (companion to ircBob; Restart recycles ircBob + Sync/ff)'
        New-BobiverseShortcut -LinkPath (Join-Path $desk 'Bobiverse Tray.lnk') `
            -TargetPath 'powershell.exe' `
            -Arguments $trayArgs `
            -WorkingDirectory $InstallRoot `
            -Description $trayDesc `
            -IconLocation $(if ($trayIco) { "$trayIco,0" } else { '' })
        New-BobiverseShortcut -LinkPath (Join-Path $start 'Bobiverse Tray.lnk') `
            -TargetPath 'powershell.exe' `
            -Arguments $trayArgs `
            -WorkingDirectory $InstallRoot `
            -Description $trayDesc `
            -IconLocation $(if ($trayIco) { "$trayIco,0" } else { '' })
        # Per-user Startup (interactive logon companion) — never BobFleet-* scheduled tasks
        $startup = [Environment]::GetFolderPath('Startup')
        if ($startup) {
            New-BobiverseShortcut -LinkPath (Join-Path $startup 'Bobiverse Tray.lnk') `
                -TargetPath 'powershell.exe' `
                -Arguments $trayArgs `
                -WorkingDirectory $InstallRoot `
                -Description $trayDesc `
                -IconLocation $(if ($trayIco) { "$trayIco,0" } else { '' })
        }
        try {
            $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
            if (-not (Test-Path -LiteralPath $runKey)) {
                New-Item -Path $runKey -Force | Out-Null
            }
            $runVal = "powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayPs1`" -InstallRoot `"$InstallRoot`" -MachineId $MachineId"
            Set-ItemProperty -LiteralPath $runKey -Name 'BobiverseTray' -Value $runVal -Type String -Force
            Write-Host 'INFO HKCU Run BobiverseTray registered'
        } catch {
            Write-Host ("WARN HKCU Run BobiverseTray failed: {0}" -f $_.Exception.Message)
        }
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

# Never register BobFleet-* scheduled tasks from bob MSI install (companion uses Startup/HKCU only)
try {
    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -like 'BobFleet-*' } |
        ForEach-Object {
            Write-Host ("INFO leaving existing scheduled task {0} untouched (MSI tray is Startup/HKCU companion, not BobFleet)" -f $_.TaskName)
        }
} catch { }

if ((-not $SkipTray) -and (-not $NoStart)) {
    $noTidy = $SkipTidy.IsPresent -or ([string]$env:BOBIVERSE_NO_TIDY).Trim() -eq '1' -or (Test-BobiverseMsiOrQuiet)
    if ($noTidy) { Write-Host 'INFO tray start with SkipTidy: running seats and Grok Bot are not killed (#32)' }
    $trayPs1 = Join-Path $InstallRoot 'scripts\Start-BobTray.ps1'
    $watchPs1 = Join-Path $InstallRoot 'tools\Watch-BobTray.ps1'
    $trayInteractive = Join-Path $InstallRoot 'scripts\Start-BobTrayInteractive.ps1'
    if (-not (Test-Path -LiteralPath $watchPs1)) {
        Write-Host 'WARN TipForm Watch-BobTray.ps1 missing - skip tray start'
    } elseif (-not [Environment]::UserInteractive -or ([Security.Principal.WindowsIdentity]::GetCurrent().Name -match 'SYSTEM')) {
        # Session 0 / quiet MSI: never Start-Process TipForm here (invisible ghosts).
        # Register ONLOGON /IT task + try RunNow into active RDP/console session.
        Write-Host 'INFO non-interactive/session0 - register interactive TipForm logon task (no session-0 Start-Process)'
        if (Test-Path -LiteralPath $trayInteractive) {
            try {
                & $trayInteractive -InstallRoot $InstallRoot -MachineId $MachineId -RunNow -SkipTidy:$noTidy
            } catch {
                Write-Host ("WARN Start-BobTrayInteractive: {0}" -f $_.Exception.Message)
            }
        }
        # Also seed Administrator Startup/HKCU when installing as SYSTEM
        $adminStartup = 'C:\Users\Administrator\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup'
        $adminDesk = 'C:\Users\Administrator\Desktop'
        if ((Test-Path 'C:\Users\Administrator') -and (Test-Path -LiteralPath $trayPs1)) {
            $trayArgs = "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayPs1`" -InstallRoot `"$InstallRoot`" -MachineId $MachineId -ForceNew"
            $trayDesc = 'bob TipForm systray (companion to ircBob; Restart recycles ircBob + Sync/ff)'
            $trayIco = Join-Path $InstallRoot 'assets\bob-systray.ico'
            if (-not (Test-Path -LiteralPath $trayIco)) { $trayIco = '' }
            if (Test-Path -LiteralPath $adminStartup) {
                New-BobiverseShortcut -LinkPath (Join-Path $adminStartup 'Bobiverse Tray.lnk') `
                    -TargetPath 'powershell.exe' -Arguments $trayArgs -WorkingDirectory $InstallRoot `
                    -Description $trayDesc -IconLocation $(if ($trayIco) { "$trayIco,0" } else { '' })
            }
            if (Test-Path -LiteralPath $adminDesk) {
                New-BobiverseShortcut -LinkPath (Join-Path $adminDesk 'Bobiverse Tray.lnk') `
                    -TargetPath 'powershell.exe' -Arguments $trayArgs -WorkingDirectory $InstallRoot `
                    -Description $trayDesc -IconLocation $(if ($trayIco) { "$trayIco,0" } else { '' })
            }
            try {
                $adminHive = 'Registry::HKEY_USERS'
                # Best-effort: load Admin NTUSER if we can resolve SID; else skip
                $adminSid = (New-Object System.Security.Principal.NTAccount('Administrator')).Translate([System.Security.Principal.SecurityIdentifier]).Value
                $runPath = "Registry::HKEY_USERS\$adminSid\Software\Microsoft\Windows\CurrentVersion\Run"
                if (-not (Test-Path -LiteralPath $runPath)) {
                    $ntuser = 'C:\Users\Administrator\NTUSER.DAT'
                    if (Test-Path -LiteralPath $ntuser) {
                        reg load "HKU\$adminSid" $ntuser | Out-Null
                    }
                }
                if (Test-Path -LiteralPath $runPath) {
                    $runVal = "powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayPs1`" -InstallRoot `"$InstallRoot`" -MachineId $MachineId"
                    New-Item -Path $runPath -Force -ErrorAction SilentlyContinue | Out-Null
                    Set-ItemProperty -LiteralPath $runPath -Name 'BobiverseTray' -Value $runVal -Type String -Force
                    Write-Host 'INFO Administrator HKU Run BobiverseTray registered'
                }
            } catch {
                Write-Host ("WARN Admin HKU Run BobiverseTray: {0}" -f $_.Exception.Message)
            }
        }
    } elseif (Test-Path -LiteralPath $trayPs1) {
        # Interactive install: kill prior tray then start TipForm in this session
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match 'Start-BobTray\.ps1' -or
                $_.CommandLine -match 'Watch-BobTray\.ps1' -or
                $_.CommandLine -match '_Watch-BobTray-'
            )
        } | ForEach-Object {
            try {
                Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue
                Write-Host ("INFO stopped prior tray pid={0}" -f $_.ProcessId)
            } catch { }
        }
        Start-Sleep -Milliseconds 500
        $trayLaunch = @(
            '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
            '-File', $trayPs1, '-InstallRoot', $InstallRoot, '-MachineId', $MachineId, '-ForceNew'
        )
        if ($noTidy) { $trayLaunch += '-SkipTidy' }
        Start-Process -FilePath 'powershell.exe' -ArgumentList $trayLaunch | Out-Null
        Write-Host 'INFO started TipForm Start-BobTray (ircBob companion)'
        if (Test-Path -LiteralPath $trayInteractive) {
            try { & $trayInteractive -InstallRoot $InstallRoot -MachineId $MachineId -RegisterOnly } catch { }
        }
    }
}

if (-not $NoStart) {
    # Soft-fail start so missing ObjectName password does not 1603 the MSI (issue #6).
    try {
        Start-Service $ServiceName -ErrorAction Stop
        Start-Sleep -Seconds 2
    } catch {
        Write-Host "WARN Start-Service $ServiceName failed: $($_.Exception.Message) - complete service logon then start"
        $report = Join-Path $here 'Report-BobiverseIntakeIssue.ps1'
        if (Test-Path -LiteralPath $report) {
            try {
                & $report -Title "bob install: Start-Service $ServiceName failed" -Body $_.Exception.Message -InstallRoot $InstallRoot
            } catch {}
        }
    }
}
Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
Write-Host "INFO Install-Bob done nick=$nick"
