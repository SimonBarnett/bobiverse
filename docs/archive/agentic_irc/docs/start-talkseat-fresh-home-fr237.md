<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/start-talkseat-fresh-home-fr237.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #237: Start-TalkSeat.ps1 fails on a fresh home

## Bug

The first `Assert-HomeBind` / `Start-OneSeatAgent` used `$expectedNick` before it
was assigned. On an empty `$IrcHome` that launched `irc_agent.py --nick ''` and
failed the bind guard (`expected-nick` required).

## Fix

- Fresh home: start with `--nick {machine}-0 --auto-nick` and
  `AGENTIC_IRC_SEAT_PID=self` so the live nick becomes `{machine}-{irc_agent PID}`
- Never call bind/start with an empty expected nick
- Refuse empty `--nick` inside `Start-OneSeatAgent` / `Assert-HomeBind`
- Remove the `Start-TalkAgent` typo (undefined function)

## Tests

`tests/test_start_talkseat_fresh_home_fr237.py`
