<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-auto-pong-bare-ping-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: auto-pong bare PING

1. Add `Test-BareIrcPing` / handle in `Send-IrcLineToSession` before forward.
2. On bare ping: write outbox PRIVMSG pong; log; do not Start-Process agent.
3. Keep Test-DropIrcLine for POINT/DIGEST; do not re-break ping me (#7).
4. Tests: parse fixtures for bare vs ping me; assert outbox write helper.
