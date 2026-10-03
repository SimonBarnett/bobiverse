<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bobiverse-channel-talk-tray-pull-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: channel talk + tray pull via !bobiverse (producer)

**Date:** 2026-09-21
**Repos:** SimonBarnett/agentic_build (Watch / Write-BobIrcStatus / tray)
**Sister protocol FR:** agentic_irc
`docs/feature-request-bobiverse-channel-talk-tray-pull-2026-09-21.md`
**Supersedes UX of:** agentic_build#36 + agentic_irc#6 DM-centric answer
**Raised by:** Simon

## Problem

Halloy still shows a POINT firehose. Quiet-talk #6 answered `!bobiverse` as
DMs (Query). Simon: conversational lines belong in **channel chat**;
`!bobiverse` is for **agents** to pull each machine's last update about
every **two minutes** and refresh the **system tray**.

Ionos often missing or shown as `Working on ?.` because local peer / job
stamps use `repo=?`.

## LOCKED

1. Stop PRIVMSG of full `BOB v1` POINT every Watch tick for humans.
2. On real field change (not lastSeen-only) or one-shot long-running
   warning: one English line to `#bobiverse`.
3. Watch / tray agents poll `!bobiverse` ~120s, ingest last-update-per-id,
   write `bob-peers\<id>.json`. Keep weekly bars.
4. Ionos must stamp a real repo (or idle) — never publish `?` as the only
   repo label when a job exists; ionos must show in tray when joined.
5. No secrets.

## Gap vs tree

| Current | Wanted |
|---|---|
| Watch-Bobiverse → Write-BobIrcStatus → POINT | Disk peers + channel change-talk; pull via !bobiverse |
| build#36 parked, not shipped | Implement this UX |
| Get-BobJobRepoStamp / peek can yield `?` | Ionos tray + talk never `Working on ?.` |

## Acceptance

1. Channel quiet except change / warning lines.
2. Tray stays fresh from `!bobiverse` ~2 min pulls without POINT spam.
3. Ionos visible with non-`?` job label or idle.
4. Off-DEV Test-Pack / Fake seams; no live Ergo in pack.
5. PR only; no UAT stamp by worker.

## Non-goals

- Halloy config. MRB PDF. Closing historical MRB #9.
