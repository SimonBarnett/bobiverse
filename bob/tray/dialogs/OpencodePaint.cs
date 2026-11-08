// OpenCode pool rows for the compiled Status card.
// C# 5 / .NET Framework 4. No WinForms: the card and the headless test both call this.
// Unknown rows draw an empty track. pct is remaining and is ignored unless known is true.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace BobDialogs
{
    internal sealed class OpencodeBarRow
    {
        public string Id = "";
        public string Heading = "";
        public bool Known;
        public int Pct;
    }

    internal static class OpencodePaint
    {
        public static List<OpencodeBarRow> Rows(string summary, IList windowLines, IList bars)
        {
            List<OpencodeBarRow> parsed = FromBars(bars);
            if (parsed.Count > 0) return parsed;
            parsed = FromLines(windowLines);
            if (parsed.Count > 0) return parsed;
            // Snapshot shape from the failed MarchHare card: line "OpenCode n/a", no windows.
            return UnknownRows();
        }

        public static List<OpencodeBarRow> UnknownRows()
        {
            List<OpencodeBarRow> rows = new List<OpencodeBarRow>();
            rows.Add(Row("free", "free  n/a"));
            rows.Add(Row("rolling", "go rolling  n/a"));
            rows.Add(Row("week", "go weekly  n/a"));
            rows.Add(Row("month", "go monthly  n/a"));
            return rows;
        }

        static OpencodeBarRow Row(string id, string heading)
        {
            OpencodeBarRow r = new OpencodeBarRow();
            r.Id = id;
            r.Heading = heading;
            r.Known = false;
            r.Pct = 0;
            return r;
        }

        static List<OpencodeBarRow> FromBars(IList bars)
        {
            List<OpencodeBarRow> rows = new List<OpencodeBarRow>();
            if (bars == null) return rows;
            foreach (object o in bars)
            {
                if (o == null) continue;
                OpencodeBarRow have = o as OpencodeBarRow;
                if (have != null)
                {
                    rows.Add(Copy(have));
                    continue;
                }
                IDictionary d = o as IDictionary;
                if (d == null) continue;
                string heading = Str(d, "heading");
                if (heading.Length == 0) heading = Str(d, "id");
                if (heading.Length == 0) continue;
                bool known = Bool(d, "known");
                int pct = Int(d, "pct");
                if (!known) pct = 0;
                if (pct < 0) pct = 0;
                if (pct > 100) pct = 100;
                OpencodeBarRow row = new OpencodeBarRow();
                row.Id = Str(d, "id");
                row.Heading = heading;
                row.Known = known;
                row.Pct = pct;
                rows.Add(row);
            }
            return rows;
        }

        static OpencodeBarRow Copy(OpencodeBarRow src)
        {
            OpencodeBarRow row = new OpencodeBarRow();
            row.Id = src.Id ?? "";
            row.Heading = src.Heading ?? "";
            row.Known = src.Known;
            row.Pct = src.Known ? Math.Max(0, Math.Min(100, src.Pct)) : 0;
            return row;
        }

        static List<OpencodeBarRow> FromLines(IList lines)
        {
            List<OpencodeBarRow> rows = new List<OpencodeBarRow>();
            if (lines == null) return rows;
            foreach (object o in lines)
            {
                string line = Convert.ToString(o);
                if (string.IsNullOrEmpty(line)) continue;
                int pct;
                bool known = TryRemaining(line, out pct);
                OpencodeBarRow row = new OpencodeBarRow();
                row.Id = "";
                row.Heading = line;
                row.Known = known;
                row.Pct = known ? pct : 0;
                rows.Add(row);
            }
            return rows;
        }

        // Remaining percent only. "100% used" without "rem" is not a full remaining bar.
        static bool TryRemaining(string line, out int pct)
        {
            pct = 0;
            if (string.IsNullOrEmpty(line)) return false;
            if (line.IndexOf("Starts on first use", StringComparison.OrdinalIgnoreCase) >= 0) return false;
            Match rem = Regex.Match(line, @"(\d+)\s*%\s*rem", RegexOptions.IgnoreCase);
            if (rem.Success)
            {
                pct = Clamp(rem.Groups[1].Value);
                return true;
            }
            if (line.IndexOf("n/a", StringComparison.OrdinalIgnoreCase) >= 0) return false;
            Match free = Regex.Match(line, @"free\s+(\d+)\s*%", RegexOptions.IgnoreCase);
            if (free.Success)
            {
                pct = Clamp(free.Groups[1].Value);
                return true;
            }
            return false;
        }

        static int Clamp(string raw)
        {
            int n;
            if (!int.TryParse(raw, out n)) return 0;
            if (n < 0) return 0;
            if (n > 100) return 100;
            return n;
        }

        static string Str(IDictionary d, string key)
        {
            if (d == null || !d.Contains(key) || d[key] == null) return "";
            return Convert.ToString(d[key]) ?? "";
        }

        static bool Bool(IDictionary d, string key)
        {
            if (d == null || !d.Contains(key) || d[key] == null) return false;
            object v = d[key];
            if (v is bool) return (bool)v;
            string s = Convert.ToString(v).ToLowerInvariant();
            return s == "true" || s == "1";
        }

        static int Int(IDictionary d, string key)
        {
            if (d == null || !d.Contains(key) || d[key] == null) return 0;
            try { return (int)Math.Round(Convert.ToDouble(d[key], System.Globalization.CultureInfo.InvariantCulture)); }
            catch { return 0; }
        }
    }
}
