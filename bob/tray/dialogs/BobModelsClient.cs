// FR #8714 / BOB-13: Weights form client for GET/PUT /bob/v1/models (BOB-01/02 contract).
// C# 5 / .NET Framework 4. Peer-IP gate is server-side; client does not invent auth headers.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

namespace BobDialogs
{
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
        public string RawBody = "";
    }

    internal static class BobModelsClient
    {
        public const string ModelsPath = "/bob/v1/models";
        public const int GetTimeoutMs = 15000;
        public const int PutTimeoutMs = 30000;

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
