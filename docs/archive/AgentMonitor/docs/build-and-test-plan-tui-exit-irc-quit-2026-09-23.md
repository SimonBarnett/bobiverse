<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-tui-exit-irc-quit-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: TUI-exit IRC PART+QUIT (issue #43)

**Spec:** `docs/feature-request-tui-exit-irc-quit-2026-09-23.md`

1. Read issue #43. Do not implement this on the issue #40 FIX PR.
2. Own branch from pulled `main`. Write `quit.req` (UTF-8 no BOM) on the watch home only; `irc_agent` PART then QUIT.
3. Skip forbidden homes. Do not stop python on another IRC home.
4. Evidence: log line for the request; `quit.req` path; no write under `.agentic-irc-cursor` / `cursor-2` / bobiverse Watch.
5. No UAT stamp.
