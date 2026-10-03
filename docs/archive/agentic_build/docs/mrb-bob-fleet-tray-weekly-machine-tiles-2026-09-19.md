<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/mrb-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - Bob Fleet tray weekly remaining + machine tiles (2026-09-19)

**Repo:** SimonBarnett/agentic_build  
**FR:** docs/feature-request-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md (park `7e8797e`)  
**HEAD reviewed:** `c31b0ed` Tray: weekly remaining bar + machine tiles (FR T1-T7)  
**Surface:** `tools/Watch-BobTray.ps1`, `src/Public/Get-BobTrayHover.ps1`, `tools/Get-BobBoxUsage.ps1`, `.grok/skills/bob-fleet-tray`, `.grok/skills/box-usage`  
**Evidence:** ionos live `Get-BobTrayHover` / `Get-BobBoxUsage -Hover` 2026-09-19 ~22:04 BST; last `unified.jsonl` billing line `creditUsagePercent=52`; Test-Pack BT0 15/0; UAT notes `docs/uat-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md`

## Verdict

**PASS** for locked FR T1-T7 (code + BT0 + live hover object). Not a cross-host job peek. Human eyeball of the WinForms card after Watch-BobTray recycle is still required.

Build agent UAT is in `/docs/uat-*.md`. Bob may declare **ready for human UAT** after the live card is seen.

## Locked rules vs this push

| Lock | Required | Evidence |
|---|---|---|
| Primary bar | Grok CLI `Weekly limit left: N%`, not session 233K/500K | `remaining_kind=weekly`; `Get-BobWeeklyRemaining` from last `billing: fetched credits config`; job `context_remaining_pct` is null and is **not** the bar |
| Do not invent % | n/a if field missing | Parser returns null without `creditUsagePercent` **and** weekly `currentPeriod.type`; monthly period rejected; Fake-Grok tests do not scrape operator log |
| Title | Bob Fleet, not Bob (ionos) | Live `title=Bob Fleet`; `Get-BobTrayTitle` is a constant |
| Tiles | Machine heading, jobs underneath | Live `jobs_text` is `ionos` then indented job line |
| Job label | GitHub owner/repo, never bare SHA | Live `SimonBarnett/agentic_build`; SHA-leaf cwd test paints `?` |

## T1-T7

| ID | Result | Notes |
|---|---|---|
| T1 | PASS | Title `Bob Fleet`. Watch-BobTray no longer paints `Bob (<id>)`. |
| T2 | PASS | `Get-BobMachines` tiles; this host first; empty tile `  no jobs`. Live: ionos tile + one running job. BT0l two-machine fixture: testhost then otherhost, running before queued. |
| T3 | PASS | `git remote get-url origin` slug; SHA-like leaf rejected. Live job is `SimonBarnett/agentic_build`, not `c31b0ed` / session id. |
| T4 | PASS | Caption `Weekly remaining`; fill width = remaining%; 0% shows empty track no fill; unknown hides track. Live remaining **48%** from 52% used (not context-window math). |
| T5 | PASS (b) | Store still local-only. No WinRM. Live footer `other hosts not in this store` because only `ionos` is registered here. Title stays Bob Fleet. Prefer (a) when peer records exist: BT0l otherhost tile from local store JSON. |
| T6 | PASS | Live short `P+ 1 run  48%` (under 63). Percent omitted when remaining unknown (`P+ idle` / `P+ N run`). |
| T7 | PASS | Park-once / ShowParkedAt / no MouseMove `Get-BobNotifyIconRect` unchanged. BT0m + BT0n green. |

## Evidence

### E1 - live hover (ionos, this job)

```
title=Bob Fleet
scope=local-store
short=P+ 1 run  48%
remaining_pct=48
remaining_kind=weekly
jobs_text:
  ionos
    SimonBarnett/agentic_build  5m  running
  other hosts not in this store
```

`Get-BobBuilds -Lane running` is job `21c8450f` cwd `C:\ai\agentic_build`. Repo label is origin slug, not the job id.

### E2 - weekly field (real CLI log, not invented)

Last `~\.grok\logs\unified.jsonl` line `billing: fetched credits config`:

- `creditUsagePercent`: 52.0
- `currentPeriod.type`: `USAGE_PERIOD_TYPE_WEEKLY`
- remaining = round(100-52) = 48

`Get-BobBoxUsage` text: `Weekly: remaining 48% (used 52%) source=unified.jsonl:billing: fetched credits config`

No `auth.json`. No billing HTTP. Session `usage.json` is not the bar.

### E3 - Test-Pack

`tools/Test-Pack.ps1` **BT0 15 pass / 0 fail**.

BT0l covers: Bob Fleet title; weekly n/a hide fill; 91% used => 9% remaining; missing `creditUsagePercent` => null; monthly period => null; missing period type => null; owner/repo job line; SHA cwd not leaked; two machine tiles; running before queued; skills name `creditUsagePercent`.

BT0m/BT0n still cover park-once and ShowParkedAt (T7).

### E4 - skills

`bob-fleet-tray` and `box-usage` rewritten: weekly bar primary, context optional on the job object only, badge `alert: watcher|stall|weekly|none`, recycle Watch-BobTray only.

## Non-conformances

None against locked T1-T7.

## Nits (not blockers)

1. **WinForms card not eyeballed in this session.** Hover object and paint path match. Operator still needs to mouse-over / left-click the robot after recycle.
2. **Watch-BobTray was down at UAT** (`BobFleet-ionos` Ready, no tray process). Recycle starts the STA script only. Do not `Stop-ScheduledTask BobFleet-*` while `21c8450f` runs.
3. **Two `Watch-BobJobs.ps1` (non-Once) processes** were already present. Out of scope. Left running.
4. **Weekly % lags the CLI footer** until grok.exe writes another `billing: fetched credits config` line. Documented. Do not scrape a second source.
5. **NC-05 id8** from the old fleet-claim MRB is intentionally gone from the visible line. This FR says `owner/repo  duration  state`. id8 remains on the job object.

## Fail bar (checked, not hit)

- Bar using session context 233K/500K
- Invented 100% / 0% when billing field missing
- Title `Bob (ionos)`
- Job line primary label is a commit SHA
- `Stop-ScheduledTask BobFleet-*` while a job runs
- `auth.json` or billing HTTP

## Ops

Recycle **Watch-BobTray.ps1 only** (hidden STA). Never `Stop-ScheduledTask BobFleet-*` while jobs run.

## Non-claims

- Not a remote multi-host store. MarchHare jobs will not appear on ionos until they share a store or a documented peek exists.
- Not a redesign of the FA robot.
- Not a replacement of the Grok CLI footer.
