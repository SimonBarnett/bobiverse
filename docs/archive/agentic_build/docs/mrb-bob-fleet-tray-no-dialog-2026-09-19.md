<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/mrb-bob-fleet-tray-no-dialog-2026-09-19.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - Bob tray dark hover card not shown (2026-09-19)

**Repo:** SimonBarnett/agentic_build
**Tip:** 1b54cdd / e50ce69 (park-once PASS claimed)
**Reporter:** Simon after tray-only recycle (Jobs/BobFleet left running)

## Verdict

**FAIL**

Native NotifyIcon tip shows (P+ 1 run). The custom dark hover dialog/card never appears. Park-once geometry is moot if Show never succeeds for the operator.

## Evidence

1. Tray recycled without quitting fleet: new Watch-BobTray PID; zero-config job still running.
2. Screenshot: white Windows tooltip P+ 1 run over tray; no dark Bob card.
3. Prior NC-T01 fixed cursor-chase by changing MouseMove placement; likely regression or ShowWithoutActivation / hit-test / exception path now prevents tip.Show().

## Required fixes (ordered)

### NC-D01 (blocker) - Dark card must show on robot hover

1. Reproduce: hover NotifyIcon robot; assert custom Form becomes Visible with title Bob (machineId).
2. Fix root cause (candidates: MouseMove not firing on Win10/11 overflow; TipForm ShowWithoutActivation never paints; placement off-screen; exception swallowed; native tip stealing hover).
3. Also wire left-click to show card once if hover is unreliable in overflow chevron.
4. Log show/hide failures to tray log (path in skill).

### NC-D02 (major) - Keep park-once

Do not reintroduce cursor-follow. Card parks once near icon/tray; Location sticky while Visible.

### NC-D03 (nit) - Short Text tip

NotifyIcon.Text P+ 1 run may remain as fallback; must not be the only UI.

## Pass bar

- Hover or left-click robot shows dark card with jobs/context/alert.
- Card does not chase cursor.
- BT0 still green.
- Recycle Watch-BobTray only for verify; do not Stop-ScheduledTask BobFleet while jobs run.

## Hand-off

Build agent ionos, cwd C:\ai\agentic_build: implement NC-D01 (+ D02). Commit/push. Do not claim UAT. Leave running jobs alone.
