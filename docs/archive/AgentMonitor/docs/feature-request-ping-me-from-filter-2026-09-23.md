<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-ping-me-from-filter-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: ping me is dropped by the FROM filter (issue #7)

https://github.com/SimonBarnett/AgentMonitor/issues/7

## LOCKED

Drop protocol lines in `Convert-IrcRawLineToFromLine`. Do not drop an
ordinary `FROM` line because its text contains `ping`. No UAT.

## Expected (issue #7)

`FROM bob #shop ping me` must forward. Server `PING` stays dropped in convert.
If the spaced-word filter stays, make the match case-sensitive and document
which user texts it removes.

## Acceptance

| ID | Gate |
|----|------|
| A1 | `FROM … ping me` is not dropped. Bare `ping` still forwards. |
| A2 | Protocol `PING` is still removed in convert. |
| A3 | No UAT stamp. |
