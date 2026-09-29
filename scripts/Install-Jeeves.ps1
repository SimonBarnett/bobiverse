#Requires -Version 5.1
<#
.SYNOPSIS
  Clean-install ircJeeves (+ optional BobIrcd if Ergo present). Nick Jeeves.
#>
[CmdletBinding()]
param(
    [string]$Nssm = '',
    [string]$InstallRoot = 'C:\ai\jeeves',
    [string]$ServiceName = 'ircJeeves',
    [string]$Python = '',
    [string]$ChairHome = '',
    [string]$ErgoRoot = 'C:\ai\ergo',
    [switch]$SkipErgo,
    [switch]$NoStart,
    [switch]$ForceTools,
    [switch]$PromptServicePassword
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

$Nssm = Resolve-BobiverseNssm -Preferred $Nssm -ScriptDir $here
if (-not $Nssm) { throw 'nssm missing — pack third_party\nssm\win64\nssm.exe or pass -Nssm' }
if (-not $Python) { $Python = Resolve-BobiversePython }
if (-not $ChairHome) { $ChairHome = Join-Path $env:USERPROFILE '.agentic-irc-jeeves' }
New-Item -ItemType Directory -Force -Path $ChairHome | Out-Null
$digestHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'
New-Item -ItemType Directory -Force -Path $digestHome | Out-Null

# Clean prior
Remove-BobiverseService -Nssm $Nssm -Name $ServiceName
Get-ScheduledTask -TaskName 'BobJeeves-chair' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

# Lay tree: copy scripts + skills into InstallRoot
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'scripts') | Out-Null
Copy-Item -Path (Join-Path $here '*') -Destination (Join-Path $InstallRoot 'scripts') -Recurse -Force
Copy-BobiverseVersion -InstallRoot $InstallRoot -RepoRoot $repoRoot
$skillsSrc = Join-Path $repoRoot '.grok\skills'
if (Test-Path $skillsSrc) {
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot '.grok\skills') | Out-Null
    Copy-Item -Path (Join-Path $skillsSrc '*') -Destination (Join-Path $InstallRoot '.grok\skills') -Recurse -Force
    Install-BobiverseSkills -RepoSkillsRoot (Join-Path $InstallRoot '.grok\skills') -SkillNames @('bobiverse-jeeves', 'harvest-agent-skills')
}

# Seed operators for !register
$ops = Join-Path $ChairHome 'operators.txt'
if (-not (Test-Path -LiteralPath $ops)) {
    [IO.File]::WriteAllText($ops, "Simon`n", [Text.UTF8Encoding]::new($false))
}

# Ergo payload: pack lays ergo\ under InstallRoot; BobIrcd AppDirectory is ErgoRoot (C:\ai\ergo)
if (-not $SkipErgo) {
    $packErgo = Join-Path $InstallRoot 'ergo'
    if (-not (Test-Path -LiteralPath (Join-Path $packErgo 'ergo.exe'))) {
        $packErgo = Join-Path $repoRoot 'ergo'
    }
    $installBobIrcd = Join-Path $here 'Install-BobIrcd.ps1'
    if (Test-Path -LiteralPath $installBobIrcd) {
        $ircdArgs = @{
            ErgoRoot    = $ErgoRoot
            NssmSource  = $Nssm
            NoStart     = $NoStart
        }
        if (Test-Path -LiteralPath (Join-Path $packErgo 'ergo.exe')) {
            $ircdArgs['PackErgoDir'] = $packErgo
        }
        & $installBobIrcd @ircdArgs
    } else {
        Write-Host 'WARN Install-BobIrcd.ps1 missing'
    }
}

$launcher = Join-Path $InstallRoot 'scripts\Start-Jeeves.ps1'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -ChairHome `"$ChairHome`" -Python `"$Python`""

[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('install', $ServiceName, 'powershell.exe'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Application', 'powershell.exe'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppDirectory', (Join-Path $InstallRoot 'scripts')))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppParameters', $appParams))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'DisplayName', 'bobiverse Jeeves chair'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'Start', 'SERVICE_AUTO_START'))
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppExit', 'Default', 'Restart'))
Set-BobiverseServiceObjectName -Nssm $Nssm -ServiceName $ServiceName -User $user -PromptIfMissing:$PromptServicePassword

$envExtra = "BOB_DIGEST_HOME=$digestHome"
[void](Invoke-BobiverseNssm -Exe $Nssm -NssmArgs @('set', $ServiceName, 'AppEnvironmentExtra', $envExtra))

# Prefer Ergo up before chair when both are installed
if (-not $SkipErgo -and -not $NoStart) {
    $ircd = Get-Service -Name 'BobIrcd' -ErrorAction SilentlyContinue
    if ($ircd -and $ircd.Status -ne 'Running') {
        Start-Service -Name 'BobIrcd' -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

if (-not $NoStart) {
    Start-Service $ServiceName
    Start-Sleep -Seconds 2
}
Get-Service $ServiceName, BobIrcd -ErrorAction SilentlyContinue | Format-Table Name, Status, StartType -AutoSize
Write-Host 'INFO Install-Jeeves done'
