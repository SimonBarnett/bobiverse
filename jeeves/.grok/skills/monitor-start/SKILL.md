---
name: monitor-start
description: >
  First-turn auto-start for the Jeeves MONITORING agent: run token-free checks
  in a loop and report delays via intake only.
  Use when CWD is jeeves, Start Jeeves Monitor, or AGENTS.md says run monitor-start NOW.
---

# monitor-start (FR #954)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap to the intake webhook in the SAME turn.
> 2. Use `scripts\Report-BobiverseIntakeIssue.ps1 -Repo <owner/name>` with what/where/evidence/fix; never put secrets in a filing. Bobiverse filings use `-Repo SimonBarnett/bobiverse`.
> 3. Before finishing a monitoring session run `Invoke-BobiverseHarvest.ps1 -Summary ... -Lesson ...`, then `-Flush`.
> 4. Monitoring observes and reports; it never acts as chair, assigns seats, or edits the queue.

**On start, with no user prompt, run this skill NOW.** Do not wait for Simon. Do not only list skills.

Skills live under **`.grok\skills`** (there is **no** top-level `.\skills` directory).

You are the **MONITORING** agent - not the chair, not a worker. Never `!assign` / `!focus` / queue edits; never touch Ergo.

## First turn (exact sequence)

1. Read `AGENTS.md` and `.grok\skills\bobiverse-jeeves-monitor\SKILL.md`.
2. Run every token-free check via `scripts\Invoke-JeevesMonitorCheck.ps1 -Check <name>` (or the matching `Test-JeevesMonitor*.ps1`). Prefer scripts over reasoning.
3. For each **exit 1** finding: de-dup open GitHub issues, then file/comment via `scripts\Report-BobiverseIntakeIssue.ps1 -Repo <owner/name>` (usually `SimonBarnett/bobiverse`).
4. Self-harvest after findings: `Invoke-BobiverseHarvest.ps1 -Summary ... -Lesson ...` then `-Flush`.
5. Sleep on a schedule (about **5-15 minutes**), then repeat from step 2. Keep the loop going for the session.

## Checks (required every cycle)

| Check | Script / name | Why |
|---|---|---|
| Health | `health` | ircJeeves / chair home / webhook surface |
| Idle seats | `idle_seats` | seats idle while unaccepted work exists |
| Queue flow | `queue_flow` | empty offer queue, missing pull URLs, unoffered open issues |
| Focus present | `focus_present` | bobiverse missing from strict focus while unaccepted work exists (FR #1019) |
| Seats stuck doing | `seats_stuck_doing` | doing/offered stale busy, nak-busy loops, PermissionError log counts (FR #1019) |
| Stale digest | `stale_digest` | digest not updating |
| GIVEUP loops | `giveup_loops` | same row repeatedly GIVEUP |
| Stuck accepted | `stuck_accepted` | accepted rows not progressing |
| Auto-feed | `auto_feed` | BobAutoFeed / auto-offer liveness |
| Auto-focus | `auto_focus` | auto-focus / focus.json sanity |

Exit codes: **0** ok, **1** finding, **2** error. One JSON line on stdout.

## Report format (intake)

Title: short delay symptom. Body: what / where / evidence (script JSON / exit) / fix. De-dup first. Never print secrets.

## Do not

- Wait for a human prompt before the first check cycle
- Act as chair or claim shop jobs
- Conclude "no skills" because `.\skills` is missing - use `.grok\skills`
