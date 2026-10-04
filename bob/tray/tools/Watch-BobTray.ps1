# Hidden Bob Fleet tray watcher + system tray icon. Flashes on ACTION_REQUIRED.
# Title is Bob Fleet. Primary bar is weekly remaining (CLI billing log).
# Job list: every registered fleet machine (bundled registry + local store +
# read-only filesystem peer peek). Fail closed: unreachable / lastSeen stale.
# No WinRM. See docs/bob-fleet-peer-peek.md.
# GOOD UI: dark TipForm on left-click / Status only. No hover events
# (no MouseMove, no iconProbe). Card stays parked until X (no hideTip).
# Restart watcher kills Watch-Bobiverse + bobiverse irc_agent, starts
# _Watch-Bobiverse-<id>, then relaunches this tray. BAD: native
# NotifyIcon.Text white chip - Clear-BobNativeTip always.
# Exactly one TipForm; never Form.Show after ShowParkedAt.
# Empty fuel: Agents start / Plan may prompt for session XAI_API_KEY or CURSOR_API_KEY
# (child process env only; never persist User/Machine env or auth.json).
# Agent / Plan (top-level, single click, no submenu; t762u): bob-worker.exe --mode agent|plan, cwd <install>\worker | <install>\plan.
# Every click = a NEW agent (never resume/continue/attach; previous agents left running). Agent selection is automatic (cursor > grok > key dialog).
# Replaces the blank Interactive PowerShell window.
# Not a Windows service. Requires powershell.exe -STA.
[CmdletBinding()]
param(
    # CAST IRON (Simon 2026-09-27): cursor + xAI usage POST to digest webhook every 30s.
    [int]$PollSec = 30,
    [int]$StallSec = 600,
    [int]$HeartbeatStaleSec = 90,
    [string]$RepoRoot
)

$ErrorActionPreference = 'Continue'
if (-not $RepoRoot) { $RepoRoot = Split-Path $PSScriptRoot -Parent }
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$psd1 = Join-Path $RepoRoot 'src\BobBridge.psd1'
if (-not (Test-Path $psd1)) { throw "missing $psd1" }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
# CatchException before any Control. Otherwise a recycle Stop-Process mid-Timer tick
# surfaces PipelineStoppedException as the Windows Forms JIT dialog.
try {
    [System.Windows.Forms.Application]::SetUnhandledExceptionMode([System.Windows.Forms.UnhandledExceptionMode]::CatchException)
}
catch { }
Add-Type -Name Native -Namespace BobTray -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
'@
$hwnd = [BobTray.Native]::GetConsoleWindow()
if ($hwnd -ne [IntPtr]::Zero) { [void][BobTray.Native]::ShowWindow($hwnd, 0) }

# ThreadException / UnhandledException handlers (mode already set above when possible).
try {
    [System.Windows.Forms.Application]::add_ThreadException({
            param($sender, $e)
            $ex = $e.Exception
            if ($ex -is [System.Management.Automation.PipelineStoppedException]) { return }
            if ($ex -and $ex.GetType().FullName -eq 'System.Management.Automation.PipelineStoppedException') { return }
            try { Write-TrayLog ('ThreadException: ' + $ex.Message) } catch { }
            try {
                if (Get-Command Report-BobDeterministicException -ErrorAction SilentlyContinue) {
                    Report-BobDeterministicException -Site 'Watch-BobTray.ThreadException' -Exception $ex -ScriptPath $PSCommandPath | Out-Null
                }
            }
            catch { }
        })
    [AppDomain]::CurrentDomain.add_UnhandledException({
            param($sender, $e)
            $obj = $e.ExceptionObject
            if ($obj -is [System.Management.Automation.PipelineStoppedException]) { return }
            try { Write-TrayLog ('UnhandledException: ' + $obj) } catch { }
            try {
                if (Get-Command Report-BobDeterministicException -ErrorAction SilentlyContinue) {
                    Report-BobDeterministicException -Site 'Watch-BobTray.UnhandledException' -Exception $obj -ScriptPath $PSCommandPath | Out-Null
                }
            }
            catch { }
        })
}
catch { }

if (-not ('BobTrayUi.TipForm' -as [type])) {
    $refs = @(
        [System.Windows.Forms.Form].Assembly.Location,
        [System.Drawing.Point].Assembly.Location
    )
    Add-Type -ReferencedAssemblies $refs -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace BobTrayUi {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct NOTIFYICONIDENTIFIER {
        public uint cbSize;
        public IntPtr hWnd;
        public uint uID;
        public Guid guidItem;
    }
    public class IconRect {
        public int X;
        public int Y;
        public int Width;
        public int Height;
        public string Source;
        public bool Ok;
    }
    public static class Shell {
        [DllImport("shell32.dll")]
        public static extern int Shell_NotifyIconGetRect(ref NOTIFYICONIDENTIFIER identifier, out RECT iconLocation);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        public static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);
        [DllImport("user32.dll")]
        public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
        [DllImport("user32.dll")]
        public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        [DllImport("user32.dll")]
        public static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);
        public const int WM_SETREDRAW = 0x000B;
        public static void SetRedraw(IntPtr hwnd, bool enable) {
            if (hwnd == IntPtr.Zero) return;
            SendMessage(hwnd, WM_SETREDRAW, enable ? new IntPtr(1) : IntPtr.Zero, IntPtr.Zero);
        }
        [DllImport("user32.dll", SetLastError = true)]
        public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
        public static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        public const int SW_SHOWNOACTIVATE = 4;
        public const int SW_SHOWNA = 8;
        public const uint NIM_MODIFY = 1;
        public const uint NIF_TIP = 0x00000004;
        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        public static extern bool Shell_NotifyIcon(uint dwMessage, ref NOTIFYICONDATA lpdata);
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        public struct NOTIFYICONDATA {
            public int cbSize;
            public IntPtr hWnd;
            public uint uID;
            public uint uFlags;
            public uint uCallbackMessage;
            public IntPtr hIcon;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
            public string szTip;
        }
        public static void ClearNotifyTip(IntPtr hWnd, uint uID) {
            NOTIFYICONDATA d = new NOTIFYICONDATA();
            d.cbSize = Marshal.SizeOf(typeof(NOTIFYICONDATA));
            d.hWnd = hWnd;
            d.uID = uID;
            d.uFlags = NIF_TIP;
            d.szTip = "";
            Shell_NotifyIcon(NIM_MODIFY, ref d);
        }
        public const int TTM_POP = 0x041C;
        public const int SW_HIDE = 0;
        public static void HideTooltipWindows() {
            IntPtr h = IntPtr.Zero;
            for (int i = 0; i < 16; i++) {
                h = FindWindowEx(IntPtr.Zero, h, "tooltips_class32", null);
                if (h == IntPtr.Zero) break;
                SendMessage(h, TTM_POP, IntPtr.Zero, IntPtr.Zero);
                ShowWindow(h, SW_HIDE);
            }
        }
        public const uint SWP_NOSIZE = 0x0001;
        public const uint SWP_NOMOVE = 0x0002;
        public const uint SWP_NOACTIVATE = 0x0010;
        public const uint SWP_SHOWWINDOW = 0x0040;
        public const uint SWP_HIDEWINDOW = 0x0080;

        public static bool TryGetNotifyIconRect(IntPtr hWnd, uint uID, out RECT rect) {
            rect = new RECT();
            if (hWnd == IntPtr.Zero) return false;
            NOTIFYICONIDENTIFIER nid = new NOTIFYICONIDENTIFIER();
            nid.cbSize = (uint)Marshal.SizeOf(typeof(NOTIFYICONIDENTIFIER));
            nid.hWnd = hWnd;
            nid.uID = uID;
            nid.guidItem = Guid.Empty;
            int hr = Shell_NotifyIconGetRect(ref nid, out rect);
            return hr == 0 && (rect.Right - rect.Left) > 0 && (rect.Bottom - rect.Top) > 0;
        }

        public static bool TryGetTrayNotifyRect(out RECT rect) {
            rect = new RECT();
            IntPtr tray = FindWindow("Shell_TrayWnd", null);
            if (tray == IntPtr.Zero) return false;
            IntPtr area = FindWindowEx(tray, IntPtr.Zero, "TrayNotifyWnd", null);
            IntPtr target = area != IntPtr.Zero ? area : tray;
            return GetWindowRect(target, out rect) && (rect.Right - rect.Left) > 0;
        }

        public static IconRect QueryNotifyIconRect(IntPtr hWnd, uint uID) {
            IconRect r = new IconRect();
            RECT rect;
            if (TryGetNotifyIconRect(hWnd, uID, out rect)) {
                r.Ok = true;
                r.Source = "icon";
                r.X = rect.Left;
                r.Y = rect.Top;
                r.Width = rect.Right - rect.Left;
                r.Height = rect.Bottom - rect.Top;
                return r;
            }
            if (TryGetTrayNotifyRect(out rect)) {
                r.Ok = true;
                r.Source = "tray";
                r.X = rect.Left;
                r.Y = rect.Top;
                r.Width = rect.Right - rect.Left;
                r.Height = rect.Bottom - rect.Top;
                return r;
            }
            r.Ok = false;
            r.Source = "";
            return r;
        }
    }
    public class TipForm : Form {
        static TipForm _live;
        public static TipForm Live { get { return _live; } }
        public static int LiveCount {
            get { return (_live != null && !_live.IsDisposed) ? 1 : 0; }
        }
        public TipForm() {
            if (_live != null && !_live.IsDisposed && !object.ReferenceEquals(_live, this)) {
                try { _live.TryHide(); } catch { }
                try { _live.Dispose(); } catch { }
            }
            _live = this;
            this.DoubleBuffered = true;
            this.SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint, true);
            this.UpdateStyles();
        }
        protected override void Dispose(bool disposing) {
            if (object.ReferenceEquals(_live, this)) _live = null;
            base.Dispose(disposing);
        }
        public bool IsUsable {
            get { return !this.IsDisposed; }
        }
        protected override bool ShowWithoutActivation { get { return true; } }
        protected override CreateParams CreateParams {
            get {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= 0x08000000; // WS_EX_NOACTIVATE
                cp.ExStyle |= 0x00000080; // WS_EX_TOOLWINDOW
                cp.ExStyle |= 0x00000008; // WS_EX_TOPMOST
                return cp;
            }
        }
        public bool TryHide() {
            if (this.IsDisposed) return true;
            try {
                if (this.IsHandleCreated) {
                    Shell.SetWindowPos(
                        this.Handle,
                        IntPtr.Zero,
                        0, 0, 0, 0,
                        Shell.SWP_NOSIZE | Shell.SWP_NOMOVE | Shell.SWP_NOACTIVATE | Shell.SWP_HIDEWINDOW);
                }
                if (this.Visible) this.Hide();
                return this.IsDisposed || !this.Visible;
            } catch (ObjectDisposedException) {
                return true;
            }
        }
        public bool ShowParkedAt(int x, int y) {
            if (this.IsDisposed) return false;
            try {
                this.Left = x;
                this.Top = y;
                if (!this.IsHandleCreated) this.CreateHandle();
                if (this.IsDisposed) return false;
                bool pos = Shell.SetWindowPos(
                    this.Handle,
                    Shell.HWND_TOPMOST,
                    x,
                    y,
                    this.Width,
                    this.Height,
                    Shell.SWP_NOACTIVATE | Shell.SWP_SHOWWINDOW);
                if (this.IsDisposed) return false;
                // Visible bookkeeping only. Do not call Form.Show() - that is a second dialog.
                if (!this.Visible) this.Visible = true;
                if (!this.Visible && !this.IsDisposed) {
                    Shell.ShowWindow(this.Handle, Shell.SW_SHOWNA);
                    if (!this.IsDisposed) this.Visible = true;
                }
                if (!this.Visible && !this.IsDisposed) {
                    Shell.ShowWindow(this.Handle, Shell.SW_SHOWNOACTIVATE);
                    if (!this.IsDisposed) this.Visible = true;
                }
                return !this.IsDisposed && this.Visible && pos;
            } catch (ObjectDisposedException) {
                return false;
            }
        }
    }
}
'@
}

Remove-Module BobBridge -ErrorAction SilentlyContinue
Import-Module $psd1 -Force

$watchJobs = Join-Path $RepoRoot 'tools\Watch-BobJobs.ps1'
$watchBobiverse = Join-Path $RepoRoot 'tools\Watch-Bobiverse.ps1'
$logDir = Join-Path $env:USERPROFILE '.grok\long-running-background-tasks'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir 'watch_bob_tray.log'

function Write-TrayLog([string]$m) {
    Add-Content -Path $logPath -Value ('{0:o} {1}' -f [datetime]::UtcNow, $m) -ErrorAction SilentlyContinue
}

# t794u/t797u/t798u helpers: Exit ordering + detached service stop/restart, and the install inventory for the About dialog.
foreach ($helper in @('BobTrayLifecycle.ps1', 'Get-BobInstallInfo.ps1', 'BobTrayStartWorker.ps1', 'BobTrayDialogs.ps1')) {
    $helperPath = Join-Path $RepoRoot ('tools\' + $helper)
    if (Test-Path -LiteralPath $helperPath) { . $helperPath } else { Write-TrayLog ('missing helper ' + $helperPath) }
}
$script:trayServiceName = 'ircBob'
$script:trayExitReason = ''
$script:aboutForm = $null

function Test-BobTrayTipAlive {
    try {
        return ($null -ne $script:tip -and -not $script:tip.IsDisposed)
    }
    catch { return $false }
}

function Enable-BobDoubleBuffer {
    param([System.Windows.Forms.Control]$Control)
    if (-not $Control) { return }
    try {
        $prop = $Control.GetType().GetProperty('DoubleBuffered', [Reflection.BindingFlags]'Instance,NonPublic')
        if ($prop) { $prop.SetValue($Control, $true, $null) }
    } catch { }
}

function Suspend-BobTrayPaint {
    # Only the tile host - never SuspendLayout / WM_SETREDRAW on TipForm.
    # Suspending the form then Controls.Clear left a blank visible card (and
    # looked like a "new empty dialog" on poll refresh).
    try {
        if ($script:tileHost -and -not $script:tileHost.IsDisposed) { $script:tileHost.SuspendLayout() }
    } catch { }
}

function Resume-BobTrayPaint {
    try {
        if ($script:tileHost -and -not $script:tileHost.IsDisposed) {
            $script:tileHost.ResumeLayout($true)
            $script:tileHost.Invalidate($true)
            $script:tileHost.Update()
        }
    } catch { }
}

function Test-BobTrayTipVisible {
    if (-not (Test-BobTrayTipAlive)) { return $false }
    try { return [bool]$script:tip.Visible }
    catch { return $false }
}

function Get-BobNotifyIconRect {
    param([System.Windows.Forms.NotifyIcon]$NotifyIcon)
    try {
        $hWnd = [IntPtr]::Zero
        $id = [uint32]0
        $t = $NotifyIcon.GetType()
        $flags = [Reflection.BindingFlags]'Instance,NonPublic'
        $windowField = $t.GetField('window', $flags)
        $idField = $t.GetField('id', $flags)
        if ($windowField -and $idField) {
            $window = $windowField.GetValue($NotifyIcon)
            if ($window) {
                $hWnd = $window.Handle
                $id = [uint32]$idField.GetValue($NotifyIcon)
            }
        }
        $r = [BobTrayUi.Shell]::QueryNotifyIconRect($hWnd, $id)
        if ($r -and $r.Ok) {
            return [pscustomobject]@{
                X      = [int]$r.X
                Y      = [int]$r.Y
                Width  = [int]$r.Width
                Height = [int]$r.Height
                Source = [string]$r.Source
            }
        }
    }
    catch {
        Write-TrayLog ('icon rect error: ' + $_.Exception.Message)
    }
    return $null
}

function Add-RoundRect([System.Drawing.Drawing2D.GraphicsPath]$path, $x, $y, $w, $h, $r) {
    $d = $r * 2
    $path.AddArc($x, $y, $d, $d, 180, 90)
    $path.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
    $path.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
    $path.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
    $path.CloseFigure()
}

# Font Awesome Free solid robot (CC BY 4.0), drawn at tray size.
function New-FaRobotIcon {
    param([System.Drawing.Color]$Badge)
    $sz = 16
    $bmp = New-Object System.Drawing.Bitmap $sz, $sz
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)
    $fg = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(232, 236, 241))
    $eye = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(28, 33, 40))
    $ant = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(232, 236, 241)), 1.2
    $g.DrawLine($ant, 8.0, 1.2, 8.0, 4.0)
    $g.FillEllipse($fg, 7.0, 0.4, 2.0, 2.0)
    $body = New-Object System.Drawing.Drawing2D.GraphicsPath
    Add-RoundRect $body 3.2 4.2 9.6 10.4 1.6
    $g.FillPath($fg, $body)
    $g.FillRectangle($fg, 1.6, 7.2, 1.8, 4.4)
    $g.FillRectangle($fg, 12.6, 7.2, 1.8, 4.4)
    $g.FillEllipse($eye, 5.1, 7.0, 2.2, 2.2)
    $g.FillEllipse($eye, 8.7, 7.0, 2.2, 2.2)
    if ($Badge.A -gt 0) {
        $br = New-Object System.Drawing.SolidBrush $Badge
        $g.FillEllipse($br, 10.2, 10.2, 5.2, 5.2)
        $br.Dispose()
    }
    $body.Dispose(); $fg.Dispose(); $eye.Dispose(); $ant.Dispose()
    $h = $bmp.GetHicon()
    $icon = [System.Drawing.Icon]::FromHandle($h)
    $clone = $icon.Clone()
    $g.Dispose(); $bmp.Dispose()
    return $clone
}

$iconIdle = New-FaRobotIcon -Badge ([System.Drawing.Color]::Transparent)
$iconAlertA = New-FaRobotIcon -Badge ([System.Drawing.Color]::FromArgb(220, 50, 47))
$iconAlertB = New-FaRobotIcon -Badge ([System.Drawing.Color]::FromArgb(255, 180, 0))
$iconContext = New-FaRobotIcon -Badge ([System.Drawing.Color]::FromArgb(210, 153, 34))
Write-TrayLog 'tray icon Font Awesome robot'

