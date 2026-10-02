// t828u: Acknowledge (About) dialog as a fast compiled exe. Same content as the old PowerShell dialog (Get-BobInstallInfo +
// Format-BobInstallInfo): ntsa badge, "by Simon Barnett", bob version + machine, and one block per install of bob/jeeves/airc/ergo
// (version, build date, commit, path, service state). The window shows at once; the install scan runs on a worker thread.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.ServiceProcess;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace BobDialogs
{
    internal class InstallRow
    {
        public string Product, Path, Version, Released, ReleasedSource, Commit, Service, ServiceState;
    }

    internal static class InstallInfo
    {
        static readonly string[][] Products = new string[][] {
            new string[] { "bob", "ircBob", "bob" }, new string[] { "jeeves", "ircJeeves", "jeeves" },
            new string[] { "airc", "Airc", "airc" }, new string[] { "ergo", "BobIrcd", "ergo" } };

        public static List<string> AiRoots(string root)
        {
            List<string> roots = new List<string>();
            string e = (Environment.GetEnvironmentVariable("BOB_AI_ROOT") ?? "").Trim();
            if (e.Length > 0) roots.Add(e);
            if (string.Equals(System.IO.Path.GetFileName(root.TrimEnd('\\')), "bob", StringComparison.OrdinalIgnoreCase))
            {
                string p = System.IO.Path.GetDirectoryName(root.TrimEnd('\\'));
                if (!string.IsNullOrEmpty(p)) roots.Add(p);
            }
            try { foreach (DriveInfo d in DriveInfo.GetDrives()) if (d.DriveType == DriveType.Fixed) roots.Add(d.Name + "ai"); } catch { }
            List<string> uniq = new List<string>();
            foreach (string r in roots) { if (uniq.FindIndex(delegate (string x) { return string.Equals(x.TrimEnd('\\'), r.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase); }) < 0) uniq.Add(r); }
            return uniq;
        }

        static string SpaceState(string s) { return Regex.Replace(s, "(?<=[a-z])(?=[A-Z])", " "); }

        // Service present? state + the install dir NSSM gave it (scripts\ parent, or the exe folder, or AppDirectory).
        public static bool Service(string name, out string state, out string dir)
        {
            state = ""; dir = "";
            try { using (ServiceController sc = new ServiceController(name)) { state = SpaceState(sc.Status.ToString()); } }
            catch { return false; }
            try
            {
                using (RegistryKey k = Registry.LocalMachine.OpenSubKey("SYSTEM\\CurrentControlSet\\Services\\" + name + "\\Parameters"))
                {
                    if (k != null)
                    {
                        string app = Convert.ToString(k.GetValue("Application") ?? "");
                        string ad = Convert.ToString(k.GetValue("AppDirectory") ?? "");
                        if (ad.Length > 0 && string.Equals(System.IO.Path.GetFileName(ad.TrimEnd('\\')), "scripts", StringComparison.OrdinalIgnoreCase)) dir = System.IO.Path.GetDirectoryName(ad.TrimEnd('\\'));
                        else if (app.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) && !Regex.IsMatch(app, "(?i)powershell|python")) dir = System.IO.Path.GetDirectoryName(app);
                        else if (ad.Length > 0) dir = ad;
                    }
                }
            }
            catch { }
            return true;
        }

        static string Git(string dir, string args)
        {
            try
            {
                if (!Directory.Exists(System.IO.Path.Combine(dir, ".git"))) return "";
                string git = null;
                foreach (string c in new string[] { "C:\\Program Files\\Git\\cmd\\git.exe", "C:\\Program Files\\Git\\bin\\git.exe" }) if (File.Exists(c)) { git = c; break; }
                if (git == null) git = "git.exe";
                ProcessStartInfo psi = new ProcessStartInfo(git, "-c safe.directory=* -C \"" + dir + "\" " + args);
                psi.UseShellExecute = false; psi.CreateNoWindow = true; psi.RedirectStandardOutput = true; psi.RedirectStandardError = true;
                using (Process p = Process.Start(psi))
                {
                    if (!p.WaitForExit(5000)) { try { p.Kill(); } catch { } return ""; }
                    return p.ExitCode == 0 ? p.StandardOutput.ReadToEnd().Trim() : "";
                }
            }
            catch { return ""; }
        }

        static bool IsProductDir(string product, string dir)
        {
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return false;
            if (product == "ergo")
            {
                foreach (string x in new string[] { "ergo.exe", "ircd.exe", "bin\\ergo.exe" }) if (File.Exists(System.IO.Path.Combine(dir, x))) return true;
                return false;
            }
            return File.Exists(System.IO.Path.Combine(dir, "VERSION")) || Directory.Exists(System.IO.Path.Combine(dir, "scripts"));
        }

        static string Utc(DateTime d) { return d.ToUniversalTime().ToString("yyyy-MM-dd HH:mm") + " UTC"; }

        static InstallRow One(string product, string dir)
        {
            string ver = "", rel = "", relSrc = "", commit = "";
            string vf = System.IO.Path.Combine(dir, "VERSION");
            ver = Common.FirstLine(vf);
            if (ver.Length == 0 && product == "ergo")
            {
                foreach (string x in new string[] { "ergo.exe", "ircd.exe", "bin\\ergo.exe" })
                {
                    string ep = System.IO.Path.Combine(dir, x);
                    if (File.Exists(ep)) { try { ver = FileVersionInfo.GetVersionInfo(ep).ProductVersion ?? ""; } catch { } break; }
                }
            }
            string bj = System.IO.Path.Combine(dir, "BUILD.json");
            if (File.Exists(bj))
            {
                try
                {
                    Dictionary<string, object> b = Common.Dict(Common.ParseJson(File.ReadAllText(bj, Encoding.UTF8)));
                    string built = Common.Str(b, "built_utc");
                    if (built.Length > 0)
                    {
                        DateTime dt = DateTime.Parse(built, System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal);
                        rel = Utc(dt); relSrc = "built";
                    }
                    commit = Common.Str(b, "commit").Trim();
                }
                catch { }
            }
            if (commit.Length == 0) commit = Git(dir, "rev-parse --short HEAD");
            if (rel.Length == 0)
            {
                string cd = Git(dir, "log -1 --format=%cI");
                if (cd.Length > 0) { try { rel = Utc(DateTime.Parse(cd, System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.AdjustToUniversal)); relSrc = "commit"; } catch { } }
            }
            if (rel.Length == 0)
            {
                try { string anchor = File.Exists(vf) ? vf : dir; rel = Utc(File.GetLastWriteTimeUtc(anchor)); relSrc = "installed"; } catch { }
            }
            InstallRow r = new InstallRow();
            r.Product = product; r.Path = dir;
            r.Version = ver.Length > 0 ? ver : "-"; r.Released = rel.Length > 0 ? rel : "-"; r.ReleasedSource = relSrc; r.Commit = commit.Length > 0 ? commit : "-";
            r.Service = ""; r.ServiceState = "";
            return r;
        }

        // One row per install folder found, per product, in bob, jeeves, airc, ergo order; a service whose folder is unknown gives one '(unknown)' row.
        public static List<InstallRow> Gather(string root)
        {
            List<InstallRow> rows = new List<InstallRow>();
            List<string> ai = AiRoots(root);
            foreach (string[] pd in Products)
            {
                string product = pd[0], service = pd[1], sub = pd[2];
                string state, sdir;
                bool hasSvc = Service(service, out state, out sdir);
                List<string> dirs = new List<string>();
                foreach (string r in ai)
                {
                    string d = System.IO.Path.Combine(r, sub);
                    if (IsProductDir(product, d)) { try { d = System.IO.Path.GetFullPath(d); } catch { } dirs.Add(d); }
                }
                string svcDir = "";
                if (hasSvc && sdir.Length > 0)
                {
                    try { svcDir = System.IO.Path.GetFullPath(sdir); } catch { svcDir = sdir; }
                    if (IsProductDir(product, svcDir)) dirs.Add(svcDir); else svcDir = "";
                }
                List<string> uniq = new List<string>();
                foreach (string d in dirs) if (uniq.FindIndex(delegate (string x) { return string.Equals(x.TrimEnd('\\'), d.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase); }) < 0) uniq.Add(d);
                foreach (string d in uniq)
                {
                    InstallRow row = One(product, d);
                    if (hasSvc) { row.Service = service; row.ServiceState = state; }
                    rows.Add(row);
                }
                if (uniq.Count == 0 && hasSvc)
                {
                    InstallRow row = new InstallRow();
                    row.Product = product; row.Path = "(unknown)"; row.Version = "-"; row.Released = "-"; row.ReleasedSource = ""; row.Commit = "-";
                    row.Service = service; row.ServiceState = state;
                    rows.Add(row);
                }
            }
            return rows;
        }

        // Same text as Format-BobInstallInfo (CRLF).
        public static string Format(List<InstallRow> rows)
        {
            if (rows.Count == 0) return "No Bobiverse products found on this machine.";
            List<string> lines = new List<string>();
            foreach (InstallRow r in rows)
            {
                lines.Add(r.Product + "  " + r.Version);
                lines.Add("    released: " + r.Released + (r.ReleasedSource.Length > 0 ? " (" + r.ReleasedSource + ")" : ""));
                lines.Add("    commit:   " + r.Commit);
                lines.Add("    path:     " + r.Path);
                if (r.Service.Length > 0) lines.Add("    service:  " + r.Service + " (" + (r.ServiceState.Length > 0 ? r.ServiceState : "unknown") + ")");
            }
            return string.Join("\r\n", lines.ToArray());
        }
    }

    internal class AboutForm : Form
    {
        readonly TextBox box;

        public AboutForm(string root)
        {
            Text = "Bobiverse systray - about";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(580, 440);
            MaximizeBox = false; MinimizeBox = false; TopMost = true;
            Font = new Font("Segoe UI", 9f);
            Icon ico = Common.AppIcon(); if (ico != null) Icon = ico;

            PictureBox logo = new PictureBox();
            logo.Image = Common.Logo(root); logo.BackColor = Color.Black; logo.SizeMode = PictureBoxSizeMode.Zoom;
            logo.Location = new Point(16, 16); logo.Size = new Size(96, 96);
            Label title = new Label();
            title.Text = "Bobiverse systray"; title.Font = new Font("Segoe UI", 15f, FontStyle.Bold); title.AutoSize = true; title.Location = new Point(128, 16);
            Label by = new Label();
            by.Text = "by Simon Barnett"; by.Font = new Font("Segoe UI", 11f); by.AutoSize = true; by.Location = new Point(130, 52);
            Label ver = new Label();
            ver.Text = "bob " + Common.BobVersion(root) + "    machine: " + Common.MachineId();
            ver.Font = new Font("Segoe UI", 9f); ver.AutoSize = true; ver.Location = new Point(130, 84);
            box = new TextBox();
            box.Multiline = true; box.ReadOnly = true; box.ScrollBars = ScrollBars.Vertical; box.Font = new Font("Consolas", 9f);
            box.Text = "reading installs..."; box.Location = new Point(16, 128); box.Size = new Size(548, 256);
            Button ok = new Button();
            ok.Text = "Close"; ok.Location = new Point(474, 398);
            ok.Click += delegate { Close(); };
            Controls.AddRange(new Control[] { logo, title, by, ver, box, ok });
            AcceptButton = ok;
            Shown += delegate { box.Select(0, 0); ok.Focus(); };
            string r = root;
            // Non-blocking data: the window is already up; the scan (services, BUILD.json, git only when needed) fills the box when done.
            ThreadPool.QueueUserWorkItem(delegate
            {
                string text;
                try { text = InstallInfo.Format(InstallInfo.Gather(r)); } catch (Exception ex) { text = "install scan failed: " + ex.Message; }
                try { BeginInvoke(new MethodInvoker(delegate { box.Text = text; box.Select(0, 0); })); } catch { }
            });
        }
    }

    internal static class AboutProgram
    {
        [STAThread]
        static int Main(string[] args)
        {
            string root = Common.Root(args);
            // Headless: write the install text to a file and exit (tests, support). No window, no single-instance lock.
            string textOut = Common.Arg(args, "--text-out");
            if (textOut.Length > 0)
            {
                File.WriteAllText(textOut, InstallInfo.Format(InstallInfo.Gather(root)), new UTF8Encoding(false));
                return 0;
            }
            if (!Common.Single("About", "Bobiverse systray - about")) return 0;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            AboutForm f = new AboutForm(root);
            Common.TimingHook(f, args);
            Application.Run(f);
            return 0;
        }
    }
}