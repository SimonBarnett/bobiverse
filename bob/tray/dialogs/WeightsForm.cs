// FR #8715 / BOB-12: Weights grid UI (Agent / CLI / Model / Context / Effort).
// FR #8714 / BOB-13: load/save via GET/PUT /bob/v1/models only (no local store).
using System;
using System.Collections.Generic;
using System.Drawing;
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

        public WeightsForm() : this("") { }

        public WeightsForm(string root)
        {
            installRoot = root ?? "";
            Text = "Bob - Weights";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(720, 380);
            MaximizeBox = false;
            MinimizeBox = false;
            TopMost = true;
            Font = new Font("Segoe UI", 9f);
            Icon ico = Common.AppIcon();
            if (ico != null) Icon = ico;

            grid = new DataGridView();
            grid.Name = "weightsGrid";
            grid.Location = new Point(12, 12);
            grid.Size = new Size(696, 300);
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
            DataGridViewComboBoxColumn colContext = new DataGridViewComboBoxColumn();
            colContext.Name = "Context";
            colContext.HeaderText = ColumnHeaders[3];
            colContext.FlatStyle = FlatStyle.Flat;
            colContext.Items.AddRange(new object[] { "", "256", "512" });
            DataGridViewComboBoxColumn colEffort = new DataGridViewComboBoxColumn();
            colEffort.Name = "Effort";
            colEffort.HeaderText = ColumnHeaders[4];
            colEffort.FlatStyle = FlatStyle.Flat;
            colEffort.Items.AddRange(new object[] { "", "low", "medium", "high", "med" });

            grid.Columns.AddRange(new DataGridViewColumn[] { colAgent, colCli, colModel, colContext, colEffort });

            status = new Label();
            status.Name = "weightsStatus";
            status.Location = new Point(12, 322);
            status.Size = new Size(420, 40);
            status.Text = "Loading…";

            save = new Button();
            save.Name = "weightsSave";
            save.Text = "Save";
            save.Location = new Point(520, 328);
            save.Size = new Size(88, 28);
            save.Enabled = false;
            save.Click += delegate { BeginSave(); };

            close = new Button();
            close.Text = "Close";
            close.Location = new Point(620, 328);
            close.Size = new Size(88, 28);
            close.Click += delegate { Close(); };

            Controls.Add(grid);
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
            BindRows(r.Rows);
            EnsureModelItems(r.Rows);
            status.ForeColor = SystemColors.ControlText;
            status.Text = "Loaded " + r.Rows.Count + " row(s) from " + r.UrlHost;
            save.Enabled = true;
            TrayLifecycle.Write(
                "weights_get",
                "host", r.UrlHost ?? "",
                "status", r.Status.ToString(),
                "rows", r.Rows.Count.ToString(),
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
                BindRows(get.Rows);
                EnsureModelItems(get.Rows);
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
                row.Cells[0].Value = Get(rows[i], "agent");
                row.Cells[1].Value = Get(rows[i], "cli");
                string model = Get(rows[i], "model");
                EnsureComboHas((DataGridViewComboBoxColumn)grid.Columns[2], model);
                row.Cells[2].Value = model;
                string ctx = Get(rows[i], "context");
                EnsureComboHas((DataGridViewComboBoxColumn)grid.Columns[3], ctx);
                row.Cells[3].Value = ctx;
                string effort = Get(rows[i], "effort");
                EnsureComboHas((DataGridViewComboBoxColumn)grid.Columns[4], effort);
                row.Cells[4].Value = effort;
            }
        }

        void EnsureModelItems(List<Dictionary<string, string>> rows)
        {
            DataGridViewComboBoxColumn col = grid.Columns[2] as DataGridViewComboBoxColumn;
            if (col == null || rows == null) return;
            for (int i = 0; i < rows.Count; i++)
                EnsureComboHas(col, Get(rows[i], "model"));
        }

        static void EnsureComboHas(DataGridViewComboBoxColumn col, string value)
        {
            if (col == null) return;
            string v = value ?? "";
            if (v.Length == 0) return;
            for (int i = 0; i < col.Items.Count; i++)
            {
                if (string.Equals(Convert.ToString(col.Items[i]), v, StringComparison.Ordinal))
                    return;
            }
            col.Items.Add(v);
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
    }
}
