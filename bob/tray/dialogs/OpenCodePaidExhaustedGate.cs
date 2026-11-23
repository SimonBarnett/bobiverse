using System;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;

namespace BobDialogs
{
    // FR #8733 / BOB-28: Workers > Open Code — dialog + quit when free and paid are both exhausted.
    // Fuel file: run/opencode-fuel.json (or BOB_OPENCODE_FUEL_FILE / BOB_OPENCODE_FUEL_CACHE_FILE).
    // Keys: free + go (paid). Null / missing fields do not gate (unknown ≠ exhausted).
    public static class OpenCodePaidExhaustedGate
    {
        public const string Title = "Bobiverse - Open Code";
        public const string Body = "OpenCode free and paid fuel are exhausted. Not starting an OpenCode seat.";

        public static string ResolvePath(string root, string envPath)
        {
            if (!string.IsNullOrEmpty(envPath)) return envPath;
            string cache = Environment.GetEnvironmentVariable("BOB_OPENCODE_FUEL_CACHE_FILE");
            if (!string.IsNullOrEmpty(cache)) return cache;
            if (string.IsNullOrEmpty(root)) return "";
            return Path.Combine(root, "run", "opencode-fuel.json");
        }

        static bool TryReadPct(string json, string key, out int pct)
        {
            pct = 0;
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(key)) return false;
            // Match "key": <int> only — null / missing leave the field unknown.
            Match m = Regex.Match(
                json,
                "\"" + Regex.Escape(key) + "\"\\s*:\\s*(-?\\d+)",
                RegexOptions.CultureInvariant);
            if (!m.Success) return false;
            return int.TryParse(m.Groups[1].Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out pct);
        }

        public static bool IsExhaustedDocument(string json)
        {
            if (string.IsNullOrEmpty(json)) return false;
            int free;
            int paid;
            // Prefer free/go (Get-BobOpencodeFuel cache). Accept opencode-free / opencode-go aliases.
            bool haveFree = TryReadPct(json, "free", out free) || TryReadPct(json, "opencode-free", out free);
            bool havePaid = TryReadPct(json, "go", out paid)
                || TryReadPct(json, "paid", out paid)
                || TryReadPct(json, "opencode-go", out paid);
            if (!haveFree || !havePaid) return false;
            return free <= 0 && paid <= 0;
        }

        public static bool ShouldQuit(string root, string envPath)
        {
            string path = ResolvePath(root, envPath);
            if (string.IsNullOrEmpty(path) || !File.Exists(path)) return false;
            try { return IsExhaustedDocument(File.ReadAllText(path)); }
            catch { return false; }
        }

        public static string DumpStatusJson(string root, string envPath)
        {
            string path = ResolvePath(root, envPath);
            bool exhausted = ShouldQuit(root, envPath);
            return "{\"ok\":true,\"exhausted\":" + (exhausted ? "true" : "false")
                + ",\"gate\":\"opencode-paid-exhausted\",\"source\":\""
                + (path ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
        }
    }
}
