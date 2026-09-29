#Requires -Version 5.1
<#
.SYNOPSIS
  Minimal bobiverse NotifyIcon: Restart ircBob (departure announce) + open log.
  Full fleet TipForm tray remains agentic_build Watch-BobTray; this ships in bob MSI.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\ai\bob',
    [string]$ServiceName = 'ircBob',
    [string]$BobHome = ''
)

$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type -Name Native -Namespace BobiverseTray -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
'@
$hwnd = [BobiverseTray.Native]::GetConsoleWindow()
if ($hwnd -ne [IntPtr]::Zero) { [void][BobiverseTray.Native]::ShowWindow($hwnd, 0) }

if (-not $BobHome) { $BobHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
$restartPs1 = Join-Path $InstallRoot 'scripts\Restart-BobEar.ps1'
if (-not (Test-Path -LiteralPath $restartPs1)) {
    $restartPs1 = Join-Path $PSScriptRoot 'Restart-BobEar.ps1'
}

$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Text = 'bobiverse Bob'
$notify.Icon = [System.Drawing.SystemIcons]::Application
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
