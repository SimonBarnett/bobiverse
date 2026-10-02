# Open Configure on the existing Cursor GitHub App install.
# Do not use /apps/cursor/installations/new when already installed:
# that flow can replace Selected-repos and drop existing repos.
# A user OAuth token cannot add GitHub App installations (API 403).
# Skill: plan-enable-prs (harvested from agentic_build setup-github-cursor).
[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
Write-Host 'Cursor Web pushes as cursor[bot] (x-access-token), not your gh user.'
Write-Host 'cursoragent is only the git author on cursor/* branches.'
Write-Host 'Configure the EXISTING install (not /installations/new):'
Write-Host 'https://github.com/settings/installations'
Write-Host 'If All repositories is already set, leave GitHub alone.'
Write-Host 'Disconnect then Connect GitHub as SimonBarnett (not MedatechUK):'
Write-Host 'https://cursor.com/dashboard/integrations'
Write-Host ''
Write-Host 'gh cannot grant this. user/installations is 403 (need a GitHub App token).'
Write-Host 'Do not PUT collaborators/cursor[bot] (404: not a user).'
Write-Host 'Do not add cursoragent as a collaborator (wrong identity for the 403).'
Write-Host 'collaborators/cursor[bot]/permission = none is not the grant test.'
Write-Host 'Real test: Cursor Web / Cloud Agent push (git-receive-pack as cursor[bot]).'
Write-Host ''
Write-Host 'Public SimonBarnett repos (human PRs already allowed; app grant is the 403 fix):'
gh repo list SimonBarnett --limit 200 --json name,isPrivate --jq '.[] | select(.isPrivate|not) | .name'
Write-Host ''
Write-Host 'Private (leave private):'
gh repo list SimonBarnett --limit 200 --json name,isPrivate --jq '.[] | select(.isPrivate) | .name'
if (-not $NoBrowser) {
    Start-Process 'https://github.com/settings/installations'
    Start-Process 'https://cursor.com/dashboard/integrations'
}
