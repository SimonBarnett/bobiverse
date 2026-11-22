using System;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;

namespace BobDialogs
{
    public static class OpencodeFreeThenPaid
    {
        public static string ResolvePath(string root, string envPath)
        {
            if (!string.IsNullOrEmpty(envPath)) return envPath;
            if (string.IsNullOrEmpty(root)) return "";
            return Path.Combine(root, "run", "opencode-fuel.json");
        }

        public static string Choose(string json)
        {
            if (string.IsNullOrEmpty(json)) return "";
            int free;
            int paid;
            bool hasFree = TryInt(json, "free", out free);
            bool hasPaid = TryInt(json, "paid", out paid);
            if (hasFree && free > 0) return "free";
            if (hasFree && free <= 0 && hasPaid && paid > 0) return "paid";
            return "";
        }

        public static string ChooseFile(string root, string envPath)
        {
            string path = ResolvePath(root, envPath);
            if (string.IsNullOrEmpty(path) || !File.Exists(path)) return "";
            try { return Choose(File.ReadAllText(path)); }
            catch { return ""; }
        }

        static bool TryInt(string json, string key, out int n)
        {
            n = 0;
            Match m = Regex.Match(json, "\"" + key + "\"\\s*:\\s*(-?\\d+)");
            if (!m.Success) return false;
            return int.TryParse(m.Groups[1].Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out n);
        }
    }
}
