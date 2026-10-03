<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-root-exit-teardown-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: watcher teardown when seat console/root exits

**Issue:** https://github.com/SimonBarnett/AgentMonitor/issues/126  
**Date:** 2026-09-26  
**Label:** bug

## Summary

When the watch seat console or root agent exits, `Watch-AgentHealth` must tear down that seat within one poll: write `quit.req` (IRC PART+QUIT), stop `irc_agent` / `irc_listen` for **this** home only, stop `!bored` and new wakes, and exit the monitor. It must not relaunch the root or stay on IRC claiming work.

## Gap vs current tree (pre-fix)

- **Grok:** unhealthy root path called `Disconnect-WatchIrc`, then set `$needStart = $true` and relaunched. Next loop `Ensure-WatchIrcSeat` rejoined IRC; `Sync-WatchBored` kept posting `!bored` (MarchHare orphan `marchhare-8592` on slot 2).
- **Cursor:** TUI loss switched to print-only after Disconnect; FR #126 requires the same hard stop (no wakes / no `!bored` / monitor exit) so an orphan watcher cannot keep a stale Jeeves claim.

## Acceptance

| ID | Criterion |
|----|-----------|
| A1 | Root agent or console exit → monitor notices within one poll (`BoredCheckSeconds`). |
| A2 | Writes `quit.req` on the bound watch home; `irc_agent` gets PART+QUIT path (Jeeves `quit_release`). |
| A3 | Stops this home's `irc_agent` / `irc_listen`; no `!bored` and no wake start after root loss. |
| A4 | Monitor exits (does not relaunch root). |
| A5 | Slot-2 teardown leaves slot-1 processes and nick untouched (bound-home guard). |

## Out of scope

- Jeeves PART-vs-QUIT release policy (AgentMonitor writes `quit.req`; irc_agent must QUIT).
- UAT stamp.
