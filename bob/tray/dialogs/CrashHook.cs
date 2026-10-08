// FR #2411: unhandled exception in tray dialogs -> GitHub issue (dedupe + spool).
// FR #2436: skip probe / do-not-file / probe-shape-only (parity with crash_report.should_skip_report).
// FR #3328: honour BOB_CRASH_REPORT / crash-report.json opt-out (parity with FR #3291 / crash_report.CrashReportPolicy).
// FR #3452: local_only / error=local_only spool must never TryPostIntake on later FlushSpool.
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
    /// <summary>FR #3328 / FR #3291: whether CrashHook may leave the box (parity with Python CrashReportPolicy).</summary>
    internal sealed class CrashReportPolicy
    {
        public bool Send = true;
        public bool IncludeLogTail = true;
        public string Source = "default";
        public string Mode = "full"; // full | local-only | off

        public string LogLabel
        {
            get
            {
                if (!Send)
                {
                    if (string.Equals(Mode, "local-only", StringComparison.OrdinalIgnoreCase))
                        return "local-only";
                    return "off";
                }
                if (!IncludeLogTail) return "on (no-log-tail)";
                return "on";
            }
        }
    }

    internal static class CrashHook
    {
        static readonly object Gate = new object();
        static string InstalledFor;
        static CrashReportPolicy PolicyCache;
        // FR #2668: expand redaction parity with Python crash_report.redact
        static readonly Regex AuthSchemeRe = new Regex(
            @"(?i)\b(?:Authorization\s*[:=]\s*)?(Bearer|Basic)\s+\S+",
            RegexOptions.Compiled);
        static readonly Regex NickServRe = new Regex(
            @"(?i)(?:PRIVMSG\s+NickServ\s+:)?(?:NickServ\s+)?(IDENTIFY|REGISTER)\s+\S+(?:\s+\S+)?",
            RegexOptions.Compiled);
        static readonly Regex IrcPassRe = new Regex(
            @"(?i)\bPASS\s+\S+",
            RegexOptions.Compiled);
        static readonly Regex UrlUserinfoRe = new Regex(
            @"(?i)(https?://)[^/\s:@]+:[^/\s@]+@",
            RegexOptions.Compiled);
        // Optional quotes around key; value is full "..." (FR #2679 multi-word JSON) or bare token.
        static readonly Regex SecretKvRe = new Regex(
            @"(?i)""?(password|passwd|\bpass\b|secret|token|api[_-]?key|xai_api_key|cursor_api_key|BOB_IRC_PASSWORD|GH_TOKEN|GITHUB_TOKEN|Authorization|NickServ|SASL)""?\s*[:=]\s*(?:""[^""]*""|[^\s"",}]+)",
            RegexOptions.Compiled);
        static readonly Regex TokenBlobRe = new Regex(
            @"(?i)\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{10,}|xox[baprs]-[A-Za-z0-9-]+)\b",
            RegexOptions.Compiled);
        // FR #2436 / Python crash_report._DO_NOT_FILE_RE + _PROBE_EXE
        static readonly Regex DoNotFileRe = new Regex(
            @"(?i)do-not-file|probe-shape-only",
            RegexOptions.Compiled);

        /// <summary>
        /// FR #3328: resolve send/local-only/off (parity with crash_report.load_crash_report_policy).
        /// Precedence: BOB_CRASH_REPORT env &gt; crash-report.json &gt; airc shell=off default &gt; fleet on.
        /// </summary>
        public static CrashReportPolicy LoadCrashReportPolicy()
        {
            return LoadCrashReportPolicy(useCache: false);
        }

        public static CrashReportPolicy LoadCrashReportPolicy(bool useCache)
        {
            if (useCache && PolicyCache != null) return PolicyCache;
            CrashReportPolicy policy = ResolveCrashReportPolicy();
            if (useCache) PolicyCache = policy;
            return policy;
        }

        static CrashReportPolicy ResolveCrashReportPolicy()
        {
            CrashReportPolicy policy = new CrashReportPolicy();
            bool? send = null;
            string mode = "full";
            string source = "default";
            bool includeTail = true;

            string root = GuessInstallRoot();
            string cfgPath = ResolveCrashConfigPath(root);
            if (cfgPath != null)
            {
                Dictionary<string, object> cfg = ReadCrashConfig(cfgPath);
                if (cfg != null)
                {
                    if (cfg.ContainsKey("include_log_tail"))
                        includeTail = ToBool(cfg["include_log_tail"], true);
                    if (cfg.ContainsKey("no_log_tail") && ToBool(cfg["no_log_tail"], false))
                        includeTail = false;
                    string modeRaw = (Convert.ToString(cfg.ContainsKey("mode") ? cfg["mode"] : "") ?? "").Trim().ToLowerInvariant();
                    if (modeRaw == "local" || modeRaw == "local-only" || modeRaw == "local_only" || modeRaw == "spool")
                    {
                        send = false;
                        mode = "local-only";
                        source = "config";
                    }
                    else if (cfg.ContainsKey("enabled"))
                    {
                        send = ToBool(cfg["enabled"], true);
                        mode = send.Value ? "full" : "off";
                        source = "config";
                    }
                }
            }

            string prod = (Environment.GetEnvironmentVariable("BOB_PRODUCT") ?? "").Trim().ToLowerInvariant();
            bool looksAirc = prod == "airc"
                || (root != null && File.Exists(Path.Combine(root, "config", "airc.json")));
            if (send == null && looksAirc && AircShellOff(root))
            {
                send = false;
                mode = "off";
                source = "airc-shell-off";
            }

            string envRaw = (Environment.GetEnvironmentVariable("BOB_CRASH_REPORT") ?? "").Trim().ToLowerInvariant();
            if (envRaw.Length > 0)
            {
                if (envRaw == "local" || envRaw == "local-only" || envRaw == "local_only" || envRaw == "spool")
                {
                    send = false;
                    mode = "local-only";
                    source = "env";
                }
                else if (envRaw == "full" || envRaw == "on" || envRaw == "1" || envRaw == "true" || envRaw == "yes")
                {
                    send = true;
                    mode = "full";
                    source = "env";
                }
                else if (envRaw == "0" || envRaw == "false" || envRaw == "no" || envRaw == "off")
                {
                    send = false;
                    mode = "off";
                    source = "env";
                }
                else if (envRaw == "no-log-tail" || envRaw == "nologtail" || envRaw == "no_log_tail")
                {
                    if (send == null) send = true;
                    includeTail = false;
                    source = "env";
                }
            }

            if (send == null)
            {
                send = true;
                mode = "full";
                source = "default";
            }

            policy.Send = send.Value;
            policy.IncludeLogTail = includeTail;
            policy.Source = source;
            policy.Mode = send.Value ? "full" : mode;
            return policy;
        }

        static bool ToBool(object value, bool defaultValue)
        {
            if (value == null) return defaultValue;
            if (value is bool) return (bool)value;
            string s = Convert.ToString(value) ?? "";
            s = s.Trim().ToLowerInvariant();
            if (s == "1" || s == "true" || s == "yes" || s == "on") return true;
            if (s == "0" || s == "false" || s == "no" || s == "off") return false;
            return defaultValue;
        }

        static string GuessInstallRoot()
        {
            foreach (string key in new string[] { "BOB_INSTALL_ROOT", "AIRC_INSTALL_ROOT", "BOB_PRODUCT_ROOT" })
            {
                string v = (Environment.GetEnvironmentVariable(key) ?? "").Trim();
                if (v.Length > 0) return v;
            }
            try
            {
                string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
                if (string.Equals(Path.GetFileName(root), "tools", StringComparison.OrdinalIgnoreCase))
                    root = Path.GetDirectoryName(root) ?? root;
                if (Directory.Exists(Path.Combine(root, "config")) || Directory.Exists(Path.Combine(root, "scripts")))
                    return root;
            }
            catch { }
            return null;
        }

        static string ResolveCrashConfigPath(string installRoot)
        {
            string overridePath = (Environment.GetEnvironmentVariable("BOB_CRASH_REPORT_CONFIG") ?? "").Trim();
            if (overridePath.Length > 0) return overridePath;
            List<string> roots = new List<string>();
            if (!string.IsNullOrEmpty(installRoot)) roots.Add(installRoot);
            foreach (string key in new string[] { "BOB_INSTALL_ROOT", "AIRC_INSTALL_ROOT", "BOB_PRODUCT_ROOT" })
            {
                string v = (Environment.GetEnvironmentVariable(key) ?? "").Trim();
                if (v.Length > 0 && !roots.Contains(v)) roots.Add(v);
            }
            foreach (string root in roots)
            {
                string cand = Path.Combine(root, "config", "crash-report.json");
                if (File.Exists(cand)) return cand;
                string cand2 = Path.Combine(root, "crash-report.json");
                if (File.Exists(cand2)) return cand2;
            }
            return null;
        }

        static Dictionary<string, object> ReadCrashConfig(string path)
        {
            try
            {
                if (string.IsNullOrEmpty(path) || !File.Exists(path)) return null;
                JavaScriptSerializer ser = new JavaScriptSerializer();
                return ser.DeserializeObject(File.ReadAllText(path, Encoding.UTF8)) as Dictionary<string, object>;
            }
            catch
            {
                return null;
            }
        }

        static bool AircShellOff(string installRoot)
        {
            if (string.IsNullOrEmpty(installRoot)) return false;
            try
            {
                string aircJson = Path.Combine(installRoot, "config", "airc.json");
                if (!File.Exists(aircJson)) return false;
                JavaScriptSerializer ser = new JavaScriptSerializer();
                Dictionary<string, object> data = ser.DeserializeObject(File.ReadAllText(aircJson, Encoding.UTF8)) as Dictionary<string, object>;
                if (data == null) return false;
                string shell = (Convert.ToString(data.ContainsKey("shell") ? data["shell"] : "") ?? "").Trim().ToLowerInvariant();
                return shell == "off" || shell == "0" || shell == "false" || shell == "no";
            }
            catch
            {
                return false;
            }
        }

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
                // FR #3328: cache policy; only flush network when send is allowed.
                CrashReportPolicy policy = LoadCrashReportPolicy(useCache: true);
                try { if (policy.Send) FlushSpool(); } catch { }
                InstalledFor = exeName;
            }
        }

        public static string Redact(string text)
        {
            // FR #2411 / FR #2668 / FR #2679: parity with Python crash_report.redact
            if (string.IsNullOrEmpty(text)) return "";
            string s = AuthSchemeRe.Replace(text, delegate(Match m) { return m.Groups[1].Value + "=<redacted>"; });
            s = NickServRe.Replace(s, delegate(Match m) { return "NickServ " + m.Groups[1].Value + " <redacted>"; });
            s = IrcPassRe.Replace(s, "PASS <redacted>");
            s = UrlUserinfoRe.Replace(s, "$1<redacted>@");
            s = SecretKvRe.Replace(s, delegate(Match m) { return m.Groups[1].Value + "=<redacted>"; });
            return TokenBlobRe.Replace(s, "<redacted-token>");
        }

        /// <summary>
        /// FR #2436: shape/probe crashes must never create intake issues or spool forever.
        /// Markers match Python crash_report.should_skip_report: exe probe/crash-probe/crash_probe,
        /// or message/body/title containing do-not-file or probe-shape-only.
        /// </summary>
        public static bool ShouldSkipReport(string exeName, Exception ex)
        {
            return ShouldSkipReport(exeName, ex, null, null);
        }

        public static bool ShouldSkipReport(string exeName, Exception ex, string body, string title)
        {
            string name = (exeName ?? "").Trim().ToLowerInvariant();
            if (name == "probe" || name == "crash-probe" || name == "crash_probe")
                return true;
            string msg = "";
            try
            {
                if (ex != null) msg = ex.Message ?? "";
            }
            catch { msg = ""; }
            string blob = msg + "\n" + (body ?? "") + "\n" + (title ?? "");
            return DoNotFileRe.IsMatch(blob);
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
                // FR #2436: mirror crash_report.should_skip_report before intake/spool.
                if (ShouldSkipReport(exeName, ex))
                    return;

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

                // FR #3328: when opt-out / local-only, spool only — never intake/gh.
                CrashReportPolicy policy = LoadCrashReportPolicy();
                if (!policy.Send)
                {
                    WriteSpool(title, body, sig, exeName, "local_only");
                    return;
                }

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
                // FR #3328: keep spool locally; never intake while disabled/local-only.
                CrashReportPolicy policy = LoadCrashReportPolicy();
                if (!policy.Send) return;
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
                        // FR #3452: opt-out / local-only stamps must never POST later when Send becomes true.
                        bool localOnlyFlag = false;
                        if (payload.ContainsKey("local_only"))
                        {
                            object lo = payload["local_only"];
                            if (lo is bool) localOnlyFlag = (bool)lo;
                            else
                            {
                                string los = Convert.ToString(lo) ?? "";
                                localOnlyFlag = los.Equals("true", StringComparison.OrdinalIgnoreCase) || los == "1";
                            }
                        }
                        string errRaw = (Convert.ToString(payload.ContainsKey("error") ? payload["error"] : "") ?? "").Trim().ToLowerInvariant();
                        if (localOnlyFlag || errRaw == "local_only" || errRaw == "local-only" || errRaw == "local" || errRaw == "spool")
                        {
                            try { File.Delete(path); } catch { }
                            continue;
                        }
                        // FR #2436: drop probe / do-not-file spool payloads (parity with crash_report.flush_spool).
                        if (ShouldSkipReport(exe, null, body, title))
                        {
                            try { File.Delete(path); } catch { }
                            continue;
                        }
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
                // FR #3328: refuse network when policy.send is false (parity with crash_report._post_intake).
                CrashReportPolicy policy = LoadCrashReportPolicy();
                if (!policy.Send) return false;
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
            // FR #3452: stamp local_only bool when opt-out (parity with crash_report._write_spool).
            string errNorm = (error ?? "").Trim().ToLowerInvariant();
            if (errNorm == "local_only" || errNorm == "local-only" || errNorm == "local" || errNorm == "spool")
                payload["local_only"] = true;
            payload["ts"] = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            long epoch = (long)(DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
            string path = Path.Combine(dir, "crash-" + sig + "-" + epoch + ".json");
            File.WriteAllText(path, new JavaScriptSerializer().Serialize(payload), new UTF8Encoding(false));
        }
    }
}
