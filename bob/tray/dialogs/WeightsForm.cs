// FR #8715 / BOB-12: Weights grid UI (Agent / CLI / Model / Context / Effort).
// Static placeholder rows only; BOB-13 binds models webhook, BOB-14 valid-only dropdowns.
using System;
using System.Drawing;
using System.Windows.Forms;

namespace BobDialogs
{
    internal class WeightsForm : Form
    {
        // Shared with --dump-weights-columns (exact order is S1 acceptance).
        public static readonly string[] ColumnHeaders = new string[] {
            "Agent", "CLI", "Model", "Context", "Effort"
        };

        // Placeholder Agent/CLI pairs from weights.html mock; BOB-13 replaces data.
        static readonly string[][] PlaceholderRows = new string[][] {
            new string[] { "Plan", "Grok" },
            new string[] { "Priority", "Grok" },
            new string[] { "Jeeves", "Grok" },
            new string[] { "Grok", "Grok" },
            new string[] { "Cursor", "Cursor" },
            new string[] { "Opencode", "Opencode" },
            new string[] { "Opencode-Free", "Opencode" }
        };

        public WeightsForm()
        {
            Text = "Bob - Weights";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(720, 360);
            MaximizeBox = false;
            MinimizeBox = false;
            TopMost = true;
            Font = new Font("Segoe UI", 9f);
            Icon ico = Common.AppIcon();
            if (ico != null) Icon = ico;

            DataGridView grid = new DataGridView();
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
            // Empty until BOB-13/14 seed valid models.
            DataGridViewComboBoxColumn colContext = new DataGridViewComboBoxColumn();
            colContext.Name = "Context";
            colContext.HeaderText = ColumnHeaders[3];
            colContext.FlatStyle = FlatStyle.Flat;
            colContext.Items.AddRange(new object[] { "256", "512" });
            DataGridViewComboBoxColumn colEffort = new DataGridViewComboBoxColumn();
            colEffort.Name = "Effort";
            colEffort.HeaderText = ColumnHeaders[4];
            colEffort.FlatStyle = FlatStyle.Flat;
            colEffort.Items.AddRange(new object[] { "low", "medium", "high" });

            grid.Columns.AddRange(new DataGridViewColumn[] { colAgent, colCli, colModel, colContext, colEffort });

            for (int i = 0; i < PlaceholderRows.Length; i++)
            {
                int idx = grid.Rows.Add();
                DataGridViewRow row = grid.Rows[idx];
                row.Cells[0].Value = PlaceholderRows[i][0];
                row.Cells[1].Value = PlaceholderRows[i][1];
                row.Cells[2].Value = "";
                row.Cells[3].Value = "256";
                row.Cells[4].Value = "medium";
            }

            Button close = new Button();
            close.Text = "Close";
            close.Location = new Point(620, 322);
            close.Size = new Size(88, 28);
            close.Click += delegate { Close(); };

            Controls.Add(grid);
            Controls.Add(close);
            AcceptButton = close;
            CancelButton = close;
            KeyPreview = true;
            KeyDown += delegate(object s, KeyEventArgs e) { if (e.KeyCode == Keys.Escape) Close(); };
        }

        public static string DumpColumnHeaders()
        {
            return string.Join("\r\n", ColumnHeaders) + "\r\n";
        }
    }
}
