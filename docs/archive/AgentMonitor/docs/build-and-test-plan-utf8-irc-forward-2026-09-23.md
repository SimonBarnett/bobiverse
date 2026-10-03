<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-utf8-irc-forward-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: UTF-8 irc forward (#10)

1. Read issue #10. After newline, decode held bytes as UTF-8 before convert.
2. Keep #6 offset/newline behaviour. Replay café vs split line.
3. Open PR linking #10. Do not stamp UAT.
