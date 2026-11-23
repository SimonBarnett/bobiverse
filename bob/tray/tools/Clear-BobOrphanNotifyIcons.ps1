#Requires -Version 5.1
# Clear ghost NotifyIcons left when a tray process dies without Dispose.
# Posts WM_MOUSEMOVE over the notification toolbars so Explorer drops dead icons.
# FR #9169: when toolbars=0 (common on Win11) the sweep is a no-op; -HealLadder /
# -RecycleExplorer recycles explorer.exe in the current interactive session and
# re-sweeps. Never recycle from session 0. ASCII-only for Windows PowerShell 5.1.
[CmdletBinding()]
param(
    [switch]$WhatIf,
    # Force explorer recycle after the first sweep (ops / ForceNew tidy).
    [switch]$RecycleExplorer,
    # Recycle explorer only when the first sweep finds zero toolbars (FR #9169).
    [switch]$HealLadder
)

$ErrorActionPreference = 'Continue'

if (-not ('BobTrayIconSweep.Api' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
namespace BobTrayIconSweep {
  public static class Api {
    public const uint WM_MOUSEMOVE = 0x0200;
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);
    [DllImport("user32.dll")]
    public static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder lpClassName, int nMaxCount);
    [DllImport("user32.dll")]
    public static extern bool EnumChildWindows(IntPtr hWndParent, EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    public static IntPtr MakeLParam(int lo, int hi) {
      return (IntPtr)((hi << 16) | (lo & 0xFFFF));
    }
    public static List<IntPtr> CollectToolbarChildren(IntPtr root) {
      var list = new List<IntPtr>();
      if (root == IntPtr.Zero) return list;
      EnumChildWindows(root, (h, lp) => {
        var sb = new System.Text.StringBuilder(256);
        GetClassName(h, sb, sb.Capacity);
        string cls = sb.ToString();
        if (cls == "ToolbarWindow32" || cls == "DirectUIHWND") {
          list.Add(h);
        }
        return true;
      }, IntPtr.Zero);
      return list;
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
    $seen = New-Object 'System.Collections.Generic.HashSet[Int64]'
    $candidates = New-Object System.Collections.Generic.List[IntPtr]
    $tray = [BobTrayIconSweep.Api]::FindWindow('Shell_TrayWnd', $null)
    if ($tray -ne [IntPtr]::Zero) {
        $notify = [BobTrayIconSweep.Api]::FindWindowEx($tray, [IntPtr]::Zero, 'TrayNotifyWnd', $null)
        if ($notify -ne [IntPtr]::Zero) {
            $pager = [BobTrayIconSweep.Api]::FindWindowEx($notify, [IntPtr]::Zero, 'SysPager', $null)
            if ($pager -eq [IntPtr]::Zero) { $pager = $notify }
            $tb = [BobTrayIconSweep.Api]::FindWindowEx($pager, [IntPtr]::Zero, 'ToolbarWindow32', $null)
            $guard = 0
            while ($tb -ne [IntPtr]::Zero -and $guard -lt 8) {
                [void]$candidates.Add($tb)
                $tb = [BobTrayIconSweep.Api]::FindWindowEx($pager, $tb, 'ToolbarWindow32', $null)
                $guard++
            }
            # FR #9169: Win11 often nests NotifyIcon chrome under DirectUIHWND; enum children.
            foreach ($child in [BobTrayIconSweep.Api]::CollectToolbarChildren($notify)) {
                [void]$candidates.Add($child)
            }
            foreach ($child in [BobTrayIconSweep.Api]::CollectToolbarChildren($tray)) {
                [void]$candidates.Add($child)
            }
        }
    }
    $overflow = [BobTrayIconSweep.Api]::FindWindow('NotifyIconOverflowWindow', $null)
    if ($overflow -ne [IntPtr]::Zero) {
        $tb2 = [BobTrayIconSweep.Api]::FindWindowEx($overflow, [IntPtr]::Zero, 'ToolbarWindow32', $null)
        $guard = 0
        while ($tb2 -ne [IntPtr]::Zero -and $guard -lt 8) {
            [void]$candidates.Add($tb2)
            $tb2 = [BobTrayIconSweep.Api]::FindWindowEx($overflow, $tb2, 'ToolbarWindow32', $null)
            $guard++
        }
        foreach ($child in [BobTrayIconSweep.Api]::CollectToolbarChildren($overflow)) {
            [void]$candidates.Add($child)
        }
    }
    foreach ($hwnd in $candidates) {
        if ($hwnd -eq [IntPtr]::Zero) { continue }
        $key = $hwnd.ToInt64()
        if ($seen.Add($key)) { [void]$list.Add($hwnd) }
    }
    return @($list)
}

function Invoke-BobTrayExplorerRecycle {
    <#
    .SYNOPSIS
      Recycle explorer.exe in the current interactive session so Shell_NotifyIcon ghosts drop.
    .NOTES
      FR #9169. Refuses session 0. -WhatIf reports intent without Stop-Process.
    #>
    [CmdletBinding()]
    param([switch]$WhatIf)
    $sid = 0
    try { $sid = [int][System.Diagnostics.Process]::GetCurrentProcess().SessionId } catch { $sid = 0 }
    if ($sid -eq 0) {
        return [pscustomobject]@{ recycled = $false; reason = 'session0'; sessionId = 0 }
    }
    $ex = @(Get-Process -Name explorer -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $sid })
    if ($ex.Count -eq 0) {
        return [pscustomobject]@{ recycled = $false; reason = 'no-explorer'; sessionId = $sid }
    }
    if ($WhatIf) {
        return [pscustomobject]@{ recycled = $false; reason = 'whatIf'; sessionId = $sid; explorerPids = @($ex | ForEach-Object { $_.Id }) }
    }
    foreach ($p in $ex) {
        try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { }
    }
    Start-Sleep -Milliseconds 900
    $still = @(Get-Process -Name explorer -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $sid })
    if ($still.Count -eq 0) {
        try { Start-Process -FilePath "$env:WINDIR\explorer.exe" } catch {
            try { Start-Process -FilePath 'explorer.exe' } catch { }
        }
    }
    # Wait for Shell_TrayWnd so a follow-up sweep can find toolbars.
    $deadline = [datetime]::UtcNow.AddSeconds(8)
    while ([datetime]::UtcNow -lt $deadline) {
        $tray = [BobTrayIconSweep.Api]::FindWindow('Shell_TrayWnd', $null)
        if ($tray -ne [IntPtr]::Zero) { break }
        Start-Sleep -Milliseconds 250
    }
    Start-Sleep -Milliseconds 400
    return [pscustomobject]@{ recycled = $true; reason = 'ok'; sessionId = $sid }
}

function Invoke-BobTrayNotifyIconSweepPass {
    $posts = 0
    $bars = @(Get-BobNotificationToolbars)
    foreach ($hwnd in $bars) {
        $posts += [int](Invoke-BobTrayToolbarSweep -Hwnd $hwnd)
    }
    return [pscustomobject]@{ toolbars = $bars.Count; mousePosts = $posts }
}

$pass1 = Invoke-BobTrayNotifyIconSweepPass
$explorerRecycled = $false
$recycleReason = ''
$wantRecycle = [bool]$RecycleExplorer
if (-not $wantRecycle -and $HealLadder -and ([int]$pass1.toolbars -eq 0)) {
    $wantRecycle = $true
}
$pass2 = $null
if ($wantRecycle) {
    $rec = Invoke-BobTrayExplorerRecycle -WhatIf:$WhatIf
    $explorerRecycled = [bool]$rec.recycled
    $recycleReason = [string]$rec.reason
    if ($explorerRecycled -or $WhatIf) {
        $pass2 = Invoke-BobTrayNotifyIconSweepPass
    }
}

$final = if ($pass2) { $pass2 } else { $pass1 }

[pscustomobject]@{
    ok                = $true
    toolbars          = [int]$final.toolbars
    mousePosts        = [int]$final.mousePosts
    toolbarsBefore    = [int]$pass1.toolbars
    mousePostsBefore  = [int]$pass1.mousePosts
    explorerRecycled  = $explorerRecycled
    recycleReason     = $recycleReason
    healLadder        = [bool]$HealLadder
    recycleRequested  = $wantRecycle
    whatIf            = [bool]$WhatIf
} | ConvertTo-Json -Compress
exit 0
