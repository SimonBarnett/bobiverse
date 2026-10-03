<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-partial-irc-log-line-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: partial irc.log line is forwarded then dropped (issue #6)

https://github.com/SimonBarnett/AgentMonitor/issues/6

## LOCKED

Wait until an `irc.log` line has a newline before converting or advancing
the offset. Do not forward a prefix. Do not skip the suffix when it arrives.
No UAT.

## Expected (issue #6)

`Sync-IrcForward` must not treat a short `StreamReader.ReadLine()` at EOF
as a finished line.

## Acceptance

| ID | Gate |
|----|------|
| A1 | Incomplete PRIVMSG (no newline) is not forwarded. Offset does not pass those bytes. |
| A2 | When the rest of the line plus newline arrives, the completed `FROM` line is forwarded once. |
| A3 | Later complete lines still forward. No UAT stamp. |
