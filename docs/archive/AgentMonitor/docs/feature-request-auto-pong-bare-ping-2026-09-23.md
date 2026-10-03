<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-auto-pong-bare-ping-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: AgentWatcher auto-pong bare PING without waking agent

## Summary
Simon (agentic_irc #183): AgentWatcher should handle PING with PONG without interrupting the agent.

## Gap
`Test-DropIrcLine` only drops case-sensitive ` PING ` (requires trailing space). `FROM simon #bobiverse PING` at EOL is **not** dropped and is forwarded via `agent -p`, interrupting the TUI session. Skills already say ping→pong, but that wakes the agent.

## Acceptance
| ID | Criterion |
|----|-----------|
| A1 | Bare `FROM … ping` / `PING` / `Ping` (whole message text) does **not** start `agent -p` / grok `-p`. |
| A2 | Instead, watcher appends `PRIVMSG <target> :<nick>: pong` (or `pong`) to that seat `outbox.txt` UTF-8 no BOM. |
| A3 | `FROM … ping me` (and other non-bare ping text) still forwards (issue #7). |
| A4 | Server raw `PING` lines still dropped in `Convert-IrcRawLineToFromLine`. |
| A5 | Unit/source tests cover A1–A3. |

## Out of scope
- Changing talk-seat Cursor TSR behaviour.
- Cleaning orphan python/node (#184).
