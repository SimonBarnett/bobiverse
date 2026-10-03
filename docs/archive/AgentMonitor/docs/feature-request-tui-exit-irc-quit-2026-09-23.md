<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-tui-exit-irc-quit-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: on TUI exit, PART then QUIT the watch IRC nick (issue #43)

https://github.com/SimonBarnett/AgentMonitor/issues/43

Parked from hostile MRB of [issue #40](https://github.com/SimonBarnett/AgentMonitor/issues/40) / [PR #38](https://github.com/SimonBarnett/AgentMonitor/pull/38). Commit `07abe04` landed on that PR with no intake. It is not issue #40. No source PDF. No UAT.

## LOCKED

1. On watch TUI exit, watch stop, unhealthy agent tree, or print-only miss-node, write `quit.req` on **this** watch IRC home only (`%USERPROFILE%\.agentic-irc-watch-cursor` or `.agentic-irc-watch-grok`).
2. `irc_agent` PARTs then QUITs so the next TUI JOIN is not a ghost nick.
3. Forbidden homes: skip disconnect. Do not write `quit.req` there.
4. After a short wait, leftover `irc_agent.py` / `irc_listen.py` bound to that home may be stopped. Do not touch other homes.
5. No UAT stamp.

## Gap vs `2eccf7e` / issue #40

`main` and issue #40 do not specify PART+QUIT on TUI close. `Disconnect-WatchIrc` on `07abe04` is a new surface.

## Acceptance

| ID | Gate |
|----|------|
| A1 | TUI close / watch stop writes `quit.req` on the watch home only. |
| A2 | Forbidden homes are not written. |
| A3 | Next watch TUI JOIN is not a ghost of the previous nick. |
| A4 | No UAT stamp. |
