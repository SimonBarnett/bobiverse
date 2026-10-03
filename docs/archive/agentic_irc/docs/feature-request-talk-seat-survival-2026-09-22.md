<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-talk-seat-survival-2026-09-22.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: talk-seat survival — detached listen by default; no home steal

**Date:** 2026-09-22  
**Source:** Simon `#bobiverse` — why bots keep dying. Analysis flamingo-17568 + marchhare.

## Summary

Talk seats keep looking dead for two distinct reasons. Skills already document ops (`killproc`, Other flamingo looks disconnected). This FR is **code** so Start-TalkSeat / listen defaults stop the common failure modes without human salvage.

## Gap vs skills (do not re-doc)

- `killproc` / `Stop-HungAgent.ps1` — salvage after death
- `agentic-irc` — deaf vs dead, Cursor kills foreground listen, PASS/464, dual home

## LOCKED

1. **Detached listen by default.** `Start-TalkSeat.ps1` / `Start-IrcTsr.ps1` must start `irc_listen` as a process that survives the Cursor agent shell (no dependency on IDE-foreground python that exits `4294967295` in ~3s). Optional: write `listen.stdout.log` for TSR tail.
2. **No home steal.** `Start-TalkSeat` must refuse to bind a home that already has a live `coordinator.pid` / agent for a different nick (already partial — make hard fail + clear error; never kill the other seat's listen).
3. **Seat host lifecycle.** Document/enforce that the PowerShell `seat=` process (or an equivalent hold) stays alive for the talk session; if seat dies, agent must exit or reconnect policy must be explicit (no orphan agent with empty listen).
4. Do not gut Ergo/Watch. Do not stamp UAT.

## Acceptance (draft)

1. Hermetic/integration: Start-TalkSeat leaves listen alive after parent shell exit simulation.
2. Second Start-TalkSeat on same home with different nick fails closed (no QUIT of first).
3. Test-Pack or pytest locks the above.
4. Bob UAT on live dual Cursor TUIs on one box.

## Related

- Skills: killproc (`agentic_build` 5e2f7dc), agentic-irc Other flamingo looks disconnected (`bddccc5` / `1ae0b7c`)
- Issue #88 talk-seat PID (related; do not reopen as this)
