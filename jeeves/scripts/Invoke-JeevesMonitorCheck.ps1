<#
.SYNOPSIS
  Token-free Jeeves MONITORING check runner (FR #787).
.DESCRIPTION
  Runs one named check under tools\monitor\*.py. Exit 0=ok, 1=finding, 2=error.
  Prints one JSON line on stdout. Prefer these scripts over reasoning.
.PARAMETER Check
  health | idle_seats | queue_flow | stale_digest | giveup_loops | stuck_accepted | auto_feed | auto_focus | focus_present | focus_redundant_items | seats_stuck_doing | skill_promote_backlog | intake_allowlist | github_resync_focus | needs_human_false_positive | opencode_seats | open_pr_stale_base | open_pr_mrb_missing | ticket_closure | depends_on | fr_digest
.PARAMETER DryRun
  Offline: scripts emit ok JSON and exit 0.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('health','idle_seats','queue_flow','stale_digest','giveup_loops','stuck_accepted','auto_feed','auto_focus','focus_present','focus_redundant_items','seats_stuck_doing','skill_promote_backlog','intake_allowlist','github_resync_focus','needs_human_false_positive','opencode_seats','open_pr_stale_base','open_pr_mrb_missing','ticket_closure','depends_on','fr_digest')]
    [string]$Check,
    [switch]$DryRun,
    [string]$InstallRoot = '',
    [string]$ChairHome = '',
    [string]$DigestHome = ''
)
$ErrorActionPreference = 'Stop'
$here = if ($InstallRoot) { $InstallRoot } else { Split-Path -Parent $PSScriptRoot }
$py = Join-Path $here "tools\monitor\$Check.py"
if (-not (Test-Path -LiteralPath $py)) {
    # Soft-skip: tip tree may lag AGENTS.md check list (non-chair / sparse sync). FR #9066.
    Write-Output (@{ check = $Check; ok = $true; skipped = $true; reason = "missing $py" } | ConvertTo-Json -Compress)
    exit 0
}
$python = $null
foreach ($c in @('python.exe', 'py.exe')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) { Write-Error 'python.exe not found'; exit 2 }
$argv = @($py)
if ($DryRun) { $argv += '--dry-run' }
if ($ChairHome) { $argv += @('--chair-home', $ChairHome) }
if ($DigestHome) { $argv += @('--digest-home', $DigestHome) }
& $python @argv
exit $LASTEXITCODE
