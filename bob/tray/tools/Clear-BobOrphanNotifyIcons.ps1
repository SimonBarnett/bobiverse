#Requires -Version 5.1
# Clear ghost NotifyIcons left when a tray process dies without Dispose.
# Posts WM_MOUSEMOVE over the notification toolbars so Explorer drops dead icons.
# Does not restart explorer.exe. ASCII-only for Windows PowerShell 5.1.
[CmdletBinding()]
param(
    [switch]$WhatIf
)

$ErrorActionPreference = 'Continue'

if (-not ('BobTrayIconSweep.Api' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace BobTrayIconSweep {
  public static class Api {
    public const uint WM_MOUSEMOVE = 0x0200;
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);
    [DllImport("user32.dll")]
    public static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    public static IntPtr MakeLParam(int lo, int hi) {
      return (IntPtr)((hi << 16) | (lo & 0xFFFF));
    }
  }
}
'@
}

function Invoke-BobTrayToolbarSweep {
    param([IntPtr]$Hwnd)
    if ($Hwnd -eq [IntPtr]::Zero) { return 0 }
    $rect = New-Object BobTrayIconSweep.Api+RECT
    if (-not [BobTrayIconSweep.Api]::GetClientRect($Hwnd, [ref]$rect)) { return 0 }
    $w = $rect.Right - $rect.Left
    $h = $rect.Bottom - $rect.Top
    if ($w -le 0 -or $h -le 0) { return 0 }
    $n = 0
    for ($y = $h - 8; $y -ge 0; $y -= 8) {
        for ($x = $w - 8; $x -ge 0; $x -= 8) {
            if (-not $WhatIf) {
                [void][BobTrayIconSweep.Api]::PostMessage(
                    $Hwnd,
                    [BobTrayIconSweep.Api]::WM_MOUSEMOVE,
                    [IntPtr]::Zero,
                    [BobTrayIconSweep.Api]::MakeLParam($x, $y)
                )
            }
            $n++
        }
    }
    return $n
}

function Get-BobNotificationToolbars {
    $list = New-Object System.Collections.Generic.List[IntPtr]
    $tray = [BobTrayIconSweep.Api]::FindWindow('Shell_TrayWnd', $null)
    if ($tray -ne [IntPtr]::Zero) {
        $notify = [BobTrayIconSweep.Api]::FindWindowEx($tray, [IntPtr]::Zero, 'TrayNotifyWnd', $null)
        if ($notify -ne [IntPtr]::Zero) {
            $pager = [BobTrayIconSweep.Api]::FindWindowEx($notify, [IntPtr]::Zero, 'SysPager', $null)
            if ($pager -eq [IntPtr]::Zero) { $pager = $notify }
            $tb = [BobTrayIconSweep.Api]::FindWindowEx($pager, [IntPtr]::Zero, 'ToolbarWindow32', $null)
            $guard = 0
            while ($tb -ne [IntPtr]::Zero -and $guard -lt 8) {
                $list.Add($tb)
                $tb = [BobTrayIconSweep.Api]::FindWindowEx($pager, $tb, 'ToolbarWindow32', $null)
                $guard++
            }
        }
    }
    $overflow = [BobTrayIconSweep.Api]::FindWindow('NotifyIconOverflowWindow', $null)
    if ($overflow -ne [IntPtr]::Zero) {
        $tb2 = [BobTrayIconSweep.Api]::FindWindowEx($overflow, [IntPtr]::Zero, 'ToolbarWindow32', $null)
        $guard = 0
        while ($tb2 -ne [IntPtr]::Zero -and $guard -lt 8) {
            $list.Add($tb2)
            $tb2 = [BobTrayIconSweep.Api]::FindWindowEx($overflow, $tb2, 'ToolbarWindow32', $null)
            $guard++
        }
    }
    return @($list)
}

$posts = 0
$bars = @(Get-BobNotificationToolbars)
foreach ($hwnd in $bars) {
    $posts += [int](Invoke-BobTrayToolbarSweep -Hwnd $hwnd)
}

[pscustomobject]@{
    ok         = $true
    toolbars   = $bars.Count
    mousePosts = $posts
    whatIf     = [bool]$WhatIf
} | ConvertTo-Json -Compress
exit 0
