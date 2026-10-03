<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/mrb-bob-fleet-tray-no-dialog-retest-2026-09-19.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - Bob tray dark card retest (2026-09-19)

**Tip:** fc3e61b Tray: show dark hover card on robot hover/click (NC-D01)
**Prior FAIL:** docs/mrb-bob-fleet-tray-no-dialog-2026-09-19.md

## Verdict

**PASS** for NC-D01/D02 offline + agent evidence (force-show + left-click + park-once). Operator eyeball: hover or left-click robot; dark Bob (machineId) card must appear. Native P+ tip may remain as short fallback only.

## Evidence

- Force-show via SetWindowPos SWP_NOACTIVATE; ShowParkedAt; icon rect cached on timer (not MouseMove).
- Left-click fallback; hover probe in icon rect.
- Park-once unchanged.
- BT0 15/0 including BT0n (per build agent).
- Watch-BobTray recycled only; BobFleet/jobs untouched.
- Live log tip show ok reason=hover (per build agent).

## Nits

1. Human confirm on ionos desktop after this MRB.
2. Ensure docs MRB FAIL file exists on main if missing from interrupted park.

## Non-claims

Not cross-host fleet. Not human UAT of all tray UX forever.
