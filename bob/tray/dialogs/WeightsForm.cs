// FR #8715 / BOB-12: Weights grid UI (Agent / CLI / Model / Context / Effort).
// FR #8714 / BOB-13: load/save via GET/PUT /bob/v1/models only (no local store).
// FR #8716 / BOB-14: Model/Context/Effort dropdowns from webhook `clis` catalog per CLI.
// FR #9053 / BOB-WEIGHTS-NO-VALIDATE: no Validate button; form dropdowns only (no validate POST).
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace BobDialogs
{
    internal class WeightsForm : Form
    {
        // Shared with --dump-weights-columns (exact order is BOB-12 S1 acceptance).
        public static readonly string[] ColumnHeaders = new string[] {
            "Agent", "CLI", "Model", "Context", "Effort"
        };

        readonly string installRoot;
        DataGridView grid;
        Label status;
        Button save;
        Button close;
        int loadBusy;
        int saveBusy;
        List<Dictionary<string, string>> lastSaved;
        Dictionary<string, List<BobModelsComboRow>> lastClis =
            new Dictionary<string, List<BobModelsComboRow>>(StringComparer.OrdinalIgnoreCase);

        public WeightsForm() : this("") { }

        public WeightsForm(string root)
        {
            installRoot = root ?? "";
            Text = "Bob - Weights";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(720, 400);
            MaximizeBox = false;
            MinimizeBox = false;
            TopMost = true;
            Font = new Font("Segoe UI", 9f);
            Icon ico = Common.AppIcon();
            if (ico != null) Icon = ico;

            grid = new DataGridView();
            grid.Name = "weightsGrid";
            grid.Location = new Point(12, 12);
            grid.Size = new Size(696, 290);
            grid.AllowUserToAddRows = false;
            grid.AllowUserToDeleteRows = false;
            grid.AllowUserToOrderColumns = false;
            grid.RowHeadersVisible = false;
            grid.SelectionMode = DataGridViewSelectionMode.FullRowSelect;
            grid.MultiSelect = false;
            grid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
            grid.DataError += delegate(object s, DataGridViewDataErrorEventArgs e) { e.ThrowException = false; };

            DataGridViewTextBoxColumn colAgent = new DataGridViewTextBoxColumn();
            colAgent.Name = "Agent";
            colAgent.HeaderText = ColumnHeaders[0];
            colAgent.ReadOnly = true;
            DataGridViewTextBoxColumn colCli = new DataGridViewTextBoxColumn();
            colCli.Name = "CLI";
            colCli.HeaderText = ColumnHeaders[1];
            colCli.ReadOnly = true;
            DataGridViewComboBoxColumn colModel = new DataGridViewComboBoxColumn();
            colModel.Name = "Model";
            colModel.HeaderText = ColumnHeaders[2];
            colModel.FlatStyle = FlatStyle.Flat;
            colModel.DisplayStyle = DataGridViewComboBoxDisplayStyle.ComboBox;
            colModel.Items.Add("");
            DataGridViewComboBoxColumn colContext = new DataGridViewComboBoxColumn();
            colContext.Name = "Context";
            colContext.HeaderText = ColumnHeaders[3];
            colContext.FlatStyle = FlatStyle.Flat;
            // FR #8716: start empty+blank only; EditingControlShowing fills from ``clis``.
            colContext.Items.Add("");
            DataGridViewComboBoxColumn colEffort = new DataGridViewComboBoxColumn();
            colEffort.Name = "Effort";
            colEffort.HeaderText = ColumnHeaders[4];
            colEffort.FlatStyle = FlatStyle.Flat;
            colEffort.Items.Add("");

            grid.Columns.AddRange(new DataGridViewColumn[] { colAgent, colCli, colModel, colContext, colEffort });
            grid.EditingControlShowing += Grid_EditingControlShowing;
            grid.CellValueChanged += Grid_CellValueChanged;

            Label subtitle = new Label();
            subtitle.Name = "weightsSubtitle";
            subtitle.Location = new Point(12, 318);
            subtitle.Size = new Size(500, 18);
            subtitle.ForeColor = Color.FromArgb(154, 171, 187);
            subtitle.Text = "GET|PUT /bob/v1/models — form dropdowns are validation";

            status = new Label();
            status.Name = "weightsStatus";
            status.Location = new Point(12, 336);
            status.Size = new Size(420, 28);
            status.Text = "Loading…";

            save = new Button();
            save.Name = "weightsSave";
            save.Text = "Save";
            save.Location = new Point(520, 348);
            save.Size = new Size(88, 28);
            save.Enabled = false;
            save.Click += delegate { BeginSave(); };

            close = new Button();
            close.Text = "Cancel";
            close.Location = new Point(620, 348);
            close.Size = new Size(88, 28);
            close.Click += delegate { Close(); };

            Controls.Add(grid);
            Controls.Add(subtitle);
            Controls.Add(status);
            Controls.Add(save);
            Controls.Add(close);
            AcceptButton = close;
            CancelButton = close;
            KeyPreview = true;
            KeyDown += delegate(object s, KeyEventArgs e) { if (e.KeyCode == Keys.Escape) Close(); };

            Shown += delegate { BeginLoad(); };
        }

        void BeginLoad()
        {
            if (Interlocked.Exchange(ref loadBusy, 1) == 1) return;
            status.Text = "Loading…";
            save.Enabled = false;
            string rootCopy = installRoot;
            ThreadPool.QueueUserWorkItem(delegate
            {
                BobModelsResult r = BobModelsClient.Get(rootCopy);
                try
                {
                    if (!IsHandleCreated || IsDisposed) return;
                    BeginInvoke((MethodInvoker)delegate { ApplyLoad(r); });
                }
                catch { }
                finally { Interlocked.Exchange(ref loadBusy, 0); }
            });
        }

        void ApplyLoad(BobModelsResult r)
        {
            if (IsDisposed) return;
            if (r == null || !r.Ok)
            {
                grid.Rows.Clear();
                string err = r != null && !string.IsNullOrEmpty(r.Error) ? r.Error : "GET failed";
                int st = r != null ? r.Status : 0;
                status.Text = "Error: " + err + (st > 0 ? " (" + st + ")" : "");
                status.ForeColor = Color.Firebrick;
                save.Enabled = false;
                TrayLifecycle.Write(
                    "weights_get",
                    "host", r != null ? (r.UrlHost ?? "") : "",
                    "status", st.ToString(),
                    "rows", "0",
                    "bodyHash", r != null ? (r.BodyHash ?? "") : "",
                    "ok", "0");
                return;
            }
            lastClis = r.Clis ?? new Dictionary<string, List<BobModelsComboRow>>(StringComparer.OrdinalIgnoreCase);
            BindRows(r.Rows);
            status.ForeColor = SystemColors.ControlText;
            int cliN = lastClis != null ? lastClis.Count : 0;
            status.Text = "Loaded " + r.Rows.Count + " row(s) from " + r.UrlHost
                + (cliN > 0 ? ("; valid clis=" + cliN) : "; valid catalog missing");
            save.Enabled = true;
            TrayLifecycle.Write(
                "weights_get",
                "host", r.UrlHost ?? "",
                "status", r.Status.ToString(),
                "rows", r.Rows.Count.ToString(),
                "clis", cliN.ToString(),
                "bodyHash", r.BodyHash ?? "",
                "ok", "1");
        }

        void BeginSave()
        {
            if (Interlocked.Exchange(ref saveBusy, 1) == 1) return;
            List<Dictionary<string, string>> rows = ReadGridRows();
            lastSaved = rows;
            save.Enabled = false;
            status.ForeColor = SystemColors.ControlText;
            status.Text = "Saving…";
            string rootCopy = installRoot;
            ThreadPool.QueueUserWorkItem(delegate
            {
                BobModelsResult put = BobModelsClient.Save(rootCopy, rows);
                BobModelsResult get = null;
                bool match = false;
                if (put != null && put.Ok)
                {
                    get = BobModelsClient.Get(rootCopy);
                    if (get != null && get.Ok)
                        match = BobModelsClient.RowsMatch(rows, get.Rows);
                }
                try
                {
                    if (!IsHandleCreated || IsDisposed) return;
                    BeginInvoke((MethodInvoker)delegate { ApplySave(put, get, match, rows); });
                }
                catch { }
                finally { Interlocked.Exchange(ref saveBusy, 0); }
            });
        }

        void ApplySave(BobModelsResult put, BobModelsResult get, bool match, List<Dictionary<string, string>> saved)
        {
            if (IsDisposed) return;
            TrayLifecycle.Write(
                "weights_save",
                "method", put != null ? (put.Method ?? "PUT") : "PUT",
                "status", put != null ? put.Status.ToString() : "0",
                "bodyHash", put != null ? (put.BodyHash ?? "") : "",
                "ok", put != null && put.Ok ? "1" : "0");

            if (put == null || !put.Ok)
            {
                string err = put != null && !string.IsNullOrEmpty(put.Error) ? put.Error : "PUT failed";
                int st = put != null ? put.Status : 0;
                status.ForeColor = Color.Firebrick;
                status.Text = "Save failed: " + err + (st > 0 ? " (" + st + ")" : "");
                save.Enabled = true;
                return;
            }

            if (get != null && get.Ok)
            {
                lastClis = get.Clis ?? lastClis;
                BindRows(get.Rows);
            }

            TrayLifecycle.Write("weights_reload_match", "match", match ? "true" : "false");
            status.ForeColor = match ? Color.DarkGreen : Color.DarkOrange;
            status.Text = match ? "Saved" : "Mismatch";
            save.Enabled = true;
        }

        void BindRows(List<Dictionary<string, string>> rows)
        {
            grid.Rows.Clear();
            if (rows == null) return;
            for (int i = 0; i < rows.Count; i++)
            {
                int idx = grid.Rows.Add();
                DataGridViewRow row = grid.Rows[idx];
                string cli = Get(rows[i], "cli");
                row.Cells[0].Value = Get(rows[i], "agent");
                row.Cells[1].Value = cli;
                string model = OnlyIfAllowed(BobModelsClient.ModelsForCli(lastClis, cli), Get(rows[i], "model"));
                string ctx = OnlyIfAllowed(BobModelsClient.ContextsFor(lastClis, cli, model), Get(rows[i], "context"));
                string effort = OnlyIfAllowed(BobModelsClient.EffortsFor(lastClis, cli, model), Get(rows[i], "effort"));
                ApplyComboCell(row, 2, BobModelsClient.ModelsForCli(lastClis, cli), model);
                ApplyComboCell(row, 3, BobModelsClient.ContextsFor(lastClis, cli, model), ctx);
                ApplyComboCell(row, 4, BobModelsClient.EffortsFor(lastClis, cli, model), effort);
            }
        }

        void ApplyComboCell(DataGridViewRow row, int colIndex, List<string> allowed, string selected)
        {
            DataGridViewComboBoxCell cell = row.Cells[colIndex] as DataGridViewComboBoxCell;
            if (cell == null)
            {
                row.Cells[colIndex].Value = selected ?? "";
                return;
            }
            cell.Items.Clear();
            cell.Items.Add("");
            if (allowed != null)
            {
                for (int i = 0; i < allowed.Count; i++)
                {
                    string v = allowed[i] ?? "";
                    if (v.Length == 0) continue;
                    cell.Items.Add(v);
                }
            }
            cell.Value = selected ?? "";
        }

        static string OnlyIfAllowed(List<string> allowed, string value)
        {
            string v = value ?? "";
            if (v.Length == 0) return "";
            if (allowed == null) return "";
            for (int i = 0; i < allowed.Count; i++)
            {
                if (string.Equals(allowed[i], v, StringComparison.Ordinal)) return v;
            }
            return "";
        }

        void Grid_EditingControlShowing(object sender, DataGridViewEditingControlShowingEventArgs e)
        {
            ComboBox cb = e.Control as ComboBox;
            if (cb == null || grid.CurrentCell == null) return;
            int col = grid.CurrentCell.ColumnIndex;
            if (col < 2 || col > 4) return;
            DataGridViewRow row = grid.Rows[grid.CurrentCell.RowIndex];
            string cli = Cell(row, 1);
            string model = Cell(row, 2);
            List<string> allowed;
            if (col == 2) allowed = BobModelsClient.ModelsForCli(lastClis, cli);
            else if (col == 3) allowed = BobModelsClient.ContextsFor(lastClis, cli, model);
            else allowed = BobModelsClient.EffortsFor(lastClis, cli, model);
            string current = Convert.ToString(cb.SelectedItem) ?? "";
            cb.Items.Clear();
            cb.Items.Add("");
            if (allowed != null)
            {
                for (int i = 0; i < allowed.Count; i++)
                {
                    string v = allowed[i] ?? "";
                    if (v.Length > 0) cb.Items.Add(v);
                }
            }
            if (OnlyIfAllowed(allowed, current).Length > 0 || current.Length == 0)
                cb.SelectedItem = current;
            else
                cb.SelectedItem = "";
        }

        void Grid_CellValueChanged(object sender, DataGridViewCellEventArgs e)
        {
            if (e.RowIndex < 0 || e.ColumnIndex != 2) return;
            if (grid == null || e.RowIndex >= grid.Rows.Count) return;
            DataGridViewRow row = grid.Rows[e.RowIndex];
            string cli = Cell(row, 1);
            string model = Cell(row, 2);
            string ctx = OnlyIfAllowed(BobModelsClient.ContextsFor(lastClis, cli, model), Cell(row, 3));
            string effort = OnlyIfAllowed(BobModelsClient.EffortsFor(lastClis, cli, model), Cell(row, 4));
            ApplyComboCell(row, 3, BobModelsClient.ContextsFor(lastClis, cli, model), ctx);
            ApplyComboCell(row, 4, BobModelsClient.EffortsFor(lastClis, cli, model), effort);
        }

        List<Dictionary<string, string>> ReadGridRows()
        {
            List<Dictionary<string, string>> rows = new List<Dictionary<string, string>>();
            for (int i = 0; i < grid.Rows.Count; i++)
            {
                DataGridViewRow gr = grid.Rows[i];
                if (gr.IsNewRow) continue;
                Dictionary<string, string> row = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                row["agent"] = Cell(gr, 0);
                row["cli"] = Cell(gr, 1);
                row["model"] = Cell(gr, 2);
                row["context"] = Cell(gr, 3);
                row["effort"] = Cell(gr, 4);
                if (row["agent"].Length == 0) continue;
                rows.Add(row);
            }
            return rows;
        }

        static string Cell(DataGridViewRow row, int i)
        {
            object v = row.Cells[i].Value;
            return v == null ? "" : Convert.ToString(v).Trim();
        }

        static string Get(Dictionary<string, string> row, string key)
        {
            if (row == null) return "";
            string v;
            if (!row.TryGetValue(key, out v) || v == null) return "";
            return v;
        }

        public static string DumpColumnHeaders()
        {
            return string.Join("\r\n", ColumnHeaders) + "\r\n";
        }

        public static string DumpValidOptions(Dictionary<string, List<BobModelsComboRow>> clis)
        {
            // FR #8716 evidence: one line per allowed (cli, model, context, effort).
            StringBuilder sb = new StringBuilder();
            sb.Append("cli\tmodel\tcontext\teffort\r\n");
            if (clis == null) return sb.ToString();
            List<string> keys = new List<string>(clis.Keys);
            keys.Sort(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < keys.Count; i++)
            {
                string cli = keys[i];
                List<BobModelsComboRow> rows = clis[cli];
                if (rows == null) continue;
                for (int r = 0; r < rows.Count; r++)
                {
                    BobModelsComboRow row = rows[r];
                    List<string> contexts = row.Contexts != null && row.Contexts.Count > 0
                        ? row.Contexts : new List<string>(new string[] { "" });
                    List<string> efforts = row.Efforts != null && row.Efforts.Count > 0
                        ? row.Efforts : new List<string>(new string[] { "" });
                    for (int c = 0; c < contexts.Count; c++)
                    {
                        for (int e = 0; e < efforts.Count; e++)
                        {
                            sb.Append(cli);
                            sb.Append('\t');
                            sb.Append(row.Model ?? "");
                            sb.Append('\t');
                            sb.Append(contexts[c] ?? "");
                            sb.Append('\t');
                            sb.Append(efforts[e] ?? "");
                            sb.Append("\r\n");
                        }
                    }
                }
            }
            return sb.ToString();
        }
    }
}
