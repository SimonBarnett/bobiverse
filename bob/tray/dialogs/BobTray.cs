// t832u: the systray as a compiled exe (bob-tray.exe). Icon, context menu, click handling, hover text, flashing and the Status / About
// windows (hosted in-process) all run natively, so the menu opens at once and nothing waits on PowerShell.
// The slow DATA work (digest webhook, Cursor/Grok usage, stall alerts, IRC watcher, !startworker queue) stays in the existing
// PowerShell tray script, started HIDDEN by this exe in "engine" mode (BOB_TRAY_ENGINE=1: it owns no icon and no window). It publishes
// <root>\run\tray-status.json every poll; this exe reads it every 2 s and tells the engine what to do through <root>\run\tray-cmd.txt
// (ack | exit | restart), which the engine picks up within 2 s.
using System;
using System.Collections;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

namespace BobDialogs
{
    internal static class WorkerLauncher
    {
        [StructLayout(LayoutKind.Sequential)]
        struct PROCESS_BASIC_INFORMATION { public IntPtr ExitStatus, PebBaseAddress, AffinityMask, BasePriority, UniqueProcessId, InheritedFromUniqueProcessId; }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct STARTUPINFO
        {
            public int cb; public string lpReserved, lpDesktop, lpTitle; public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
            public short wShowWindow, cbReserved2; public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct PROCESS_INFORMATION { public IntPtr hProcess, hThread; public int dwProcessId, dwThreadId; }

        [DllImport("ntdll.dll")] static extern int NtQueryInformationProcess(IntPtr h, int cls, ref PROCESS_BASIC_INFORMATION pbi, int len, out int ret);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern bool CreateProcessW(string app, StringBuilder cmd, IntPtr pa, IntPtr ta, bool inherit, int flags, IntPtr env, string cwd, ref STARTUPINFO si, out PROCESS_INFORMATION pi);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);

        public const int MaxWorkers = 2;   // t815u: hard cap per machine (tray click and !startworker alike)
        static readonly Regex SeatName = new Regex("^bob-worker(-[0-9a-f]+)?$", RegexOptions.IgnoreCase);

        static int ParentOf(Process p)
        {
            try
            {
                PROCESS_BASIC_INFORMATION pbi = new PROCESS_BASIC_INFORMATION(); int ret;
                if (NtQueryInformationProcess(p.Handle, 0, ref pbi, Marshal.SizeOf(pbi), out ret) == 0) return pbi.InheritedFromUniqueProcessId.ToInt32();
            }
            catch { }
            return -1;
        }

        // Live seats: a onefile exe is bootloader + same-named child = ONE seat (parent is itself a bob-worker => not counted).
        public static int Seats()
        {
            List<int> ids = new List<int>(); List<int> parents = new List<int>();
            foreach (Process p in Process.GetProcesses())
            {
                try { if (SeatName.IsMatch(p.ProcessName)) { ids.Add(p.Id); parents.Add(ParentOf(p)); } } catch { }
            }
            int n = 0;
            for (int i = 0; i < ids.Count; i++) if (!ids.Contains(parents[i])) n++;
            return n;
        }

        public static string CapRefusal()
        {
            int n = Seats();
            return n >= MaxWorkers ? "Max " + MaxWorkers + " workers (" + n + " already running). Close a worker window first." : "";
        }

        // FR #1643: true when another process still has the hashed bob-worker-*.exe open (seat holds the run copy).
        static bool IsWorkerExeInUse(string path)
        {
            try
            {
                using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                    return false;
            }
            catch (IOException) { return true; }
            catch (UnauthorizedAccessException) { return true; }
            catch { return true; }
        }

        static string Quote(string a) { return Regex.IsMatch(a, "[\\s\"]") ? "\"" + a.Replace("\"", "\\\"") + "\"" : a; }

