<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/start-irc-pair-fr238.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #238: sanctioned detached IRC pair launcher

## Problem

IRC clients started from an agent **tool shell** die when the tool command
ends (job object / child tree teardown). Agents then improvised
`%TEMP%\watch-grok-irc-launch.py`, which is unreviewed and breaks
`coordinator.pid` lifetime (seat= no longer the monitor).

## Rule

Seat agents never start `irc_agent` / `irc_listen`. Prefer Watch-AgentHealth
**irc ensure**. Report IRC-down on the outbox.

## Sanctioned launcher

```text
python scripts/start_irc_pair.py \
  --coordinator-pid <Watch-AgentHealth PID> \
  --home ~/.agentic-irc-watch-grok \
  --nick marchhare-<monitorPid> \
  --channel '#marchhare'
```

Or `scripts/Start-IrcPair.ps1` with the same parameters.

### Behaviour

- Detach from the caller job: `CREATE_BREAKAWAY_FROM_JOB | DETACHED_PROCESS |
  CREATE_NEW_PROCESS_GROUP` (Windows); falls back without breakaway if denied
- Writes `coordinator.pid` with `seat=<coordinator-pid>`, `agent=`, `listen=`,
  `launcher=start_irc_pair`
- Sets `AGENTIC_IRC_COORDINATOR_PID` for the agent process
- `irc_agent` warns when `seat=` does not look like Watch-AgentHealth

## Tests

`tests/test_start_irc_pair_fr238.py`
