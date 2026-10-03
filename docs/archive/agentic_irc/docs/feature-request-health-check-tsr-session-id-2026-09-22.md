<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-health-check-tsr-session-id-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: health-check TSR + forward IRC + persist session id

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/135  
**Raised by:** Simon on `#bobiverse`  
**UAT + hostile MRB owner:** Bob  

## Problem

Simon: the agent health check must include an IRC TSR check. Received
IRC traffic must be forwarded to the agent. The session id must be
saved so a restart does not reload all skills every time.

Today `Desktop\Watch-AgentHealth.ps1` (`--grok` / `--cursor`) only
watches whether `agent.exe` / `agent.cmd` is alive and restarts it
with a full skill-load prompt. It does not:

- probe the talk-seat IRC TSR (`irc_listen` / `listen.stdout.log` /
  `FROM` traffic)
- forward received IRC into the live agent
- persist a session id and resume that session on restart

## Gap vs current tree

- Talk-seat TSR is `irc_listen` + IDE `notify_on_output` on `^FROM`
  (`agentic-irc` skill). That is not part of `Watch-AgentHealth`.
- Sister (different surface): agentic_build #163 Watch-IrcTsr /
  silence recycle. This FR is the **Desktop health check** plus
  session resume, not the bulk-close watchdog.
- Fresh `--grok` / `--cursor` start always ships the full irc+build
  skill prompt. No saved session id.

## LOCKED

1. Health check must verify the IRC TSR for this seat (listen
   process + recent received traffic, not process-alive-only).
2. Received IRC traffic must be forwarded to the agent (Cursor or
   Grok) so a live seat acts without a human paste.
3. Persist the agent session id. Restart resumes that session and
   must not reload all skills from scratch every time.
4. Do not gut `--grok` / `--cursor` or the harvest imperative.
5. **Agent still initialises the IRC connection** (`irc_agent` /
   talk-seat join). The agent does not poll for new IRC traffic.
6. **Caller polls.** Checking for new IRC traffic is the health-check
   / Watch-AgentHealth caller (listen log / `FROM`), not the agent.
7. **Agent TSR fires when data exists.** When the caller sees new
   traffic, it triggers the agent wake. No human paste.
8. No UAT stamp from workers. Bob owns UAT.

## Status (worker, 2026-09-22)

| Item | State |
|------|--------|
| `scripts/Watch-AgentHealth.ps1` | In repo (`--grok` / `--cursor`) |
| Session store | `~/.grok/bob-bridge/watch-agent-health-{cursor\|grok}.session` |
| IRC stale threshold | 900s default (`-IrcStaleSeconds`) |
| Offline tests | `tests/test_agent_health.py` + `scripts/agent_health.py` |
| Bob UAT / MRB | Not stamped by worker |

## UNKNOWN

1. Whether Cursor `--resume` flag spelling or JSON field names drift across CLI builds after a **bound** `session_id` from first boot (Grok uses `--session-id` / `--resume`).
3. Silence threshold tuning on very quiet seats (override `-IrcStaleSeconds`).

## Acceptance

1. Kill or freeze `irc_listen` (TSR). Health check reports IRC TSR
   unhealthy and recovers it (or the agent) within a bounded time
   (LOCKED once UNKNOWN 3 is measured).
2. A `FROM` / PRIVMSG that reaches listen is delivered to the agent
   without a human paste into the IDE.
3. Restart of the watched agent reuses the saved session id; skills
   are not fully reloaded on every restart.
4. No UAT stamp on the implementing PR.

## Out of scope

- agentic_build #175 persistent workers.
- agentic_build #163 silence-recycle watchdog (sister; do not
  duplicate that intake).
- Stamping UAT.
