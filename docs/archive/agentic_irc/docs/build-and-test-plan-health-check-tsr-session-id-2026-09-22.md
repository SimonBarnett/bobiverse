<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-health-check-tsr-session-id-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: health-check TSR + session id (#135)

**Date:** 2026-09-22  
**Repo:** SimonBarnett/agentic_irc  
**FR:** docs/feature-request-health-check-tsr-session-id-2026-09-22.md  
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/135  

## Goals

1. Land `scripts/Watch-AgentHealth.ps1` (`--grok` / `--cursor`): caller polls `listen.stdout.log` for `FROM`; agent still owns `irc_agent`.
2. IRC TSR health = `coordinator.pid` agent/listen PIDs + listen log present + not stale (default 900s).
3. Repair: `Start-IrcTsr.ps1` when agent alive listen dead; else optional `Stop-HungAgent.ps1 -Roll` from agentic_build.
4. Session id at `~/.grok/bob-bridge/watch-agent-health-{cursor|grok}.session`; wakes use `--resume` (no full skill boot each time).
5. Offline pytest for `scripts/agent_health.py` + script smoke strings.

## Non-goals

- agentic_build #163 silence watchdog duplicate.
- UAT stamp on PR. Bob chairs MRB on #135.
- Committing `password=` / `XAI_API_KEY=` lines.

## Phases

### P0 — Helpers + script
`agent_health.py` + `Watch-AgentHealth.ps1` in `scripts/`.

### P1 — Tests
`tests/test_agent_health.py`; `pytest -q` green.

### P2 — PR
Branch `work/fix-issue-135-health-check-tsr`. Title includes `#135`. Never push `main`. Never merge.

## Kickoff

Read FR + this plan. No API keys in git. Do not stamp ready for human UAT.
