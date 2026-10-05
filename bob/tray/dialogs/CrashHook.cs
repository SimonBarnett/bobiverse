// FR #2411: unhandled exception in tray dialogs -> GitHub issue (dedupe + spool).
// Mirrors common/scripts/crash_report.py for WinForms exes compiled by Build-BobDialogs.ps1.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace BobDialogs
{
    internal static class CrashHook
    {
        static readonly object Gate = new object();
        static string InstalledFor;
        static readonly Regex SecretRe = new Regex(
            @"(?i)(password|passwd|secret|token|api[_-]?key|xai_api_key|cursor_api_key|BOB_IRC_PASSWORD|GH_TOKEN|GITHUB_TOKEN|Authorization|Bearer|NickServ|SASL)\s*[=:]\s*\S+",
            RegexOptions.Compiled);
        static readonly Regex TokenBlobRe = new Regex(
            @"(?i)\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{10,}|xox[baprs]-[A-Za-z0-9-]+)\b",
            RegexOptions.Compiled);

        public static void Install(string exeName)
        {
            if (string.IsNullOrEmpty(exeName)) exeName = "bob-dialog";
            lock (Gate)
            {
                if (string.Equals(InstalledFor, exeName, StringComparison.Ordinal)) return;
                try
                {
                    Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
                }
                catch { }
                Application.ThreadException += delegate(object sender, ThreadExceptionEventArgs e)
                {
                    try { Report(exeName, e.Exception); } catch { }
                };
                AppDomain.CurrentDomain.UnhandledException += delegate(object sender, UnhandledExceptionEventArgs e)
                {
                    try { Report(exeName, e.ExceptionObject as Exception); } catch { }
                };
                try { FlushSpool(); } catch { }
                InstalledFor = exeName;
            }
        }

        public static string Redact(string text)
        {
            if (string.IsNullOrEmpty(text)) return "";
            string s = SecretRe.Replace(text, delegate(Match m) { return m.Groups[1].Value + "=<redacted>"; });
            return TokenBlobRe.Replace(s, "<redacted-token>");
        }

        public static string Signature(Exception ex)
        {
            List<string> parts = new List<string>();
            parts.Add(ex == null ? "?" : ex.GetType().Name);
            try
            {
                if (ex != null)
                {
                    string[] lines = (ex.StackTrace ?? "").Replace("\r", "").Split('\n');
                    int n = 0;
                    for (int i = 0; i < lines.Length && n < 8; i++)
                    {
                        string line = lines[i].Trim();
                        if (line.Length == 0) continue;
                        // "at Ns.Type.Method() in File.cs:line 12"
                        Match m = Regex.Match(line, @"at\s+(\S+)\s+in\s+(.+):line\s+(\d+)");
                        if (m.Success)
                        {
                            parts.Add(Path.GetFileName(m.Groups[2].Value) + ":" + m.Groups[3].Value + ":" + m.Groups[1].Value);
                            n++;
                            continue;
                        }
                        Match m2 = Regex.Match(line, @"at\s+(\S+)");
                        if (m2.Success)
                        {
                            parts.Add("?:?:" + m2.Groups[1].Value);
                            n++;
                        }
                    }
                }
            }
            catch { }
            string joined = string.Join("|", parts.ToArray());
            using (SHA256 sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes(joined));
                StringBuilder hex = new StringBuilder(16);
                for (int i = 0; i < 8; i++) hex.Append(hash[i].ToString("x2"));
                return hex.ToString();
            }
        }

        public static string SpoolDir()
        {
            string overrideDir = (Environment.GetEnvironmentVariable("BOB_CRASH_SPOOL") ?? "").Trim();
            if (overrideDir.Length > 0) return overrideDir;
            string local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            if (string.IsNullOrEmpty(local)) local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (string.IsNullOrEmpty(local)) local = Path.GetTempPath();
            return Path.Combine(local, "Bobiverse", "crash-spool");
        }

        public static void Report(string exeName, Exception ex)
        {
            try
            {
                string sig = Signature(ex);
                string et = ex == null ? "?" : ex.GetType().Name;
                string msg = Redact(ex == null ? "" : (ex.Message ?? ""));
                if (msg.Length > 180) msg = msg.Substring(0, 180);
                string ver = ReadVersion();
                string mach = Common.MachineId();
                string title = ("crash: " + exeName + " " + et + " " + sig);
                if (title.Length > 200) title = title.Substring(0, 200);
                string tb = "";
                try { tb = Redact(ex == null ? et : ex.ToString()); } catch { tb = et + ": " + msg; }
                if (tb.Length > 12000) tb = tb.Substring(tb.Length - 12000);
                string body =
                    "what: unhandled exception in `" + exeName + "`\n" +
                    "where: machine=`" + mach + "` version=`" + ver + "` platform=`" + Environment.OSVersion + "`\n" +
                    "crash-sig:" + sig + "\n" +
                    "exception: " + et + ": " + msg + "\n\n" +
                    "```\n" + tb + "\n```\n" +
                    "\n---\n_via-crash-hook exe=`" + exeName + "` sig=`" + sig + "` ts=`" +
                    DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "`_\n";

                if (!TryPostIntake(title, body, sig, exeName))
                {
                    WriteSpool(title, body, sig, exeName, "post_failed");
                }
            }
            catch
            {
                try
                {
                    WriteSpool(
                        "crash: " + (exeName ?? "dialog") + " hook-failure",
                        Redact("crash hook failed"),
                        "hookfail",
                        exeName ?? "dialog",
                        "hook_failure");
                }
                catch { }
            }
        }

        public static void FlushSpool()
        {
            try
            {
                string dir = SpoolDir();
                if (!Directory.Exists(dir)) return;
                string[] files = Directory.GetFiles(dir, "crash-*.json");
                Array.Sort(files);
                JavaScriptSerializer ser = new JavaScriptSerializer();
                foreach (string path in files)
                {
                    try
                    {
                        Dictionary<string, object> payload = ser.DeserializeObject(File.ReadAllText(path, Encoding.UTF8)) as Dictionary<string, object>;
                        if (payload == null) { try { File.Delete(path); } catch { } continue; }
                        string title = Convert.ToString(payload.ContainsKey("title") ? payload["title"] : "crash: spool") ?? "crash: spool";
                        string body = Convert.ToString(payload.ContainsKey("body") ? payload["body"] : "") ?? "";
                        string sig = Convert.ToString(payload.ContainsKey("sig") ? payload["sig"] : Path.GetFileNameWithoutExtension(path)) ?? "unknown";
                        string exe = Convert.ToString(payload.ContainsKey("exe") ? payload["exe"] : "unknown") ?? "unknown";
                        if (TryPostIntake(title, body, sig, exe))
                        {
                            try { File.Delete(path); } catch { }
                        }
                    }
                    catch { }
                }
            }
            catch { }
        }

        static string ReadVersion()
        {
            try
            {
                string env = (Environment.GetEnvironmentVariable("BOBIVERSE_VERSION") ?? Environment.GetEnvironmentVariable("BOB_VERSION") ?? "").Trim();
                if (env.Length > 0) return env;
                string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
                if (string.Equals(Path.GetFileName(root), "tools", StringComparison.OrdinalIgnoreCase))
                    root = Path.GetDirectoryName(root) ?? root;
                string verPath = Path.Combine(root, "VERSION");
                if (File.Exists(verPath))
                {
                    string v = File.ReadAllText(verPath, Encoding.UTF8).Trim();
                    if (v.Length > 64) v = v.Substring(0, 64);
                    if (v.Length > 0) return v;
                }
            }
            catch { }
            return "unknown";
        }

        static string FindReportScript()
        {
            try
            {
                string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
                if (string.Equals(Path.GetFileName(root), "tools", StringComparison.OrdinalIgnoreCase))
                    root = Path.GetDirectoryName(root) ?? root;
                string[] cands = new string[] {
                    Path.Combine(root, "scripts", "Report-BobiverseIntakeIssue.ps1"),
                    Path.Combine(root, "common", "scripts", "Report-BobiverseIntakeIssue.ps1")
                };
                foreach (string c in cands) if (File.Exists(c)) return c;
            }
            catch { }
            return null;
        }

        static bool TryPostIntake(string title, string body, string sig, string exeName)
        {
            try
            {
                string script = FindReportScript();
                if (script == null) return false;
                string ps = null;
                foreach (string c in new string[] {
                    Path.Combine(Environment.SystemDirectory, "WindowsPowerShell", "v1.0", "powershell.exe"),
                    "powershell.exe" })
                {
                    if (c == "powershell.exe" || File.Exists(c)) { ps = c; break; }
                }
                if (ps == null) return false;

                // Write body to a temp file to avoid argv length / quoting issues on WinPS 5.1.
                string tmpBody = Path.Combine(Path.GetTempPath(), "bob-crash-" + sig + "-" + Process.GetCurrentProcess().Id + ".txt");
                File.WriteAllText(tmpBody, body, new UTF8Encoding(false));
                try
                {
                    string cmd =
                        "$ErrorActionPreference='Stop'; " +
                        "$body = Get-Content -LiteralPath '" + tmpBody.Replace("'", "''") + "' -Raw -Encoding UTF8; " +
                        "& '" + script.Replace("'", "''") + "' -Repo 'SimonBarnett/bobiverse' -Kind issue " +
                        "-Title '" + title.Replace("'", "''") + "' -Body $body " +
                        "-IdempotencyKey 'crash-" + sig + "' -Agent 'crash_hook:" + exeName + "' -TimeoutSec 8";
                    ProcessStartInfo psi = new ProcessStartInfo(ps, "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"" + cmd.Replace("\"", "\\\"") + "\"");
                    psi.UseShellExecute = false;
                    psi.CreateNoWindow = true;
                    psi.RedirectStandardOutput = true;
                    psi.RedirectStandardError = true;
                    using (Process p = Process.Start(psi))
                    {
                        if (p == null) return false;
                        if (!p.WaitForExit(12000))
                        {
                            try { p.Kill(); } catch { }
                            return false;
                        }
                        return p.ExitCode == 0;
                    }
                }
                finally
                {
                    try { File.Delete(tmpBody); } catch { }
                }
            }
            catch
            {
                return false;
            }
        }

        static void WriteSpool(string title, string body, string sig, string exeName, string error)
        {
            string dir = SpoolDir();
            Directory.CreateDirectory(dir);
            Dictionary<string, object> payload = new Dictionary<string, object>();
            payload["title"] = title;
            payload["body"] = body;
            payload["repo"] = "SimonBarnett/bobiverse";
            payload["sig"] = sig;
            payload["exe"] = exeName;
            payload["error"] = error;
            payload["ts"] = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            long epoch = (long)(DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
            string path = Path.Combine(dir, "crash-" + sig + "-" + epoch + ".json");
            File.WriteAllText(path, new JavaScriptSerializer().Serialize(payload), new UTF8Encoding(false));
        }
    }
}
