// t828u: shared helpers for the two fast dialog exes (bob-about.exe, bob-status.exe). C# 5 (csc.exe of .NET Framework 4, always present on Windows).
// Cold start target: well under 1 s. No PowerShell, no Python, no network: data is read from files the tray / installs already wrote.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace BobDialogs
{
    internal static class Native
    {
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
        [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
        [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    }

    internal static class Common
    {
        static Mutex keep;
        public static readonly DateTime StartedAt = SafeStart();

        static DateTime SafeStart()
        {
            try { return Process.GetCurrentProcess().StartTime; } catch { return DateTime.Now; }
        }

        // Single instance per dialog: the first process owns the mutex; a second launch only brings the first window forward.
        public static bool Single(string key, string windowTitle)
        {
            bool created;
            keep = new Mutex(true, "Local\\Bobiverse_" + key, out created);
            if (created) return true;
            if (windowTitle.Length == 0) return false;
            try
            {
                IntPtr h = Native.FindWindow(null, windowTitle);
                if (h != IntPtr.Zero)
                {
                    if (Native.IsIconic(h)) Native.ShowWindow(h, 9);
                    Native.SetForegroundWindow(h);
                }
            }
            catch { }
            return false;
        }

        public static string Arg(string[] args, string name)
        {
            for (int i = 0; i + 1 < args.Length; i++) if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase)) return args[i + 1];
            return "";
        }

        public static bool Flag(string[] args, string name)
        {
            foreach (string a in args) if (string.Equals(a, name, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        // Install root: --root, else the parent of the exe's tools\ folder (flat install), else the exe folder.
        // FR #2585: normalize so single-instance mutex matches across quoted/trailing-slash argv variants.
        public static string NormalizeRoot(string r)
        {
            if (string.IsNullOrEmpty(r)) return "";
            string s = r.Trim().Trim('"').Trim('\'');
            try { s = Path.GetFullPath(s); } catch { }
            return s.TrimEnd('\\', '/');
        }

        public static string TrayMutexKey(string root)
        {
            // Keep path casing from GetFullPath so a tip build matches a live pre-FR#2585 tray mutex.
            string n = NormalizeRoot(root);
            if (n.Length == 0) n = "default";
            return "Tray_" + n.Replace('\\', '_').Replace('/', '_').Replace(':', '_');
        }

        public static string Root(string[] args)
        {
            string r = Arg(args, "--root");
            if (r.Length > 0) return NormalizeRoot(r);
            string dir = NormalizeRoot(AppDomain.CurrentDomain.BaseDirectory);
            if (string.Equals(Path.GetFileName(dir), "tools", StringComparison.OrdinalIgnoreCase)) return Path.GetDirectoryName(dir) ?? dir;
            return dir;
        }

        public static string MachineId()
        {
            string m = (Environment.GetEnvironmentVariable("BOB_MACHINE_ID") ?? "").Trim();
            return m.Length > 0 ? m : Environment.MachineName.ToLowerInvariant();
        }

        public static string BobVersion(string root)
        {
            string v = (Environment.GetEnvironmentVariable("BOBIVERSE_BOB_VERSION") ?? "").Trim();
            if (v.Length == 0)
            {
                string ai = (Environment.GetEnvironmentVariable("BOB_AI_ROOT") ?? "").Trim();
                string[] cands = new string[] { Path.Combine(root, "VERSION"), Path.Combine(root, "src\\VERSION"),
                    ai.Length > 0 ? Path.Combine(ai, "bob\\VERSION") : "" };
                foreach (string c in cands)
                {
                    if (c.Length == 0) continue;
                    string t = FirstLine(c);
                    if (t.Length > 0) { v = t; break; }
                }
            }
            return v.Length > 0 ? v : "unknown";
        }

        public static string FirstLine(string path)
        {
            try
            {
                if (!File.Exists(path)) return "";
                using (StreamReader sr = new StreamReader(path, Encoding.UTF8, true))
                    return (sr.ReadLine() ?? "").Trim();
            }
            catch { return ""; }
        }

        // ---- tiny JSON helpers (JavaScriptSerializer ships with .NET Framework) ----
        public static object ParseJson(string text)
        {
            JavaScriptSerializer js = new JavaScriptSerializer();
            js.MaxJsonLength = int.MaxValue;
            return js.DeserializeObject(text);
        }

        public static Dictionary<string, object> Dict(object o) { return o as Dictionary<string, object>; }

        public static IList List(object o) { return o as IList; }

        public static string Str(Dictionary<string, object> d, string key)
        {
            object v;
            if (d == null || !d.TryGetValue(key, out v) || v == null) return "";
            return Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture);
        }

        public static bool Bool(Dictionary<string, object> d, string key)
        {
            object v;
            if (d == null || !d.TryGetValue(key, out v) || v == null) return false;
            if (v is bool) return (bool)v;
            string s = Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture).ToLowerInvariant();
            return s == "true" || s == "1";
        }

        public static int Int(Dictionary<string, object> d, string key, int dflt)
        {
            object v;
            if (d == null || !d.TryGetValue(key, out v) || v == null) return dflt;
            try { return (int)Math.Round(Convert.ToDouble(v, System.Globalization.CultureInfo.InvariantCulture)); } catch { return dflt; }
        }

        // ---- shared look ----
        public static Image Logo(string root)
        {
            try
            {
                Assembly a = Assembly.GetExecutingAssembly();
                using (Stream s = a.GetManifestResourceStream("ntsa-gut-logo.png"))
                {
                    if (s != null) { using (MemoryStream ms = new MemoryStream()) { s.CopyTo(ms); ms.Position = 0; return Image.FromStream(ms); } }
                }
            }
            catch { }
            try
            {
                string p = Path.Combine(root, "assets\\ntsa-gut-logo.png");
                if (File.Exists(p)) { byte[] b = File.ReadAllBytes(p); return Image.FromStream(new MemoryStream(b)); }
            }
            catch { }
            return null;
        }

        public static Icon AppIcon()
        {
            try { return Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { return null; }
        }

        // `--timing-out <file>`: write the milliseconds from process start to the first shown window, then exit (cold-start measurement).
        public static void TimingHook(Form f, string[] args)
        {
            string png = Arg(args, "--png-out");
            if (png.Length > 0)
            {
                // `--png-out <file>`: render the window (after the background data has landed), save it and exit (visual checks, docs).
                f.Shown += delegate
                {
                    System.Windows.Forms.Timer t = new System.Windows.Forms.Timer();
                    t.Interval = 1500;
                    t.Tick += delegate
                    {
                        t.Stop();
                        try { using (Bitmap bmp = new Bitmap(f.Width, f.Height)) { f.DrawToBitmap(bmp, new Rectangle(0, 0, f.Width, f.Height)); bmp.Save(png, System.Drawing.Imaging.ImageFormat.Png); } } catch { }
                        f.Close();
                    };
                    t.Start();
                };
            }
            string file = Arg(args, "--timing-out");
            if (file.Length == 0) return;
            f.Shown += delegate
            {
                try { File.WriteAllText(file, ((int)(DateTime.Now - StartedAt).TotalMilliseconds).ToString()); } catch { }
                f.BeginInvoke(new MethodInvoker(delegate { f.Close(); }));
            };
        }
    }
}