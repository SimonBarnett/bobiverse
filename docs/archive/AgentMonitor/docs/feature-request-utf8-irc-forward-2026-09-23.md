<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-utf8-irc-forward-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: Sync-IrcForward UTF-8 mojibake (issue #10)

https://github.com/SimonBarnett/AgentMonitor/issues/10

Parked from MRB of #6 / SHA `c5b5319` (PR #9). Not a red gate on #6 A1–A3. No UAT.

## LOCKED

1. Decode a complete line as UTF-8 before convert.
2. Keep #6: no forward and no offset advance until newline.
3. Do not treat each byte as a UTF-16 character (`$sb.Append([char]$b)`).
4. No UAT.

## Acceptance

| ID | Gate |
|----|------|
| A1 | Complete UTF-8 PRIVMSG (e.g. café) forwards as the same Unicode, not mojibake. |
| A2 | Incomplete line without newline still holds offset (#6 A1 stays green). |
| A3 | No UAT stamp. |