        // FR #2421: prefer bob-worker --describe-launch JSON (same plan as Watch-BobTray / CLI).
        static bool TryDescribeLaunch(string installExe, string root, string mode, string machine, out string run, out List<string> argv, out string wd, out string title)
        {
            run = ""; argv = null; wd = ""; title = "";
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = installExe;
                StringBuilder args = new StringBuilder();
                args.Append("--describe-launch --mode ").Append(Quote(mode));
                args.Append(" --install-root ").Append(Quote(root));
                if (machine.Length > 0) args.Append(" --machine-id ").Append(Quote(machine));
                psi.Arguments = args.ToString();
                psi.UseShellExecute = false;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                psi.CreateNoWindow = true;
                using (Process p = Process.Start(psi))
                {
                    if (p == null) return false;
                    // FR #2430: drain stderr while reading stdout — redirecting both without
                    // draining stderr can fill the pipe and deadlock until the 8s kill.
                    string stderr = "";
                    System.Threading.Thread errThread = new System.Threading.Thread(() =>
                    {
                        try { stderr = p.StandardError.ReadToEnd(); } catch { }
                    });
                    errThread.IsBackground = true;
                    errThread.Start();
                    string json = p.StandardOutput.ReadToEnd();
                    errThread.Join(8000);
                    if (!p.WaitForExit(8000)) { try { p.Kill(); } catch { } return false; }
                    if (p.ExitCode != 0 || string.IsNullOrWhiteSpace(json)) return false;
                    Dictionary<string, object> d = Common.Dict(Common.ParseJson(json.Trim()));
                    if (d == null) return false;
                    run = Common.Str(d, "run_exe");
                    wd = Common.Str(d, "cwd");
                    title = Common.Str(d, "title");
                    IList raw = Common.List(d.ContainsKey("argv") ? d["argv"] : null);
                    if (raw == null || raw.Count == 0 || run.Length == 0) return false;
                    argv = new List<string>();
                    foreach (object o in raw) argv.Add(Convert.ToString(o, System.Globalization.CultureInfo.InvariantCulture));
                    return argv.Count > 0;
                }
            }
            catch { return false; }
        }

