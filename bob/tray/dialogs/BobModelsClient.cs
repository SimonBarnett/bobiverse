// FR #8714 / BOB-13: Weights form client for GET/PUT /bob/v1/models (BOB-01/02 contract).
// FR #9266 / BOB-TRAY-UI-06: Discover local CLI models + POST /bob/v1/models/refresh catalog.
// C# 5 / .NET Framework 4. Peer-IP gate is server-side; client does not invent auth headers.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace BobDialogs
{
    internal sealed class BobModelsComboRow
    {
        public string Model = "";
        public List<string> Contexts = new List<string>();
        public List<string> Efforts = new List<string>();
    }

    internal sealed class BobModelsResult
    {
        public bool Ok;
        public int Status;
        public string Error = "";
        public string Url = "";
        public string UrlHost = "";
        public string BodyHash = "";
        public string Method = "";
        public List<Dictionary<string, string>> Rows = new List<Dictionary<string, string>>();
        // FR #8716 / BOB-14: webhook allow-list keyed by lowercase CLI (grok/cursor/opencode).
        public Dictionary<string, List<BobModelsComboRow>> Clis =
            new Dictionary<string, List<BobModelsComboRow>>(StringComparer.OrdinalIgnoreCase);
        public string RawBody = "";
    }

    /// <summary>FR #9266: local CLI listing result before POST refresh.</summary>
    internal sealed class BobModelsDiscoverResult
    {
        public Dictionary<string, List<string>> Models =
            new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, string> Reasons =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        public int TotalCount;
    }

    internal static class BobModelsClient
    {
        public const string ModelsPath = "/bob/v1/models";
        public const string ModelsRefreshPath = "/bob/v1/models/refresh";
        public const int GetTimeoutMs = 15000;
        public const int PutTimeoutMs = 30000;
        public const int RefreshTimeoutMs = 60000;
        public const int DiscoverTimeoutMs = 20000;
        static readonly string[] RefreshClis = new string[] { "grok", "cursor", "opencode" };
        static readonly Regex AnsiRe = new Regex(@"\x1b\[[0-9;]*[A-Za-z]", RegexOptions.Compiled);
        static readonly Regex HeaderRe = new Regex(
            @"^(available models|models|default model|you are logged|logged in)\b",
            RegexOptions.IgnoreCase | RegexOptions.Compiled);
        static readonly Regex OpencodeModelRe = new Regex(
            @"^[\w.\-]+/[\w.\-:]+$",
            RegexOptions.Compiled);

        public static string ResolveUrl(string installRoot)
        {
            string envUrl = (Environment.GetEnvironmentVariable("BOB_MODELS_URL") ?? "").Trim();
            if (envUrl.Length > 0) return envUrl;

            string fromCfg = ReadConfigString(installRoot, "modelsUrl");
            if (fromCfg.Length > 0) return fromCfg;

            string digest = (Environment.GetEnvironmentVariable("BOB_DIGEST_URL") ?? "").Trim();
            if (digest.Length == 0)
                digest = (Environment.GetEnvironmentVariable("BOB_DIGEST_REPORT_URL") ?? "").Trim();
            if (digest.Length == 0)
                digest = ReadConfigString(installRoot, "digestUrl");
            if (digest.Length == 0)
                digest = ReadConfigString(installRoot, "reportUrl");
            if (digest.Length == 0)
                digest = "https://bob.ntsa.uk/bob/v1/report";

            try
            {
                Uri u = new Uri(digest);
                string root = u.GetLeftPart(UriPartial.Authority);
                return root.TrimEnd('/') + ModelsPath;
            }
            catch
            {
                return "https://bob.ntsa.uk" + ModelsPath;
            }
        }

        static string ReadConfigString(string installRoot, string key)
        {
            string[] cands = ConfigCandidates(installRoot);
            for (int i = 0; i < cands.Length; i++)
            {
                string path = cands[i];
                if (path.Length == 0 || !File.Exists(path)) continue;
                try
                {
                    string text = File.ReadAllText(path, Encoding.UTF8);
                    if (text.Length > 0 && text[0] == '\uFEFF') text = text.Substring(1);
                    Dictionary<string, object> doc = Common.Dict(Common.ParseJson(text));
                    if (doc == null) continue;
                    object v;
                    if (!doc.TryGetValue(key, out v) || v == null) continue;
                    string s = Convert.ToString(v) ?? "";
                    s = s.Trim();
                    if (s.Length > 0) return s;
                }
                catch { }
            }
            return "";
        }

        static string[] ConfigCandidates(string installRoot)
        {
            string root = installRoot ?? "";
            string localApp = Environment.GetEnvironmentVariable("LOCALAPPDATA") ?? "";
            return new string[] {
                Path.Combine(root, "config", "bobiverse.local.json"),
                Path.Combine(root, "config", "bobiverse.json"),
                Path.Combine(root, "tray", "config", "bobiverse.local.json"),
                Path.Combine(root, "tray", "config", "bobiverse.json"),
                localApp.Length > 0 ? Path.Combine(localApp, "Bobiverse", "bobiverse.local.json") : "",
                localApp.Length > 0 ? Path.Combine(localApp, "Bobiverse", "bobiverse.json") : ""
            };
        }

        public static string ResolveRefreshUrl(string installRoot)
        {
            string models = ResolveUrl(installRoot);
            if (models.EndsWith(ModelsPath, StringComparison.OrdinalIgnoreCase))
                return models.Substring(0, models.Length - ModelsPath.Length) + ModelsRefreshPath;
            try
            {
                Uri u = new Uri(models);
                return u.GetLeftPart(UriPartial.Authority).TrimEnd('/') + ModelsRefreshPath;
            }
            catch
            {
                return "https://bob.ntsa.uk" + ModelsRefreshPath;
            }
        }

        /// <summary>
        /// FR #9266: run local ``grok models`` / ``agent models`` / ``opencode models`` on this seat.
        /// Chair/Ergo must not spawn these CLIs; Weights posts the result to /models/refresh.
        /// </summary>
        public static BobModelsDiscoverResult DiscoverLocalModels()
        {
            BobModelsDiscoverResult r = new BobModelsDiscoverResult();
            for (int i = 0; i < RefreshClis.Length; i++)
            {
                string cli = RefreshClis[i];
                string reason;
                List<string> ids = DiscoverOne(cli, out reason);
                r.Reasons[cli] = reason ?? "";
                r.Models[cli] = ids != null ? ids : new List<string>();
                if (ids != null) r.TotalCount += ids.Count;
            }
            return r;
        }

        public static BobModelsResult PostClientCatalog(
            string installRoot,
            Dictionary<string, List<string>> catalog)
        {
            BobModelsResult r = new BobModelsResult();
            r.Method = "POST";
            r.Url = ResolveRefreshUrl(installRoot);
            r.UrlHost = HostOf(r.Url);
            string body = SerializeClientCatalog(catalog);
            r.BodyHash = Sha256Hex(body);
            try
            {
                byte[] bytes = Encoding.UTF8.GetBytes(body);
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(r.Url);
                req.Method = "POST";
                req.Timeout = RefreshTimeoutMs;
                req.ReadWriteTimeout = RefreshTimeoutMs;
                req.ContentType = "application/json; charset=utf-8";
                req.Accept = "application/json";
                req.ContentLength = bytes.Length;
                using (Stream s = req.GetRequestStream())
                {
                    s.Write(bytes, 0, bytes.Length);
                }
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    r.Status = (int)resp.StatusCode;
                    r.RawBody = ReadBody(resp);
                    r.Clis = ParseClis(r.RawBody);
                    r.Ok = r.Status >= 200 && r.Status < 300;
                    if (!r.Ok) r.Error = ShortError(r.RawBody, r.Status);
                }
            }
            catch (WebException wex)
            {
                FillWebException(r, wex);
            }
            catch (Exception ex)
            {
                r.Ok = false;
                r.Error = Redact(ex.GetType().Name + ": " + ex.Message);
            }
            return r;
        }

        public static string SerializeClientCatalog(Dictionary<string, List<string>> catalog)
        {
            Dictionary<string, object> doc = new Dictionary<string, object>();
            doc["source"] = "weights-client";
            Dictionary<string, object> clis = new Dictionary<string, object>();
            if (catalog != null)
            {
                foreach (KeyValuePair<string, List<string>> kv in catalog)
                {
                    string cli = (kv.Key ?? "").Trim().ToLowerInvariant();
                    if (cli.Length == 0) continue;
                    ArrayList ids = new ArrayList();
                    List<string> list = kv.Value;
                    if (list != null)
                    {
                        for (int i = 0; i < list.Count; i++)
                        {
                            string m = (list[i] ?? "").Trim();
                            if (m.Length > 0) ids.Add(m);
                        }
                    }
                    if (ids.Count == 0) continue;
                    clis[cli] = ids;
                }
            }
            doc["clis"] = clis;
            return new JavaScriptSerializer().Serialize(doc);
        }

        static List<string> DiscoverOne(string cli, out string reason)
        {
            reason = "not_installed";
            string exe = null;
            string arg = "models";
            if (cli == "grok")
            {
                exe = ResolveGrokExe();
            }
            else if (cli == "cursor")
            {
                exe = ResolveCursorAgent();
            }
            else if (cli == "opencode")
            {
                exe = ResolveOpencodeExe();
            }
            if (string.IsNullOrEmpty(exe))
            {
                reason = "not_installed";
                return new List<string>();
            }
            string stdout;
            int exitCode;
            if (!RunListing(exe, arg, out stdout, out exitCode, out reason))
                return new List<string>();
            if (exitCode != 0)
            {
                reason = "exit_nonzero";
                return new List<string>();
            }
            List<string> ids = cli == "opencode"
                ? ParseOpencodeModelsText(stdout)
                : ParseGrokModelsText(stdout);
            if (ids == null || ids.Count == 0)
            {
                reason = "empty_listing";
                return new List<string>();
            }
            reason = "ok";
            return ids;
        }

        static string ResolveGrokExe()
        {
            string explicitExe = (Environment.GetEnvironmentVariable("BOB_GROK_EXE") ?? "").Trim();
            if (explicitExe.Length > 0 && File.Exists(explicitExe)) return explicitExe;
            string which = WhichOnPath("grok");
            if (which.Length > 0) return which;
            string home = Environment.GetEnvironmentVariable("USERPROFILE")
                ?? Environment.GetEnvironmentVariable("HOME")
                ?? "";
            if (home.Length > 0)
            {
                string cand = Path.Combine(home, ".grok", "bin", "grok.exe");
                if (File.Exists(cand)) return cand;
            }
            return "";
        }

        static string ResolveCursorAgent()
        {
            string local = Environment.GetEnvironmentVariable("LOCALAPPDATA") ?? "";
            if (local.Length > 0)
            {
                string cand = Path.Combine(local, "cursor-agent", "agent.cmd");
                if (File.Exists(cand)) return cand;
            }
            string[] names = new string[] { "agent.cmd", "cursor-agent.cmd", "agent", "cursor-agent" };
            for (int i = 0; i < names.Length; i++)
            {
                string found = WhichOnPath(names[i]);
                if (found.Length == 0) continue;
                if (found.EndsWith("agent.exe", StringComparison.OrdinalIgnoreCase)) continue;
                return found;
            }
            return "";
        }

        static string ResolveOpencodeExe()
        {
            string explicitExe = (Environment.GetEnvironmentVariable("BOB_OPENCODE_EXE") ?? "").Trim();
            if (explicitExe.Length > 0 && File.Exists(explicitExe)) return explicitExe;
            return WhichOnPath("opencode");
        }

        static string WhichOnPath(string name)
        {
            if (string.IsNullOrEmpty(name)) return "";
            string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
            string[] parts = pathEnv.Split(new char[] { ';' }, StringSplitOptions.RemoveEmptyEntries);
            string[] exts = new string[] { "", ".exe", ".cmd", ".bat" };
            for (int i = 0; i < parts.Length; i++)
            {
                string dir = parts[i].Trim().Trim('"');
                if (dir.Length == 0) continue;
                for (int e = 0; e < exts.Length; e++)
                {
                    string cand = Path.Combine(dir, name + exts[e]);
                    if (File.Exists(cand)) return cand;
                }
            }
            return "";
        }

        static bool RunListing(string exe, string arg, out string stdout, out int exitCode, out string reason)
        {
            stdout = "";
            exitCode = -1;
            reason = "ok";
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = exe;
                psi.Arguments = arg;
                psi.UseShellExecute = false;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                psi.RedirectStandardInput = true;
                psi.CreateNoWindow = true;
                psi.StandardOutputEncoding = Encoding.UTF8;
                string disable = Environment.GetEnvironmentVariable("GROK_DISABLE_AUTOUPDATER");
                if (string.IsNullOrEmpty(disable))
                    psi.EnvironmentVariables["GROK_DISABLE_AUTOUPDATER"] = "1";
                using (Process p = Process.Start(psi))
                {
                    if (p == null)
                    {
                        reason = "spawn_error";
                        return false;
                    }
                    StringBuilder sb = new StringBuilder();
                    p.OutputDataReceived += delegate(object s, DataReceivedEventArgs e)
                    {
                        if (e.Data != null) sb.AppendLine(e.Data);
                    };
                    p.BeginOutputReadLine();
                    if (!p.WaitForExit(DiscoverTimeoutMs))
                    {
                        try { p.Kill(); } catch { }
                        reason = "timeout";
                        return false;
                    }
                    // Drain async output after exit.
                    p.WaitForExit();
                    exitCode = p.ExitCode;
                    stdout = sb.ToString();
                    if (stdout.Length > 256 * 1024)
                        stdout = stdout.Substring(0, 256 * 1024);
                    return true;
                }
            }
            catch (System.ComponentModel.Win32Exception)
            {
                reason = "not_installed";
                return false;
            }
            catch
            {
                reason = "spawn_error";
                return false;
            }
        }

        public static List<string> ParseGrokModelsText(string text)
        {
            List<string> outList = new List<string>();
            if (string.IsNullOrEmpty(text)) return outList;
            string cleaned = AnsiRe.Replace(text, "");
            string[] lines = cleaned.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
            Dictionary<string, bool> seen = new Dictionary<string, bool>(StringComparer.Ordinal);
            for (int i = 0; i < lines.Length; i++)
            {
                string line = (lines[i] ?? "").Trim();
                if (line.Length == 0 || line.StartsWith("#")) continue;
                if (HeaderRe.IsMatch(line)) continue;
                if (line.ToLowerInvariant().StartsWith("default model:")) continue;
                if (line.StartsWith("* ") || line.StartsWith("- ") || line.StartsWith("\u2022 "))
                    line = line.Substring(2).Trim();
                line = Regex.Replace(line, @"\s*\([^)]*\)\s*$", "").Trim();
                int dash = line.IndexOf(" - ", StringComparison.Ordinal);
                if (dash > 0) line = line.Substring(0, dash).Trim();
                string token = "";
                string[] parts = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length > 0) token = parts[0].Trim().Trim('*');
                if (token.Length == 0) continue;
                if (!Regex.IsMatch(token, @"^[\w.\-]+$")) continue;
                string lower = token.ToLowerInvariant();
                if (lower == "available" || lower == "models" || lower == "model" || lower == "default")
                    continue;
                if (seen.ContainsKey(token)) continue;
                seen[token] = true;
                outList.Add(token);
            }
            return outList;
        }

        public static List<string> ParseOpencodeModelsText(string text)
        {
            List<string> outList = new List<string>();
            if (string.IsNullOrEmpty(text)) return outList;
            string cleaned = AnsiRe.Replace(text, "");
            string[] lines = cleaned.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
            Dictionary<string, bool> seen = new Dictionary<string, bool>(StringComparer.Ordinal);
            for (int i = 0; i < lines.Length; i++)
            {
                string line = (lines[i] ?? "").Trim();
                if (line.Length == 0 || line.StartsWith("#")) continue;
                int dash = line.IndexOf(" - ", StringComparison.Ordinal);
                if (dash > 0) line = line.Substring(0, dash).Trim();
                line = Regex.Replace(line, @"\s*\([^)]*\)\s*$", "").Trim();
                if (!OpencodeModelRe.IsMatch(line)) continue;
                if (seen.ContainsKey(line)) continue;
                seen[line] = true;
                outList.Add(line);
            }
            return outList;
        }

        public static BobModelsResult Get(string installRoot)
        {
            BobModelsResult r = new BobModelsResult();
            r.Method = "GET";
            r.Url = ResolveUrl(installRoot);
            r.UrlHost = HostOf(r.Url);
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(r.Url);
                req.Method = "GET";
                req.Timeout = GetTimeoutMs;
                req.ReadWriteTimeout = GetTimeoutMs;
                req.Accept = "application/json";
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    r.Status = (int)resp.StatusCode;
                    r.RawBody = ReadBody(resp);
                    r.BodyHash = Sha256Hex(r.RawBody);
                    r.Rows = ParseAgents(r.RawBody);
                    r.Clis = ParseClis(r.RawBody);
                    r.Ok = r.Status >= 200 && r.Status < 300;
                    if (!r.Ok) r.Error = "HTTP " + r.Status;
                }
            }
            catch (WebException wex)
            {
                FillWebException(r, wex);
            }
            catch (Exception ex)
            {
                r.Ok = false;
                r.Error = Redact(ex.GetType().Name + ": " + ex.Message);
            }
            return r;
        }

        public static BobModelsResult Save(string installRoot, List<Dictionary<string, string>> rows)
        {
            BobModelsResult r = new BobModelsResult();
            r.Method = "PUT";
            r.Url = ResolveUrl(installRoot);
            r.UrlHost = HostOf(r.Url);
            string body = SerializeAgents(rows);
            r.BodyHash = Sha256Hex(body);
            try
            {
                byte[] bytes = Encoding.UTF8.GetBytes(body);
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(r.Url);
                req.Method = "PUT";
                req.Timeout = PutTimeoutMs;
                req.ReadWriteTimeout = PutTimeoutMs;
                req.ContentType = "application/json; charset=utf-8";
                req.Accept = "application/json";
                req.ContentLength = bytes.Length;
                using (Stream s = req.GetRequestStream())
                {
                    s.Write(bytes, 0, bytes.Length);
                }
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    r.Status = (int)resp.StatusCode;
                    r.RawBody = ReadBody(resp);
                    if (r.RawBody.Length > 0)
                        r.Rows = ParseAgents(r.RawBody);
                    else
                        r.Rows = rows != null ? CloneRows(rows) : new List<Dictionary<string, string>>();
                    r.Ok = r.Status >= 200 && r.Status < 300;
                    if (!r.Ok) r.Error = ShortError(r.RawBody, r.Status);
                }
            }
            catch (WebException wex)
            {
                FillWebException(r, wex);
            }
            catch (Exception ex)
            {
                r.Ok = false;
                r.Error = Redact(ex.GetType().Name + ": " + ex.Message);
            }
            return r;
        }

        public static bool RowsMatch(List<Dictionary<string, string>> a, List<Dictionary<string, string>> b)
        {
            if (a == null || b == null) return false;
            if (a.Count != b.Count) return false;
            Dictionary<string, Dictionary<string, string>> byAgent = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < b.Count; i++)
            {
                string agent = Get(b[i], "agent");
                if (agent.Length == 0) return false;
                byAgent[agent] = b[i];
            }
            for (int i = 0; i < a.Count; i++)
            {
                string agent = Get(a[i], "agent");
                Dictionary<string, string> other;
                if (!byAgent.TryGetValue(agent, out other)) return false;
                if (!string.Equals(Get(a[i], "cli"), Get(other, "cli"), StringComparison.Ordinal)
                    || !string.Equals(Get(a[i], "model"), Get(other, "model"), StringComparison.Ordinal)
                    || !string.Equals(Get(a[i], "context"), Get(other, "context"), StringComparison.Ordinal)
                    || !string.Equals(Get(a[i], "effort"), Get(other, "effort"), StringComparison.Ordinal))
                    return false;
            }
            return true;
        }

        public static string ResultToJson(BobModelsResult r)
        {
            Dictionary<string, object> doc = new Dictionary<string, object>();
            doc["ok"] = r != null && r.Ok;
            doc["status"] = r != null ? r.Status : 0;
            doc["error"] = r != null ? (r.Error ?? "") : "null result";
            doc["urlHost"] = r != null ? (r.UrlHost ?? "") : "";
            doc["method"] = r != null ? (r.Method ?? "") : "";
            doc["bodyHash"] = r != null ? (r.BodyHash ?? "") : "";
            ArrayList agents = new ArrayList();
            if (r != null && r.Rows != null)
            {
                for (int i = 0; i < r.Rows.Count; i++)
                {
                    Dictionary<string, object> row = new Dictionary<string, object>();
                    row["agent"] = Get(r.Rows[i], "agent");
                    row["cli"] = Get(r.Rows[i], "cli");
                    row["model"] = Get(r.Rows[i], "model");
                    row["context"] = Get(r.Rows[i], "context");
                    row["effort"] = Get(r.Rows[i], "effort");
                    agents.Add(row);
                }
            }
            doc["agents"] = agents;
            return new JavaScriptSerializer().Serialize(doc);
        }

        public static List<Dictionary<string, string>> ParseAgents(string json)
        {
            List<Dictionary<string, string>> rows = new List<Dictionary<string, string>>();
            if (string.IsNullOrEmpty(json)) return rows;
            string text = json;
            if (text.Length > 0 && text[0] == '\uFEFF') text = text.Substring(1);
            object parsed = Common.ParseJson(text);
            Dictionary<string, object> doc = Common.Dict(parsed);
            object agentsObj = null;
            if (doc != null && doc.ContainsKey("agents"))
                agentsObj = doc["agents"];
            else
                agentsObj = parsed;
            IEnumerable list = agentsObj as IEnumerable;
            if (list == null || agentsObj is string) return rows;
            foreach (object item in list)
            {
                // Skip Dictionary's own Keys/Values if someone passed a map by mistake.
                Dictionary<string, object> raw = Common.Dict(item);
                if (raw == null) continue;
                Dictionary<string, string> row = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                row["agent"] = Str(raw, "agent");
                row["cli"] = Str(raw, "cli");
                row["model"] = Str(raw, "model");
                row["context"] = Str(raw, "context");
                row["effort"] = Str(raw, "effort");
                if (row["agent"].Length == 0) continue;
                rows.Add(row);
            }
            return rows;
        }

        public static Dictionary<string, List<BobModelsComboRow>> ParseClis(string json)
        {
            // FR #8716 / FR #8819: clis from GET /bob/v1/models.
            // Nested Si shape (8819): clis[DisplayCli].models[model].contexts[ctx].efforts
            // Legacy flat list (8716): clis[cli] = [{model,contexts,efforts}, ...]
            Dictionary<string, List<BobModelsComboRow>> clis =
                new Dictionary<string, List<BobModelsComboRow>>(StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrEmpty(json)) return clis;
            string text = json;
            if (text.Length > 0 && text[0] == '﻿') text = text.Substring(1);
            object parsed = Common.ParseJson(text);
            Dictionary<string, object> doc = Common.Dict(parsed);
            if (doc == null || !doc.ContainsKey("clis")) return clis;
            Dictionary<string, object> rawClis = Common.Dict(doc["clis"]);
            if (rawClis == null) return clis;
            foreach (KeyValuePair<string, object> kv in rawClis)
            {
                string cli = (kv.Key ?? "").Trim().ToLowerInvariant();
                if (cli.Length == 0) continue;
                List<BobModelsComboRow> rows = new List<BobModelsComboRow>();
                Dictionary<string, object> nested = Common.Dict(kv.Value);
                if (nested != null && nested.ContainsKey("models"))
                {
                    Dictionary<string, object> models = Common.Dict(nested["models"]);
                    if (models != null)
                    {
                        foreach (KeyValuePair<string, object> mk in models)
                        {
                            string model = (mk.Key ?? "").Trim();
                            if (model.Length == 0) continue;
                            Dictionary<string, object> modelObj = Common.Dict(mk.Value);
                            if (modelObj == null) continue;
                            object ctxRaw = modelObj.ContainsKey("contexts") ? modelObj["contexts"] : null;
                            Dictionary<string, object> ctxMap = Common.Dict(ctxRaw);
                            BobModelsComboRow row = new BobModelsComboRow();
                            row.Model = model;
                            row.Contexts = new List<string>();
                            row.Efforts = new List<string>();
                            if (ctxMap != null)
                            {
                                foreach (KeyValuePair<string, object> ck in ctxMap)
                                {
                                    string ctx = (ck.Key ?? "").Trim();
                                    if (ctx.Length == 0) continue;
                                    if (!row.Contexts.Contains(ctx)) row.Contexts.Add(ctx);
                                    Dictionary<string, object> ctxObj = Common.Dict(ck.Value);
                                    if (ctxObj == null) continue;
                                    List<string> efforts = StrList(ctxObj, "efforts");
                                    for (int ei = 0; ei < efforts.Count; ei++)
                                    {
                                        string e = efforts[ei];
                                        if (e.Length == 0) continue;
                                        if (!row.Efforts.Contains(e)) row.Efforts.Add(e);
                                    }
                                }
                            }
                            rows.Add(row);
                        }
                    }
                }
                else
                {
                    IEnumerable list = kv.Value as IEnumerable;
                    if (list == null || kv.Value is string) continue;
                    foreach (object item in list)
                    {
                        Dictionary<string, object> raw = Common.Dict(item);
                        if (raw == null) continue;
                        BobModelsComboRow row = new BobModelsComboRow();
                        row.Model = Str(raw, "model");
                        if (row.Model.Length == 0) continue;
                        row.Contexts = StrList(raw, "contexts");
                        row.Efforts = StrList(raw, "efforts");
                        rows.Add(row);
                    }
                }
                clis[cli] = rows;
            }
            return clis;
        }

        static List<string> StrList(Dictionary<string, object> raw, string key)
        {
            List<string> outList = new List<string>();
            if (raw == null || !raw.ContainsKey(key)) return outList;
            IEnumerable list = raw[key] as IEnumerable;
            if (list == null || raw[key] is string) return outList;
            foreach (object item in list)
            {
                if (item == null) continue;
                string s = Convert.ToString(item);
                if (s == null) continue;
                s = s.Trim();
                if (s.Length > 0) outList.Add(s);
            }
            return outList;
        }

        public static List<string> ModelsForCli(Dictionary<string, List<BobModelsComboRow>> clis, string cli)
        {
            List<string> models = new List<string>();
            List<BobModelsComboRow> rows = RowsForCli(clis, cli);
            if (rows == null) return models;
            for (int i = 0; i < rows.Count; i++)
            {
                string m = rows[i].Model ?? "";
                if (m.Length == 0) continue;
                if (!models.Contains(m)) models.Add(m);
            }
            return models;
        }

        public static List<string> ContextsFor(Dictionary<string, List<BobModelsComboRow>> clis, string cli, string model)
        {
            return FieldFor(clis, cli, model, true);
        }

        public static List<string> EffortsFor(Dictionary<string, List<BobModelsComboRow>> clis, string cli, string model)
        {
            return FieldFor(clis, cli, model, false);
        }

        static List<string> FieldFor(Dictionary<string, List<BobModelsComboRow>> clis, string cli, string model, bool contexts)
        {
            List<string> values = new List<string>();
            List<BobModelsComboRow> rows = RowsForCli(clis, cli);
            if (rows == null) return values;
            string want = (model ?? "").Trim();
            for (int i = 0; i < rows.Count; i++)
            {
                if (want.Length > 0 && !string.Equals(rows[i].Model, want, StringComparison.Ordinal))
                    continue;
                List<string> src = contexts ? rows[i].Contexts : rows[i].Efforts;
                if (src == null) continue;
                for (int j = 0; j < src.Count; j++)
                {
                    string v = src[j] ?? "";
                    if (v.Length == 0) continue;
                    if (!values.Contains(v)) values.Add(v);
                }
            }
            return values;
        }

        static List<BobModelsComboRow> RowsForCli(Dictionary<string, List<BobModelsComboRow>> clis, string cli)
        {
            if (clis == null) return null;
            string key = (cli ?? "").Trim().ToLowerInvariant();
            if (key.Length == 0) return null;
            List<BobModelsComboRow> rows;
            if (clis.TryGetValue(key, out rows)) return rows;
            return null;
        }

        public static string SerializeAgents(List<Dictionary<string, string>> rows)
        {
            ArrayList agents = new ArrayList();
            if (rows != null)
            {
                for (int i = 0; i < rows.Count; i++)
                {
                    Dictionary<string, object> row = new Dictionary<string, object>();
                    row["agent"] = Get(rows[i], "agent");
                    row["cli"] = Get(rows[i], "cli");
                    row["model"] = Get(rows[i], "model");
                    row["context"] = Get(rows[i], "context");
                    row["effort"] = Get(rows[i], "effort");
                    agents.Add(row);
                }
            }
            Dictionary<string, object> doc = new Dictionary<string, object>();
            doc["agents"] = agents;
            return new JavaScriptSerializer().Serialize(doc);
        }

        public static string Sha256Hex(string text)
        {
            if (text == null) text = "";
            using (SHA256 sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes(text));
                StringBuilder sb = new StringBuilder(hash.Length * 2);
                for (int i = 0; i < hash.Length; i++) sb.Append(hash[i].ToString("x2"));
                return sb.ToString();
            }
        }

        static List<Dictionary<string, string>> CloneRows(List<Dictionary<string, string>> rows)
        {
            List<Dictionary<string, string>> outRows = new List<Dictionary<string, string>>();
            for (int i = 0; i < rows.Count; i++)
            {
                Dictionary<string, string> c = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                c["agent"] = Get(rows[i], "agent");
                c["cli"] = Get(rows[i], "cli");
                c["model"] = Get(rows[i], "model");
                c["context"] = Get(rows[i], "context");
                c["effort"] = Get(rows[i], "effort");
                outRows.Add(c);
            }
            return outRows;
        }

        static void FillWebException(BobModelsResult r, WebException wex)
        {
            r.Ok = false;
            HttpWebResponse resp = wex.Response as HttpWebResponse;
            if (resp != null)
            {
                try { r.Status = (int)resp.StatusCode; } catch { }
                try { r.RawBody = ReadBody(resp); } catch { r.RawBody = ""; }
                r.Error = ShortError(r.RawBody, r.Status);
            }
            else
            {
                r.Error = Redact(wex.Status.ToString() + ": " + wex.Message);
            }
        }

        static string ShortError(string body, int status)
        {
            string msg = "";
            try
            {
                Dictionary<string, object> doc = Common.Dict(Common.ParseJson(body ?? ""));
                if (doc != null && doc.ContainsKey("error") && doc["error"] != null)
                    msg = Convert.ToString(doc["error"]) ?? "";
            }
            catch { }
            if (msg.Length == 0) msg = "HTTP " + status;
            return Redact(msg);
        }

        static string ReadBody(HttpWebResponse resp)
        {
            using (Stream s = resp.GetResponseStream())
            using (StreamReader sr = new StreamReader(s, Encoding.UTF8))
            {
                string text = sr.ReadToEnd() ?? "";
                if (text.Length > 0 && text[0] == '\uFEFF') text = text.Substring(1);
                return text;
            }
        }

        static string HostOf(string url)
        {
            try { return new Uri(url).Host; }
            catch { return ""; }
        }

        static string Get(Dictionary<string, string> row, string key)
        {
            if (row == null) return "";
            string v;
            if (!row.TryGetValue(key, out v) || v == null) return "";
            return v;
        }

        static string Str(Dictionary<string, object> raw, string key)
        {
            object v;
            if (!raw.TryGetValue(key, out v) || v == null) return "";
            return (Convert.ToString(v) ?? "").Trim();
        }

        static string Redact(string s)
        {
            if (s == null) return "";
            string outS = s;
            string[] secrets = new string[] {
                Environment.GetEnvironmentVariable("BOB_MODELS_TOKEN") ?? "",
                Environment.GetEnvironmentVariable("BOB_GIT_WEBHOOK_SECRET") ?? ""
            };
            for (int i = 0; i < secrets.Length; i++)
            {
                string sec = (secrets[i] ?? "").Trim();
                if (sec.Length >= 8)
                    outS = outS.Replace(sec, "REDACTED");
            }
            return outS;
        }
    }
}
