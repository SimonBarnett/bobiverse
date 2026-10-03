<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-watch-irc-tsr-cursor-listen-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: IRC TSR + Cursor listen watchdog (silence recycle)

**Date:** 2026-09-22
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/163
**Raised by:** Hostile MRB of SHA `8be01ef013b9ea5c1b6018651375c338462a31ef` (PR #140 / issue #140)
**UAT + hostile MRB owner:** Bob

PR #140 is the bulk-close stale MRB boards chair. Its head commit is
`Watch-IrcTsr: recycle listen if wake log silent for 60s` (2 files). The
same PR also adds `Start-IrcTsr.ps1`, `Irc-Tsr-Runner.ps1`,
`Watch-CursorIrc.ps1`, and ionos wrappers. **No** `docs/feature-request-*.md`
covers that surface. Do **not** implement on the #140 FIX job.

## Problem

Fleet Cursor IRC seats (`cursor-<machine-id>`, `~/.agentic-irc-cursor`) need
a keep-alive that restarts `irc_listen.py` / the TSR runner when the child
is dead or the wake log is stale. That work landed on an unrelated
CONFLICTING PR with zero Test-Pack cases.

## LOCKED

1. One FR for the TSR runner + `Watch-IrcTsr` + `Watch-CursorIrc` + install
   wrappers. Not part of #140 / #118.
2. Off-DEV Test-Pack. No live Ergo. No live `gh`. PR only.
3. Recycle gate must not treat an idle `#bobiverse` as dead. A 60s
   `irc.log` LastWriteTime check recycles a healthy listen on a quiet
   channel. Silence must be measured on the TSR wake file
   (`irc-tsr-*-wake.jsonl` / `AGENT_LOOP_WAKE_irc-tsr`) or an equivalent
   process heartbeat, not chat-log mtime.
4. Do not default `-MachineId` to `ionos`. Fleet id comes from
   `BOB_MACHINE_ID` / install wrapper.
5. Secrets stay out of git. Read the existing connect password file; no
   `password=` / `XAI_API_KEY=` assignments.
6. Watch-Bobiverse stays dumb (no grok.exe / no fold-in of this poller).

## UNKNOWN

- Scheduled-task name vs `_Watch-IrcTsr-<id>` / `_Watch-CursorIrc-<id>`.
- Poll interval and restart-after age.
- Whether `Watch-CursorIrc` starts TSR only or also `irc_agent.py`.

## Gap vs tree (main `849d772`)

| Current | Wanted |
|---|---|
| No `Watch-IrcTsr` / `Start-IrcTsr` on main | Spec + tests, then a dedicated PR |
| SHA `8be01ef` on PR #140 | Strip from #140; implement here |

## Acceptance

- **AC1** Intake + plan exist. Implementation is not on PR #140.
- **AC2** Watchdog restarts when the TSR runner or `irc_listen.py` child is
  gone, or the wake heartbeat is stale. Idle `irc.log` is not a fail.
- **AC3** Test-Pack asserts the healthy/stale/idle-log matrix off-DEV.
- **AC4** No secret assignments in git.

## Non-goals

- Bulk-close stale MRB boards (#140 / #118).
- Watch-GrokTalk fleet install (#126 sister).
- Shop-channel / change-only webhook (#124 / #141).
- Stamping UAT. Any MRB PDF.
