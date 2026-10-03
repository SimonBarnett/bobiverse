<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-fleet-gh-posting-readiness-2026-09-20.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: fleet GitHub posting readiness (issue #11)

**FR:** `docs/feature-request-fleet-gh-posting-readiness-2026-09-20.md`  
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/11

## Build

1. **`src/Private/Get-BobGh.ps1`** — `Get-BobGhExe`, `Get-BobGhPostingReadiness` (live probe), `Test-BobGhIssuePosting`, `Install-BobGitHubCliIfMissing`, heartbeat snapshot helper.
2. **`Get-BobHealth`** — expose `gh_posting` object.
3. **`Get-BobCapacity` / machine rows** — carry `gh_posting` from `machine.json` or live probe on this host.
4. **`Select-BobGitWorker -Kind mrb`** — skip machines without `issue_posting_ready`.
5. **`Install-BobFleet`** — winget GitHub CLI when missing; print readiness + remediation (no secrets in git).
6. **`Write-FleetHeartbeat` / `Register-BobMachine`** — persist `gh_posting` snapshot on the machine record.
7. **Tray / box-usage** — `Get-BobTrayHover.gh_posting` + `Get-BobBoxUsage` health line.
8. **Skills** — `cursor-mrb-dev`, `grok-build-fleet` token contract.

## Test (off-DEV)

```powershell
powershell -NoProfile -File .\tools\Test-Pack.ps1
```

Cases **BT0x1–BT0x5**: absent gh, dead token, ok fixture, mrb picker skips not-ready, Install-BobFleet mentions gh provisioning.

Existing **BT0t/BT0u** still cover `Test-BobGhIssuePosting` throw paths.

## Human smoke (optional, on a fleet box with real gh)

```powershell
Import-Module .\src\BobBridge.psd1 -Force
Get-BobGhPostingReadiness | Format-List
Get-BobHealth | Select-Object gh_posting
```

Expect `issue_posting_ready=true` when `gh auth status` and `gh repo view SimonBarnett/agentic_build` succeed.
