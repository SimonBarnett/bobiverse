<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-partial-irc-log-line-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: partial irc.log line (#6)

1. Read issue #6. Fix `Sync-IrcForward` so a short read at EOF is not a finished line.
2. Replay the observed split (`spl` then `it line`). Prefix not forwarded; completed line forwarded once.
3. Open PR linking #6. Do not stamp UAT.