        // Same contract as Start-BobTrayWorkerExe: fresh agent every click, run-copy of the exe so a seat never locks the install,
        // its own visible console (CREATE_NEW_CONSOLE). Returns the pid, or 0 with `error` set.
        public static int Launch(string root, string mode, string machine, out string error)
        {
            error = "";
            string refusal = CapRefusal();
            if (refusal.Length > 0) { error = refusal; return 0; }
            string exe = Path.Combine(root, "worker\\bob-worker.exe");
            if (!File.Exists(exe)) { error = "bob-worker.exe is missing:\n" + exe + "\n\nReinstall or upgrade the bob MSI."; return 0; }

            string run = "";
            List<string> argv = null;
            string wd = "";
            string title = "";
            bool fromPlan = TryDescribeLaunch(exe, root, mode, machine, out run, out argv, out wd, out title);

            if (!fromPlan)
            {
                // Fallback: local hash/argv (must stay aligned with describe_worker_exe_launch).
                string hash;
                using (SHA256 sha = SHA256.Create()) using (FileStream fs = new FileStream(exe, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                    hash = BitConverter.ToString(sha.ComputeHash(fs)).Replace("-", "").Substring(0, 12).ToLowerInvariant();
                string bin = Path.Combine(Environment.GetEnvironmentVariable("LOCALAPPDATA") ?? Path.GetTempPath(), "Bobiverse\\worker\\bin");
                Directory.CreateDirectory(bin);
                run = Path.Combine(bin, "bob-worker-" + hash + ".exe");
                argv = new List<string>(new string[] { "--mode", mode, "--install-root", root });
                if (machine.Length > 0) { argv.Add("--machine-id"); argv.Add(machine); }
                wd = Path.Combine(root, mode == "plan" ? "plan" : "worker");
                title = "Bob " + mode + " - starting (closing this window ends the agent)";
            }

            string binDir = Path.GetDirectoryName(run) ?? Path.Combine(Environment.GetEnvironmentVariable("LOCALAPPDATA") ?? Path.GetTempPath(), "Bobiverse\\worker\\bin");
            Directory.CreateDirectory(binDir);
            if (!File.Exists(run))
            {
                File.Copy(exe, run, true);
            }
            // FR #1643: defer delete while a live seat still holds the hashed run exe (in use / locked).
            foreach (string old in Directory.GetFiles(binDir, "bob-worker-*.exe"))
            {
                if (string.Equals(old, run, StringComparison.OrdinalIgnoreCase)) continue;
                if (IsWorkerExeInUse(old)) continue;
                try { File.Delete(old); } catch { }
            }

            if (string.IsNullOrEmpty(wd) || !Directory.Exists(wd))
            {
                wd = Path.Combine(root, mode == "plan" ? "plan" : "worker");
                if (!Directory.Exists(wd)) wd = root;
            }
            if (string.IsNullOrEmpty(title)) title = "Bob " + mode + " - starting (closing this window ends the agent)";

            StringBuilder cmd = new StringBuilder(Quote(run));
            foreach (string a in argv) cmd.Append(' ').Append(Quote(a));
            STARTUPINFO si = new STARTUPINFO(); si.cb = Marshal.SizeOf(si);
            si.lpTitle = title;
            PROCESS_INFORMATION pi;
            if (!CreateProcessW(run, cmd, IntPtr.Zero, IntPtr.Zero, false, 0x10 /* CREATE_NEW_CONSOLE */, IntPtr.Zero, wd, ref si, out pi))
            { error = "start failed: " + new Win32Exception(Marshal.GetLastWin32Error()).Message; return 0; }
            CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
            return pi.dwProcessId;
        }
    }

    internal static class RobotIcon
    {
        [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr h);

        // Font Awesome Free solid robot (CC BY 4.0) drawn at tray size, same drawing as the PowerShell tray's New-FaRobotIcon.
        public static Icon Make(Color badge)
        {
            using (Bitmap bmp = new Bitmap(16, 16))
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias; g.PixelOffsetMode = PixelOffsetMode.HighQuality; g.Clear(Color.Transparent);
                using (SolidBrush fg = new SolidBrush(Color.FromArgb(232, 236, 241))) using (SolidBrush eye = new SolidBrush(Color.FromArgb(28, 33, 40)))
                using (Pen ant = new Pen(Color.FromArgb(232, 236, 241), 1.2f))
                {
                    g.DrawLine(ant, 8.0f, 1.2f, 8.0f, 4.0f);
                    g.FillEllipse(fg, 7.0f, 0.4f, 2.0f, 2.0f);
                    using (GraphicsPath body = new GraphicsPath())
                    {
                        float x = 3.2f, y = 4.2f, w = 9.6f, h = 10.4f, d = 3.2f;
                        body.AddArc(x, y, d, d, 180, 90); body.AddArc(x + w - d, y, d, d, 270, 90); body.AddArc(x + w - d, y + h - d, d, d, 0, 90); body.AddArc(x, y + h - d, d, d, 90, 90);
                        body.CloseFigure(); g.FillPath(fg, body);
                    }
                    g.FillRectangle(fg, 1.6f, 7.2f, 1.8f, 4.4f); g.FillRectangle(fg, 12.6f, 7.2f, 1.8f, 4.4f);
                    g.FillEllipse(eye, 5.1f, 7.0f, 2.2f, 2.2f); g.FillEllipse(eye, 8.7f, 7.0f, 2.2f, 2.2f);
                    if (badge.A > 0) using (SolidBrush br = new SolidBrush(badge)) g.FillEllipse(br, 10.2f, 10.2f, 5.2f, 5.2f);
                }
                IntPtr h2 = bmp.GetHicon();
                Icon clone = (Icon)Icon.FromHandle(h2).Clone();
                DestroyIcon(h2);
                return clone;
            }
        }
    }

    // What the tray shows, decided from the engine's snapshot (pure: also used by --dump-state for tests).
    internal class TrayState
    {
        public string Short = "", Alert = "none";
        public bool Attention, Pulse;
        public long AttentionSeq;

        public static TrayState Parse(string json)
        {
            TrayState s = new TrayState();
            Dictionary<string, object> d = Common.Dict(Common.ParseJson(json));
            if (d == null) return s;
            s.Short = Common.Str(d, "short"); s.Alert = Common.Str(d, "alert"); if (s.Alert.Length == 0) s.Alert = "none";
            s.Attention = Common.Bool(d, "attention"); s.Pulse = Common.Bool(d, "pulse"); s.AttentionSeq = Common.Int(d, "attention_seq", 0);
            return s;
        }

        // Tooltip text: NotifyIcon.Text holds at most 63 chars.
        public string Tip(bool acked)
        {
            string t = Short.Length > 0 ? Short : "Bob";
            if (Attention && !acked) t = "! " + t;
            return t.Length > 63 ? t.Substring(0, 63) : t;
        }
    }