# --- Agents submenu (AgentMonitor watch seats) -----------------------------
# The two watch-seat agents (Cursor, Grok) become ONE "Agents" tray menu; you
# then select which. Each entry uses the SAME icon as its Desktop shortcut (the
# agent app .exe, matching AgentMonitor shortcuts/*.lnk IconLocation). If an
# agent app is not installed the icon is greyed and clicking it initialises the
# setup (tools/Install-AgentMonitor.ps1). App installed = exe on disk (#180);
# Watch-AgentHealth.cmd is only needed to launch the watch seat.
# Skill: agent-monitor-setup.
$script:agentMonitorDirCandidates = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Watch-AgentHealth'),
    (Join-Path $env:USERPROFILE 'Desktop\Watch-AgentHealth'),
    'C:\ai\AgentMonitor',
    'D:\ai\AgentMonitor'
)
$script:installAgentMonitor = Join-Path $RepoRoot 'tools\Install-AgentMonitor.ps1'

function Resolve-BobTrayAgentMonitorDir {
    foreach ($d in $script:agentMonitorDirCandidates) {
        if (-not $d) { continue }
        $cmd = Join-Path $d 'Watch-AgentHealth.cmd'
        if (Test-Path -LiteralPath $cmd) { return $d }
    }
    return $script:agentMonitorDirCandidates[0]
}

$script:agentMonitorDir = Resolve-BobTrayAgentMonitorDir
$script:agentMonitorCmd = Join-Path $script:agentMonitorDir 'Watch-AgentHealth.cmd'

function Resolve-BobTrayDesktopShortcutExe {
    param([string]$Kind)
    # Desktop / Public Desktop .lnk IconLocation or TargetPath (parity with agent shortcuts).
    $kind = ([string]$Kind).ToLowerInvariant()
    $names = if ($kind -eq 'cursor') {
        @('Cursor.lnk', 'cursor.lnk')
    }
    elseif ($kind -eq 'grok') {
        @('Grok Bot.lnk', 'Grok.lnk', 'GrokBot.lnk')
    }
    else { @() }
    $dirs = @(
        [Environment]::GetFolderPath('Desktop')
        (Join-Path $env:USERPROFILE 'Desktop')
        (Join-Path $env:PUBLIC 'Desktop')
    ) | Where-Object { $_ } | Select-Object -Unique
    try {
        $sh = New-Object -ComObject WScript.Shell
        foreach ($d in $dirs) {
            if (-not (Test-Path -LiteralPath $d)) { continue }
            foreach ($n in $names) {
                $lnkPath = Join-Path $d $n
                if (-not (Test-Path -LiteralPath $lnkPath)) { continue }
                $lnk = $sh.CreateShortcut($lnkPath)
                $icon = ([string]$lnk.IconLocation).Split(',')[0].Trim().Trim('"')
                if ($icon -and (Test-Path -LiteralPath $icon)) { return $icon }
                $target = [string]$lnk.TargetPath
                if ($target -and (Test-Path -LiteralPath $target)) { return $target }
            }
        }
    }
    catch { }
    return $null
}

function Get-BobTrayAgentExeCandidates {
    param([string]$Kind)
    $kind = ([string]$Kind).ToLowerInvariant()
    $cands = @()
    $fromLnk = Resolve-BobTrayDesktopShortcutExe $kind
    if ($fromLnk) { $cands += $fromLnk }
    if ($kind -eq 'cursor') {
        $cands += @(
            (Join-Path $env:LOCALAPPDATA 'Programs\cursor\Cursor.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Cursor\Cursor.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Cursor\cursor.exe'),
            (Join-Path ${env:ProgramFiles} 'Cursor\Cursor.exe'),
            (Join-Path ${env:ProgramFiles} 'cursor\Cursor.exe')
        )
        try {
            $cmd = Get-Command cursor.cmd, cursor.exe, Cursor.exe -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
                $cands = @([string]$cmd.Source) + $cands
            }
        } catch { }
    }
    elseif ($kind -eq 'grok') {
        # Prefer Grok Bot desktop app before CLI grok.exe (better tray icon).
        # Ionos / fleet often install under Program Files (Public Desktop Grok Bot.lnk).
        $cands += @(
            (Join-Path ${env:ProgramFiles} 'Grok Bot\Grok Bot.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'Grok Bot\Grok Bot.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Grok Bot\Grok Bot.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\GrokBot\Grok Bot.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\grok-bot\Grok Bot.exe'),
            (Join-Path $env:USERPROFILE '.grok\bin\grok.exe')
        )
        try {
            $cmd = Get-Command 'Grok Bot.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
                $cands = @([string]$cmd.Source) + $cands
            }
        } catch { }
    }
    return @($cands | Where-Object { $_ } | Select-Object -Unique)
}

function Resolve-BobTrayAgentExe {
    param([string]$Kind)
    foreach ($p in Get-BobTrayAgentExeCandidates $Kind) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    return $null
}

function Resolve-BobTrayAgentIconExe {
    param([string]$Kind)
    # Icon path: Desktop shortcut first (same as agent .lnk), then branded desktop apps.
    $kind = ([string]$Kind).ToLowerInvariant()
    $fromLnk = Resolve-BobTrayDesktopShortcutExe $kind
    if ($fromLnk) { return $fromLnk }
    if ($kind -eq 'grok') {
        foreach ($p in @(
                (Join-Path ${env:ProgramFiles} 'Grok Bot\Grok Bot.exe'),
                (Join-Path ${env:ProgramFiles(x86)} 'Grok Bot\Grok Bot.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\Grok Bot\Grok Bot.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\GrokBot\Grok Bot.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\grok-bot\Grok Bot.exe')
            )) {
            if ($p -and (Test-Path -LiteralPath $p)) { return $p }
        }
    }
    return (Resolve-BobTrayAgentExe $Kind)
}

function Get-BobTrayAgentDefs {
    # kind = Watch-AgentHealth.cmd argument; exe = resolved agent app path (#180).
    @(
        [ordered]@{ name = 'Cursor'; kind = 'cursor'; exe = (Resolve-BobTrayAgentExe 'cursor') }
        [ordered]@{ name = 'Grok'; kind = 'grok'; exe = (Resolve-BobTrayAgentExe 'grok') }
    )
}

function Test-BobTrayAgentInstalled {
    param($Agent)
    # Grey only when the agent *app* is missing. Watch-AgentHealth deploy is separate (#180).
    if (-not $Agent) { return $false }
    $exe = [string]$Agent.exe
    if (-not $exe) { $exe = Resolve-BobTrayAgentExe $Agent.kind }
    return [bool]($exe -and (Test-Path -LiteralPath $exe))
}

function Test-BobTrayAgentMonitorReady {
    $script:agentMonitorDir = Resolve-BobTrayAgentMonitorDir
    $script:agentMonitorCmd = Join-Path $script:agentMonitorDir 'Watch-AgentHealth.cmd'
    return (Test-Path -LiteralPath $script:agentMonitorCmd)
}

function ConvertTo-BobTrayGrayImage {
    param([System.Drawing.Image]$Image)
    $w = $Image.Width; $h = $Image.Height
    $out = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($out)
    $cm = New-Object System.Drawing.Imaging.ColorMatrix
    $cm.Matrix00 = 0.30; $cm.Matrix01 = 0.30; $cm.Matrix02 = 0.30
    $cm.Matrix10 = 0.59; $cm.Matrix11 = 0.59; $cm.Matrix12 = 0.59
    $cm.Matrix20 = 0.11; $cm.Matrix21 = 0.11; $cm.Matrix22 = 0.11
    $cm.Matrix33 = 0.92
    $ia = New-Object System.Drawing.Imaging.ImageAttributes
    $ia.SetColorMatrix($cm)
    $rect = New-Object System.Drawing.Rectangle 0, 0, $w, $h
    $g.DrawImage($Image, $rect, 0, 0, $w, $h, [System.Drawing.GraphicsUnit]::Pixel, $ia)
    $g.Dispose()
    return $out
}

function Test-BobTrayImageMostlyEmpty {
    param([System.Drawing.Bitmap]$Bitmap)
    if (-not $Bitmap) { return $true }
    try {
        $w = [Math]::Min(8, $Bitmap.Width)
        $h = [Math]::Min(8, $Bitmap.Height)
        if ($w -le 0 -or $h -le 0) { return $true }
        $opaque = 0
        for ($y = 0; $y -lt $h; $y++) {
            for ($x = 0; $x -lt $w; $x++) {
                $c = $Bitmap.GetPixel($x, $y)
                if ($c.A -gt 32 -and ($c.R + $c.G + $c.B) -gt 24) { $opaque++ }
            }
        }
        return ($opaque -lt 2)
    }
    catch { return $false }
}

function New-BobTrayAgentBadgeImage {
    param([string]$Kind)
    $kind = ([string]$Kind).ToLowerInvariant()
    $letter = 'A'
    # Bright chips - black/near-black badges vanish on the dark TipForm / menu.
    $bgCol = [System.Drawing.Color]::FromArgb(88, 166, 255)
    $fgCol = [System.Drawing.Color]::White
    if ($kind -eq 'cursor') {
        $letter = 'C'
        $bgCol = [System.Drawing.Color]::FromArgb(232, 236, 241)
        $fgCol = [System.Drawing.Color]::FromArgb(28, 33, 40)
    }
    elseif ($kind -eq 'grok') {
        $letter = 'G'
        $bgCol = [System.Drawing.Color]::FromArgb(255, 180, 0)
        $fgCol = [System.Drawing.Color]::FromArgb(28, 33, 40)
    }
    $bmp = New-Object System.Drawing.Bitmap 32, 32
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)
    $brush = New-Object System.Drawing.SolidBrush $bgCol
    $g.FillEllipse($brush, 1, 1, 30, 30)
    $brush.Dispose()
    $font = New-Object System.Drawing.Font('Segoe UI', 14.0, [System.Drawing.FontStyle]::Bold)
    $sf = New-Object System.Drawing.StringFormat
    $sf.Alignment = [System.Drawing.StringAlignment]::Center
    $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
    $fgBrush = New-Object System.Drawing.SolidBrush $fgCol
    $g.DrawString($letter, $font, $fgBrush, (New-Object System.Drawing.RectangleF 0, 0, 32, 32), $sf)
    $fgBrush.Dispose(); $font.Dispose(); $sf.Dispose(); $g.Dispose()
    return $bmp
}

function ConvertTo-BobTrayTipVisibleImage {
    param([System.Drawing.Image]$Image)
    # Dark app glyphs (Cursor/Grok) disappear on the dark tip - plate them on a light chip.
    if (-not $Image) { return $null }
    $size = 32
    $out = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($out)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.Clear([System.Drawing.Color]::Transparent)
    $plate = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(232, 236, 241))
    $g.FillEllipse($plate, 0, 0, $size - 1, $size - 1)
    $plate.Dispose()
    $pad = 4
    $dest = New-Object System.Drawing.Rectangle $pad, $pad, ($size - 2 * $pad), ($size - 2 * $pad)
    $g.DrawImage($Image, $dest)
    $g.Dispose()
    return $out
}

function Get-BobTrayAgentImage {
    param($Agent, [bool]$Installed)
    $img = $null
    $kind = ''
    if ($Agent -and $Agent.kind) { $kind = [string]$Agent.kind }
    $iconExe = $null
    if ($kind) { $iconExe = Resolve-BobTrayAgentIconExe $kind }
    if (-not $iconExe -and $Agent -and $Agent.exe) { $iconExe = [string]$Agent.exe }
    try {
        if ($iconExe -and (Test-Path -LiteralPath $iconExe)) {
            $ico = [System.Drawing.Icon]::ExtractAssociatedIcon($iconExe)
            if ($ico) { $img = $ico.ToBitmap() }
            if ($img -and (Test-BobTrayImageMostlyEmpty $img)) {
                $img.Dispose()
                $img = $null
            }
        }
    }
    catch { $img = $null }
    if (-not $img) {
        if ($kind) { $img = New-BobTrayAgentBadgeImage $kind }
        else {
            try { $img = $iconIdle.ToBitmap() } catch { $img = New-BobTrayAgentBadgeImage 'cursor' }
        }
    }
    else {
        # Extracted exe icons are often black-on-transparent; plate for dark tip/menu.
        $plated = ConvertTo-BobTrayTipVisibleImage $img
        if ($plated) {
            try { $img.Dispose() } catch { }
            $img = $plated
        }
    }
    # Soft greyscale when not installed - keep alpha high enough to stay visible on dark tip.
    if (-not $Installed -and $img) {
        $gray = ConvertTo-BobTrayGrayImage $img
        if ($img -ne $gray) { try { $img.Dispose() } catch { } }
        $img = $gray
    }
    return $img
}

function Initialize-BobTrayAgentSetup {
    param($Agent)
    if (-not (Test-Path $script:installAgentMonitor)) {
        Write-TrayLog ('agents: setup script missing ' + $script:installAgentMonitor)
        return
    }
    Write-TrayLog ('agents: initialise setup for {0}' -f $Agent.kind)
    $ps = (Get-Command powershell.exe).Source
    Start-Process -FilePath $ps `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script:installAgentMonitor, '-Agent', $Agent.kind) `
        -WorkingDirectory $RepoRoot | Out-Null
}

function ConvertTo-BobTrayProcessArgumentString {
    param([string[]]$ArgumentList)
    # ProcessStartInfo.Arguments needs Windows-style quoting (PS 5.1 has no Start-Process -Environment).
    $parts = foreach ($a in @($ArgumentList)) {
        $s = [string]$a
        if ($s -notmatch '[\s"]') { $s }
        else { '"' + ($s.Replace('"', '\"')) + '"' }
    }
    return ($parts -join ' ')
}

function Get-BobTrayGrokSessionRoot {
    return (Join-Path ([IO.Path]::GetTempPath()) 'bob-grok-session')
}

function New-BobTrayGrokSessionEnv {
    # grok >= 1.0.41 resolves the OAuth session in ~/.grok/auth.json BEFORE XAI_API_KEY, so a
    # session key from the #314 dialog was silently ignored on any signed-in machine.
    # GROK_AUTH_PATH -> a fresh per-start temp path with no auth.json makes the child resolve
    # auth_type=ApiKey (skills/config under ~/.grok stay as-is). The key stays child-env only:
    # never User/Machine env, never written to disk by the tray.
    param([Parameter(Mandatory = $true)][string]$ApiKey)
    try { Clear-BobTrayGrokSessionDirs } catch { }
    $dir = Join-Path (Get-BobTrayGrokSessionRoot) ([guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return @{
        XAI_API_KEY    = $ApiKey
        GROK_AUTH_PATH = (Join-Path $dir 'auth.json')
    }
}

function Register-BobTrayGrokSession {
    param($Process, [hashtable]$SessionEnv)
    if (-not $SessionEnv -or -not $SessionEnv.ContainsKey('GROK_AUTH_PATH')) { return }
    $dir = Split-Path -Parent ([string]$SessionEnv['GROK_AUTH_PATH'])
    $script:bobTrayGrokSessions = @(@($script:bobTrayGrokSessions | Where-Object { $_ }) + @([pscustomobject]@{ Process = $Process; Dir = $dir }))
}

function Clear-BobTrayGrokSessionDirs {
    # If the session key is rejected, grok's TUI can fall back to a browser sign-in and save an
    # auth.json into the session dir. Remove each session dir once its child exits, and sweep
    # untracked leftovers (e.g. from a previous tray) older than MaxAgeHours.
    param([int]$MaxAgeHours = 24)
    $keep = @()
    foreach ($s in @($script:bobTrayGrokSessions | Where-Object { $_ })) {
        $exited = $true
        try { if ($s.Process) { $exited = [bool]$s.Process.HasExited } } catch { $exited = $true }
        if (-not $exited) { $keep += $s; continue }
        try {
            if (Test-Path -LiteralPath $s.Dir) { Remove-Item -LiteralPath $s.Dir -Recurse -Force -ErrorAction Stop }
            Write-TrayLog ('grok session: removed session auth dir ' + $s.Dir)
        }
        catch { $keep += $s }
    }
    $script:bobTrayGrokSessions = @($keep)
    $root = Get-BobTrayGrokSessionRoot
    if (-not (Test-Path -LiteralPath $root)) { return }
    $live = @{}
    foreach ($s in $script:bobTrayGrokSessions) { $live[[string]$s.Dir] = $true }
    $cutoff = (Get-Date).AddHours(-$MaxAgeHours)
    foreach ($d in @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue)) {
        if ($live.ContainsKey($d.FullName)) { continue }
        if ($d.LastWriteTime -lt $cutoff) {
            try { Remove-Item -LiteralPath $d.FullName -Recurse -Force -ErrorAction Stop } catch { }
        }
    }
}

function Start-BobTrayProcessWithSessionEnv {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [hashtable]$SessionEnv
    )
    if (-not $SessionEnv -or $SessionEnv.Count -eq 0) {
        return (Start-Process -FilePath $FilePath `
                -ArgumentList $ArgumentList `
                -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru)
    }
    # Child-only env: UseShellExecute=false + ProcessStartInfo.EnvironmentVariables.
    # Never persist API keys to User/Machine environment or rewrite auth.json.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = ConvertTo-BobTrayProcessArgumentString -ArgumentList $ArgumentList
    if ($WorkingDirectory) { $psi.WorkingDirectory = $WorkingDirectory }
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    foreach ($k in @($SessionEnv.Keys)) {
        $psi.EnvironmentVariables[[string]$k] = [string]$SessionEnv[$k]
    }
    $proc = [System.Diagnostics.Process]::Start($psi)
    Register-BobTrayGrokSession -Process $proc -SessionEnv $SessionEnv
    return $proc
}

