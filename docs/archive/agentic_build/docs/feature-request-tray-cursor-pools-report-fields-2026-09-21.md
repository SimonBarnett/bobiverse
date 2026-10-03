<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-tray-cursor-pools-report-fields-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: tray — one bar per Cursor quota pool + !report task lines

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/91
**Surface:** `Watch-BobTray`, `Get-BobTrayHover`, `bob-seats.json`, `bob-fleet-tray` skill
**Sister:** https://github.com/SimonBarnett/agentic_irc/issues/36 (`!report` / `!bobiverse` JSON digest, PR #37)
**Raised by:** Simon (screenshot 2026-09-21 ~10:12 BST, ionos tray + Grok job loops on irc #34 / #36)
**UAT + hostile MRB owner:** Bob

Me-project. Do not productise the tray.

## Problem

Live card `#Bobiverse (ionos)`:

- One top strip: **Cursor Models (-£75.03) - reset 23 Sep**
- Machine rows are **Grok weekly** only: ionos Smart Catalogue 12%, ce-priority-dev1 ntsa 4%, flamingo Club Madeira 8%, marchhare ntsa 4%
- Job lines: `grok.exe ? running` twice under ionos. No repo, no SHA, no task description, no runtime. `?` is the same hole #26 called out.

The house has **more than one Cursor quota pool** (seats / accounts). Collapsing them into a single Models bar hides which pool a Composer vs Cursor-Grok job is burning. The Grok 4.5 session on the screenshot is already looping #34 and #36; the tray cannot show that work.

`!report` (irc #36) is the write path for:

```text
!report TASK START|STOP {repo} {sha} {model} {description} {run-time}
!report PCENT {machine} {Source} xx%
!report UPTIME {since}
```

The tray does not read those fields yet.

## LOCKED

1. **One bar per Cursor quota pool.** Every seat/account in `config/bob-seats.json` (and any pool `Get-BobCursorAgentWeeklyRemaining` / usage fetch already knows) gets its **own** bar: label, used or remaining %, reset date, overage GBP if known. Do **not** fold them into one “Cursor Models” strip.
2. **Grok weekly bars stay per machine** (existing rows). Do not replace those with Cursor bars.
3. **Job lines come from `!report` digest** (and local job store if digest not in yet):
   - `START`: `{repo}  {sha}  {model}  {description}  {run-time}`
   - `STOP`: last task stays one dim line or drops after one tick — pick one in implementation; do not leave `grok.exe ? running`
   - Never invent `?` for repo/sha when the digest has them
4. **PCENT** from `!report` updates the matching bar (`Source` = `cursor-models` / seat id / `grok-build` / …). Same number twice is not a redraw storm.
5. **UPTIME** may be a quiet subtitle on that machine tile (`up since …`). Not a fifth firehose.
6. Same card on every box once peer digest / `!bobiverse` JSON pull exists. Until irc #36 lands, local jobs + seats still paint pools and must not regress to `?` when the local packet has repo/sha.
7. No secrets on the card. Recycle tray only; never `Stop-ScheduledTask BobFleet-*` while jobs run.

## Layout (target)

```text
#Bobiverse
Cursor pools (one bar each)
  seat-A  Models     9%   reset 23 Sep   -£75.03
  seat-B  Models     8%   reset …
  …
Machines
  ionos            grok week 12%  reset 26 Sep
    START SimonBarnett/agentic_irc  395c499  composer-2.5  report digest  1m52s
    START SimonBarnett/agentic_irc  …        grok-4.6      house-clean    1m52s
  ce-priority-dev1 grok week 4%   reset 22 Sep
    no jobs
  flamingo         …
  marchhare        …
```

Exact seat labels come from `Format-BobCursorAccountLabel` / seats JSON — do not invent marketing names.

## Ask

### agentic_build

- `Get-BobTrayHover` / `Watch-BobTray`: render N Cursor pool bars from seats + usage, not one Models bar.
- Job block: prefer digest JSON from `!bobiverse` / `bob-peers` fields `task.repo|sha|model|description|run_time|state`. Fallback to local `Get-BobBuilds` **using the same fields** so ionos stops showing `?` even before irc ingest is live.
- Test-Pack fixtures: two Cursor seats → two bars; a START report → line contains sha + description; no `?` when sha present; missing digest → idle `no jobs` not a fake task.
- Skill `bob-fleet-tray` documents the new card.

### agentic_irc

- #36 must keep digest JSON stable enough for the tray parser. If the JSON shape moves, update this FR. Do not re-POINT `BOB v1` to fill the card.

## Acceptance

1. Two or more Cursor seats in fixture → two or more top bars, each with its own % / reset.
2. Machine with a START report shows repo, short sha, model, description, runtime — not `grok.exe ? running`.
3. Machine with no task: `no jobs`.
4. Off-DEV Test-Pack; no live Ergo required to paint fixtures.
5. PR + hostile MRB on #91. Only Bob stamps UAT.

## Non-goals

- Redesigning Halloy.
- Putting JSON on `#bobiverse`.
- Closing irc #34 / #36 from this PR.
- WinRM peek.
- Productising seats as a public billing UI.
