<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-orphan-python-node-on-start-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: clear orphan python/node on watcher start

## Summary
Simon (agentic_irc #184): lots of dead python and node left by crashed watchers. Clear orphan executables on start.

## Gap
`Stop-OrphanCursorWatchForwards` runs on `--new` / low-commit paths, not every watch start. Crashed seats leave `python.exe` (irc_listen/irc_agent) and orphan `node.exe` (cursor-agent forwards) around.

## Acceptance
| ID | Criterion |
|----|-----------|
| A1 | On watch start (`WatchWorker`), prune orphan cursor-agent forward/worker-server nodes (existing helper). |
| A2 | On watch start, stop `python.exe` whose command line references **this** watch IrcHome only (not talk-seat / bobiverse / other homes). |
| A3 | Do not kill fleet `Git task` / other-session cursor-agent nodes. |
| A4 | Log counts pruned. |
