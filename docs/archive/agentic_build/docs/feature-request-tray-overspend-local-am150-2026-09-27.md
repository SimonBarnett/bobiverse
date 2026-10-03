<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-tray-overspend-local-am150-2026-09-27.md, last changed 2026-09-27. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR AgentMonitor #150: TipForm overspend + pools from local machine

Filed on AgentMonitor; TipForm / `Get-BobTrayHover` / `Watch-BobTray` live in
**agentic_build** (same ownership as AgentMonitor #148 → PR #422).

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Cursor overspend local | `account_overage_gbp` from local Spending only | BT0overspend423 | Digest cache GBP painted |
| S2 | This-host Grok weekly local | Digest weekly/pcent cannot overwrite known local weekly | BT0am150 | Digest 11% wins over local 77% |
| S3 | Publish unchanged | `Write-BobIrcStatus` still POSTs local overage/weekly | existing digest tests | Publish removed |

## Changes

- `Get-BobCursorOverageGbp` local-only (#423).
- Digest `grok-build` pcent / `machines.*.weekly` skip this host when local weekly known (#150).