    internal class TrayContext : ApplicationContext
    {
        readonly string root, machine, runDir, snapFile, cmdFile;
        readonly bool noEngine;
        readonly NotifyIcon notify = new NotifyIcon();
        readonly ContextMenuStrip menu = new ContextMenuStrip();
        readonly Icon idle = RobotIcon.Make(Color.Transparent), alertA = RobotIcon.Make(Color.FromArgb(220, 50, 47)),
            alertB = RobotIcon.Make(Color.FromArgb(255, 180, 0)), context = RobotIcon.Make(Color.FromArgb(210, 153, 34));
        readonly System.Windows.Forms.Timer flash = new System.Windows.Forms.Timer(), poll = new System.Windows.Forms.Timer(), watchdog = new System.Windows.Forms.Timer();
        TrayState state = new TrayState();
        DateTime lastWrite = DateTime.MinValue; long lastLen = -1;
        bool flashOn, acked, exiting;
        string exitReason = "";
        long ackedSeq = -1;
        Process engine;
        int engineStarts; DateTime engineWindow = DateTime.Now;
        StatusForm statusForm; AboutForm aboutForm;
        public readonly List<string> MenuItems = new List<string>();
        public string ExitReason { get { return exitReason ?? ""; } }

        public TrayContext(string root, string machine, bool noEngine, string[] args)
        {
            this.root = root; this.machine = machine; this.noEngine = noEngine;
            runDir = Path.Combine(root, "run"); Directory.CreateDirectory(runDir);
            snapFile = Path.Combine(runDir, "tray-status.json"); cmdFile = Path.Combine(runDir, "tray-cmd.txt");

            ToolStripMenuItem miStatus = Item("Status", delegate { ShowStatus(); });
            miStatus.Font = new Font(miStatus.Font, FontStyle.Bold);   // bold = the default action
            Item("Agent", delegate { StartWorker("agent"); });
            Item("Plan", delegate { StartWorker("plan"); });
            Item("Acknowledge", delegate { Acknowledge(); ShowAbout(); });
            Item("Open log", delegate { OpenLog(); });
            menu.Items.Add(new ToolStripSeparator()); MenuItems.Add("-");
            Item("Restart", delegate { Restart(); });
            Item("Exit", delegate { ExitTray(); });
            notify.ContextMenuStrip = menu;
            notify.Icon = idle; notify.Text = "Bob";
            notify.MouseClick += delegate (object s, MouseEventArgs e) { if (e.Button == MouseButtons.Left) { Acknowledge(); ShowStatus(); } };
            notify.MouseDoubleClick += delegate (object s, MouseEventArgs e) { if (e.Button == MouseButtons.Left) ShowStatus(); };

            flash.Interval = 450; flash.Tick += delegate { Flash(); };
            poll.Interval = 2000; poll.Tick += delegate { Reload(); };
            watchdog.Interval = 15000; watchdog.Tick += delegate { Watchdog(); };

            IntPtr pre = menu.Handle;                    // build the native menu now: the first right-click is as fast as the tenth
            Reload();
            notify.Visible = true;
            if (!noEngine) StartEngine();
            flash.Start(); poll.Start(); watchdog.Start();

            string timing = Common.Arg(args, "--timing-out");
            if (timing.Length > 0)
            {
                // cold start + menu-open measurement: ms to icon-visible, then ms to the menu's Opened event (shown off-screen), then exit
                int tVisible = (int)(DateTime.Now - Common.StartedAt).TotalMilliseconds;
                DateTime m0 = DateTime.Now;
                bool wrote = false;
                menu.Opened += delegate
                {
                    if (wrote) return; wrote = true;
                    int tMenu = (int)(DateTime.Now - m0).TotalMilliseconds;
                    try { File.WriteAllText(timing, tVisible + "," + tMenu); } catch { }
                    ExitThread();
                };
                // opened from the message loop (a Show inside the constructor would run before Application.Run)
                Timer t1 = new Timer(); t1.Interval = 10;
                t1.Tick += delegate { t1.Stop(); m0 = DateTime.Now; menu.Show(new Point(-3000, -3000)); };
                t1.Start();
                Timer t2 = new Timer(); t2.Interval = 15000;
                t2.Tick += delegate { t2.Stop(); if (!wrote) { wrote = true; try { File.WriteAllText(timing, tVisible + ",-1"); } catch { } ExitThread(); } };
                t2.Start();
            }
        }