function Get-BobTrayWatchWorkspace {
    # FR #369 / #102: explicit -Cwd for Watch-AgentHealth.
    # Default per-machine seat work dir C:\bob-seat-work\<machine> - never live \ai trees.
    # Config: BOB_SEAT_WORK (exact path) or BOB_SEAT_WORK_ROOT (parent; child = <machine>).
    param([string]$FallbackRoot = '')
    $exact = ([string]$env:BOB_SEAT_WORK).Trim()
    if ($exact) {
        $path = [IO.Path]::GetFullPath($exact)
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType Directory -Force -Path $path | Out-Null
        }
        return $path
    }

    $mid = $null
    try { $mid = Get-BobTrayMachineId } catch { $mid = $null }
    if (-not $mid) { $mid = ([string]$env:BOB_MACHINE_ID).Trim() }
    if (-not $mid) { $mid = ([string]$env:COMPUTERNAME).Trim() }
    if (-not $mid) { $mid = 'local' }
    $mid = ($mid.ToLowerInvariant() -replace '[^a-z0-9_-]+', '-').Trim('-')
    if (-not $mid) { $mid = 'local' }

    $parent = ([string]$env:BOB_SEAT_WORK_ROOT).Trim()
    if (-not $parent) {
        $parent = 'C:\bob-seat-work'
    }
    else {
        $parent = [IO.Path]::GetFullPath($parent)
    }
    # Refuse accidental config that points the seat at a live \ai root.
    $parentLeaf = [IO.Path]::GetFileName($parent.TrimEnd('\', '/'))
    if ($parentLeaf -eq 'ai' -or $parent -match '(?i)[/\\]ai$') {
        $parent = 'C:\bob-seat-work'
    }

    $path = Join-Path $parent $mid
    try {
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType Directory -Force -Path $path | Out-Null
        }
        return [IO.Path]::GetFullPath($path)
    }
    catch {
        Write-TrayLog ("agents: seat work dir create failed {0}: {1}" -f $path, $_.Exception.Message)
    }
    if ($FallbackRoot -and (Test-Path -LiteralPath $FallbackRoot)) {
        $fb = [IO.Path]::GetFullPath($FallbackRoot)
        if ($fb -notmatch '(?i)[/\\]ai$') { return $fb }
    }
    # Last resort: still prefer bob-seat-work\local over \ai
    $last = 'C:\bob-seat-work\local'
    New-Item -ItemType Directory -Force -Path $last | Out-Null
    return [IO.Path]::GetFullPath($last)
}

function Watch-BobTrayAgentWatchEarlyExit {
    # FR #102: if the watch worker dies within ~10s, surface it (log + balloon).
    param(
        $Process,
        [int]$Seconds = 10,
        [string]$BootstrapLog = ''
    )
    if (-not $Process) { return }
    $pidWatch = 0
    try { $pidWatch = [int]$Process.Id } catch { return }
    $deadline = (Get-Date).AddSeconds([Math]::Max(3, $Seconds))
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        if ($Process.HasExited) { break }
        if (-not (Get-Process -Id $pidWatch -ErrorAction SilentlyContinue)) { break }
    }
    $alive = Get-Process -Id $pidWatch -ErrorAction SilentlyContinue
    if ($alive) { return }
    $logHint = if ($BootstrapLog) { $BootstrapLog } else { (Join-Path $env:TEMP 'Watch-AgentHealth-start.log') }
    $msg = ('agents: watch seat exited after early start (pid={0}; see {1})' -f $pidWatch, $logHint)
    Write-TrayLog $msg
    try {
        if (Get-Command Show-BobTrayBalloon -ErrorAction SilentlyContinue) {
            Show-BobTrayBalloon -Title 'Watch seat failed' -Text $msg
        }
        elseif ($script:NotifyIcon) {
            $script:NotifyIcon.ShowBalloonTip(8000, 'Watch seat failed', $msg, [System.Windows.Forms.ToolTipIcon]::Error)
        }
    }
    catch { }
}

function Get-BobTrayFuelLocalMachineId {
    $mid = [string]$env:BOB_MACHINE_ID
    if (-not $mid) {
        try { $mid = [string](Get-ThisMachineId) } catch { $mid = $null }
    }
    if (-not $mid -and $script:lastFuelSnapshot -and $script:lastFuelSnapshot.machine) {
        $mid = [string]$script:lastFuelSnapshot.machine
    }
    if ($mid) {
        try { $mid = [string](Resolve-BobiverseMachineId $mid) } catch { }
        return $mid.Trim().ToLowerInvariant()
    }
    return $null
}

function Get-BobTrayGrokFuelRemaining {
    # CAST IRON (Simon 2026-09-27 + AgentMonitor#150): Grok agent start uses LOCAL
    # weekly remaining (Get-BobWeeklyRemaining / unified.jsonl), not digest
    # pcent.grok-chat (that key is Cursor Sand) and not a poisoned seat-cache 0.
    # Grok 1.0.41: remaining_pct=$null (TipForm n/a) is a real local reading â€”
    # return $null so Resolve-BobTrayGrokFuelAtStart uses Get-BobGrokAvailability.
    if (Get-Command Get-BobWeeklyRemaining -ErrorAction SilentlyContinue) {
        try {
            $w = Get-BobWeeklyRemaining
            if ($w) {
                if ($null -ne $w.remaining_pct -and [string]$w.remaining_pct -ne '') {
                    try { return [int]$w.remaining_pct } catch { }
                }
                # Local billing doc present with unknown % â€” do not fall through to
                # TipForm snapshot / digest Sand 0% (false exhaustion dialog).
                return $null
            }
        }
        catch { }
    }
    $snap = $script:lastFuelSnapshot
    $mid = Get-BobTrayFuelLocalMachineId
    if ($snap) {
        foreach ($m in @($snap.machines)) {
            if (-not $m) { continue }
            $id = [string]$m.id
            if (-not $id) { continue }
            try { $id = [string](Resolve-BobiverseMachineId $id) } catch { }
            if (-not $id) { continue }
            if ($mid -and ($id.ToLowerInvariant() -eq $mid)) {
                # Prefer availability when snapshot % is absent; never invent 0 from n/a.
                if ($null -ne $m.remaining_pct -and [string]$m.remaining_pct -ne '') {
                    try { return [int]$m.remaining_pct } catch { }
                }
                return $null
            }
        }
        if ($null -ne $snap.remaining_pct -and [string]$snap.remaining_pct -ne '') {
            try { return [int]$snap.remaining_pct } catch { }
        }
    }
    return $null
}

function Get-BobTrayDigestReportUrl {
    $u = [string]$env:BOB_DIGEST_REPORT_URL
    if ($u) { return $u.Trim() }
    return 'https://irc.ntsa.uk/bob/v1/report'
}

function Get-BobTrayMachineGrokChatPcent {
    <#
      FR #356: read machines.<id>.pcent["grok-chat"] from the digest once at start.
      Returns [int] when present (including 0); $null when blank/missing/unreachable.
    #>
    param(
        [string]$MachineId,
        [object]$Digest
    )
    $mid = [string]$MachineId
    if (-not $mid) { $mid = Get-BobTrayFuelLocalMachineId }
    if (-not $mid) { return $null }
    try { $mid = [string](Resolve-BobiverseMachineId $mid) } catch { }
    $mid = $mid.Trim().ToLowerInvariant()
    $doc = $Digest
    if (-not $doc) {
        # Prefer hover cache when it already carries pcent (avoids a second GET on every paint).
        if ($script:lastFuelSnapshot -and $script:lastFuelSnapshot.digest_machines) {
            $doc = [pscustomobject]@{ machines = $script:lastFuelSnapshot.digest_machines }
        }
    }
    if (-not $doc) {
        try {
            # UTF-8 explicitly (PS 5.1 would decode a charset-less body as Latin-1: "A-circumflex + dot").
            $resp = Invoke-WebRequest -Uri (Get-BobTrayDigestReportUrl) -UseBasicParsing -TimeoutSec 8 -Headers @{ Accept = 'application/json' }
            $ms = $resp.RawContentStream
            $ms.Position = 0
            $buf = New-Object byte[] ([int]$ms.Length)
            [void]$ms.Read($buf, 0, $buf.Length)
            $doc = [System.Text.Encoding]::UTF8.GetString($buf) | ConvertFrom-Json
        }
        catch {
            Write-TrayLog ('agents: digest fuel read failed: ' + $_.Exception.Message)
            return $null
        }
    }
    $ent = $null
    if ($doc.machines) {
        if ($doc.machines -is [System.Collections.IDictionary] -or ($doc.machines.PSObject.Properties.Name -contains $mid)) {
            try { $ent = $doc.machines.$mid } catch { $ent = $null }
        }
        if (-not $ent) {
            foreach ($m in @($doc.machines)) {
                if (-not $m) { continue }
                $id = [string]$m.id
                if (-not $id) { continue }
                try { $id = [string](Resolve-BobiverseMachineId $id) } catch { }
                if ($id -and $id.ToLowerInvariant() -eq $mid) { $ent = $m; break }
            }
        }
    }
    if (-not $ent -or -not $ent.pcent) { return $null }
    $raw = $null
    try { $raw = $ent.pcent.'grok-chat' } catch { $raw = $null }
    if ($null -eq $raw) {
        try { $raw = $ent.pcent.psobject.Properties['grok-chat'].Value } catch { $raw = $null }
    }
    if ($null -eq $raw -or [string]$raw -eq '') { return $null }
    try { return [int]$raw } catch { return $null }
}

