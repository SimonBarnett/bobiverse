<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request - Bob Fleet tray: weekly remaining + machine tiles (2026-09-19)

**Repo:** SimonBarnett/agentic_build
**Surface:** tools/Watch-BobTray.ps1, Get-BobTrayHover.ps1, Get-BobBoxUsage.ps1, bob-fleet-tray skill
**Status:** parked for build agent

## Charge (Simon)

1. Job lines must show the **GitHub repo name**, not a commit/HEAD SHA.
2. The percentage that matters is **Weekly limit left** (Grok CLI footer, e.g. "Weekly limit left: 9%"). Purpose: decide **where to instantiate build agents** this week on this account.
3. Show that remaining % as a **bar that drains as weekly quota is used** (remaining fills left; empty = spent).
4. Title **Bob (ionos)** is wrong for a multi-machine world. Do not brand the card as one machine id.
5. Layout: **Machine as a tile**, with **tasks on that machine listed underneath**.

## Context vs weekly (LOCKED)

| Metric | Source today | Role |
|---|---|---|
| Session context (e.g. 233K/500K) | usage.json / models_cache | Optional secondary; NOT the primary routing signal |
| **Weekly limit left %** | Grok CLI status / settings surface that shows "Weekly limit left: N%" | **PRIMARY** bar for fleet routing |

Do **not** invent weekly %. Prefer a real CLI/settings field (settings_cache, grok usage, or documented grok command). If the value is unavailable: bar shows n/a / hidden fill (same honesty as NC-02 null context) - never fake 100% or 0%.

## LOCKED UI

| ID | Rule |
|---|---|
| T1 | Card title: **Bob Fleet** (or similar product name) - not Bob (machineId). |
| T2 | Body groups by **machine tile** (ionos, marchhare, …). Under each tile: running (and queued) jobs for that machine. |
| T3 | Each job line: **owner/repo** (from git remote), duration, state. Prefer repo over cwd leaf; never show bare commit SHA as the primary label. |
| T4 | Primary bar: **Weekly remaining** (label explicit). Fill width = remaining%. Drains as used. |
| T5 | Cross-machine: if BobBridge store is still local-only, either (a) aggregate peer machine job records when available, or (b) show this machine tile honestly plus a note that peers need fleet peek - but title stays Bob Fleet and layout is tile-ready. Prefer (a) when feasible without inventing WinRM. |
| T6 | Short NotifyIcon.Text may summarize weekly remaining + run count (63 char limit). |
| T7 | Keep park-once dark card show (NC-D01) and no cursor-chase (NC-T01). |

## Acceptance

1. With weekly limit readable as 9%, bar shows ~9% remaining (not context window math).
2. Job under ionos shows e.g. SimonBarnett/agentic_irc not a SHA.
3. Title is not Bob (ionos); machines appear as tiles with jobs nested.
4. Null weekly => n/a bar, not depleted fake.
5. BT0 / tray tests updated; skill bob-fleet-tray rewritten.
6. Build agent UATs and MRBs back to Bob (standing order).

## Non-goals

- Inventing remaining-token counts the CLI does not expose.
- Replacing Grok CLI itself.
- Stopping BobFleet to reload (Watch-BobTray recycle only).

## Kickoff

Read this FR + current Watch-BobTray / Get-BobTrayHover / box-usage. Find real weekly-limit signal. Implement T1-T7. Commit/push. You UAT (hover card screenshot notes ok) and hostile-MRB back to Bob.
