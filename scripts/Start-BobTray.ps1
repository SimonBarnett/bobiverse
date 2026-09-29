#Requires -Version 5.1
<#
.SYNOPSIS
  Minimal bobiverse NotifyIcon: Restart ircBob (departure announce) + open log.
  Full fleet TipForm tray remains agentic_build Watch-BobTray; this ships in bob MSI.
.NOTES
  If Watch-BobTray is already running, exit (one tray only). Do not use
  SystemIcons.Application — it renders blank on Win11 tray.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\ai\bob',
    [string]$ServiceName = 'ircBob',
    [string]$BobHome = ''
)

$ErrorActionPreference = 'Continue'

# Prefer the full fleet tray when present (DEV1 / agentic_build).
$fleetTray = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'Watch-BobTray\.ps1' }
if ($fleetTray) {
    Write-Host 'INFO Watch-BobTray already running - skip minimal Start-BobTray'
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type -Name Native -Namespace BobiverseTray -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
'@ -ErrorAction SilentlyContinue
$hwnd = [BobiverseTray.Native]::GetConsoleWindow()
if ($hwnd -ne [IntPtr]::Zero) { [void][BobiverseTray.Native]::ShowWindow($hwnd, 0) }

if (-not $BobHome) { $BobHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
$restartPs1 = Join-Path $InstallRoot 'scripts\Restart-BobEar.ps1'
if (-not (Test-Path -LiteralPath $restartPs1)) {
    $restartPs1 = Join-Path $PSScriptRoot 'Restart-BobEar.ps1'
}

function New-BobTrayRobotIcon {
    $sz = 16
    $bmp = New-Object System.Drawing.Bitmap $sz, $sz
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)
    $fg = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(232, 236, 241))
    $eye = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(28, 33, 40))
    $ant = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(232, 236, 241)), 1.2
    $g.DrawLine($ant, 8.0, 1.2, 8.0, 4.0)
    $g.FillEllipse($fg, 7.0, 0.4, 2.0, 2.0)
    $g.FillRectangle($fg, 3.2, 4.2, 9.6, 10.4)
    $g.FillRectangle($fg, 1.6, 7.2, 1.8, 4.4)
    $g.FillRectangle($fg, 12.6, 7.2, 1.8, 4.4)
    $g.FillEllipse($eye, 5.1, 7.0, 2.2, 2.2)
    $g.FillEllipse($eye, 8.7, 7.0, 2.2, 2.2)
    $h = $bmp.GetHicon()
    $icon = [System.Drawing.Icon]::FromHandle($h)
    $clone = $icon.Clone()
    $g.Dispose(); $bmp.Dispose(); $fg.Dispose(); $eye.Dispose(); $ant.Dispose()
    return $clone
}

$notify = New-Object System.Windows.Forms.NotifyIcon
# Keep Text empty — non-empty NotifyIcon.Text becomes a white Win11 tip chip.
$notify.Text = ''
try {
    $notify.Icon = New-BobTrayRobotIcon
} catch {
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $notify.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($psExe)
}
$notify.Visible = $true

function Invoke-RestartEar {
    if (-not (Test-Path -LiteralPath $restartPs1)) {
        [System.Windows.Forms.MessageBox]::Show("Missing Restart-BobEar.ps1", 'bobiverse') | Out-Null
        return
    }
    Start-Process -FilePath 'powershell.exe' -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $restartPs1,
        '-ServiceName', $ServiceName, '-Reason', 'tray-restart'
    ) -WindowStyle Hidden
}

function Open-IrcLog {
    $log = Join-Path $BobHome 'irc.log'
    if (Test-Path -LiteralPath $log) {
        Start-Process -FilePath 'notepad.exe' -ArgumentList $log
    } else {
        [System.Windows.Forms.MessageBox]::Show("No log yet: $log", 'bobiverse') | Out-Null
    }
}

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$miRestart = $menu.Items.Add('Restart ircBob')
$miRestart.add_Click({ Invoke-RestartEar })
$miLog = $menu.Items.Add('Open irc.log')
$miLog.add_Click({ Open-IrcLog })
$miSvc = $menu.Items.Add('Services (ircBob)')
$miSvc.add_Click({ Start-Process 'services.msc' })
[void]$menu.Items.Add('-')
$miExit = $menu.Items.Add('Exit tray')
$miExit.add_Click({
    $notify.Visible = $false
    $notify.Dispose()
    [System.Windows.Forms.Application]::Exit()
})
$notify.ContextMenuStrip = $menu
$notify.add_DoubleClick({ Invoke-RestartEar })

[System.Windows.Forms.Application]::Run()