function Resolve-BobTrayGrokFuelAtStart {
    <#
      Grok watch-seat start fuel gate (CAST IRON Simon 2026-09-27 + FR #430):
      Local weekly remaining first (TipForm machine tile / Get-BobWeeklyRemaining).
      Digest pcent.grok-chat is Cursor Sand - never use it when a local weekly doc exists
      (Grok 1.0.41 n/a included). Legacy digest fill only when no local unified.jsonl.
      - remaining > 0  => pool
      - remaining = 0  => session-key (dialog) - confirmed exhaustion only
      - remaining blank: Get-BobGrokAvailability - verified local auth+period => pool;
        unknown/stale/auth-failed => stop-unknown (never treat as exhausted)
    #>
    param(
        [object]$Digest,
        [string]$MachineId
    )
    $remain = Get-BobTrayGrokFuelRemaining
    $week = $null
    if (Get-Command Get-BobWeeklyRemaining -ErrorAction SilentlyContinue) {
        try { $week = Get-BobWeeklyRemaining } catch { $week = $null }
    }
    # Digest pcent.grok-chat is Cursor Sand (Write-BobIrcStatus), not xAI weekly.
    # Only use it as a legacy fill when this host has NO local unified.jsonl reading
    # (hermetic / peer-only FR #356 cases). Local n/a => Get-BobGrokAvailability.
    if ($null -eq $remain -and -not $week -and $Digest) {
        $remain = Get-BobTrayMachineGrokChatPcent -MachineId $MachineId -Digest $Digest
    }
    if ($null -ne $remain) {
        if ([int]$remain -gt 0) {
            return [pscustomobject]@{
                remaining    = [int]$remain
                fuel_mode    = 'pool'
                action       = 'start-pool'
                availability = 'available'
                reason       = 'legacy-remaining-pct'
            }
        }
        return [pscustomobject]@{
            remaining    = [int]$remain
            fuel_mode    = 'session-key'
            action       = 'prompt-session'
            availability = 'exhausted'
            reason       = 'legacy-remaining-pct-zero'
        }
    }
    $auth = $null
    if (Get-Command Get-BobGrokAuthSnapshot -ErrorAction SilentlyContinue) {
        try { $auth = Get-BobGrokAuthSnapshot } catch { $auth = $null }
    }
    $avail = $null
    if (Get-Command Get-BobGrokAvailability -ErrorAction SilentlyContinue) {
        try { $avail = Get-BobGrokAvailability -Weekly $week -Auth $auth } catch { $avail = $null }
    }
    if ($avail -and [string]$avail.state -eq 'available') {
        return [pscustomobject]@{
            remaining    = $null
            fuel_mode    = 'pool'
            action       = 'start-pool'
            availability = 'available'
            reason       = [string]$avail.reason
        }
    }
    if ($avail -and [string]$avail.state -eq 'exhausted') {
        return [pscustomobject]@{
            remaining    = 0
            fuel_mode    = 'session-key'
            action       = 'prompt-session'
            availability = 'exhausted'
            reason       = [string]$avail.reason
        }
    }
    $reason = 'unknown'
    $state = 'unknown'
    if ($avail) {
        $reason = [string]$avail.reason
        $state = [string]$avail.state
    }
    return [pscustomobject]@{
        remaining    = $null
        fuel_mode    = 'unknown'
        action       = 'stop-unknown'
        availability = $state
        reason       = $reason
    }
}

function Publish-BobTrayFuelMode {
    <#
      FR #356: report fuel_mode on the seat's machine entry. Never send the key.
    #>
    param(
        [Parameter(Mandatory = $true)][ValidateSet('pool', 'session-key', 'unknown')][string]$FuelMode,
        [string]$MachineId
    )
    $mid = [string]$MachineId
    if (-not $mid) { $mid = Get-BobTrayFuelLocalMachineId }
    if (-not $mid) {
        Write-TrayLog 'agents: fuel_mode publish skipped (no machine id)'
        return $false
    }
    try { $mid = [string](Resolve-BobiverseMachineId $mid) } catch { }
    $payload = [ordered]@{
        op        = 'merge'
        machine   = $mid
        online    = $true
        fuel_mode = $FuelMode
        fuel      = $FuelMode
    }
    $json = ($payload | ConvertTo-Json -Compress -Depth 5)
    if ($json -match '(?i)xai_api_key|password|sk-|Bearer') {
        Write-TrayLog 'agents: fuel_mode publish blocked (secret-like payload)'
        return $false
    }
    try {
        if (Get-Command Invoke-BobDigestWebhookMergePost -ErrorAction SilentlyContinue) {
            Invoke-BobDigestWebhookMergePost -Payload ([pscustomobject]$payload) | Out-Null
        }
        else {
            Invoke-RestMethod -Method Post -Uri (Get-BobTrayDigestReportUrl) -Body $json -ContentType 'application/json; charset=utf-8' -TimeoutSec 8 | Out-Null
        }
        Write-TrayLog ('agents: reported fuel_mode={0} machine={1}' -f $FuelMode, $mid)
        return $true
    }
    catch {
        Write-TrayLog ('agents: fuel_mode publish failed: ' + $_.Exception.Message)
        return $false
    }
}

function Get-BobTrayCursorFuelRemaining {
    # CAST IRON (Simon 2026-09-27): Cursor pool check is LOCAL Spending only
    # (Get-BobCursorAgentWeeklyRemaining / planUsage.autoPercentUsed). Never GET digest
    # or trust digest cursor_pools / pcent to decide whether a pool has remaining.
    if (Get-Command Get-BobCursorAgentWeeklyRemaining -ErrorAction SilentlyContinue) {
        try {
            $localDoc = Get-BobCursorAgentWeeklyRemaining
            if ($localDoc) {
                $fromLocal = $null
                if (Get-Command Get-BobCursorGroupRemainFromLocalDoc -ErrorAction SilentlyContinue) {
                    $fromLocal = Get-BobCursorGroupRemainFromLocalDoc -LocalCursorDoc $localDoc -GroupId 'auto'
                }
                if ($null -eq $fromLocal -and $null -ne $localDoc.remaining_pct -and [string]$localDoc.remaining_pct -ne '') {
                    try { $fromLocal = [int]$localDoc.remaining_pct } catch { }
                }
                if ($null -ne $fromLocal) { return [int]$fromLocal }
            }
        }
        catch { }
    }
    # Fallback: last TipForm snapshot (already local-preferring via Get-BobCursorPoolsForTray).
    $snap = $script:lastFuelSnapshot
    if (-not $snap) { return $null }
    $autoIds = @('auto', 'low-cost-models', 'cursor-models')
    $bestAuto = $null
    $bestAny = $null
    foreach ($p in @($snap.cursor_pools)) {
        if (-not $p) { continue }
        if ($null -eq $p.remaining_pct -or [string]$p.remaining_pct -eq '') { continue }
        try { $v = [int]$p.remaining_pct } catch { continue }
        if ($null -eq $bestAny -or $v -gt $bestAny) { $bestAny = $v }
        $gid = [string]$p.group_id
        if (-not $gid -and $p.id) { $gid = [string]$p.id }
        $gid = $gid.ToLowerInvariant()
        if ($autoIds -contains $gid) {
            if ($null -eq $bestAuto -or $v -gt $bestAuto) { $bestAuto = $v }
        }
    }
    if ($null -ne $bestAuto) { return $bestAuto }
    if ($null -ne $snap.account_remaining_pct -and [string]$snap.account_remaining_pct -ne '') {
        try { return [int]$snap.account_remaining_pct } catch { }
    }
    return $bestAny
}

function Test-BobTrayAgentFuelExhausted {
    param([string]$Kind)
    $k = ([string]$Kind).ToLowerInvariant()
    if ($k -eq 'grok') {
        # FR #356: blank/missing is NOT exhausted (dialog); it is unknown -> stop elsewhere.
        $decision = Resolve-BobTrayGrokFuelAtStart
        return ($decision.action -eq 'prompt-session')
    }
    $remain = $null
    if ($k -eq 'cursor') { $remain = Get-BobTrayCursorFuelRemaining }
    # Cursor: unknown/null local remaining => do not block (host may have no Cursor login).
    if ($null -eq $remain) { return $false }
    return ($remain -le 0)
}

function Show-BobTraySessionApiKeyDialog {
    param(
        [string]$Title = 'Session API key',
        [string]$Prompt = 'No remaining tokens. Enter an API key for this start only (not saved).'
    )
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $Title
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
    $form.MinimizeBox = $false
    $form.MaximizeBox = $false
    $form.ShowInTaskbar = $true
    $form.TopMost = $true
    $form.ClientSize = New-Object System.Drawing.Size 440, 150
    $lbl = New-Object System.Windows.Forms.Label
    $lbl.AutoSize = $false
    $lbl.Location = New-Object System.Drawing.Point 12, 12
    $lbl.Size = New-Object System.Drawing.Size 416, 48
    $lbl.Text = $Prompt
    $tb = New-Object System.Windows.Forms.TextBox
    $tb.Location = New-Object System.Drawing.Point 12, 68
    $tb.Size = New-Object System.Drawing.Size 416, 24
    $tb.UseSystemPasswordChar = $true
    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = 'OK'
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $ok.Location = New-Object System.Drawing.Point 272, 108
    $ok.Size = New-Object System.Drawing.Size 75, 28
    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = 'Cancel'
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $cancel.Location = New-Object System.Drawing.Point 353, 108
    $cancel.Size = New-Object System.Drawing.Size 75, 28
    $form.AcceptButton = $ok
    $form.CancelButton = $cancel
    $form.Controls.AddRange(@($lbl, $tb, $ok, $cancel))
    try {
        $result = $form.ShowDialog()
        if ($result -ne [System.Windows.Forms.DialogResult]::OK) { return $null }
        $key = [string]$tb.Text
        if ([string]::IsNullOrWhiteSpace($key)) { return $null }
        return $key.Trim()
    }
    finally {
        try { $tb.Text = '' } catch { }
        try { $form.Dispose() } catch { }
    }
}

function Start-BobTrayAgentWatch {
    param($Agent)
    if (-not (Test-BobTrayAgentMonitorReady)) {
        Initialize-BobTrayAgentSetup $Agent
        return
    }
    # #285 + CAST IRON (Simon 2026-09-27): hide the watch PowerShell host; agent TUI
    # must be visible (Build-BobWatchSeatLaunchArgs passes -Windows on, never off).
    # Direct -WatchWorker avoids an outer re-spawn.
    $ps1 = Join-Path $script:agentmonitorDir 'Watch-AgentHealth.exe'
    if (-not (Test-Path -LiteralPath $ps1)) {
        Write-TrayLog ('agents: missing Watch-AgentHealth.exe under ' + $script:agentMonitorDir)
        return
    }
    $slotHelpers = Join-Path $RepoRoot 'tools\Bob-WatchSeatSlot.ps1'
    if (-not (Test-Path -LiteralPath $slotHelpers)) {
        $slotHelpers = Join-Path $PSScriptRoot 'Bob-WatchSeatSlot.ps1'
    }
    if (Test-Path -LiteralPath $slotHelpers) {
        . $slotHelpers
    }
    else {
        Write-TrayLog 'agents: missing Bob-WatchSeatSlot.ps1 (FR #345)'
        return
    }
    $kind = ([string]$Agent.kind).ToLowerInvariant()
    $sessionEnv = $null
    if ($kind -eq 'grok') {
        # Local weekly first (CAST IRON); digest pcent only fills nulls.
        $fuel = Resolve-BobTrayGrokFuelAtStart
        if ($fuel.action -eq 'stop-unknown') {
            $why = if ($fuel.reason) { [string]$fuel.reason } else { 'unknown' }
            Write-TrayLog ('agents: grok fuel_mode=unknown reason={0} - refusing keyless start' -f $why)
            try { Publish-BobTrayFuelMode -FuelMode 'unknown' } catch { }
            try {
                [void][System.Windows.Forms.MessageBox]::Show(
                    ("Grok Build availability is {0} ({1}). Not exhausted - fix local auth/billing freshness, then retry. Do not enter an API key unless the pool is confirmed at 0%." -f $(if ($fuel.availability) { $fuel.availability } else { 'unknown' }), $why),
                    'Grok fuel unknown',
                    [System.Windows.Forms.MessageBoxButtons]::OK,
                    [System.Windows.Forms.MessageBoxIcon]::Warning
                )
            }
            catch { }
            return
        }
        if ($fuel.action -eq 'prompt-session') {
            Write-TrayLog 'agents: grok fuel remaining 0 - requesting session XAI_API_KEY dialog'
            $key = Show-BobTraySessionApiKeyDialog -Title 'Grok session API key' -Prompt "No Grok tokens remaining on this machine.`r`nEnter XAI_API_KEY for this start only (not saved; process-scoped for the child only)."
            if (-not $key) {
                Write-TrayLog 'agents: no tokens - dialog cancelled; nothing started'
                try { Publish-BobTrayFuelMode -FuelMode 'session-key' } catch { }
                try {
                    [void][System.Windows.Forms.MessageBox]::Show(
                        'no tokens',
                        'Grok seat',
                        [System.Windows.Forms.MessageBoxButtons]::OK,
                        [System.Windows.Forms.MessageBoxIcon]::Information
                    )
                }
                catch { }
                return
            }
            $sessionEnv = New-BobTrayGrokSessionEnv -ApiKey $key
            try { Publish-BobTrayFuelMode -FuelMode 'session-key' } catch { }
        }
        else {
            Write-TrayLog ('agents: grok fuel_mode=pool remaining={0}' -f $fuel.remaining)
            try { Publish-BobTrayFuelMode -FuelMode 'pool' } catch { }
        }
    }
    elseif (Test-BobTrayAgentFuelExhausted -Kind $kind) {
        if ($kind -eq 'cursor') {
            # cursor-agent supports --api-key / CURSOR_API_KEY (session BYOK).
            Write-TrayLog 'agents: cursor fuel remaining 0 - requesting session CURSOR_API_KEY dialog'
            $key = Show-BobTraySessionApiKeyDialog -Title 'Cursor session API key' -Prompt "No Cursor tokens remaining (auto / cursor_pools).`r`nEnter CURSOR_API_KEY for this start only (not saved; process-scoped for the child only)."
            if (-not $key) {
                Write-TrayLog 'agents: no tokens - dialog cancelled; nothing started'
                try {
                    [void][System.Windows.Forms.MessageBox]::Show(
                        'no tokens',
                        'Cursor seat',
                        [System.Windows.Forms.MessageBoxButtons]::OK,
                        [System.Windows.Forms.MessageBoxIcon]::Information
                    )
                }
                catch { }
                return
            }
            $sessionEnv = @{ CURSOR_API_KEY = $key }
        }
    }
    $ps = $ps1
    # FR #345: explicit next free slot + -IrcHome (pairs AgentMonitor #97)
    try {
        $pick = Resolve-BobWatchNextFreeSlot -Kind $kind -ExcludePid $PID
    }
    catch {
        Write-TrayLog ('agents: no free slot: ' + $_.Exception.Message)
        try {
            $script:notifyIcon.ShowBalloonTip(8000, 'Bob Fleet Agents', ('No free {0} watch slot' -f $kind), [System.Windows.Forms.ToolTipIcon]::Error)
        }
        catch { }
        return
    }
    New-Item -ItemType Directory -Force -Path $pick.IrcHome | Out-Null
    # CAST IRON (Simon 2026-09-23): tray/agent links ALWAYS -New (skills + prompt), never resume.
    # Cursor always --model auto (Simon 2026-09-23).
    # FR #369 / #102: always pass -Cwd (per-machine bob-seat-work; never live \ai).
    # FR #345: explicit slot + -IrcHome.
    $cwd = Get-BobTrayWatchWorkspace -FallbackRoot $script:agentMonitorDir
    $launchArgs = Build-BobWatchSeatLaunchArgs -ScriptPath $ps1 -Kind $kind -Slot $pick.Slot -IrcHome $pick.IrcHome -New -Cwd $cwd
    Write-TrayLog ('agents: launch {0} NEW slot={1} home={2} cwd={3} model={4} sessionKey={5}' -f $Agent.kind, $pick.Slot, $pick.IrcHome, $cwd, $(if ($kind -eq 'cursor') { 'auto' } else { 'n/a' }), $(if ($sessionEnv) { 'yes' } else { 'no' }))
    Write-BobTrayStartLog -Action 'tray-start' -Fields @{
        kind = $kind
        slot = $pick.Slot
        home = $pick.IrcHome
        cwd  = $cwd
    }
    $child = Start-BobTrayProcessWithSessionEnv -FilePath $ps -ArgumentList $launchArgs -WorkingDirectory $script:agentMonitorDir -SessionEnv $sessionEnv
    Watch-BobTrayAgentWatchEarlyExit -Process $child -Seconds 10 -BootstrapLog (Join-Path $env:TEMP 'Watch-AgentHealth-start.log')
    # Async verify (do not block tray UI long): background job checks identity
    $verifyScript = {
        param($Kind, $Slot, $SeatIrcHome, $Helpers, $RepoRoot)
        . $Helpers
        $v = Test-BobWatchSeatIdentityOk -Kind $Kind -Slot $Slot -ExpectedHome $SeatIrcHome -TimeoutSec 60
        $logLine = if ($v.ok) {
            'tray-verify-ok'
        }
        else {
            'tray-verify-fail'
        }
        Write-BobTrayStartLog -Action $logLine -Fields @{
            kind   = $Kind
            slot   = $Slot
            home   = $SeatIrcHome
            nick   = $v.nick
            reason = $v.reason
        }
        if (-not $v.ok) {
            $null = Stop-BobWatchSeatByHome -IrcHome $SeatIrcHome -Reason ('tray-verify-fail: ' + $v.reason)
        }
        return $v
    }
    try {
        Start-Job -ScriptBlock $verifyScript -ArgumentList @($kind, $pick.Slot, $pick.IrcHome, $slotHelpers, $RepoRoot) | Out-Null
    }
    catch {
        # Fallback synchronous short wait if jobs blocked
        $v = Test-BobWatchSeatIdentityOk -Kind $kind -Slot $pick.Slot -ExpectedHome $pick.IrcHome -TimeoutSec 15
        if (-not $v.ok) {
            Write-TrayLog ('agents: verify fail slot={0} {1}' -f $pick.Slot, $v.reason)
            try {
                $script:notifyIcon.ShowBalloonTip(10000, 'Bob Fleet Agents', ('Seat {0} identity failed: {1}' -f $pick.Slot, $v.reason), [System.Windows.Forms.ToolTipIcon]::Error)
            }
            catch { }
            [void](Stop-BobWatchSeatByHome -IrcHome $pick.IrcHome -Reason $v.reason)
        }
        else {
            Write-TrayLog ('agents: verify ok slot={0} nick={1}' -f $pick.Slot, $v.nick)
        }
    }
}

function Stop-BobTrayAgentWatchSeat {
    param(
        [ValidateSet('cursor', 'grok')][string]$Kind,
        [int]$Slot
    )
    $slotHelpers = Join-Path $RepoRoot 'tools\Bob-WatchSeatSlot.ps1'
    if (-not (Test-Path -LiteralPath $slotHelpers)) {
        $slotHelpers = Join-Path $PSScriptRoot 'Bob-WatchSeatSlot.ps1'
    }
    if (-not (Test-Path -LiteralPath $slotHelpers)) {
        Write-TrayLog 'agents: stop missing Bob-WatchSeatSlot.ps1'
        return
    }
    . $slotHelpers
    $seatHomePath = Get-BobWatchSeatHomePath -Kind $Kind -Slot $Slot
    $st = Read-BobWatchSeatState -StatePath (Get-BobWatchSeatStatePath -Kind $Kind -Slot $Slot)
    if ($st -and $st.ircHome) { $seatHomePath = [string]$st.ircHome }
    $stop = Stop-BobWatchSeatByHome -IrcHome $seatHomePath -Reason 'tray-stop'
    Write-BobTrayStartLog -Action 'tray-stop' -Fields @{
        kind   = $Kind
        slot   = $Slot
        home   = $seatHomePath
        ok     = $stop.ok
        killed = $stop.killed
        reason = $stop.reason
    }
    Write-TrayLog ('agents: stop {0} slot={1} ok={2} killed={3} {4}' -f $Kind, $Slot, $stop.ok, $stop.killed, $stop.reason)
    if (-not $stop.ok) {
        try {
            $script:notifyIcon.ShowBalloonTip(8000, 'Bob Fleet Agents', $stop.reason, [System.Windows.Forms.ToolTipIcon]::Warning)
        }
        catch { }
    }
}

function Invoke-BobTrayAgent {
    param($Agent)
    if (-not (Test-BobTrayAgentInstalled $Agent)) {
        Initialize-BobTrayAgentSetup $Agent
        return
    }
    if (-not (Test-BobTrayAgentMonitorReady)) {
        Initialize-BobTrayAgentSetup $Agent
        return
    }
    Start-BobTrayAgentWatch $Agent
}

function Get-BobTrayVisionaryCloneRoot {
    foreach ($c in @('D:\ai\skills-visionary', 'C:\ai\skills-visionary', 'C:\src\skills-visionary')) {
        if (Test-Path -LiteralPath (Join-Path $c '.grok\skills\visionary\SKILL.md')) {
            return [IO.Path]::GetFullPath($c)
        }
    }
    return $null
}

function Sync-BobTrayVisionarySkills {
    # Plan seats load visionary ONLY from https://github.com/SimonBarnett/skills-visionary
    # (sister pack may include git-setup slice; do not pull agentic_build skills here).
    $installer = Join-Path $RepoRoot 'tools\Install-VisionarySkills.ps1'
    if (-not (Test-Path -LiteralPath $installer)) {
        throw "missing $installer"
    }
    $ps = (Get-Command powershell.exe).Source
    $out = & $ps -NoProfile -ExecutionPolicy Bypass -File $installer -Pull 2>&1
    $code = $LASTEXITCODE
    foreach ($line in @($out)) { Write-TrayLog ('visionary: ' + $line) }
    $root = Get-BobTrayVisionaryCloneRoot
    if ($code -ne 0) {
        # A failed refresh must not block Plan when a previous skills-visionary copy exists:
        # launch with that copy and log the warning (the dialog is only for "nothing to load").
        if ($root) {
            Write-TrayLog ('plan: WARNING visionary sync failed (exit {0}); launching with existing copy {1}' -f $code, $root)
            return $root
        }
        $why = @(@($out) | ForEach-Object { [string]$_ } | Where-Object { $_ -match '\S' } | Select-Object -First 1)
        $detail = if ($why.Count) { ': ' + ([string]$why[0]).Trim() } else { '' }
        throw ('Install-VisionarySkills failed (exit {0}){1}' -f $code, $detail)
    }
    if ($root) { return $root }
    throw 'skills-visionary clone not found after sync'
}

function Resolve-BobTrayGrokCliExe {
    $p = Join-Path $env:USERPROFILE '.grok\bin\agent.exe'
    if (Test-Path -LiteralPath $p) { return $p }
    $cmd = Get-Command agent.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd -and $cmd.Source) { return [string]$cmd.Source }
    return $null
}

function Resolve-BobTrayCursorAgentCmd {
    $p = Join-Path $env:LOCALAPPDATA 'cursor-agent\agent.cmd'
    if (Test-Path -LiteralPath $p) { return $p }
    $cmd = Get-Command agent.cmd, cursor-agent.cmd -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd -and $cmd.Source) { return [string]$cmd.Source }
    return $null
}

