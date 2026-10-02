#Requires -Version 5.1
# Deterministic WinForms Updating dialog for Bob Systray git install.
# Stays open until -DoneFlag exists (or -TimeoutSec). No LLM.
# ASCII-only: Windows PowerShell 5.1 misparses UTF-8 no BOM with fancy punctuation.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DoneFlag,
    [string]$Title = 'Bob Systray',
    [string]$Message = 'Updating from git... installing scripts (no LLM).',
    [int]$TimeoutSec = 1800
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = $Title
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.MinimizeBox = $false
$form.MaximizeBox = $false
$form.ControlBox = $false
$form.TopMost = $true
$form.ShowInTaskbar = $true
$form.ClientSize = New-Object System.Drawing.Size 380, 120
$form.BackColor = [System.Drawing.Color]::FromArgb(22, 27, 34)
$form.ForeColor = [System.Drawing.Color]::FromArgb(230, 237, 243)

$lbl = New-Object System.Windows.Forms.Label
$lbl.AutoSize = $false
$lbl.Location = New-Object System.Drawing.Point 16, 16
$lbl.Size = New-Object System.Drawing.Size 348, 48
$lbl.Text = $Message
$lbl.ForeColor = $form.ForeColor

$hint = New-Object System.Windows.Forms.Label
$hint.AutoSize = $false
$hint.Location = New-Object System.Drawing.Point 16, 72
$hint.Size = New-Object System.Drawing.Size 348, 32
$hint.Text = 'Please wait. The tray starts when this finishes.'
$hint.ForeColor = [System.Drawing.Color]::FromArgb(139, 148, 158)

$form.Controls.Add($lbl)
$form.Controls.Add($hint)

$deadline = [datetime]::UtcNow.AddSeconds([Math]::Max(30, $TimeoutSec))
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 400
$timer.Add_Tick({
        if (Test-Path -LiteralPath $DoneFlag) {
            $timer.Stop()
            $form.Close()
            return
        }
        if ([datetime]::UtcNow -ge $deadline) {
            $timer.Stop()
            $form.Close()
        }
    })
$form.Add_Shown({ $timer.Start() })
$form.Add_FormClosed({ $timer.Stop(); $timer.Dispose() })
[void]$form.ShowDialog()
exit 0
