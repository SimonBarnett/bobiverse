<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-ping-me-from-filter-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: ping me FROM filter (#7)

1. Read issue #7. Stop dropping ordinary FROM text that contains `ping`.
2. Confirm `Test-DropIrcLine` / convert: `ping me` forwards; server PING still dropped.
3. Open PR linking #7. Do not stamp UAT.