function Initialize-BobTrayConsoleLauncher {
    # CreateProcess + CREATE_NEW_CONSOLE with an explicit child environment block.
    # .NET ProcessStartInfo cannot ask for a NEW console when UseShellExecute=false (needed for
    # child-only env), and Start-Process has no -Environment on PS 5.1.
    if ('BobTray.ConsoleLauncher' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
namespace BobTray {
public static class ConsoleLauncher {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct STARTUPINFO {
        public int cb; public string lpReserved; public string lpDesktop; public string lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct PROCESS_INFORMATION { public IntPtr hProcess, hThread; public int dwProcessId, dwThreadId; }
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool CreateProcessW(string app, StringBuilder cmd, IntPtr pa, IntPtr ta, bool inherit,
        uint flags, IntPtr env, string cwd, ref STARTUPINFO si, out PROCESS_INFORMATION pi);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    const uint CREATE_NEW_CONSOLE = 0x00000010;
    const uint CREATE_UNICODE_ENVIRONMENT = 0x00000400;
    public static int Start(string app, string commandLine, string cwd, string title, IDictionary overrides) {
        var env = new SortedDictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (DictionaryEntry e in Environment.GetEnvironmentVariables()) { env[(string)e.Key] = (string)e.Value; }
        if (overrides != null) {
            foreach (DictionaryEntry e in overrides) {
                string k = Convert.ToString(e.Key);
                if (e.Value == null) { env.Remove(k); } else { env[k] = Convert.ToString(e.Value); }
            }
        }
        var sb = new StringBuilder();
        foreach (var kv in env) { sb.Append(kv.Key).Append('=').Append(kv.Value).Append('\0'); }
        sb.Append('\0');
        IntPtr block = Marshal.StringToHGlobalUni(sb.ToString());
        sb.Clear();
        try {
            var si = new STARTUPINFO();
            si.cb = Marshal.SizeOf(typeof(STARTUPINFO));
            si.lpTitle = string.IsNullOrEmpty(title) ? null : title;
            PROCESS_INFORMATION pi;
            if (!CreateProcessW(app, new StringBuilder(commandLine), IntPtr.Zero, IntPtr.Zero, false,
                    CREATE_NEW_CONSOLE | CREATE_UNICODE_ENVIRONMENT, block,
                    string.IsNullOrEmpty(cwd) ? null : cwd, ref si, out pi)) {
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            }
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            return pi.dwProcessId;
        }
        finally { Marshal.FreeHGlobal(block); }
    }
}
}
'@
}

function Start-BobTrayVisibleProcessWithSessionEnv {
    # Plan seats: the TUI needs its OWN visible console window. The tray is a hidden powershell
    # (-WindowStyle Hidden) that owns a hidden console. ProcessStartInfo UseShellExecute=false +
    # CreateNoWindow=false does not create a console: the plan agent.exe attached to the tray's
    # hidden console and ran invisibly ("plan mode does not start"). Start-Process (no session key)
    # joined -ArgumentList unquoted on PS 5.1, splitting --rules into words.
    # Now: CreateProcess CREATE_NEW_CONSOLE, Windows-quoted args, session key only in the child's
    # environment block (never tray / User / Machine env, never on disk).
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [hashtable]$SessionEnv,
        [string]$Title = 'Plan seat'
    )
    Initialize-BobTrayConsoleLauncher
    $argStr = ConvertTo-BobTrayProcessArgumentString -ArgumentList $ArgumentList
    $app = $FilePath
    $cmdLine = ('"{0}" {1}' -f $FilePath, $argStr)
    if ([IO.Path]::GetExtension($FilePath) -match '^\.(cmd|bat)$') {
        # CreateProcess cannot run a batch file directly: cmd.exe /d /s /c ""x.cmd" args"
        $app = $env:ComSpec
        if (-not $app) { $app = Join-Path $env:WINDIR 'System32\cmd.exe' }
        $cmdLine = ('"{0}" /d /s /c ""{1}" {2}"' -f $app, $FilePath, $argStr)
    }
    $overrides = @{}
    if ($SessionEnv) {
        foreach ($k in @($SessionEnv.Keys)) { $overrides[[string]$k] = [string]$SessionEnv[$k] }
    }
    $childPid = [BobTray.ConsoleLauncher]::Start($app, $cmdLine, $WorkingDirectory, $Title, $overrides)
    $overrides = $null
    $proc = $null
    try { $proc = [System.Diagnostics.Process]::GetProcessById($childPid) }
    catch { $proc = [pscustomobject]@{ Id = $childPid; HasExited = $true } }
    Write-TrayLog ('plan: started pid={0} (own console) {1}' -f $childPid, (Split-Path -Leaf $FilePath))
    Register-BobTrayGrokSession -Process $proc -SessionEnv $SessionEnv
    return $childPid
}

function Start-BobTrayWorkerExe {
    <#
    .SYNOPSIS
      Tray Agent / Plan click (t762u): start a NEW bob-worker.exe, which picks cursor > grok > key-dialog by token availability.
    .DESCRIPTION
      One plain click, no submenu. Every click starts a FRESH agent: no resume / continue / attach to any earlier session, window or
      process (t765u). The exe is copied to %LOCALAPPDATA%\Bobiverse\worker\bin\bob-worker-<hash>.exe and THAT copy is run, so a running
      seat never locks <install>\worker\bob-worker.exe and an MSI upgrade / uninstall is never blocked by (or kills) a seat.
      ONE window per click: the exe's own console hosts the agent (the agent inherits it; no second console, no watcher window); the exe owns the IRC relay, !bored,
      IRC-loss exit and hang restarts, and ending either the exe or the agent ends both. Plan = exe --mode plan (no IRC).
    #>
    param([ValidateSet('agent', 'plan')][string]$Mode, [switch]$Quiet)
    try {
        # t815u: hard cap of 2 live workers per machine (tray click and remote !startworker alike)
        $capRefusal = Get-BobTrayWorkerCapRefusal
        if ($capRefusal) {
            Write-TrayLog ('{0}: refused: {1}' -f $Mode, $capRefusal)
            if (-not $Quiet) { try { [void][System.Windows.Forms.MessageBox]::Show($capRefusal, 'Bobiverse', 'OK', 'Information') } catch { } }
            return 0
        }
        $exe = Join-Path $RepoRoot 'worker\bob-worker.exe'
        if (-not (Test-Path -LiteralPath $exe)) {
            Write-TrayLog ('{0}: worker exe missing: {1} (reinstall the bob MSI)' -f $Mode, $exe)
            if (-not $Quiet) { try { [void][System.Windows.Forms.MessageBox]::Show(('bob-worker.exe is missing:{0}{1}{0}{0}Reinstall or upgrade the bob MSI.' -f "`n", $exe), 'Bobiverse', 'OK', 'Warning') } catch { } }
            return 0
        }
        $hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.Substring(0, 12).ToLowerInvariant()
        $binDir = Join-Path $env:LOCALAPPDATA 'Bobiverse\worker\bin'
        New-Item -ItemType Directory -Force -Path $binDir | Out-Null
        $run = Join-Path $binDir ('bob-worker-{0}.exe' -f $hash)
        if (-not (Test-Path -LiteralPath $run)) {
            Copy-Item -LiteralPath $exe -Destination $run -Force
            # FR #1643: defer delete while hashed run exe is still in use by a live seat (locked = leave for later).
            Get-ChildItem -LiteralPath $binDir -Filter 'bob-worker-*.exe' -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -ne $run } |
                ForEach-Object {
                    $old = $_.FullName
                    try {
                        $fs = [System.IO.File]::Open($old, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
                        $fs.Close(); $fs.Dispose()
                        Remove-Item -LiteralPath $old -Force -ErrorAction Stop
                    }
                    catch {
                        # in use / defer - seat still holds this bob-worker-<hash>.exe
                    }
                }
        }
        $argv = @('--mode', $Mode, '--install-root', $RepoRoot)
        $mid = Get-BobTrayMachineId
        if ($mid) { $argv += @('--machine-id', $mid) }
        # t787u: the tray is a hidden powershell that owns a HIDDEN console. ProcessStartInfo UseShellExecute=false +
        # CreateNoWindow=false does NOT create a console: the exe (and the agent that inherits its console) attached to the
        # tray's hidden console - the click "did nothing" (MarchHare 2026-10-02: the exe ran, grok started, no window).
        # CREATE_NEW_CONSOLE gives each click its OWN visible console: the exe's console IS the one agent window.
        $wd = Join-Path $RepoRoot $(if ($Mode -eq 'plan') { 'plan' } else { 'worker' })
        $title = ('Bob {0} - starting (closing this window ends the agent)' -f $Mode)
        $childPid = @(Start-BobTrayVisibleProcessWithSessionEnv -FilePath $run -ArgumentList $argv -WorkingDirectory $wd -Title $title)[-1]
        Write-TrayLog ('{0}: started bob-worker.exe pid={1} mode={2} own visible console (NEW agent every click; selection cursor>grok>key dialog)' -f $Mode, $childPid, $Mode)
        return [int]$childPid   # t810u: the remote !startworker path reports it
    }
    catch {
        Write-TrayLog ('{0}: start failed: {1}' -f $Mode, $_.Exception.Message)
        return 0
    }
}

$script:attention = $false
$script:attentionSeq = 0
$script:bobTrayGrokSessions = @()
$script:flashOn = $false
$script:lastAlerts = @()
$script:jobsPid = $null
$script:jobsOwned = $false
$script:hoverTitle = Get-BobTrayTitle -MachineId $env:BOB_MACHINE_ID
$script:hoverBody = $script:hoverTitle
$script:remainingPct = $null
# Last TipForm fuel snapshot from Update-Hover (machines / cursor_pools / account).
# Used by Start-BobTrayAgentWatch when deciding whether to prompt for a session API key.
$script:lastFuelSnapshot = $null
$script:alertKind = 'none'
$script:iconRectCache = $null
$script:cardClosed = $false
$script:tileHost = $null
$script:tip = $null
$script:tipRecreating = $false
$script:notifyTipText = ' '
$seen = @{
    watcher_down = $false
    grokbot_down = $false
    inbox        = @{}
    running      = @{}
    stall        = @{}
}

function Test-JobsWatcherUp {
    $hits = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match 'Watch-BobJobs\.ps1' -and
            $_.CommandLine -notmatch '(?i)-Once\b'
        })
    return $hits
}

function Test-IrcAgentUp {
    $hits = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match 'irc_agent\.py' -and
            $_.CommandLine -match 'bobiverse'
        })
    return $hits
}

function Test-BobiverseWatcherUp {
    $hits = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            ($_.CommandLine -match 'Watch-Bobiverse\.ps1' -or $_.CommandLine -match '_Watch-Bobiverse')
        })
    return $hits
}

function Get-BobTrayMachineId {
    $mid = $null
    try { $mid = Get-ThisMachineId } catch { }
    if (-not $mid) { $mid = [string]$env:BOB_MACHINE_ID }
    if (-not $mid) { $mid = [string]$env:COMPUTERNAME }
    if ($mid) { return $mid.ToLowerInvariant() }
    return $null
}

function Stop-BobiverseMoot {
    $mid = Get-BobTrayMachineId
    if ($mid) {
        $task = "_Watch-Bobiverse-$mid"
        try {
            Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
            Write-TrayLog "stopped scheduled task $task"
        }
        catch { }
    }
    foreach ($p in @(Test-BobiverseWatcherUp)) {
        try {
            Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue
            Write-TrayLog "killed Watch-Bobiverse pid=$($p.ProcessId)"
        }
        catch { }
    }
    foreach ($p in @(Test-IrcAgentUp)) {
        try {
            Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue
            Write-TrayLog "killed bobiverse irc_agent pid=$($p.ProcessId)"
        }
        catch { }
    }
}

function Start-BobiverseMootWrapper {
    $mid = Get-BobTrayMachineId
    if ($mid) {
        $task = "_Watch-Bobiverse-$mid"
        try {
            Start-ScheduledTask -TaskName $task -ErrorAction Stop
            Write-TrayLog "started scheduled task $task"
            return
        }
        catch { }
    }
    $ps = (Get-Command powershell.exe).Source
    $wrapId = Join-Path $RepoRoot ("tools\_Watch-Bobiverse-{0}.ps1" -f $mid)
    $wrap = Join-Path $RepoRoot 'tools\_Watch-Bobiverse.ps1'
    $file = $null
    if ($mid -and (Test-Path $wrapId)) { $file = $wrapId }
    elseif (Test-Path $wrap) { $file = $wrap }
    elseif (Test-Path $watchBobiverse) { $file = $watchBobiverse }
    if (-not $file) {
        Write-TrayLog 'no Watch-Bobiverse wrapper to start'
        return
    }
    Write-TrayLog "starting moot wrapper $file"
    Start-Process -FilePath $ps `
        -ArgumentList @('-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', $file) `
        -WorkingDirectory $RepoRoot -WindowStyle Hidden | Out-Null
}

function Select-BobTraySingleWatcher {
    # Idempotent tray start: keep ONE watcher (oldest root process), stop duplicates.
    # A hit whose parent is also a hit is the same watcher tree (wrapper -> inner), not a duplicate.
    param([object[]]$Hits, [string]$Label)
    $all = @($Hits | Where-Object { $null -ne $_ })
    if ($all.Count -eq 0) { return $null }
    $ids = @{}
    foreach ($h in $all) { $ids[[int]$h.ProcessId] = $true }
    $roots = @($all | Where-Object { -not $ids.ContainsKey([int]$_.ParentProcessId) } | Sort-Object CreationDate, ProcessId)
    if ($roots.Count -eq 0) { $roots = @($all | Sort-Object CreationDate, ProcessId) }
    $keep = $roots[0]
    foreach ($extra in @($roots | Select-Object -Skip 1)) {
        try {
            Stop-Process -Id ([int]$extra.ProcessId) -Force -ErrorAction SilentlyContinue
            Write-TrayLog ('{0}: stopped duplicate pid={1} (keeping pid={2})' -f $Label, $extra.ProcessId, $keep.ProcessId)
        }
        catch { }
    }
    return $keep
}

function Start-IrcWatcher {
    # PS 5.1: a one-element array returned from Test-BobiverseWatcherUp unrolls to a bare
    # CimInstance whose .Count is $null, so "$hits.Count -gt 0" was false and every tray
    # (re)start spawned a SECOND Watch-Bobiverse ear. Always wrap in @(...).
    $hits = @(Test-BobiverseWatcherUp)
    if ($hits.Count -gt 0) {
        $keep = Select-BobTraySingleWatcher -Hits $hits -Label 'irc watcher'
        Write-TrayLog ('irc watcher: reuse existing Watch-Bobiverse pid={0}' -f $keep.ProcessId)
        return
    }
    Start-BobiverseMootWrapper
}

function Get-BobTrayIrcNick {
    $mid = $env:BOB_MACHINE_ID
    if (-not $mid) {
        try {
            if (Get-Command Get-BobMachineId -ErrorAction SilentlyContinue) {
                $mid = Get-BobMachineId
            }
        }
        catch { }
    }
    if (-not $mid) { $mid = $env:COMPUTERNAME }
    $mid = ([string]$mid).Trim().ToLowerInvariant()
    if (-not $mid) { $mid = 'unknown' }
    return ('bob-{0}' -f $mid)
}

function Wait-BobTrayIrcOutboxDrained {
    # FR #453: poll until outbox no longer contains Marker (irc_agent accepted/sent it).
    param(
        [Parameter(Mandatory)][string]$OutboxPath,
        [Parameter(Mandatory)][string]$Marker,
        [int]$TimeoutSec = 30,
        [int]$PollMs = 250
    )
    $deadline = [datetime]::UtcNow.AddSeconds([Math]::Max(1, $TimeoutSec))
    while ([datetime]::UtcNow -lt $deadline) {
        if (-not (Test-Path -LiteralPath $OutboxPath)) {
            return [pscustomobject]@{ ok = $true; reason = 'missing' }
        }
        $raw = ''
        try { $raw = [IO.File]::ReadAllText($OutboxPath) } catch { }
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return [pscustomobject]@{ ok = $true; reason = 'empty' }
        }
        if ($raw.IndexOf($Marker, [StringComparison]::Ordinal) -lt 0) {
            return [pscustomobject]@{ ok = $true; reason = 'absent' }
        }
        Start-Sleep -Milliseconds ([Math]::Max(50, $PollMs))
    }
    return [pscustomobject]@{ ok = $false; reason = 'timeout' }
}

function Wait-BobTrayIrcAgentStopped {
    # After quit.request, prefer agent exit before force-kill (FR #453).
    param([int]$TimeoutSec = 10, [int]$PollMs = 250)
    $deadline = [datetime]::UtcNow.AddSeconds([Math]::Max(1, $TimeoutSec))
    while ([datetime]::UtcNow -lt $deadline) {
        $hits = @(Test-IrcAgentUp)
        if ($hits.Count -eq 0) {
            return [pscustomobject]@{ ok = $true; reason = 'stopped' }
        }
        Start-Sleep -Milliseconds ([Math]::Max(50, $PollMs))
    }
    return [pscustomobject]@{ ok = $false; reason = 'timeout' }
}

function Write-BobTrayIrcDepartureAnnounce {
    # agentic_irc #250 / FR #453: announce on #bobiverse BEFORE quit/disconnect.
    # Stale outbox backlog can bury the line for minutes; archive then write ONLY
    # the departure PRIVMSG so irc_agent drains it before PART/QUIT.
    param(
        [ValidateSet('Exit', 'Restart')]
        [string]$Reason = 'Exit',
        [string]$IrcHome,
        [int]$DrainTimeoutSec = 30
    )
    if (-not $IrcHome) { return [pscustomobject]@{ ok = $false; error = 'no_home' } }
    try {
        $nick = Get-BobTrayIrcNick
        $outbox = Join-Path $IrcHome 'outbox.txt'
        $msg = '{0}: tray {1} - logging off IRC (graceful PART/QUIT)' -f $nick, $Reason
        $line = 'PRIVMSG #bobiverse :{0}' -f $msg
        if (Test-Path -LiteralPath $outbox) {
            $len = 0
            try { $len = ([IO.FileInfo]$outbox).Length } catch { }
            if ($len -gt 0) {
                $stamp = [datetime]::UtcNow.ToString('yyyyMMdd-HHmmss')
                $bak = Join-Path $IrcHome ("outbox.bak-depart-{0}.txt" -f $stamp)
                try {
                    [IO.File]::Copy($outbox, $bak, $true)
                    Write-TrayLog ('irc departure archived outbox ({0} bytes) -> {1}' -f $len, $bak)
                }
                catch {
                    Write-TrayLog ('irc departure outbox archive failed: ' + $_.Exception.Message)
                }
            }
        }
        [IO.File]::WriteAllText($outbox, $line + "`n", (New-Object System.Text.UTF8Encoding $false))
        Write-TrayLog ('irc departure announce: {0}' -f $msg)
        $drain = Wait-BobTrayIrcOutboxDrained -OutboxPath $outbox -Marker $line -TimeoutSec $DrainTimeoutSec
        if (-not $drain.ok) {
            Write-TrayLog ('irc departure announce drain timeout ({0}s) - continuing quit' -f $DrainTimeoutSec)
        }
        else {
            Write-TrayLog ('irc departure announce drained ({0})' -f $drain.reason)
        }
        return [pscustomobject]@{ ok = [bool]$drain.ok; line = $line; drain = $drain }
    }
    catch {
        Write-TrayLog ('irc departure announce failed: ' + $_.Exception.Message)
        return [pscustomobject]@{ ok = $false; error = $_.Exception.Message }
    }
}

function Request-BobTrayIrcLogout {
    # CAST IRON (Simon 2026-09-27): closing systray must log off bob IRC account.
    # agentic_irc #250 / FR #453: announce + drain FIRST, then quit.request, wait
    # for irc_agent stop, then Stop-BobiverseMoot. Never kill before announce flush.
    # Use $ircHome - $HOME/$home is a read-only automatic variable in PowerShell.
    param(
        [ValidateSet('Exit', 'Restart')]
        [string]$Reason = 'Exit',
        [switch]$SkipAnnounce
    )
    $ircHome = $null
    try {
        if (Get-Command Get-BobIrcHome -ErrorAction SilentlyContinue) {
            $ircHome = Get-BobIrcHome
        }
    }
    catch { }
    if (-not $ircHome) {
        $ircHome = Join-Path $env:USERPROFILE '.bobiverse'
    }
    if ($ircHome -and (Test-Path -LiteralPath $ircHome)) {
        if (-not $SkipAnnounce) {
            Write-BobTrayIrcDepartureAnnounce -Reason $Reason -IrcHome $ircHome | Out-Null
        }
        try {
            $quitPath = Join-Path $ircHome 'agent.quit.request'
            Set-Content -LiteralPath $quitPath -Value ('tray-{0} {1:o}' -f $Reason.ToLowerInvariant(), [datetime]::UtcNow) -Encoding ascii
            Write-TrayLog ("irc logout: wrote {0}" -f $quitPath)
            $stopped = Wait-BobTrayIrcAgentStopped -TimeoutSec 10
            if ($stopped.ok) {
                Write-TrayLog 'irc logout: bobiverse irc_agent stopped after quit.request'
            }
            else {
                Write-TrayLog 'irc logout: irc_agent still up after quit.wait - Stop-BobiverseMoot will force'
            }
        }
        catch {
            Write-TrayLog ('irc logout quit.request failed: ' + $_.Exception.Message)
        }
    }
    try { Stop-BobiverseMoot } catch {
        Write-TrayLog ('irc logout Stop-BobiverseMoot: ' + $_.Exception.Message)
    }
}

