using System;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;

namespace BobDialogs
{
    public static class GrokNoTokenGate
    {
        public const string Title = "Bobiverse - Grok";
        public const string Body = "No tokens on this box. Grok will quit.";

        public static string ResolvePath(string root, string envPath)
        {
            if (!string.IsNullOrEmpty(envPath)) return envPath;
            if (string.IsNullOrEmpty(root)) return "";
            return Path.Combine(root, "run", "grok-fuel.json");
        }

        public static bool IsEmptyDocument(string json)
        {
            if (string.IsNullOrEmpty(json)) return false;
            Match m = Regex.Match(json, "\"remaining_pct\"\\s*:\\s*(-?\\d+)");
            if (!m.Success) return false;
            int n;
            if (!int.TryParse(m.Groups[1].Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out n))
                return false;
            return n <= 0;
        }

        public static bool ShouldQuit(string root, string envPath)
        {
            string path = ResolvePath(root, envPath);
            if (string.IsNullOrEmpty(path) || !File.Exists(path)) return false;
            try { return IsEmptyDocument(File.ReadAllText(path)); }
            catch { return false; }
        }
    }
}