        ToolStripMenuItem Item(string text, EventHandler h)
        {
            ToolStripMenuItem mi = new ToolStripMenuItem(text); mi.Click += h; menu.Items.Add(mi); MenuItems.Add(text); return mi;
        }

        // ---- engine (hidden PowerShell: all slow data work) ----
        void StartEngine()
        {
            try
            {
                string wrap = Path.Combine(root, "tools\\_Watch-BobTray-" + machine + ".ps1");
                string script = File.Exists(wrap) ? wrap : Path.Combine(root, "tools\\Watch-BobTray.ps1");
                if (!File.Exists(script)) return;
                string ps = Path.Combine(Environment.GetEnvironmentVariable("SystemRoot") ?? "C:\\Windows", "System32\\WindowsPowerShell\\v1.0\\powershell.exe");
                ProcessStartInfo psi = new ProcessStartInfo(ps, "-NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File \"" + script + "\"");
                psi.UseShellExecute = false; psi.CreateNoWindow = true; psi.WorkingDirectory = root;
                psi.EnvironmentVariables["BOB_TRAY_ENGINE"] = "1";
                psi.EnvironmentVariables["BOB_TRAY_EXE_PID"] = Process.GetCurrentProcess().Id.ToString();
                if (machine.Length > 0) psi.EnvironmentVariables["BOB_MACHINE_ID"] = machine;
                engine = Process.Start(psi);
            }
            catch { engine = null; }
        }

        void Watchdog()
        {
            if (exiting || noEngine) return;
            try
            {
                if (engine != null && !engine.HasExited) return;
                if ((DateTime.Now - engineWindow).TotalMinutes > 5) { engineWindow = DateTime.Now; engineStarts = 0; }
                if (++engineStarts > 3) return;       // no restart storm
                StartEngine();
            }
            catch { }
        }

        void Command(string cmd)
        {
            try { File.AppendAllText(cmdFile, cmd + "\r\n"); } catch { }
        }

