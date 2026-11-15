// t828u: Status card as a fast compiled exe. Same content as the TipForm: Copilot pool + Grok account rows
// (Cursor spending-group bars removed after account unification), workers as "{irc nick}: {[kind/start_model[!]] }{doing|idle}" from the digest (FR #7147),
// alert, version footer.
// Non-pool fields come from <root>\run\tray-status.json (alerts/title/attention). FR #7510: pool paint
// (grok / OpenCode / Copilot / digest_pools) prefers <root>\run\tray-digest-pools.json so TipForm/Status
// keep updating when the PS engine is dead. This exe never touches the network; re-reads every 2 s.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace BobDialogs
{
    internal class Bar { public bool Known; public int Pct, R, G, B; }

    internal class StatusRow
    {
        public string Heading = "", Help = "";
        public bool Red;
        public Bar Bar = new Bar();
        public List<string> Lines = new List<string>();
    }

    internal class DigestPoolPaint
    {
        public string Id = "", Family = "", Label = "", Heading = "";
        public bool Known;
        public int Pct;
    }

    internal class StatusModel
    {
        public string Title = "bob", Alert = "none", Version = "", Overspend = "", Note = "";
        public string CopilotLine = "Copilot - unknown";
        public string CopilotStaleLine = "";
        public long CopilotFreshUntil = 0;
        // FR #6317: remaining-% bar for Copilot UsageRow (null/unknown => empty track).
        public bool CopilotBarKnown;
        public int CopilotBarPct;
        public int CopilotBarR = 88, CopilotBarG = 166, CopilotBarB = 255;
        public string OpencodeLine = "OpenCode  n/a";
        public List<string> OpencodeWindowLines = new List<string>();
        public List<OpencodeBarRow> OpencodeBars = new List<OpencodeBarRow>();
        public List<StatusRow> Cursor = new List<StatusRow>(), Grok = new List<StatusRow>();
        // FR #7243: digest-driven extra pools (Grok chat, OpenCode free, Cursor, …).
        public List<DigestPoolPaint> DigestPools = new List<DigestPoolPaint>();

        static StatusRow ParseRow(Dictionary<string, object> d)
        {
            StatusRow r = new StatusRow();
            r.Heading = Common.Str(d, "heading"); r.Help = Common.Str(d, "help"); r.Red = Common.Bool(d, "red");
            r.Bar.Known = Common.Bool(d, "known");
            r.Bar.Pct = Math.Max(0, Math.Min(100, Common.Int(d, "pct", 0)));
            r.Bar.R = Common.Int(d, "r", 88); r.Bar.G = Common.Int(d, "g", 166); r.Bar.B = Common.Int(d, "b", 255);
            IList w = Common.List(d.ContainsKey("workers") ? d["workers"] : null);
            if (w != null) foreach (object o in w) { string s = Convert.ToString(o); if (!string.IsNullOrEmpty(s)) r.Lines.Add(s); }
            return r;
        }

        public static StatusModel Parse(string json)
        {
            StatusModel m = new StatusModel();
            Dictionary<string, object> d = Common.Dict(Common.ParseJson(json));
            if (d == null) { m.Note = "snapshot is not an object"; return m; }
            string t = Common.Str(d, "title"); if (t.Length > 0) m.Title = t;
            m.Version = Common.Str(d, "version"); m.Overspend = Common.Str(d, "overspend");
            string note = Common.Str(d, "note"); if (note.Length > 0) m.Note = note;
            string oc = Common.Str(d, "opencode_line"); if (oc.Length > 0) m.OpencodeLine = oc;
            IList ocw = Common.List(d.ContainsKey("opencode_window_lines") ? d["opencode_window_lines"] : null);
            if (ocw != null) foreach (object o in ocw) { string s = Convert.ToString(o); if (!string.IsNullOrEmpty(s)) m.OpencodeWindowLines.Add(s); }
            IList ocb = Common.List(d.ContainsKey("opencode_bars") ? d["opencode_bars"] : null);
            if (ocb != null)
            {
                foreach (OpencodeBarRow row in OpencodePaint.Rows(m.OpencodeLine, null, ocb))
                    m.OpencodeBars.Add(row);
            }
            string cp = Common.Str(d, "copilot_line"); if (cp.Length > 0) m.CopilotLine = cp;
            string cps = Common.Str(d, "copilot_stale_line"); if (cps.Length > 0) m.CopilotStaleLine = cps;
            m.CopilotFreshUntil = Common.Long(d, "copilot_fresh_until", 0);
            // FR #6317: optional copilot_bar { known, pct, r, g, b } from tray snapshot.
            Dictionary<string, object> cbar = Common.Dict(d.ContainsKey("copilot_bar") ? d["copilot_bar"] : null);
            if (cbar != null)
            {
                m.CopilotBarKnown = Common.Bool(cbar, "known");
                m.CopilotBarPct = Math.Max(0, Math.Min(100, Common.Int(cbar, "pct", 0)));
                m.CopilotBarR = Common.Int(cbar, "r", 88);
                m.CopilotBarG = Common.Int(cbar, "g", 166);
                m.CopilotBarB = Common.Int(cbar, "b", 255);
            }
            string a = Common.Str(d, "alert"); if (a.Length > 0) m.Alert = a;
            IList c = Common.List(d.ContainsKey("cursor") ? d["cursor"] : null);
            if (c != null) foreach (object o in c) { Dictionary<string, object> rd = Common.Dict(o); if (rd != null && Common.Str(rd, "heading").Length > 0) m.Cursor.Add(ParseRow(rd)); }
            IList g = Common.List(d.ContainsKey("grok") ? d["grok"] : null);
            if (g != null) foreach (object o in g) { Dictionary<string, object> rd = Common.Dict(o); if (rd != null && Common.Str(rd, "heading").Length > 0) m.Grok.Add(ParseRow(rd)); }
            IList dp = Common.List(d.ContainsKey("digest_pools") ? d["digest_pools"] : null);
            if (dp != null)
            {
                foreach (object o in dp)
                {
                    Dictionary<string, object> rd = Common.Dict(o);
                    if (rd == null) continue;
                    DigestPoolPaint p = new DigestPoolPaint();
                    p.Id = Common.Str(rd, "id");
                    p.Family = Common.Str(rd, "family");
                    p.Label = Common.Str(rd, "label");
                    p.Heading = Common.Str(rd, "heading");
                    p.Known = Common.Bool(rd, "known");
                    p.Pct = Math.Max(0, Math.Min(100, Common.Int(rd, "remaining_pct", 0)));
                    if (p.Label.Length == 0) p.Label = p.Id;
                    if (p.Heading.Length == 0) p.Heading = p.Label;
                    m.DigestPools.Add(p);
                }
            }
            return m;
        }

        // FR #7510: replace pool paint fields from tray-digest-pools.json; keep title/alert/version from tray-status.
        public void OverlayDigestPools(StatusModel pools, bool digestOk, string digestNote)
        {
            if (pools == null) return;
            Grok = pools.Grok ?? new List<StatusRow>();
            DigestPools = pools.DigestPools ?? new List<DigestPoolPaint>();
            if (!string.IsNullOrEmpty(pools.OpencodeLine)) OpencodeLine = pools.OpencodeLine;
            OpencodeWindowLines = pools.OpencodeWindowLines ?? new List<string>();
            OpencodeBars = pools.OpencodeBars ?? new List<OpencodeBarRow>();
            if (!string.IsNullOrEmpty(pools.CopilotLine)) CopilotLine = pools.CopilotLine;
            if (!string.IsNullOrEmpty(pools.CopilotStaleLine)) CopilotStaleLine = pools.CopilotStaleLine;
            CopilotFreshUntil = pools.CopilotFreshUntil;
            CopilotBarKnown = pools.CopilotBarKnown;
            CopilotBarPct = pools.CopilotBarPct;
            CopilotBarR = pools.CopilotBarR;
            CopilotBarG = pools.CopilotBarG;
            CopilotBarB = pools.CopilotBarB;
            if (!digestOk)
            {
                string n = digestNote;
                if (string.IsNullOrEmpty(n)) n = "digest unreachable";
                if (string.IsNullOrEmpty(Note)) Note = n;
                else if (Note.IndexOf("digest", StringComparison.OrdinalIgnoreCase) < 0) Note = Note + "; " + n;
            }
            else if (!string.IsNullOrEmpty(pools.Note) && string.IsNullOrEmpty(Note))
            {
                Note = pools.Note;
            }
        }
    }

    internal class CardView : Panel
    {
        public string AssetsRoot = "";
        public StatusModel Model = new StatusModel();
        public string Footer = "";
        readonly Font fTitle = new Font("Segoe UI Semibold", 11f), fSect = new Font("Segoe UI Semibold", 9.5f), fHead = new Font("Segoe UI Semibold", 9f),
            fText = new Font("Segoe UI", 9f), fSmall = new Font("Segoe UI", 8f);
        static readonly Color Bg = Color.FromArgb(22, 27, 34), Fg = Color.FromArgb(230, 237, 243), Muted = Color.FromArgb(139, 148, 158),
            Track = Color.FromArgb(48, 54, 61), Red = Color.FromArgb(248, 81, 73);
        const TextFormatFlags Tf = TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix | TextFormatFlags.Left | TextFormatFlags.Top;
        readonly List<KeyValuePair<Rectangle, string>> helpRects = new List<KeyValuePair<Rectangle, string>>();
        readonly ToolTip tip = new ToolTip();
        string lastTip = "";
        public Rectangle CloseRect = new Rectangle(386, 8, 24, 22);
        public const int W = 420;

        public CardView()
        {
            DoubleBuffered = true; BackColor = Bg; ResizeRedraw = true;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint, true);
            tip.ShowAlways = true; tip.UseAnimation = false; tip.UseFading = false; tip.AutoPopDelay = 30000;
        }

        void Draw(Graphics g, string s, Font f, Color c, int x, int y) { TextRenderer.DrawText(g, s, f, new Point(x, y), c, Tf); }

        static int TextW(Graphics g, string s, Font f) { return TextRenderer.MeasureText(g, s, f, Size.Empty, Tf).Width; }

        static GraphicsPath Round(int x, int y, int w, int h, int r)
        {
            GraphicsPath p = new GraphicsPath(); int d = Math.Max(1, r * 2);
            p.AddArc(x, y, d, d, 180, 90); p.AddArc(x + w - d, y, d, d, 270, 90); p.AddArc(x + w - d, y + h - d, d, d, 0, 90); p.AddArc(x, y + h - d, d, d, 90, 90);
            p.CloseFigure(); return p;
        }

        // FR #7378: only the exact [stale] token is red; the rest of the heading stays Fg.
        // r.Red (whole-heading) is ignored for UsageRow paint so OpenCode/Copilot/xAI match TipForm.
        int DrawHeadingWithStaleToken(Graphics g, string heading, Font font, int x, int y)
        {
            const string tok = "[stale]";
            string h = heading ?? "";
            int i = h.IndexOf(tok, StringComparison.Ordinal);
            if (i < 0)
            {
                Draw(g, h, font, Fg, x, y);
                return TextW(g, h, font);
            }
            string prefix = h.Substring(0, i);
            string suffix = h.Substring(i + tok.Length);
            int cur = x;
            if (prefix.Length > 0)
            {
                Draw(g, prefix, font, Fg, cur, y);
                cur += TextW(g, prefix, font);
            }
            Draw(g, tok, font, Red, cur, y);
            cur += TextW(g, tok, font);
            if (suffix.Length > 0)
            {
                Draw(g, suffix, font, Fg, cur, y);
                cur += TextW(g, suffix, font);
            }
            return cur - x;
        }

        int UsageRow(Graphics g, int x, int y, StatusRow r, int barW)
        {
            DrawHeadingWithStaleToken(g, r.Heading, fHead, x, y);
            if (r.Help.Length > 0) helpRects.Add(new KeyValuePair<Rectangle, string>(new Rectangle(x, y, barW, 18), r.Help));
            int by = y + 20;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using (GraphicsPath t = Round(x, by, barW, 10, 5)) using (SolidBrush b = new SolidBrush(Track)) g.FillPath(b, t);
            if (r.Bar.Known && r.Bar.Pct > 0)
            {
                int w = (int)((barW - 2) * r.Bar.Pct / 100.0); if (w < 8) w = 8;
                using (GraphicsPath f = Round(x + 1, by + 1, w, 8, 4)) using (SolidBrush b = new SolidBrush(Color.FromArgb(r.Bar.R, r.Bar.G, r.Bar.B))) g.FillPath(b, f);
            }
            g.SmoothingMode = SmoothingMode.Default;
            return by + 14;
        }

        int Section(Graphics g, int y, string title, string right)
        {
            return Section(g, y, title, right, null, Fg);
        }

        int Section(Graphics g, int y, string title, string right, string fuelFamily)
        {
            return Section(g, y, title, right, fuelFamily, Fg);
        }

        // FR #6149 logo + FR #6148 / FIX #6180 titleColor for stale Copilot.
        int Section(Graphics g, int y, string title, string right, string fuelFamily, Color titleColor)
        {
            int x = 14;
            if (fuelFamily != null && fuelFamily.Length > 0)
            {
                Image logo = Common.FuelLogo(AssetsRoot, fuelFamily);
                if (logo != null)
                {
                    try { g.DrawImage(logo, x, y, 18, 18); }
                    catch { }
                    finally { try { logo.Dispose(); } catch { } }
                    x += 22;
                }
                else
                {
                    string fb = Common.FuelLogoFallback(fuelFamily);
                    Draw(g, "[" + fb + "]", fSmall, Muted, x, y + 2);
                    x += TextW(g, "[" + fb + "]", fSmall) + 6;
                }
            }
            Draw(g, title, fSect, titleColor, x, y);
            if (right.Length > 0) Draw(g, right, fHead, Red, W - 14 - TextW(g, right, fHead) - 2, y);
            return y + 22;
        }

        internal static string SelectCopilotLine(StatusModel m, DateTime utcNow)
        {
            if (m == null) return "Copilot - unknown";
            string line = m.CopilotLine;
            if (string.IsNullOrEmpty(line)) line = "Copilot - unknown";
            if (m.CopilotFreshUntil > 0)
            {
                long nowEpoch = new DateTimeOffset(utcNow).ToUnixTimeSeconds();
                if (nowEpoch >= m.CopilotFreshUntil)
                {
                    if (!string.IsNullOrEmpty(m.CopilotStaleLine)) line = m.CopilotStaleLine;
                    else if (line.IndexOf("[stale", StringComparison.Ordinal) < 0)
                        line = line.Replace("Copilot - ", "Copilot - [stale] ").Replace("Copilot  ", "Copilot - [stale] ");
                }
            }
            return line;
        }

        // Draws (or just measures) the whole card and returns its height.
        public int Render(Graphics g)
        {
            helpRects.Clear();
            StatusModel m = Model;
            int y = 12;
            Draw(g, m.Title, fTitle, Fg, 14, y);
            Draw(g, "X", fHead, Muted, CloseRect.X + 6, 10);
            y += 26;
            // Dashboard = per-machine Grok pools + workers and one account-wide Copilot pool.
            // FR #5032: no "Grok accounts" heading --- every row is a Grok pool.
            // FR #6149: fuel-family logos (assets\fuel-logos) with text fallback.
            // FR #6285: xAI weekly section only (Cursor not mixed into this heading).
            if (m.Note.Length > 0) { Draw(g, m.Note, fText, Muted, 14, y); y += 22; }
            y = Section(g, y, "xAI weekly", "", "xai");
            if (m.Grok.Count > 0)
            {
                if (m.Overspend != null && m.Overspend.Length > 0)
                    y = Section(g, y, "", m.Overspend, "xai");
                foreach (StatusRow r in m.Grok)
                {
                    y = UsageRow(g, 32, y, r, 354);
                    if (r.Lines.Count == 0) { y += 4; continue; }
                    foreach (string line in r.Lines) { Draw(g, line, fText, Fg, 46, y + 2); y += 16; }
                    y += 8;
                }
            }
            // FR #6147 / FR #6301: section title is OpenCode; window rows carry % left + reset.
            y = Section(g, y, "OpenCode", "", "opencode");
            // Free plus Go rolling/weekly/monthly. Empty snapshot fields still draw
            // four unknown tracks (known=false), never a 100% fill.
            IList barSource = m.OpencodeBars != null && m.OpencodeBars.Count > 0 ? (IList)m.OpencodeBars : null;
            foreach (OpencodeBarRow b in OpencodePaint.Rows(m.OpencodeLine, m.OpencodeWindowLines, barSource))
            {
                StatusRow r = new StatusRow();
                r.Heading = b.Heading ?? "";
                r.Bar.Known = b.Known;
                r.Bar.Pct = b.Known ? Math.Max(0, Math.Min(100, b.Pct)) : 0;
                // FR #6301: green->red remaining fill from bar RGB (Get-BobTrayBarFillRgb).
                r.Bar.R = b.R; r.Bar.G = b.G; r.Bar.B = b.B;
                y = UsageRow(g, 32, y, r, 354);
            }
            // FR #6317: Copilot like OpenCode rows — family header (no right text / not red),
            // then left-aligned 'Copilot - <text>' UsageRow + remaining bar.
            string paintCopilot = SelectCopilotLine(m, DateTime.UtcNow);
            if (paintCopilot.StartsWith("Copilot  ", StringComparison.Ordinal))
                paintCopilot = "Copilot - " + paintCopilot.Substring("Copilot  ".Length).Trim();
            // FR #7243: digest pools that are not the xAI weekly / OpenCode Go / Copilot sections.
            foreach (DigestPoolPaint p in m.DigestPools)
            {
                if (p == null) continue;
                string pid = (p.Id ?? "").Trim().ToLowerInvariant();
                if (pid == "grok-build" || pid == "opencode-go" || pid == "copilot") continue;
                string fam = string.IsNullOrEmpty(p.Family) ? "xai" : p.Family;
                string ttl = string.IsNullOrEmpty(p.Label) ? pid : p.Label;
                y = Section(g, y, ttl, "", fam);
                StatusRow extra = new StatusRow();
                extra.Heading = p.Heading ?? ttl;
                extra.Bar.Known = p.Known;
                extra.Bar.Pct = p.Known ? Math.Max(0, Math.Min(100, p.Pct)) : 0;
                extra.Bar.R = 88; extra.Bar.G = 166; extra.Bar.B = 255;
                y = UsageRow(g, 32, y, extra, 354);
            }
            y = Section(g, y, "Copilot", "", "copilot");
            StatusRow copilotRow = new StatusRow();
            copilotRow.Heading = paintCopilot;
            copilotRow.Bar.Known = m.CopilotBarKnown;
            copilotRow.Bar.Pct = m.CopilotBarKnown ? Math.Max(0, Math.Min(100, m.CopilotBarPct)) : 0;
            copilotRow.Bar.R = m.CopilotBarR;
            copilotRow.Bar.G = m.CopilotBarG;
            copilotRow.Bar.B = m.CopilotBarB;
            y = UsageRow(g, 32, y, copilotRow, 354);
            y += 6;
            Draw(g, "alert: " + m.Alert, fSmall, m.Alert == "none" ? Muted : Red, 14, y);
            string v = Footer.Length > 0 ? Footer : m.Version;
            if (v.Length > 0) Draw(g, v, fSmall, Muted, Math.Max(14, W - 14 - TextW(g, v, fSmall)), y);
            return y + 16 + 16;
        }

        protected override void OnPaint(PaintEventArgs e) { e.Graphics.Clear(Bg); Render(e.Graphics); }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            string t = "";
            foreach (KeyValuePair<Rectangle, string> kv in helpRects) if (kv.Key.Contains(e.Location)) { t = kv.Value; break; }
            Cursor = CloseRect.Contains(e.Location) ? Cursors.Hand : Cursors.Default;
            if (t != lastTip) { lastTip = t; if (t.Length > 0) tip.Show(t, this, e.X + 12, e.Y + 18, 30000); else tip.Hide(this); }
            base.OnMouseMove(e);
        }
    }

    internal class StatusForm : Form
    {
        readonly CardView card = new CardView();
        readonly string file;
        readonly string digestPoolsFile;
        DateTime lastWrite = DateTime.MinValue;
        long lastLen = -1;
        DateTime lastDigestWrite = DateTime.MinValue;
        long lastDigestLen = -1;
        readonly System.Windows.Forms.Timer poll = new System.Windows.Forms.Timer();
        string lastPaintedCopilot = "";

        public StatusForm(string root)
        {
            file = Path.Combine(root, "run\\tray-status.json");
            digestPoolsFile = Path.Combine(root, "run\\tray-digest-pools.json");
            card.AssetsRoot = root ?? "";
            Text = "Bobiverse status";
            FormBorderStyle = FormBorderStyle.None; ShowInTaskbar = false; TopMost = true; StartPosition = FormStartPosition.Manual;
            BackColor = Color.FromArgb(22, 27, 34);
            Icon ico = Common.AppIcon(); if (ico != null) Icon = ico;
            card.Dock = DockStyle.Fill; Controls.Add(card);
            card.Footer = "bob " + Common.BobVersion(root);
            KeyPreview = true;
            KeyDown += delegate (object s, KeyEventArgs e) { if (e.KeyCode == Keys.Escape) Close(); };
            card.MouseDown += delegate (object s, MouseEventArgs e)
            {
                if (card.CloseRect.Contains(e.Location)) { Close(); return; }
                if (e.Button == MouseButtons.Left && e.Y < 34) { Native2.Drag(Handle); }
            };
            // FR #6924: re-read MSI VERSION + deployed identity when Status is shown.
            Shown += delegate { card.Footer = "bob " + Common.BobVersion(root); Invalidate(); };
            Reload(true);
            Resize2(true);
            poll.Interval = 2000; poll.Tick += delegate { Reload(false); }; poll.Start();
        }

        void Resize2(bool place)
        {
            int h;
            using (Graphics g = CreateGraphics()) h = card.Render(g);
            h = Math.Max(110, h);
            Size = new Size(CardView.W, h);
            if (place)
            {
                Point pt = Cursor.Position;
                Rectangle wa = Screen.FromPoint(pt).WorkingArea;
                int x = Math.Max(wa.Left + 8, Math.Min(pt.X - CardView.W / 2, wa.Right - CardView.W - 8));
                bool top = pt.Y < wa.Top + wa.Height / 2;
                int y = top ? wa.Top + 8 : wa.Bottom - h - 8;
                Location = new Point(x, Math.Max(wa.Top + 4, y));
            }
        }

        static string ReadAllUtf8Shared(string path)
        {
            using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (StreamReader sr = new StreamReader(fs, Encoding.UTF8, true))
                return sr.ReadToEnd();
        }

        // FR #7510: merge tray-status (non-pool) with tray-digest-pools (pool paint). Shared by Reload and --check.
        internal static StatusModel LoadMerged(string statusPath, string digestPoolsPath)
        {
            StatusModel m = null;
            if (!string.IsNullOrEmpty(statusPath) && File.Exists(statusPath))
            {
                m = StatusModel.Parse(ReadAllUtf8Shared(statusPath));
            }
            // FR #7595: header age comes from the digest ts, never tray-status.json mtime.
            if (m == null) m = new StatusModel();

            if (string.IsNullOrEmpty(digestPoolsPath) || !File.Exists(digestPoolsPath))
            {
                if (string.IsNullOrEmpty(m.Note))
                    m.Note = "digest unreachable (tray-digest-pools.json missing)";
                else if (m.Note.IndexOf("digest", StringComparison.OrdinalIgnoreCase) < 0)
                    m.Note = m.Note + "; digest unreachable (tray-digest-pools.json missing)";
                return m;
            }

            string djson = ReadAllUtf8Shared(digestPoolsPath);
            StatusModel pools = StatusModel.Parse(djson);
            Dictionary<string, object> raw = Common.Dict(Common.ParseJson(djson));
            bool digestOk = true;
            string digestNote = "";
            if (raw != null)
            {
                if (raw.ContainsKey("digest_ok")) digestOk = Common.Bool(raw, "digest_ok");
                digestNote = Common.Str(raw, "note");
                if (string.IsNullOrEmpty(digestNote)) digestNote = Common.Str(raw, "digest_error");
                if (!digestOk && string.IsNullOrEmpty(digestNote)) digestNote = "digest unreachable";
            }
            m.OverlayDigestPools(pools, digestOk, digestNote);
            // FR #7595: a fresh digest clears an engine snapshot-age note.
            ApplyDigestHeaderAge(m, raw, digestOk);
            return m;
        }

        // Header age is the digest document ts (unix seconds). A fresh digest clears
        // any engine snapshot-age note. An old digest says how old the digest is.
        internal static void ApplyDigestHeaderAge(StatusModel m, Dictionary<string, object> raw, bool digestOk)
        {
            if (m == null || !digestOk) return;
            long ts = 0;
            if (raw != null && raw.ContainsKey("digest_ts")) ts = Common.Long(raw, "digest_ts", 0);
            bool fresh = true;
            int ageMin = 0;
            if (ts > 0)
            {
                if (ts > 100000000000L) ts = ts / 1000L;
                long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                long age = now - ts;
                if (age < 0) age = 0;
                ageMin = (int)(age / 60L);
                fresh = age <= 600;
            }
            bool bad = !string.IsNullOrEmpty(m.Note)
                && (m.Note.IndexOf("snapshot is", StringComparison.OrdinalIgnoreCase) >= 0
                    || m.Note.IndexOf("not polling", StringComparison.OrdinalIgnoreCase) >= 0);
            if (fresh)
            {
                if (bad) m.Note = "";
            }
            else if (string.IsNullOrEmpty(m.Note) || bad)
            {
                m.Note = "digest is " + ageMin + " min old";
            }
        }

        void Reload(bool first)
        {
            try
            {
                bool statusExists = File.Exists(file);
                bool digestExists = File.Exists(digestPoolsFile);
                if (!statusExists && !digestExists)
                {
                    if (first) { card.Model = new StatusModel(); card.Model.Note = "waiting for the tray to write its first poll..."; }
                    return;
                }
                FileInfo fi = statusExists ? new FileInfo(file) : null;
                FileInfo di = digestExists ? new FileInfo(digestPoolsFile) : null;
                bool statusUnchanged = (!statusExists) || (!first && fi.LastWriteTimeUtc == lastWrite && fi.Length == lastLen);
                bool digestUnchanged = (!digestExists) || (!first && di.LastWriteTimeUtc == lastDigestWrite && di.Length == lastDigestLen);
                if (!first && statusUnchanged && digestUnchanged)
                {
                    // FR #6148: re-age Copilot line while the window stays open even if snapshot bytes are unchanged.
                    string after = CardView.SelectCopilotLine(card.Model, DateTime.UtcNow);
                    if (!string.Equals(lastPaintedCopilot, after, StringComparison.Ordinal))
                    {
                        lastPaintedCopilot = after;
                        card.Invalidate();
                    }
                    return;
                }
                StatusModel m = LoadMerged(statusExists ? file : null, digestExists ? digestPoolsFile : null);
                if (fi != null) { lastWrite = fi.LastWriteTimeUtc; lastLen = fi.Length; }
                if (di != null) { lastDigestWrite = di.LastWriteTimeUtc; lastDigestLen = di.Length; }
                lastPaintedCopilot = CardView.SelectCopilotLine(m, DateTime.UtcNow);
                card.Model = m;
                if (!first) { Resize2(false); }
                card.Invalidate();
            }
            catch (Exception ex)
            {
                if (first) { card.Model = new StatusModel(); card.Model.Note = "status unavailable: " + ex.Message; }
            }
        }

        protected override CreateParams CreateParams
        {
            get { CreateParams cp = base.CreateParams; cp.ClassStyle |= 0x20000; /* CS_DROPSHADOW */ return cp; }
        }
    }

    internal static class Native2
    {
        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool ReleaseCapture();
        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
        public static void Drag(IntPtr h) { ReleaseCapture(); SendMessage(h, 0xA1, (IntPtr)2, IntPtr.Zero); }
    }

    internal static class StatusProgram
    {
        [STAThread]
        static int Main(string[] args)
        {
            CrashHook.Install("bob-status");
            string root = Common.Root(args);
            // Headless: validate/echo the snapshot as the card would see it (tests, support).
            string check = Common.Arg(args, "--check");
            if (check.Length > 0)
            {
                // FR #7510: optional --digest-pools, else sibling tray-digest-pools.json next to --check.
                string digestPools = Common.Arg(args, "--digest-pools");
                if (digestPools.Length == 0)
                {
                    try
                    {
                        string sib = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(check)) ?? "", "tray-digest-pools.json");
                        if (File.Exists(sib)) digestPools = sib;
                    }
                    catch { digestPools = ""; }
                }
                StatusModel m;
                if (digestPools.Length > 0 && File.Exists(digestPools))
                    m = StatusForm.LoadMerged(check, digestPools);
                else
                    m = StatusModel.Parse(File.ReadAllText(check, Encoding.UTF8));
                string outFile = Common.Arg(args, "--text-out");
                StringBuilder sb = new StringBuilder();
                sb.AppendLine(m.Title); sb.AppendLine("cursor=" + m.Cursor.Count + " grok=" + m.Grok.Count + " alert=" + m.Alert);
                if (m.Note != null && m.Note.Length > 0) sb.AppendLine("note=" + m.Note);
                foreach (StatusRow r in m.Cursor) sb.AppendLine("C " + r.Heading);
                foreach (StatusRow r in m.Grok) { sb.AppendLine("G " + r.Heading); foreach (string l in r.Lines) sb.AppendLine("W " + l); }
                sb.AppendLine(m.OpencodeLine);
                foreach (OpencodeBarRow b in OpencodePaint.Rows(m.OpencodeLine, m.OpencodeWindowLines, m.OpencodeBars))
                    sb.AppendLine((b.Known ? "OB " : "OU ") + b.Heading + " pct=" + b.Pct.ToString());
                foreach (DigestPoolPaint p in m.DigestPools)
                {
                    if (p == null || string.IsNullOrEmpty(p.Heading)) continue;
                    sb.AppendLine("P " + p.Heading);
                }
                sb.AppendLine(m.CopilotLine);
                if (outFile.Length > 0) File.WriteAllText(outFile, sb.ToString(), new UTF8Encoding(false)); else Console.Write(sb.ToString());
                return 0;
            }
            if (!Common.Single("Status", "Bobiverse status")) return 0;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            StatusForm f = new StatusForm(root);
            Common.TimingHook(f, args);
            Application.Run(f);
            return 0;
        }
    }
}