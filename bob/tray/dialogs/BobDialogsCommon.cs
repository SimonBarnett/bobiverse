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

        // FR #6924: MSI VERSION (+ optional deployed short SHA). Identity order:
        // MANIFEST.json > provenance.txt > tools\provenance.txt > HOTPATCH.json > BUILD.json.
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
            if (v.Length == 0) v = "unknown";
            string sha = DeployedSourceShortSha(root);
            return sha.Length > 0 ? (v + " (" + sha + ")") : v;
        }

        public static string ExeSourceShortSha(string root)
        {
            if (string.IsNullOrEmpty(root)) return "";
            string tools = Path.Combine(root, "tools");
            if (string.Equals(Path.GetFileName(root), "tools", StringComparison.OrdinalIgnoreCase))
                tools = root;
            string got = ShortShaFromJsonFile(Path.Combine(tools, "MANIFEST.json"));
            if (got.Length > 0) return got;
            return ShortShaFromProvenance(Path.Combine(tools, "provenance.txt"));
        }

        public static string ScriptsSourceShortSha(string root)
        {
            if (string.IsNullOrEmpty(root)) return "";
            string got = ShortShaFromJsonFile(Path.Combine(root, "MANIFEST.json"));
            if (got.Length > 0) return got;
            got = ShortShaFromProvenance(Path.Combine(root, "provenance.txt"));
            if (got.Length > 0) return got;
            got = ShortShaFromJsonFile(Path.Combine(root, "HOTPATCH.json"));
            if (got.Length > 0) return got;
            return ShortShaFromJsonFile(Path.Combine(root, "BUILD.json"));
        }

        // FR #7247: tools\\MANIFEST is the running exe; install-root MANIFEST is scripts.
        // Same SHA => one token; mismatch => "exe aaa / scripts bbb".
        public static string DeployedSourceShortSha(string root)
        {
            string exe = ExeSourceShortSha(root);
            string scripts = ScriptsSourceShortSha(root);
            if (exe.Length > 0 && scripts.Length > 0 && !string.Equals(exe, scripts, StringComparison.OrdinalIgnoreCase))
                return "exe " + exe + " / scripts " + scripts;
            return exe.Length > 0 ? exe : scripts;
        }

        static string ShortShaToken(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return "";
            string s = raw.Trim();
            if (s.Length < 7 || s.Length > 40) return "";
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
                if (!ok) return "";
            }
            return s.Substring(0, 7).ToLowerInvariant();
        }

        static string ShortShaFromJsonFile(string path)
        {
            try
            {
                if (!File.Exists(path)) return "";
                string text = File.ReadAllText(path, Encoding.UTF8);
                Dictionary<string, object> d = Dict(ParseJson(text));
                if (d == null) return "";
                string[] keys = new string[] { "source_commit", "workflow_commit", "commit", "hotpatch_commit", "sha" };
                foreach (string k in keys)
                {
                    object o;
                    if (!d.TryGetValue(k, out o) || o == null) continue;
                    string got = ShortShaToken(Convert.ToString(o));
                    if (got.Length > 0) return got;
                }
            }
            catch { }
            return "";
        }

        static string ShortShaFromProvenance(string path)
        {
            try
            {
                if (!File.Exists(path)) return "";
                string[] lines = File.ReadAllLines(path, Encoding.UTF8);
                string source = "", workflow = "", commit = "";
                foreach (string line in lines)
                {
                    if (string.IsNullOrEmpty(line)) continue;
                    int eq = line.IndexOf('=');
                    if (eq <= 0) continue;
                    string k = line.Substring(0, eq).Trim().ToLowerInvariant();
                    string v = ShortShaToken(line.Substring(eq + 1));
                    if (v.Length == 0) continue;
                    if (k == "source_commit" && source.Length == 0) source = v;
                    else if (k == "workflow_commit" && workflow.Length == 0) workflow = v;
                    else if (k == "commit" && commit.Length == 0) commit = v;
                }
                if (source.Length > 0) return source;
                if (workflow.Length > 0) return workflow;
                return commit;
            }
            catch { return ""; }
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

        public static long Long(Dictionary<string, object> d, string key, long dflt)
        {
            if (d == null || !d.ContainsKey(key) || d[key] == null) return dflt;
            try { return Convert.ToInt64(d[key]); } catch { return dflt; }
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


        // FR #6149: Bobiverse-owned fuel-family badges (assets\fuel-logos\<family>.png).
        public static string FuelLogoFallback(string family)
        {
            string f = (family ?? "").Trim().ToLowerInvariant();
            if (f == "cursor" || f == "cu") return "Cu";
            if (f == "xai" || f == "grok" || f == "grok-chat" || f == "grok_chat" || f == "x-ai") return "xAI";
            if (f == "opencode" || f == "oc") return "OC";
            if (f == "copilot" || f == "gh" || f == "github") return "Gh";
            if (f.Length == 0) return "?";
            return f.Length <= 3 ? f.ToUpperInvariant() : f.Substring(0, 3).ToUpperInvariant();
        }

        public static Image FuelLogo(string root, string family)
        {
            string key = null;
            string f = (family ?? "").Trim().ToLowerInvariant();
            if (f == "cursor" || f == "cu") key = "cursor";
            else if (f == "xai" || f == "grok" || f == "grok-chat" || f == "grok_chat" || f == "x-ai") key = "xai";
            else if (f == "opencode" || f == "oc") key = "opencode";
            else if (f == "copilot" || f == "gh" || f == "github") key = "copilot";
            if (key == null) return null;
            try
            {
                string p = Path.Combine(root ?? "", "assets", "fuel-logos", key + ".png");
                if (File.Exists(p))
                {
                    byte[] b = File.ReadAllBytes(p);
                    return Image.FromStream(new MemoryStream(b));
                }
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