function Restart-BobTrayWatcher {
    # CAST IRON: Restart uses the SAME bootstrap as Start (Start-BobFleetTray -ForceNew).
    # No separate Restart shortcut. No LLM.
    Write-TrayLog 'Restart: Start-BobFleetTray -ForceNew (same bootstrap as Start Menu)'
    try {
        $script:notifyIcon.ShowBalloonTip(8000, 'Bob Systray', 'Restarting (bootstrap + tidy)...', [System.Windows.Forms.ToolTipIcon]::Info)
    }
    catch { }
    # Log off IRC before this process dies (replacement will rejoin).
    # agentic_irc #250: same graceful announce+quit path as Exit (not a raw kill).
    try { Request-BobTrayIrcLogout -Reason Restart } catch { Write-TrayLog ('restart irc logout: ' + $_.Exception.Message) }
    $startTray = Join-Path $RepoRoot 'tools\Start-BobFleetTray.ps1'
    $ps = (Get-Command powershell.exe).Source
    if (Test-Path -LiteralPath $startTray) {
        Start-Process -FilePath $ps `
            -ArgumentList @('-NoProfile', '-STA', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', $startTray, '-RepoRoot', $RepoRoot, '-ForceNew') `
            -WorkingDirectory $RepoRoot -WindowStyle Hidden | Out-Null
    }
    else {
        Write-TrayLog 'Restart: Start-BobFleetTray.ps1 missing'
    }
    $ctx.ExitThread()
}

function Start-JobsWatcher {
    # Same PS 5.1 unroll bug as Start-IrcWatcher: wrap in @(...) so one existing
    # Watch-BobJobs is reused instead of spawning a duplicate on every tray start.
    $hits = @(Test-JobsWatcherUp)
    if ($hits.Count -gt 0) {
        $keep = Select-BobTraySingleWatcher -Hits $hits -Label 'jobs watcher'
        $script:jobsPid = [int]$keep.ProcessId
        $script:jobsOwned = $false
        return
    }
    # t784u: Watch-BobJobs.ps1 is not shipped in the bob MSI / vendored tray. Without this guard the tray spawned a hidden
    # powershell for the missing file every 30 s (MarchHare 2026-10-02 12:16Z log: 'started Watch-BobJobs pid=...' x N).
    if (-not (Test-Path -LiteralPath $watchJobs)) {
        if (-not $script:jobsMissingLogged) { Write-TrayLog "Watch-BobJobs.ps1 not installed ($watchJobs); not starting it"; $script:jobsMissingLogged = $true }
        return
    }
    $p = Start-Process -FilePath (Get-Command powershell.exe).Source `
        -ArgumentList @('-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', $watchJobs) `
        -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru
    $script:jobsPid = $p.Id
    $script:jobsOwned = $true
    Write-TrayLog "started Watch-BobJobs pid=$($p.Id)"
}

function Set-Attention([string[]]$alerts) {
    $script:lastAlerts = @($alerts)
    $script:attention = $true
    $script:attentionSeq = [int64]$script:attentionSeq + 1
    $text = ($alerts | Select-Object -First 1)
    if ($text.Length -gt 60) { $text = $text.Substring(0, 60) }
    Clear-BobNativeTip
    Write-TrayLog ($alerts -join ' | ')
}

