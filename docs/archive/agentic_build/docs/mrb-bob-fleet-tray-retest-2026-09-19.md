<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/mrb-bob-fleet-tray-retest-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - Bob tray watcher retest (2026-09-19)

**Tip:** `f1f3ac6` Tray: this-machine title; hide unknown context bar (MRB NC-01..04)  
**Prior:** docs/mrb-bob-fleet-tray-2026-09-19.md **FAIL**

## Verdict

**PASS** for NC-01..NC-05 as scoped. Ready for operator tray recycle on each box. **Not** a cross-host fleet product (honestly out of scope until BobBridge gains peer peek).

## Evidence

Live `Get-BobTrayHover` on ionos after pull:
- `title`: `Bob (ionos)`
- `scope`: `this-machine`
- idle/job copy uses this-machine wording; body shows `context remaining  n/a` when unknown
- running job line includes `id8` (`1299cb65`)
- `remaining_pct`: null with known job still running (no fake %)

Offline: Test-Pack **BT0 13 pass / 0 fail** including **BT0l tray hover**.

| NC | Retest |
|---|---|
| NC-01 | Pass - no "fleet" claim; `Bob (<id>)` |
| NC-02 | Pass - n/a + fill_width null when unknown |
| NC-03 | Pass - skills/docs session-window only |
| NC-04 | Pass - pulse only when known and under 10%; `alert:` line |
| NC-05 | Pass - id8 on card lines |

## Ops note

Recycle **Watch-BobTray.ps1** only (not Stop-ScheduledTask BobFleet-*) when no critical misunderstanding of the old binary; do not recycle fleet task while jobs in flight.