        // ---- state from the snapshot ----
        void Reload()
        {
            try
            {
                if (File.Exists(snapFile))
                {
                    FileInfo fi = new FileInfo(snapFile);
                    if (fi.LastWriteTimeUtc != lastWrite || fi.Length != lastLen)
                    {
                        string json;
                        using (FileStream fs = new FileStream(snapFile, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                        using (StreamReader sr = new StreamReader(fs, Encoding.UTF8, true)) json = sr.ReadToEnd();
                        TrayState s = TrayState.Parse(json);
                        if (s.AttentionSeq != state.AttentionSeq) acked = false;
                        lastWrite = fi.LastWriteTimeUtc; lastLen = fi.Length; state = s;
                    }
                }
            }
            catch { }
            ApplyIcon();
        }

        bool Flashing { get { return state.Attention && !acked && ackedSeq != state.AttentionSeq; } }

        void ApplyIcon()
        {
            try
            {
                notify.Text = state.Tip(!Flashing);
                if (!Flashing) notify.Icon = state.Pulse ? context : idle;
            }
            catch { }
        }

        void Flash()
        {
            if (!Flashing) return;
            flashOn = !flashOn;
            notify.Icon = flashOn ? alertA : alertB;
        }

        void Acknowledge()
        {
            acked = true; ackedSeq = state.AttentionSeq;
            Command("ack");
            ApplyIcon();
        }

        // ---- actions ----
        void ShowStatus()
        {
            try
            {
                if (statusForm != null && !statusForm.IsDisposed) { statusForm.Activate(); statusForm.BringToFront(); return; }
                statusForm = new StatusForm(root);
                statusForm.FormClosed += delegate { statusForm = null; };
                statusForm.Show();
            }
            catch { }
        }

        void ShowAbout()
        {
            try
            {
                if (aboutForm != null && !aboutForm.IsDisposed) { aboutForm.Activate(); aboutForm.BringToFront(); return; }
                aboutForm = new AboutForm(root);
                aboutForm.FormClosed += delegate { aboutForm = null; };
                aboutForm.Show();
            }
            catch { }
        }

        void ApplyEngineEnv()
        {
            // The worker must start with the environment the engine (the old tray) had: run\tray-env.json, written by the engine at start.
            try
            {
                string f = Path.Combine(runDir, "tray-env.json");
                if (!File.Exists(f)) return;
                Dictionary<string, object> d = Common.Dict(Common.ParseJson(File.ReadAllText(f, Encoding.UTF8)));
                if (d == null) return;
                foreach (KeyValuePair<string, object> kv in d)
                    if (Regex.IsMatch(kv.Key, "^(BOB_|AGENTIC_|BOBIVERSE_)[A-Z0-9_]+$")) Environment.SetEnvironmentVariable(kv.Key, Convert.ToString(kv.Value));
            }
            catch { }
        }

        void StartWorker(string mode)
        {
            ApplyEngineEnv();
            string err; string mid = machine.Length > 0 ? machine : Common.MachineId();
            int pid = WorkerLauncher.Launch(root, mode, mid, out err);
            if (pid == 0 && err.Length > 0)
                try { MessageBox.Show(err, "Bobiverse", MessageBoxButtons.OK, err.StartsWith("start failed") || err.StartsWith("bob-worker.exe") ? MessageBoxIcon.Warning : MessageBoxIcon.Information); } catch { }
        }

        void OpenLog()
        {
            try
            {
                string p = Path.Combine(Environment.GetEnvironmentVariable("USERPROFILE") ?? "", ".grok\\long-running-background-tasks\\watch_bob_tray.log");
                if (File.Exists(p)) Process.Start("notepad.exe", "\"" + p + "\"");
            }
            catch { }
        }

        void Detached(string file, string args)
        {
            try { ProcessStartInfo psi = new ProcessStartInfo(file, args); psi.UseShellExecute = false; psi.CreateNoWindow = true; Process.Start(psi); } catch { }
        }

        void CloseWindows()
        {
            try { if (statusForm != null && !statusForm.IsDisposed) statusForm.Close(); } catch { }
            try { if (aboutForm != null && !aboutForm.IsDisposed) aboutForm.Close(); } catch { }
        }

        // Exit order unchanged (t798u): dialogs + icon go first, then the ircBob stop (detached, never waited for), then the engine is asked to leave.
        void ExitTray()
        {
            if (exiting) return;
            exiting = true;
            exitReason = "Exit";
            TrayLifecycle.Write("exit", "reason", "Exit", "via", "bob-tray-Exit");
            TrayLifecycle.SuppressWatchdog("Exit");
            CloseWindows();
            notify.Visible = false;
            Detached(Path.Combine(Environment.GetEnvironmentVariable("SystemRoot") ?? "C:\\Windows", "System32\\sc.exe"), "stop ircBob");
            Command("exit");
            FinishAfterEngine(4000);
        }

        void Restart()
        {
            if (exiting) return;
            exiting = true;
            exitReason = "Restart";
            TrayLifecycle.Write("exit", "reason", "Restart", "via", "bob-tray-Restart");
            CloseWindows();
            notify.Visible = false;
            Command("restart");   // the engine announces the IRC logout and runs Start-BobFleetTray -ForceNew (replaces this exe, restarts ircBob)
            FinishAfterEngine(6000);
        }

        void FinishAfterEngine(int waitMs)
        {
            flash.Stop(); poll.Stop(); watchdog.Stop();
            ThreadPoolWait(waitMs);
            ExitThread();
        }

        void ThreadPoolWait(int ms)
        {
            DateTime end = DateTime.Now.AddMilliseconds(ms);
            while (DateTime.Now < end)
            {
                try { if (engine == null || engine.HasExited) return; } catch { return; }
                System.Threading.Thread.Sleep(100);
            }
            try { if (engine != null && !engine.HasExited) engine.Kill(); } catch { }
        }

        protected override void ExitThreadCore()
        {
            try { notify.Visible = false; notify.Dispose(); } catch { }
            base.ExitThreadCore();
        }
    }

    internal static class TrayProgram
    {
        [STAThread]
        static int Main(string[] args)
        {
            CrashHook.Install("bob-tray");
            string root = Common.Root(args);
            string machine = Common.Arg(args, "--machine");
            if (machine.Length == 0) machine = (Environment.GetEnvironmentVariable("BOB_MACHINE_ID") ?? "").Trim();
            if (machine.Length == 0) machine = Common.MachineId();
            // Headless helpers (tests / support): no icon, no lock.
            string dumpState = Common.Arg(args, "--dump-state");
            if (dumpState.Length > 0)
            {
                TrayState s = TrayState.Parse(File.ReadAllText(dumpState, Encoding.UTF8));
                File.WriteAllText(Common.Arg(args, "--text-out"), "tip=" + s.Tip(false) + "\r\ntip_acked=" + s.Tip(true) + "\r\nattention=" + s.Attention + "\r\nseq=" + s.AttentionSeq + "\r\npulse=" + s.Pulse + "\r\nalert=" + s.Alert + "\r\n", new UTF8Encoding(false));
                return 0;
            }
            if (Common.Flag(args, "--seats")) { File.WriteAllText(Common.Arg(args, "--text-out"), WorkerLauncher.Seats().ToString() + "\r\n" + WorkerLauncher.CapRefusal(), new UTF8Encoding(false)); return 0; }
            bool timing = Common.Arg(args, "--timing-out").Length > 0;
            string dumpMenu = Common.Arg(args, "--dump-menu");
            if (!timing && dumpMenu.Length == 0 && !Common.Single("Tray_" + root.Replace('\\', '_').Replace(':', '_'), "")) return 0;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Environment.SetEnvironmentVariable("BOB_MACHINE_ID", machine);
            Environment.SetEnvironmentVariable("BOB_AI_ROOT", Environment.GetEnvironmentVariable("BOB_AI_ROOT") ?? (string.Equals(Path.GetFileName(root.TrimEnd('\\')), "bob", StringComparison.OrdinalIgnoreCase) ? Path.GetDirectoryName(root.TrimEnd('\\')) : ""));
            TrayContext ctx = new TrayContext(root, machine, Common.Flag(args, "--no-engine") || timing || dumpMenu.Length > 0, args);
            if (dumpMenu.Length > 0) { File.WriteAllText(dumpMenu, string.Join("\r\n", ctx.MenuItems.ToArray()), new UTF8Encoding(false)); return 0; }
            TrayLifecycle.Write("tray-up", "via", "bob-tray.exe", "machine", machine);
            Application.Run(ctx);
            string reason = string.IsNullOrEmpty(ctx.ExitReason) ? "unexpected" : ctx.ExitReason;
            TrayLifecycle.Write("process-exit", "reason", reason, "via", "bob-tray.exe");
            return 0;
        }
    }

    // FR #1642: append JSON lines to %LOCALAPPDATA%\Bobiverse\tray-lifecycle.log; suppress intentional Exit.
    internal static class TrayLifecycle
    {
        static string Dir()
        {
            string d = Path.Combine(Environment.GetEnvironmentVariable("LOCALAPPDATA") ?? Path.GetTempPath(), "Bobiverse");
            Directory.CreateDirectory(d);
            return d;
        }

        static string Esc(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        public static void Write(string ev, params string[] kv)
        {
            try
            {
                StringBuilder sb = new StringBuilder();
                sb.Append("{\"ts\":\"").Append(DateTime.UtcNow.ToString("o")).Append("\",\"event\":\"").Append(Esc(ev)).Append("\",\"pid\":").Append(Process.GetCurrentProcess().Id);
                sb.Append(",\"user\":\"").Append(Esc(Environment.UserName)).Append("\"");
                for (int i = 0; i + 1 < kv.Length; i += 2)
                    sb.Append(",\"").Append(Esc(kv[i])).Append("\":\"").Append(Esc(kv[i + 1])).Append("\"");
                sb.Append("}");
                File.AppendAllText(Path.Combine(Dir(), "tray-lifecycle.log"), sb.ToString() + "\r\n", new UTF8Encoding(false));
            }
            catch { }
        }

        public static void SuppressWatchdog(string reason)
        {
            try
            {
                DateTime until = DateTime.UtcNow.AddMinutes(1440);
                string json = "{\"ts\":\"" + DateTime.UtcNow.ToString("o") + "\",\"reason\":\"" + Esc(reason) + "\",\"pid\":" + Process.GetCurrentProcess().Id + ",\"ttl_minutes\":1440,\"until\":\"" + until.ToString("o") + "\"}";
                File.WriteAllText(Path.Combine(Dir(), "tray-watchdog.suppress"), json, new UTF8Encoding(false));
                Write("watchdog-suppress", "reason", reason, "ttlMinutes", "1440");
            }
            catch { }
        }
    }
}