function Update-Hover {
    try {
        $h = Get-BobTrayHover
        $script:hoverBody = [string]$h.body
        # FR #345: list each watch seat separately (nick + slot) on tooltip body
        try {
            $slotHelpers = Join-Path $RepoRoot 'tools\Bob-WatchSeatSlot.ps1'
            if (-not (Test-Path -LiteralPath $slotHelpers)) {
                $slotHelpers = Join-Path $PSScriptRoot 'Bob-WatchSeatSlot.ps1'
            }
            if (Test-Path -LiteralPath $slotHelpers) {
                . $slotHelpers
                $seatLines = @()
                foreach ($s in @(Get-BobWatchLiveSeatSummaries -Kind all)) {
                    $seatLines += ('seat {0}/{1}: {2}' -f $s.kind, $s.slot, $(if ($s.nick) { $s.nick } else { '(starting)' }))
                }
                if ($seatLines.Count -gt 0) {
                    $script:hoverBody = ($script:hoverBody + "`r`n" + ($seatLines -join "`r`n")).Trim()
                }
            }
        }
        catch { }
        $script:hoverTitle = [string]$h.title
        if (-not $script:hoverTitle) { $script:hoverTitle = Get-BobTrayTitle -MachineId $env:BOB_MACHINE_ID }
        if ($null -eq $h.remaining_pct -or $h.remaining_pct -eq '') { $script:remainingPct = $null }
        else { $script:remainingPct = [int]$h.remaining_pct }
        $script:lastFuelSnapshot = [pscustomobject]@{
            machine               = $(if ($h.machine) { [string]$h.machine } else { $null })
            remaining_pct         = $script:remainingPct
            machines              = @($h.machines)
            cursor_pools          = @($h.cursor_pools)
            account_remaining_pct = $h.account_remaining_pct
        }
        $paint = Get-BobTrayBarPaint -RemainingPct $script:remainingPct -BarWidth 392
        $script:alertKind = Get-BobTrayAlertKind -Alerts $script:lastAlerts -RemainingPct $script:remainingPct
        $short = [string]$h.short
        if ($script:attention) { $short = '! ' + $short }
        if ($short.Length -gt 63) { $short = $short.Substring(0, 63) }
        $script:notifyTipText = $short
        # t828u/t832u: bob-status.exe / bob-tray.exe paint from this snapshot (dashboard only, plus the tray's hover text + attention state).
        try {
            if (Get-Command Write-BobTrayStatusSnapshot -ErrorAction SilentlyContinue) {
                $snapModel = New-BobTrayStatusModel -Hover $h -AlertKind $script:alertKind -Alerts @($script:lastAlerts) -Version (Get-BobTrayProductVersionLabel) -Machine ([string]$env:BOB_MACHINE_ID) -Title $script:hoverTitle `
                    -Short $script:notifyTipText -Attention ([bool]$script:attention) -AttentionSeq ([int64]$script:attentionSeq) -Pulse ([bool]$paint.pulse)
                [void](Write-BobTrayStatusSnapshot -Root $RepoRoot -Model $snapModel)
            }
        }
        catch { Write-TrayLog ('status snapshot error: ' + $_.Exception.Message) }
        Clear-BobNativeTip
        if ($script:titleLabel) {
            $script:titleLabel.Text = $script:hoverTitle
            if ($script:jobsLabel) { $script:jobsLabel.Text = $(if ($h.jobs_text) { [string]$h.jobs_text } else { '' }) }
            if ($null -eq $h.account_remaining_pct -or [string]$h.account_remaining_pct -eq '') {
                if ($null -ne $h.account_overspend_pct) {
                    # Format-BobCursorAccountLabel will pick tip/overspend when RemainingPct empty
                }
            }
            Rebuild-BobTrayTiles -Machines @($h.machines) -CursorPools @($h.cursor_pools) -AccountName $h.account_name -AccountPct $h.account_remaining_pct -AccountLabel $h.account_label -AccountReset $h.account_reset_label -AccountOverageGbp $h.account_overage_gbp -ChairChannels @($h.chair_channels)
            if ($script:alertLabel) {
                $script:alertLabel.Text = ('alert: {0}' -f $script:alertKind)
                $yAlert = 40
                if ($script:tileHost) { $yAlert = $script:tileHost.Bottom + 8 }
                $script:alertLabel.Location = New-Object System.Drawing.Point 14, $yAlert
            }
            Update-BobTrayVersionLabelLayout
            if ((Test-BobTrayTipVisible) -and $script:alertLabel) {
                $bottom = $script:alertLabel.Bottom
                if ($script:versionLabel -and $script:versionLabel.Bottom -gt $bottom) { $bottom = $script:versionLabel.Bottom }
                $script:tip.Height = [Math]::Max(110, $bottom + 16)
            }
            if (-not $script:attention -and -not $paint.pulse -and $notify.Icon -ne $iconIdle) {
                $notify.Icon = $iconIdle
            }
        }
    }
    catch {
        Write-TrayLog ("hover error: " + $_.Exception.Message)
    }
}

function Clear-Attention {
    $script:attention = $false
    $script:flashOn = $false
    $notify.Icon = $iconIdle
    Update-Hover
}

function Clear-BobNativeTip {
    try {
        $flags = [Reflection.BindingFlags]'NonPublic,Instance'
        $w = $notify.GetType().GetField('window', $flags)
        $id = $notify.GetType().GetField('id', $flags)
        if (-not $w -or -not $id) { $notify.Text = ' '; return }
        $nw = $w.GetValue($notify)
        if (-not $nw) { $notify.Text = ' '; return }
        $hwnd = $nw.Handle
        $uid = [uint32]$id.GetValue($notify)
        [BobTrayUi.Shell]::ClearNotifyTip($hwnd, $uid)
        [BobTrayUi.Shell]::HideTooltipWindows()
        $notify.Text = ''
    }
    catch {
        try { $notify.Text = '' } catch { try { $notify.Text = ' ' } catch { } }
        try { [BobTrayUi.Shell]::HideTooltipWindows() } catch { }
    }
}

function Hide-BobTrayCard {
    $script:cardClosed = $true
    try {
        if (Test-BobTrayTipAlive) {
            $hidden = $false
            try { $hidden = [bool]$script:tip.TryHide() } catch { }
            if (-not $hidden) {
                try { if ($script:tip.Visible) { $script:tip.Hide() } } catch { }
            }
        }
    }
    catch {
        Write-TrayLog ('tip hide error: ' + $_.Exception.Message)
    }
    Clear-BobNativeTip
}

# t795u: Status is THE default action of the icon: the menu item (bold = default), left click and double click all run it.
function Invoke-BobTrayStatus {
    # t828u: Status is a compiled exe (instant, single-instance, reads the snapshot Update-Hover writes). The in-process card is the fallback
    # when tools\bob-status.exe is not installed. Update-Hover refreshes the snapshot; the exe re-reads it every 2 s while open.
    if ((Get-Command Start-BobTrayDialog -ErrorAction SilentlyContinue) -and (Start-BobTrayDialog -Root $RepoRoot -Name 'status')) { return }
    Update-Hover
    Show-BobTrayCard -Reason 'click'
}

# t804u: the ntsa logo badge shown by Acknowledge is assets\ntsa-gut-logo.png (Simon's avatar: braided red/orange/blue/green lines over
# green ">ntsa" on black; shipped in the repo, the pack and the work-tree sync). If the file is missing or unreadable the dialog simply
# has no picture; nothing is drawn in its place.
$script:ntsaGutLogoPath = Join-Path $RepoRoot 'assets\ntsa-gut-logo.png'

function Get-BobTrayLogoImage {
    if (Test-Path -LiteralPath $script:ntsaGutLogoPath) {
        try {
            $bytes = [IO.File]::ReadAllBytes($script:ntsaGutLogoPath)
            return [System.Drawing.Image]::FromStream((New-Object System.IO.MemoryStream (, $bytes)))
        }
        catch { Write-TrayLog ('logo load failed ' + $script:ntsaGutLogoPath + ': ' + $_.Exception.Message) }
    }
    else { Write-TrayLog ('logo missing: ' + $script:ntsaGutLogoPath) }
    return $null
}

# Acknowledge: clears the alert and shows the ntsa gut logo badge, "by Simon Barnett", and every installed product.
function Show-BobTrayAbout {
    # t828u: compiled exe first (opens at once, scans installs on its own thread, single-instance); the in-process dialog below is the fallback.
    if ((Get-Command Start-BobTrayDialog -ErrorAction SilentlyContinue) -and (Start-BobTrayDialog -Root $RepoRoot -Name 'about')) {
        Write-TrayLog 'about dialog: bob-about.exe started'
        return
    }
    try {
        if ($script:aboutForm -and -not $script:aboutForm.IsDisposed) {
            $script:aboutForm.Activate()
            $script:aboutForm.BringToFront()
            return
        }
        $rows = @(Get-BobInstallInfo -RepoRoot $RepoRoot)
        $text = Format-BobInstallInfo -Rows $rows
        $mid = [string]$env:BOB_MACHINE_ID
        $form = New-Object System.Windows.Forms.Form
        $form.Text = 'Bobiverse systray - about'
        $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
        $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
        $form.ClientSize = New-Object System.Drawing.Size 580, 440
        $form.MaximizeBox = $false
        $form.MinimizeBox = $false
        $form.TopMost = $true
        try { $form.Icon = $iconIdle } catch { }
        $logo = New-Object System.Windows.Forms.PictureBox
        $logo.Image = Get-BobTrayLogoImage
        $logo.BackColor = [System.Drawing.Color]::Black
        $logo.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
        $logo.Location = New-Object System.Drawing.Point 16, 16
        $logo.Size = New-Object System.Drawing.Size 96, 96
        $title = New-Object System.Windows.Forms.Label
        $title.Text = 'Bobiverse systray'
        $title.Font = New-Object System.Drawing.Font 'Segoe UI', 15, ([System.Drawing.FontStyle]::Bold)
        $title.AutoSize = $true
        $title.Location = New-Object System.Drawing.Point 128, 16
        $by = New-Object System.Windows.Forms.Label
        $by.Text = 'by Simon Barnett'
        $by.Font = New-Object System.Drawing.Font 'Segoe UI', 11
        $by.AutoSize = $true
        $by.Location = New-Object System.Drawing.Point 130, 52
        $ver = New-Object System.Windows.Forms.Label
        $ver.Text = ((Get-BobTrayProductVersionLabel) + '    machine: ' + $(if ($mid) { $mid } else { $env:COMPUTERNAME.ToLowerInvariant() }))
        $ver.Font = New-Object System.Drawing.Font 'Segoe UI', 9
        $ver.AutoSize = $true
        $ver.Location = New-Object System.Drawing.Point 130, 84
        $box = New-Object System.Windows.Forms.TextBox
        $box.Multiline = $true
        $box.ReadOnly = $true
        $box.ScrollBars = [System.Windows.Forms.ScrollBars]::Vertical
        $box.Font = New-Object System.Drawing.Font 'Consolas', 9
        $box.Text = $text
        $box.Location = New-Object System.Drawing.Point 16, 128
        $box.Size = New-Object System.Drawing.Size 548, 256
        $ok = New-Object System.Windows.Forms.Button
        $ok.Text = 'Close'
        $ok.Location = New-Object System.Drawing.Point 474, 398
        $ok.Add_Click({ $script:aboutForm.Close() })
        foreach ($c in @($logo, $title, $by, $ver, $box, $ok)) { $form.Controls.Add($c) }
        $form.AcceptButton = $ok
        $form.Add_FormClosed({ $script:aboutForm = $null })
        $form.Add_Shown({ $box.Select(0, 0); $ok.Focus() })
        $script:aboutForm = $form
        $form.Show()
        Write-TrayLog ('about dialog shown: ' + $rows.Count + ' install folder(s)')
    }
    catch { Write-TrayLog ('about dialog error: ' + $_.Exception.Message) }
}

# Close every dialog the tray owns: the pools card and the about dialog. Never throws.
function Close-BobTrayDialogs {
    # t828u: the compiled dialogs belong to this install: close the ones started from <root>\tools.
    try {
        foreach ($pr in @(Get-Process -Name 'bob-about', 'bob-status' -ErrorAction SilentlyContinue)) {
            try { if ($pr.Path -and $pr.Path.StartsWith((Join-Path $RepoRoot 'tools'), [StringComparison]::OrdinalIgnoreCase)) { [void]$pr.CloseMainWindow(); if (-not $pr.WaitForExit(500)) { $pr.Kill() } } } catch { }
        }
    } catch { }
    try { if ($script:aboutForm -and -not $script:aboutForm.IsDisposed) { $script:aboutForm.Close(); $script:aboutForm.Dispose() } } catch { }
    $script:aboutForm = $null
    try {
        if (Test-BobTrayTipAlive) {
            try { [void]$script:tip.TryHide() } catch { try { $script:tip.Hide() } catch { } }
            $script:tip.Dispose()
        }
    }
    catch { }
    $script:tip = $null
}

# t798u: Exit. 1) close dialogs + dispose the icon immediately, 2) leave the UI loop, 3) start the service stop detached
# (fire and forget: sc.exe in its own process, never waited for). Nothing else runs before the icon is gone.
function Invoke-BobTrayExit {
    $script:trayExitReason = 'Exit'
    Write-TrayLog 'Exit: close dialogs, dispose icon, exit UI, stop ircBob (detached)'
    [void](Invoke-BobTrayExitSequence `
            -CloseDialogs { Close-BobTrayDialogs } `
            -DisposeIcon { $notify.Visible = $false; $notify.Dispose() } `
            -ExitUi { $ctx.ExitThread() } `
            -StopService { [void](Stop-BobTrayService -ServiceName $script:trayServiceName) })
}

function Get-BobTrayCursorHelpTooltip {
    return (Get-BobTrayCursorGroupHelpTooltip -GroupId '')
}

function Get-BobTrayProductVersionLabel {
    $ver = [string]$env:BOBIVERSE_BOB_VERSION
    if (-not $ver.Trim()) {
        foreach ($cand in @(
                (Join-Path $RepoRoot 'VERSION'),
                (Join-Path $RepoRoot 'src\VERSION'),
                (Join-Path (Split-Path $RepoRoot -Parent) 'bob\VERSION'),
                ([string]$env:BOB_AI_ROOT + '\bob\VERSION')   # t780u (was a hard-coded C:\ai\bob; Start-BobTray sets BOB_AI_ROOT)
            )) {
            if ($cand -and (Test-Path -LiteralPath $cand)) {
                try {
                    $ver = ([string](Get-Content -LiteralPath $cand -TotalCount 1 -ErrorAction Stop)).Trim()
                    if ($ver) { break }
                }
                catch { }
            }
        }
    }
    if (-not $ver.Trim()) { $ver = 'unknown' }
    return ('bob {0}' -f $ver.Trim())
}

function Update-BobTrayVersionLabelLayout {
    if (-not $script:versionLabel -or -not $script:tip) { return }
    $script:versionLabel.Text = (Get-BobTrayProductVersionLabel)
    $y = 40
    if ($script:alertLabel) { $y = $script:alertLabel.Top }
    elseif ($script:tileHost) { $y = $script:tileHost.Bottom + 8 }
    # Right-align inside tip card (width 420, ~14px inset).
    $script:versionLabel.Location = New-Object System.Drawing.Point 14, $y
    try {
        $need = [int]$script:versionLabel.PreferredSize.Width
        $x = [Math]::Max(14, 420 - 14 - $need)
        $script:versionLabel.Location = New-Object System.Drawing.Point $x, $y
    }
    catch { }
}

function Format-BobTrayCursorOverspendLine {
    param($OverageGbp)
    if ($null -eq $OverageGbp -or [string]$OverageGbp -eq '') { return $null }
    $v = [double]$OverageGbp
    if ($v -le 0) { return $null }
    return ('overspend {0}{1:N2}' -f [char]0x00A3, $v)
}

function Add-BobTraySectionHeader {
    param(
        [int]$X,
        [int]$Y,
        [string]$Title,
        [System.Drawing.Image]$Icon,
        [switch]$WithHelp,
        $Agent,
        [string]$RightText,
        [System.Drawing.Color]$RightColor
    )
    $iconW = 0
    if ($Icon) {
        $pic = New-Object System.Windows.Forms.PictureBox
        $pic.Image = $Icon
        $pic.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
        $pic.Size = New-Object System.Drawing.Size 18, 18
        $pic.BackColor = [System.Drawing.Color]::Transparent
        $pic.Location = New-Object System.Drawing.Point $X, ($Y + 1)
        if ($Agent) {
            $pic.Cursor = [System.Windows.Forms.Cursors]::Hand
            $pic.Tag = $Agent
            $pic.Add_Click({ param($s, $e) Invoke-BobTrayAgent $s.Tag })
        }
        $script:tileHost.Controls.Add($pic)
        $iconW = 22
    }
    $nm = New-Object System.Windows.Forms.Label
    $nm.AutoSize = $true
    $nm.Font = New-Object System.Drawing.Font 'Segoe UI Semibold', 9.5
    $nm.ForeColor = $fg
    $nm.BackColor = [System.Drawing.Color]::Transparent
    $nm.Text = $Title
    $nm.Location = New-Object System.Drawing.Point ($X + $iconW), $Y
    if ($Agent) {
        $nm.Cursor = [System.Windows.Forms.Cursors]::Hand
        $nm.Tag = $Agent
        $nm.Add_Click({ param($s, $e) Invoke-BobTrayAgent $s.Tag })
    }
    $script:tileHost.Controls.Add($nm)
    if ($WithHelp) {
        $helpX = ($X + $iconW) + $nm.PreferredWidth + 6
        $help = New-Object System.Windows.Forms.Label
        $help.AutoSize = $true
        $help.Text = '?'
        $help.Font = New-Object System.Drawing.Font 'Segoe UI Semibold', 9
        $help.ForeColor = $muted
        $help.BackColor = [System.Drawing.Color]::Transparent
        $help.Cursor = [System.Windows.Forms.Cursors]::Hand
        $help.Location = New-Object System.Drawing.Point $helpX, ($Y + 1)
        $script:tileHost.Controls.Add($help)
        Set-BobTrayHelpTip -Control $help -Text (Get-BobTrayCursorHelpTooltip)
    }
    if ($RightText) {
        $rt = New-Object System.Windows.Forms.Label
        $rt.AutoSize = $true
        $rt.Font = New-Object System.Drawing.Font 'Segoe UI Semibold', 9
        if ($null -ne $RightColor -and $RightColor.A -gt 0) { $rt.ForeColor = $RightColor }
        else { $rt.ForeColor = [System.Drawing.Color]::FromArgb(248, 81, 73) }
        $rt.BackColor = [System.Drawing.Color]::Transparent
        $rt.Text = $RightText
        # Right-align inside the tile host (392px), not past the TipForm edge.
        $hostW = 392
        if ($script:tileHost -and $script:tileHost.ClientSize.Width -gt 40) {
            $hostW = $script:tileHost.ClientSize.Width
        }
        $textW = [System.Windows.Forms.TextRenderer]::MeasureText(
            $RightText,
            $rt.Font,
            [System.Drawing.Size]::Empty,
            [System.Windows.Forms.TextFormatFlags]::NoPadding
        ).Width
        $x = [Math]::Max(0, $hostW - $textW - 2)
        $rt.Location = New-Object System.Drawing.Point $x, $Y
        $script:tileHost.Controls.Add($rt)
    }
    return ($Y + 22)
}

function Set-BobTrayHelpTip {
    param($Control, [string]$Text)
    if (-not $Control -or -not $Text) { return }
    if (-not $script:bobTrayHelpTip) {
        $script:bobTrayHelpTip = New-Object System.Windows.Forms.ToolTip
        $script:bobTrayHelpTip.ShowAlways = $true
        $script:bobTrayHelpTip.UseAnimation = $false
        $script:bobTrayHelpTip.UseFading = $false
        $script:bobTrayHelpTip.InitialDelay = 200
        $script:bobTrayHelpTip.ReshowDelay = 100
        $script:bobTrayHelpTip.AutoPopDelay = 30000
        $script:bobTrayHelpTip.IsBalloon = $false
    }
    $script:bobTrayHelpTip.SetToolTip($Control, $Text)
    $Control.Tag = $Text
    $Control.Add_MouseHover({
            param($s, $e)
            try {
                $tip = [string]$s.Tag
                if ($tip -and $script:bobTrayHelpTip) {
                    $script:bobTrayHelpTip.Show($tip, $s, 0, $s.Height, 30000)
                }
            } catch { }
        })
    $Control.Add_MouseLeave({
            param($s, $e)
            try { if ($script:bobTrayHelpTip) { $script:bobTrayHelpTip.Hide($s) } } catch { }
        })
}

function Add-BobTrayUsageRow {
    param(
        [int]$X,
        [int]$Y,
        [string]$Heading,
        $RemainingPct,
        [int]$BarWidth,
        [System.Drawing.Image]$Icon,
        $HeadingColor,
        [string]$HelpText
    )
    $nameFont = New-Object System.Drawing.Font 'Segoe UI Semibold', 9
    $iconW = 0
    if ($Icon) {
        $pic = New-Object System.Windows.Forms.PictureBox
        $pic.Image = $Icon
        $pic.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::CenterImage
        $pic.Size = New-Object System.Drawing.Size 16, 16
        $pic.BackColor = [System.Drawing.Color]::Transparent
        $pic.Location = New-Object System.Drawing.Point $X, ($Y + 2)
        $script:tileHost.Controls.Add($pic)
        $iconW = 20
    }
    $nm = New-Object System.Windows.Forms.Label
    $nm.AutoSize = $true
    $nm.Font = $nameFont
    if ($null -ne $HeadingColor) { $nm.ForeColor = $HeadingColor }
    else { $nm.ForeColor = $fg }
    $nm.BackColor = [System.Drawing.Color]::Transparent
    $nm.Text = $Heading
    $nm.Location = New-Object System.Drawing.Point ($X + $iconW), $Y
    $script:tileHost.Controls.Add($nm)
    if ($HelpText) {
        $helpX = ($X + $iconW) + $nm.PreferredWidth + 6
        $help = New-Object System.Windows.Forms.Label
        $help.AutoSize = $true
        $help.Text = '?'
        $help.Font = New-Object System.Drawing.Font 'Segoe UI Semibold', 9
        $help.ForeColor = $muted
        $help.BackColor = [System.Drawing.Color]::Transparent
        $help.Cursor = [System.Windows.Forms.Cursors]::Hand
        $help.Location = New-Object System.Drawing.Point $helpX, ($Y + 1)
        $script:tileHost.Controls.Add($help)
        Set-BobTrayHelpTip -Control $help -Text $HelpText
    }
    $barY = $Y + 20
    $barX = $X + $iconW
    $bar = New-Object System.Windows.Forms.Panel
    $bar.Location = New-Object System.Drawing.Point $barX, $barY
    $bar.Size = New-Object System.Drawing.Size $BarWidth, 10
    $bar.BackColor = $bg
    $bar.Tag = $RemainingPct
    $bar.Visible = $true
    $bar.Add_Paint({
            param($s, $e)
            $p = Get-BobTrayBarPaint -RemainingPct $s.Tag -BarWidth $s.Width
            $g = $e.Graphics
            $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
            $track = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(48, 54, 61))
            $pathT = New-Object System.Drawing.Drawing2D.GraphicsPath
            Add-RoundRect $pathT 0 0 $s.Width 10 5
            $g.FillPath($track, $pathT)
            if ($p.known -and $p.show_fill -and $null -ne $p.fill_width -and $p.fill_width -gt 0) {
                $col = [System.Drawing.Color]::FromArgb([int]$p.fill_r, [int]$p.fill_g, [int]$p.fill_b)
                $fill = New-Object System.Drawing.SolidBrush $col
                $pathF = New-Object System.Drawing.Drawing2D.GraphicsPath
                Add-RoundRect $pathF 1 1 $p.fill_width 8 4
                $g.FillPath($fill, $pathF)
                $pathF.Dispose(); $fill.Dispose()
            }
            $pathT.Dispose(); $track.Dispose()
        })
    $script:tileHost.Controls.Add($bar)
    return ($barY + 14)
}

function Rebuild-BobTrayTiles {
    param($Machines, $CursorPools, $AccountName, $AccountPct, $AccountLabel, $AccountReset, $AccountOverageGbp, $ChairChannels)
    if (-not $script:tileHost) { return }

    # Format everything first so a throw never leaves a cleared host.
    $y = 0
    $jobFont = New-Object System.Drawing.Font 'Segoe UI', 9
    $cursorAgent = $null
    $grokAgent = $null
    foreach ($a in Get-BobTrayAgentDefs) {
        if ($a.kind -eq 'cursor') { $cursorAgent = $a }
        if ($a.kind -eq 'grok') { $grokAgent = $a }
    }
    $cursorIcon = $null
    $grokIcon = $null
    if ($cursorAgent) {
        try { $cursorIcon = Get-BobTrayAgentImage -Agent $cursorAgent -Installed (Test-BobTrayAgentInstalled $cursorAgent) } catch { }
    }
    if ($grokAgent) {
        try { $grokIcon = Get-BobTrayAgentImage -Agent $grokAgent -Installed (Test-BobTrayAgentInstalled $grokAgent) } catch { }
    }

    # Build into a staging panel, then swap - never Controls.Clear on the live host
    # while the TipForm is visible (that flashed a blank "new" dialog on poll).
    $stage = New-Object System.Windows.Forms.Panel
    $stage.Location = $script:tileHost.Location
    $stage.Width = $script:tileHost.Width
    $stage.BackColor = $bg
    $stage.AutoScroll = $false
    Enable-BobDoubleBuffer -Control $stage
    $oldHost = $script:tileHost
    $script:tileHost = $stage
    try {
        # #42: no separate ChanServ section. The ChanServ-registered channels ARE the
        # 'Grok accounts' rows below: one per digest roster machine, keyed by machine id.
        $overLine = Format-BobTrayCursorOverspendLine -OverageGbp $AccountOverageGbp
        $overColor = [System.Drawing.Color]::FromArgb(248, 81, 73)
        $y = Add-BobTraySectionHeader -X 0 -Y $y -Title 'Cursor' -Icon $cursorIcon -WithHelp -Agent $cursorAgent `
            -RightText $overLine -RightColor $overColor
        $pools = @($CursorPools)
        if ($pools.Count -eq 0) {
            $acctName = 'cursor'
            if ($AccountName) { $acctName = [string]$AccountName }
            $acctLabel = $null
            if ($AccountLabel) { $acctLabel = [string]$AccountLabel }
            else {
                try { $acctLabel = Format-BobCursorAccountLabel -RemainingPct $AccountPct -UsedPct $null }
                catch { $acctLabel = 'empty' }
            }
            $acctColor = $null
            if ($acctLabel -and ($acctLabel -match '^-' -or $acctLabel.IndexOf([char]0x00A3) -ge 0)) {
                $acctColor = [System.Drawing.Color]::FromArgb(248, 81, 73)
            }
            $acctHeading = ('{0} ({1})' -f $acctName, $acctLabel)
            if ($AccountReset) { $acctHeading = ('{0} - {1}' -f $acctHeading, [string]$AccountReset) }
            $y = Add-BobTrayUsageRow -X 0 -Y $y -Heading $acctHeading `
                -RemainingPct $AccountPct -BarWidth 392 -Icon $null -HeadingColor $acctColor
            $y += 6
        }
        else {
            # Indent Cursor spending groups like machine tiles under Grok accounts.
            $indent = 18
            # Always show every pool (incl. 0%). When low-cost is 0 but another pool still has %,
            # keep that bar visible so operators see what still allows spend.
            foreach ($pool in $pools) {
                if (-not $pool) { continue }
                $heading = [string]$pool.heading
                if (-not $heading) { continue }
                $poolColor = $null
                $pctLbl = [string]$pool.pct_label
                if ($pctLbl -and ($pctLbl -match '^-' -or $pctLbl.IndexOf([char]0x00A3) -ge 0)) {
                    $poolColor = [System.Drawing.Color]::FromArgb(248, 81, 73)
                }
                $poolPct = $pool.remaining_pct
                $help = $null
                try {
                    $gid = [string]$pool.group_id
                    if (-not $gid -and $pool.id) { $gid = [string]$pool.id }
                    $help = Get-BobTrayCursorGroupHelpTooltip -GroupId $gid
                } catch { $help = Get-BobTrayCursorHelpTooltip }
                $y = Add-BobTrayUsageRow -X $indent -Y $y -Heading $heading `
                    -RemainingPct $poolPct -BarWidth 354 -Icon $null -HeadingColor $poolColor -HelpText $help
                $y += 4
            }
            $y += 2
        }
        $y += 4
        $y = Add-BobTraySectionHeader -X 0 -Y $y -Title 'Grok accounts' -Icon $grokIcon -Agent $grokAgent
        $indent = 18
        $shownMachines = @{}
        foreach ($m in @($Machines)) {
            if (-not $m) { continue }
            $id = [string]$m.id
            $resolved = $null
            try { $resolved = Get-BobCanonicalMachineId $id } catch { $resolved = $id }
            if (-not $resolved) { continue }
            # v0.1.19 (#79): one row per CANONICAL machine, whatever alias the source row carried.
            if ($shownMachines.ContainsKey([string]$resolved)) { continue }
            $shownMachines[[string]$resolved] = $true
            $id = ([string]$resolved).ToUpperInvariant()
            $pct = $m.remaining_pct
            # 0% is real (#179). Unknown/stale (period over) is hidden, never "n/a" or a stale reset.
            $pctLabel = $null
            if ($null -ne $pct -and [string]$pct -ne '') { $pctLabel = ('{0}%' -f [int]$pct) }
            $seat = [string]$m.seat_label
            if (-not $seat) { $seat = [string]$m.seat_email }
            $nameHeading = $id
            if ($seat) { $nameHeading = ('{0}  -  {1}' -f $id, $seat) }
            $machHeading = $nameHeading
            if ($pctLabel) { $machHeading = ('{0} ({1})' -f $nameHeading, $pctLabel) }
            if ($pctLabel -and $m.reset_label) { $machHeading = ('{0} - {1}' -f $machHeading, [string]$m.reset_label) }
            $y = Add-BobTrayUsageRow -X $indent -Y $y -Heading $machHeading `
                -RemainingPct $pct -BarWidth 354 -Icon $null
            # v0.1.18: ONE line per worker process on this machine, "{irc nick}: {doing|idle}".
            # Fleet-wide Cursor values are shown ONCE in the Cursor section above, not repeated here.
            $wLines = @($m.worker_lines | Where-Object { $_ })
            $jobTxt = ($wLines -join "`n")
            if (-not $jobTxt) { $y += 4; continue }
            $jl = New-Object System.Windows.Forms.Label
            $jl.AutoSize = $true
            $jl.MaximumSize = New-Object System.Drawing.Size 392, 0
            $jl.Font = $jobFont
            $jl.ForeColor = $fg
            $jl.BackColor = [System.Drawing.Color]::Transparent
            $jl.Text = $jobTxt
            $jl.Location = New-Object System.Drawing.Point ($indent + 14), $y
            $script:tileHost.Controls.Add($jl)
            $nLines = @($jobTxt -split "`n").Count
            $y += [Math]::Max(18, (16 * $nLines) + 8)
        }
        $script:tileHost.Height = [Math]::Max(10, $y)
    }
    catch {
        $script:tileHost = $oldHost
        try { $stage.Dispose() } catch { }
        throw
    }

    # Atomic swap on the TipForm: add stage, remove old - live card never empty.
    try {
        if ($script:tip -and -not $script:tip.IsDisposed) {
            $idx = $script:tip.Controls.GetChildIndex($oldHost)
            $script:tip.Controls.Add($stage)
            if ($idx -ge 0) { $script:tip.Controls.SetChildIndex($stage, $idx) }
            $script:tip.Controls.Remove($oldHost)
        }
        try { $oldHost.Dispose() } catch { }
    }
    catch {
        $script:tileHost = $oldHost
        try { $stage.Dispose() } catch { }
        Write-TrayLog ('tile swap error: ' + $_.Exception.Message)
    }
}

$bg = [System.Drawing.Color]::FromArgb(22, 27, 34)
$fg = [System.Drawing.Color]::FromArgb(230, 237, 243)
$muted = [System.Drawing.Color]::FromArgb(139, 148, 158)
$script:tip = $null

function Initialize-BobTrayTipForm {
    if (Test-BobTrayTipAlive) { return }
    if ($script:tip) {
        try { $script:tip.Dispose() } catch { }
        $script:tip = $null
    }
    $script:tip = New-Object BobTrayUi.TipForm
    $script:tip.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $script:tip.ControlBox = $false
    $script:tip.ShowInTaskbar = $false
    $script:tip.TopMost = $true
    $script:tip.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $script:tip.BackColor = $bg
    $script:tip.Padding = New-Object System.Windows.Forms.Padding 14
    $script:tip.Width = 420
    Enable-BobDoubleBuffer -Control $script:tip
    $script:titleLabel = New-Object System.Windows.Forms.Label
    $script:titleLabel.AutoSize = $true
    $script:titleLabel.Font = New-Object System.Drawing.Font 'Segoe UI Semibold', 11
    $script:titleLabel.ForeColor = $fg
    $script:titleLabel.Text = $script:hoverTitle
    $script:titleLabel.Location = New-Object System.Drawing.Point 14, 12
    $script:closeBtn = New-Object System.Windows.Forms.Label
    $script:closeBtn.AutoSize = $true
    $script:closeBtn.Text = 'X'
    $script:closeBtn.Font = New-Object System.Drawing.Font 'Segoe UI Semibold', 10
    $script:closeBtn.ForeColor = $muted
    $script:closeBtn.Cursor = [System.Windows.Forms.Cursors]::Hand
    $script:closeBtn.Location = New-Object System.Drawing.Point 392, 10
    $script:closeBtn.Add_Click({ Hide-BobTrayCard })
    $script:barCaption = New-Object System.Windows.Forms.Label
    $script:barCaption.AutoSize = $true
    $script:barCaption.Font = New-Object System.Drawing.Font 'Segoe UI', 8.5
    $script:barCaption.ForeColor = $muted
    $script:barCaption.Text = 'Weekly remaining  n/a'
    $script:barCaption.Location = New-Object System.Drawing.Point 14, 40
    $script:barCaption.Visible = $false
    $script:barPanel = New-Object System.Windows.Forms.Panel
    $script:barPanel.Location = New-Object System.Drawing.Point 14, 62
    $script:barPanel.Size = New-Object System.Drawing.Size 392, 10
    $script:barPanel.BackColor = $bg
    $script:barPanel.Visible = $false
    $script:jobsLabel = New-Object System.Windows.Forms.Label
    $script:jobsLabel.AutoSize = $true
    $script:jobsLabel.MaximumSize = New-Object System.Drawing.Size 392, 0
    $script:jobsLabel.Font = New-Object System.Drawing.Font 'Segoe UI', 9
    $script:jobsLabel.ForeColor = $fg
    $script:jobsLabel.Location = New-Object System.Drawing.Point 14, 62
    $script:jobsLabel.Text = ''
    $script:jobsLabel.Visible = $false
    $script:tileHost = New-Object System.Windows.Forms.Panel
    $script:tileHost.Location = New-Object System.Drawing.Point 14, 38
    $script:tileHost.Size = New-Object System.Drawing.Size 392, 10
    $script:tileHost.BackColor = $bg
    Enable-BobDoubleBuffer -Control $script:tileHost
    $script:alertLabel = New-Object System.Windows.Forms.Label
    $script:alertLabel.AutoSize = $true
    $script:alertLabel.Font = New-Object System.Drawing.Font 'Segoe UI', 8
    $script:alertLabel.ForeColor = $muted
    $script:alertLabel.Location = New-Object System.Drawing.Point 14, 86
    $script:alertLabel.Text = 'alert: none'
    $script:versionLabel = New-Object System.Windows.Forms.Label
    $script:versionLabel.AutoSize = $true
    $script:versionLabel.Font = New-Object System.Drawing.Font 'Segoe UI', 8
    $script:versionLabel.ForeColor = $muted
    $script:versionLabel.Text = (Get-BobTrayProductVersionLabel)
    $script:versionLabel.Location = New-Object System.Drawing.Point 300, 86
    $script:tip.Controls.Add($script:titleLabel)
    $script:tip.Controls.Add($script:closeBtn)
    $script:tip.Controls.Add($script:barCaption)
    $script:tip.Controls.Add($script:barPanel)
    $script:tip.Controls.Add($script:jobsLabel)
    $script:tip.Controls.Add($script:tileHost)
    $script:tip.Controls.Add($script:alertLabel)
    $script:tip.Controls.Add($script:versionLabel)
    $script:tip.Add_Shown({
            if (Test-BobTrayTipAlive -and $script:alertLabel) {
                Update-BobTrayVersionLabelLayout
                $script:tip.Height = [Math]::Max($script:alertLabel.Bottom, $(if ($script:versionLabel) { $script:versionLabel.Bottom } else { 0 })) + 16
            }
        })
}

Initialize-BobTrayTipForm

function Show-BobTrayCard {
    param([string]$Reason = 'click')
    try {
        # Click / Status only. No hover events. Stay parked until X.
        if ($Reason -ne 'click') { return }
        $script:cardClosed = $false
        if (-not (Test-BobTrayTipAlive)) {
            Initialize-BobTrayTipForm
            Write-TrayLog 'tip recreated after dispose'
        }
        if (Test-BobTrayTipVisible) { return }
        Clear-BobNativeTip
        try { $script:iconRectCache = Get-BobNotifyIconRect $notify } catch { }
        # Paint from the last poll. Do not Get-BobTrayHover here: peer DNS/UNC
        # would freeze the UI and the native "P+ idle" tip would win.
        $bottom = 110
        if ($script:jobsLabel) { $bottom = $script:jobsLabel.Bottom }
        if ($script:tileHost) { $bottom = $script:tileHost.Bottom }
        if ($script:alertLabel) { $bottom = $script:alertLabel.Bottom }
        Update-BobTrayVersionLabelLayout
        if ($script:versionLabel -and $script:versionLabel.Bottom -gt $bottom) { $bottom = $script:versionLabel.Bottom }
        $script:tip.Height = [Math]::Max(110, $bottom + 16)
        # Park once on click. Stay in that place until X. No hideTip.
        if (-not (Test-BobTrayTipVisible)) {
            $iconRect = $script:iconRectCache
            $pt = [System.Windows.Forms.Cursor]::Position
            $work = [System.Windows.Forms.Screen]::FromPoint($pt).WorkingArea
            $place = Get-BobTrayTipPlacement -TipWidth $script:tip.Width -TipHeight $script:tip.Height `
                -IconRect $iconRect -Cursor $pt -WorkArea $work -AlreadyVisible $false
            $script:tip.Location = New-Object System.Drawing.Point ([int]$place.x), ([int]$place.y)
            $shown = $false
            try {
                $shown = [bool]$script:tip.ShowParkedAt([int]$place.x, [int]$place.y)
            }
            catch {
                Write-TrayLog ("tip ShowParkedAt error reason=${Reason}: " + $_.Exception.Message)
                if ($_.Exception.Message -match 'disposed') {
                    try { if ($script:tip) { $script:tip.Dispose() } } catch { }
                    $script:tip = $null
                    if (-not $script:tipRecreating) {
                        $script:tipRecreating = $true
                        try { Show-BobTrayCard -Reason 'click' }
                        finally { $script:tipRecreating = $false }
                    }
                    return
                }
            }
            # Do not call Form.Show() after ShowParkedAt - that is a second dialog.
            if (-not (Test-BobTrayTipVisible)) {
                $handle = $false
                $loc = '?'
                try {
                    $handle = $script:tip.IsHandleCreated
                    $loc = "$($script:tip.Left),$($script:tip.Top)"
                }
                catch { }
                Write-TrayLog ("tip show fail reason=$Reason visible=false handle=$handle loc=$loc src=$($place.source) parked=$shown")
            }
            else {
                Write-TrayLog ("tip show ok reason=$Reason src=$($place.source) loc=$($script:tip.Left),$($script:tip.Top) size=$($script:tip.Width)x$($script:tip.Height)")
            }
        }
    }
    catch {
        Write-TrayLog ("tip show error reason=${Reason}: " + $_.Exception.Message)
        if ($_.Exception.Message -match 'disposed') {
            try { if ($script:tip) { $script:tip.Dispose() } } catch { }
            $script:tip = $null
        }
    }
}

$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = $iconIdle
$notify.Visible = $false
$notify.Text = ''
$menu = New-Object System.Windows.Forms.ContextMenuStrip
$miStatus = $menu.Items.Add('Status')
$miStatus.Font = New-Object System.Drawing.Font($miStatus.Font, [System.Drawing.FontStyle]::Bold)   # t795u: bold = the default item
# t762u: ONE plain click each (NO submenus). Every click starts a NEW agent via bob-worker.exe
# (cursor pool > 0 -> agent.cmd; else Grok weekly tokens -> agent.exe; else key dialog). Never resumes/attaches (t765u).
$miAgents = $menu.Items.Add('Agent')
$miAgents.Add_Click({ Start-BobTrayWorkerExe -Mode 'agent' })
$miPlan = $menu.Items.Add('Plan')
$miPlan.Add_Click({ Start-BobTrayWorkerExe -Mode 'plan' })
$miAck = $menu.Items.Add('Acknowledge')
$miLog = $menu.Items.Add('Open log')
[void]$menu.Items.Add('-')
$miRestart = $menu.Items.Add('Restart')
$miExit = $menu.Items.Add('Exit')
$notify.ContextMenuStrip = $menu

$miStatus.Add_Click({ Invoke-BobTrayStatus })
$miAck.Add_Click({
        Clear-Attention
        Show-BobTrayAbout
    })
$miLog.Add_Click({ if (Test-Path $logPath) { Start-Process notepad.exe $logPath } })
$ctx = New-Object System.Windows.Forms.ApplicationContext
$miRestart.Add_Click({ Restart-BobTrayWatcher })
$miExit.Add_Click({ Invoke-BobTrayExit })
$notify.Add_MouseClick({
        param($s, $e)
        if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
            if ($script:attention) { Clear-Attention }
            Invoke-BobTrayStatus
        }
    })
$notify.Add_MouseDoubleClick({
        param($s, $e)
        if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) { Invoke-BobTrayStatus }
    })

$flash = New-Object System.Windows.Forms.Timer
$flash.Interval = 450
$flash.Add_Tick({
        try {
            if (-not $script:attention) { return }
            $script:flashOn = -not $script:flashOn
            $notify.Icon = $(if ($script:flashOn) { $iconAlertA } else { $iconAlertB })
        }
        catch [System.Management.Automation.PipelineStoppedException] { return }
        catch { }
    })

$poll = New-Object System.Windows.Forms.Timer
$poll.Interval = [Math]::Max(5000, $PollSec * 1000)
$poll.Add_Tick({
        try {
            try { Clear-BobTrayGrokSessionDirs } catch { }
            Start-JobsWatcher
            $alerts = @(Get-BobStallAlerts -Seen $seen -StallSec $StallSec -HeartbeatStaleSec $HeartbeatStaleSec)
            if ($alerts.Count -gt 0) { Set-Attention $alerts }
            # FR #1553: refresh TipForm workers from digest BEFORE Get-BobTrayHover (8s bound).
            # Hover can hang on peer DNS/UNC; this keeps tray-status.json worker lines moving.
            try {
                if (Get-Command Sync-BobTrayStatusWorkersFromDigest -ErrorAction SilentlyContinue) {
                    [void](Sync-BobTrayStatusWorkersFromDigest -Root $RepoRoot -TimeoutSec 8)
                }
            }
            catch { Write-TrayLog ('tray worker sync: ' + $_.Exception.Message) }
            Update-Hover
            # CAST IRON: local Cursor (pcent + overspend) + xAI weekly -> digest webhook every tick.
            if (Get-Command Write-BobIrcStatus -ErrorAction SilentlyContinue) {
                try { Write-BobIrcStatus | Out-Null } catch {
                    if ($_.Exception -is [System.Management.Automation.PipelineStoppedException]) { return }
                    Write-TrayLog ('digest Write-BobIrcStatus: ' + $_.Exception.Message)
                    try {
                        if (Get-Command Report-BobDeterministicException -ErrorAction SilentlyContinue) {
                            Report-BobDeterministicException -Site 'Watch-BobTray.Write-BobIrcStatus' -Exception $_.Exception -ScriptPath $PSCommandPath | Out-Null
                        }
                    }
                    catch { }
                }
            }
        }
        catch [System.Management.Automation.PipelineStoppedException] { return }
        catch {
            Write-TrayLog ("poll error: " + $_.Exception.Message)
            try {
                if (Get-Command Report-BobDeterministicException -ErrorAction SilentlyContinue) {
                    Report-BobDeterministicException -Site 'Watch-BobTray.poll' -Exception $_.Exception -ScriptPath $PSCommandPath | Out-Null
                }
            }
            catch { }
        }
    })

# FR #1553: ThreadPool (non-UI) 10s timer — TipForm workers keep updating even when the
# WinForms poll is stuck inside Get-BobTrayHover peer DNS/UNC.
# Event Action runs in its own runspace: re-dot BobTrayDialogs each tick.
$script:trayWorkerSyncTimer = New-Object System.Timers.Timer
$script:trayWorkerSyncTimer.Interval = 10000
$script:trayWorkerSyncTimer.AutoReset = $true
$script:trayWorkerSyncTimer.SynchronizingObject = $null
$script:trayWorkerSyncMsg = [pscustomobject]@{
    Root    = $RepoRoot
    Dialogs = (Join-Path $RepoRoot 'tools\BobTrayDialogs.ps1')
}
$script:trayWorkerSyncSub = Register-ObjectEvent -InputObject $script:trayWorkerSyncTimer -EventName Elapsed -Action {
    try {
        $msg = $Event.MessageData
        if (-not $msg -or -not $msg.Root) { return }
        if ($msg.Dialogs -and (Test-Path -LiteralPath $msg.Dialogs)) { . $msg.Dialogs }
        if (Get-Command Sync-BobTrayStatusWorkersFromDigest -ErrorAction SilentlyContinue) {
            [void](Sync-BobTrayStatusWorkersFromDigest -Root ([string]$msg.Root) -TimeoutSec 8)
        }
    }
    catch { }
} -MessageData $script:trayWorkerSyncMsg
$script:trayWorkerSyncTimer.Start()

# t810u: remote "!startworker" - heartbeat + consume the ear's queued requests (the ear runs in session 0 and cannot open a window).
$script:startWorkerDir = Get-BobTrayStartWorkerDir -Root $RepoRoot
$startWorkerTimer = New-Object System.Windows.Forms.Timer
$startWorkerTimer.Interval = 2000
$startWorkerTimer.Add_Tick({
        try {
            [void](Invoke-BobTrayStartWorkerQueue -Dir $script:startWorkerDir `
                    -Launch { param($mode) Start-BobTrayWorkerExe -Mode $mode -Quiet } `
                    -Log { param($m) Write-TrayLog $m })
            if (Test-BobTrayEngineMode) {
                [void](Invoke-BobTrayExeCommands -Root $RepoRoot `
                        -OnAck { Clear-Attention } -OnExit { Invoke-BobTrayExit } -OnRestart { Restart-BobTrayWatcher } `
                        -ParentGone { Write-TrayLog 'engine: bob-tray.exe is gone - leaving without IRC logout (the next tray start reuses the watchers)'; [Environment]::Exit(0) })
            }
        }
        catch [System.Management.Automation.PipelineStoppedException] { return }
        catch { Write-TrayLog ('startworker queue: ' + $_.Exception.Message) }
    })

$pulse = New-Object System.Windows.Forms.Timer
$pulse.Interval = 60000
$pulseOff = New-Object System.Windows.Forms.Timer
$pulseOff.Interval = 700
$pulseOff.Add_Tick({
        try {
            $pulseOff.Stop()
            if (-not $script:attention) { $notify.Icon = $iconIdle }
        }
        catch [System.Management.Automation.PipelineStoppedException] { return }
        catch { }
    })
$pulse.Add_Tick({
        try {
            if ($script:attention) { return }
            $paint = Get-BobTrayBarPaint -RemainingPct $script:remainingPct
            if (-not $paint.pulse) { return }
            $notify.Icon = $iconContext
            $pulseOff.Stop(); $pulseOff.Start()
        }
        catch [System.Management.Automation.PipelineStoppedException] { return }
        catch { }
    })

# Exception hooks registered at script start (before Controls). Do not call
# SetUnhandledExceptionMode again here - it fails after NotifyIcon/TipForm exist.

try { Clear-BobTrayGrokSessionDirs } catch { }
Start-JobsWatcher
try { Start-IrcWatcher } catch { Write-TrayLog ('irc watcher: ' + $_.Exception.Message) }
Update-Hover
# First digest heartbeat immediately (then every PollSec).
try {
    if (Get-Command Write-BobIrcStatus -ErrorAction SilentlyContinue) { Write-BobIrcStatus | Out-Null }
}
catch { Write-TrayLog ('digest startup: ' + $_.Exception.Message) }
# TipForm handle only on click - startup CreateHandle caused hover stub.
if (Test-BobTrayEngineMode) { Write-TrayLog 'engine mode: bob-tray.exe owns the icon and the menu (this process is headless)'; [void](Write-BobTrayEngineEnv -Root $RepoRoot) }
else { $notify.Visible = $true }
$flash.Start()
$poll.Start()
$pulse.Start()
[void](Write-BobTrayAlive -Dir $script:startWorkerDir)
$startWorkerTimer.Start()
Write-TrayLog 'tray up'
[System.Windows.Forms.Application]::Run($ctx)
$poll.Stop(); $flash.Stop(); $pulse.Stop(); $pulseOff.Stop(); $startWorkerTimer.Stop()
try {
    if ($script:trayWorkerSyncTimer) { $script:trayWorkerSyncTimer.Stop(); $script:trayWorkerSyncTimer.Dispose() }
    if ($script:trayWorkerSyncSub) { Unregister-Event -SourceIdentifier $script:trayWorkerSyncSub.Name -ErrorAction SilentlyContinue; Remove-Job $script:trayWorkerSyncSub -Force -ErrorAction SilentlyContinue }
}
catch { }
try { Remove-Item -LiteralPath (Join-Path $script:startWorkerDir 'tray.alive') -Force -ErrorAction SilentlyContinue } catch { }
# Exit path (menu Exit/Restart already announced+logout). Idempotent; skip second announce.
# t798u: Exit already stopped ircBob (detached); the slow logout/kill path is only for Restart and external stops.
if ($script:trayExitReason -ne 'Exit') {
    try { Request-BobTrayIrcLogout -Reason Exit -SkipAnnounce } catch { Write-TrayLog ('final irc logout: ' + $_.Exception.Message) }
}
if (Test-BobTrayTipAlive) {
    try { [void]$script:tip.TryHide() } catch { try { $script:tip.Hide() } catch { } }
    try { $script:tip.Dispose() } catch { }
}
$script:tip = $null
$notify.Visible = $false
$notify.Dispose()
if ($script:jobsOwned -and $script:jobsPid) {
    try { Stop-Process -Id $script:jobsPid -Force -ErrorAction SilentlyContinue } catch { }
}


