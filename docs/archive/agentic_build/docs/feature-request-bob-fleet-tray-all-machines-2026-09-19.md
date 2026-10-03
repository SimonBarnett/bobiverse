<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bob-fleet-tray-all-machines-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request — Bob Fleet tray: show ALL machines + jobs (2026-09-19)

**Repo:** SimonBarnett/agentic_build  
**Surface:** Watch-BobTray, Get-BobTrayHover, BobBridge fleet store, bob-fleet-tray skill  
**Status:** parked for build agent  
**Triggered by:** Simon human eyeball on ionos / MarchHare / CE-PRIORITY-DEV1 — each card only showed **this** host + “other hosts not in this store”.

## Charge (Simon)

1. The hover card must list **every fleet machine**, not only the box where the tray is running.
2. Under each machine tile: the **tasks/jobs running (and queued) on that machine**.
3. Keep prior locks: title **Bob Fleet**; primary bar **weekly remaining %** (n/a if unknown); job lines **owner/repo** (not bare SHA); park-once dark card; recycle Watch-BobTray only.

## Problem today

T5 of the weekly-tiles FR allowed (b) local-only honesty. Live cards on three boxes each show one tile + footer `other hosts not in this store`. That fails the multi-machine routing UX Simon wants when deciding where to put work.

Registered hosts (Grok Bot local-exec / BobBridge), observed 2026-09-19:

| Machine id | Hostname / label |
|---|---|
| ionos | WIN-MPRE8VI4U6U |
| marchhare | MarchHare |
| ce-priority-dev1 | CE-PRIORITY-DEV1 |

## LOCKED UI

| ID | Rule |
|---|---|
| M1 | Card always enumerates **all known fleet machines** (from shared registry + any peer heartbeat), even if a host has zero jobs (`  no jobs`). |
| M2 | Under each machine: running then queued jobs for **that** machine only (`owner/repo  duration  state`). |
| M3 | No “other hosts not in this store” cop-out when peers are registered — either show them or show an explicit **unreachable / lastSeen stale** state on that tile. |
| M4 | Same card shape on every box (ionos tray and MarchHare tray and DEV1 tray show the same multi-host picture once peek works). |
| M5 | Do not invent jobs or weekly %. Stale weekly billing log may stay n/a or aged; label honesty over fake freshness. |
| M6 | Prefer a **shared store or documented peer peek** (file share, BobBridge fleet peek, or read-only pull of peer `fleet/` + `machine.json`). No silent WinRM invention; if a transport is required, document it and fail closed with tile status. |
| M7 | Preserve NC-T01 park-once and NC-D01 show-on-hover/click. Never `Stop-ScheduledTask BobFleet-*` while jobs run. |

## Acceptance

1. With three registered machines, any tray hover lists all three tiles.
2. A job running on ionos appears under the ionos tile on MarchHare’s and DEV1’s cards (once peek is live), not only on ionos.
3. Empty machine shows `  no jobs`; unreachable shows clear stale/unreachable — not omitted.
4. BT0 fixtures cover ≥2 remote tiles + local; skills rewritten.
5. Build agent UATs (hover notes from ≥2 boxes if available) and hostile-MRBs back to Bob.

## Non-goals

- Replacing Grok CLI weekly footer.
- Full remote process control UI.
- Merging unrelated Grok Bot sidebar agents into the tray.

## Kickoff

Read this FR + `docs/feature-request-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md` + current Get-BobTrayHover / Watch-BobTray / fleet layout. Implement M1–M7. Commit/push. You UAT and hostile-MRB back to Bob.
