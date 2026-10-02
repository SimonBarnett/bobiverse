#Requires -Version 5.1
<#
.SYNOPSIS
  Install/update Windows service BobIrcd (Ergo) from the jeeves pack or -ErgoRoot.
.NOTES
  Layout: Ergo root holds ergo.exe, ircd.yaml, nssm.exe (NSSM contract from agentic_build).
  Does not overwrite an existing ircd.yaml (operator TLS/PASS/ChanServ).
#>
[CmdletBinding()]
param(
    [string]$ErgoRoot = 'C:\ai\ergo',
    [string]$ServiceName = 'BobIrcd',
    [string]$PackErgoDir = '',
    [string]$NssmSource = '',
    [switch]$NoStart,
    [switch]$SkipFirewall
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'Bobiverse-Common.ps1')

if (-not (Test-BobiverseIsAdmin)) {
    Request-BobiverseUacRelaunch -Bound $PSBoundParameters
}

New-Item -ItemType Directory -Force -Path $ErgoRoot | Out-Null

# Stage binary + defaults from pack when Ergo root lacks ergo.exe
if (-not $PackErgoDir) {
    $repoRoot = Split-Path -Parent $here
    foreach ($c in @(
            (Join-Path $repoRoot 'ergo'),
            (Join-Path $repoRoot 'third_party\ergo\win64')
        )) {
        if (Test-Path -LiteralPath (Join-Path $c 'ergo.exe')) { $PackErgoDir = $c; break }
    }
}
$exe = Join-Path $ErgoRoot 'ergo.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    if (-not $PackErgoDir -or -not (Test-Path -LiteralPath (Join-Path $PackErgoDir 'ergo.exe'))) {
        throw "missing $exe and no pack ergo payload (expected pack\ergo\ergo.exe)"
    }
    Write-Host "INFO seeding Ergo root from $PackErgoDir"
    Copy-Item -Path (Join-Path $PackErgoDir '*') -Destination $ErgoRoot -Recurse -Force
}

$conf = Join-Path $ErgoRoot 'ircd.yaml'
if (-not (Test-Path -LiteralPath $conf)) {
    $defaultYaml = Join-Path $ErgoRoot 'default.yaml'
    if (Test-Path -LiteralPath $defaultYaml) {
        Copy-Item -LiteralPath $defaultYaml -Destination $conf -Force
        Write-Host "WARN created $conf from default.yaml — edit TLS, server PASS, and enable ChanServ/NickServ registration before production use"
    } else {
        throw "missing $conf (and no default.yaml to seed)"
    }
}

# NSSM must live in Ergo root (Install-BobIrcd contract)
$nssm = Join-Path $ErgoRoot 'nssm.exe'
if (-not (Test-Path -LiteralPath $nssm)) {
    if (-not $NssmSource) {
        $NssmSource = Resolve-BobiverseNssm -ScriptDir $here
    }
    if (-not $NssmSource -or -not (Test-Path -LiteralPath $NssmSource)) {
        throw "missing $nssm — pack third_party\\nssm\\win64\\nssm.exe or pass -NssmSource"
    }
    Copy-Item -LiteralPath $NssmSource -Destination $nssm -Force
    Write-Host "INFO installed nssm.exe into Ergo root"
}

$logDir = Join-Path $ErgoRoot 'logs'
$stdout = Join-Path $logDir 'service.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$oldTask = 'BobIrcd-ionos'
try { Stop-ScheduledTask -TaskName $oldTask -ErrorAction SilentlyContinue } catch { }
Unregister-ScheduledTask -TaskName $oldTask -Confirm:$false -ErrorAction SilentlyContinue

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing -and $existing.Status -eq 'Running') {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$binPath = "`"$nssm`""
$display = 'Bobiverse IRC (Ergo)'
if (-not $existing) {
    & sc.exe create $ServiceName binPath= $binPath start= auto DisplayName= $display obj= LocalSystem
    if ($LASTEXITCODE -ne 0) { throw "sc create $ServiceName failed ($LASTEXITCODE)" }
} else {
    & sc.exe config $ServiceName binPath= $binPath start= auto DisplayName= $display obj= LocalSystem
    if ($LASTEXITCODE -ne 0) { throw "sc config $ServiceName failed ($LASTEXITCODE)" }
}
& sc.exe description $ServiceName 'Private Ergo ircd for #bobiverse (TLS :6697)' | Out-Null
& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/10000 | Out-Null

$paramKey = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
if (-not (Test-Path $paramKey)) {
    New-Item -Path $paramKey -Force | Out-Null
}
New-ItemProperty -Path $paramKey -Name Application -Value $exe -PropertyType ExpandString -Force | Out-Null
New-ItemProperty -Path $paramKey -Name AppParameters -Value 'run --conf ircd.yaml' -PropertyType ExpandString -Force | Out-Null
New-ItemProperty -Path $paramKey -Name AppDirectory -Value $ErgoRoot -PropertyType ExpandString -Force | Out-Null
New-ItemProperty -Path $paramKey -Name AppStdout -Value $stdout -PropertyType ExpandString -Force | Out-Null
New-ItemProperty -Path $paramKey -Name AppStderr -Value $stdout -PropertyType ExpandString -Force | Out-Null

$exitKey = Join-Path $paramKey 'AppExit'
if (-not (Test-Path $exitKey)) {
    New-Item -Path $exitKey -Force | Out-Null
}
Set-ItemProperty -Path $exitKey -Name '(default)' -Value 'Restart'

if (-not $SkipFirewall) {
    if (-not (Get-NetFirewallRule -DisplayName 'Bobiverse IRC TLS 6697' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName 'Bobiverse IRC TLS 6697' -Direction Inbound -Protocol TCP -LocalPort 6697 -Action Allow -Profile Any | Out-Null
        Write-Host 'INFO firewall rule Bobiverse IRC TLS 6697'
    }
}

if (-not $NoStart) {
    Start-Service -Name $ServiceName
    $ok = $false
    foreach ($i in 1..20) {
        Start-Sleep -Seconds 1
        $svc = Get-Service -Name $ServiceName
        $proc = Get-Process ergo -ErrorAction SilentlyContinue
        if ($svc.Status -eq 'Running' -and $proc) { $ok = $true; break }
    }
    if (-not $ok) {
        Write-Host "WARN $ServiceName may need ircd.yaml/TLS fixes (status=$((Get-Service $ServiceName).Status); see $stdout)"
    }
}

Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
Write-Host "INFO Install-BobIrcd done ErgoRoot=$ErgoRoot"
