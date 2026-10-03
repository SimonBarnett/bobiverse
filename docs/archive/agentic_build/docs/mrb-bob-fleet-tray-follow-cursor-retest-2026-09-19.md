<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/mrb-bob-fleet-tray-follow-cursor-retest-2026-09-19.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - Bob tray hover park-once retest (2026-09-19)

**Tip:** e50ce69 Tray: park hover card near icon; do not follow cursor (NC-T01)
**Prior FAIL:** docs/mrb-bob-fleet-tray-follow-cursor-2026-09-19.md

## Verdict

**PASS** for NC-T01..NC-T03 (offline + source). Ready for operator tray recycle to pick up the binary.

## Evidence

| Check | Result |
|---|---|
| MouseMove | Parks via Get-BobTrayTipPlacement on first show only; comment forbids later Location updates from cursor |
| Icon rect | Shell_NotifyIconGetRect present |
| No-activate | TipForm ShowWithoutActivation + WS_EX_NOACTIVATE |
| Test-Pack | BT0 **14 pass / 0 fail** including **BT0m tray tip placement** |
| NC-01..05 | BT0l still green |

## Ops

Live tray still runs the old script until Watch-BobTray is restarted. Recycle tray process only (not Stop-ScheduledTask BobFleet-*) when the lane is quiet enough.

## Non-claims

Not a cross-host fleet product. Human eyeball on the robot icon still recommended after recycle.
