<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-root-exit-teardown-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: root/console exit teardown (issue #126)

**Spec:** `docs/feature-request-root-exit-teardown-2026-09-26.md`

1. Own branch from pulled `main`.
2. Add `Complete-WatchSeatRootExit` / `Test-WatchSeatRootGone`: Disconnect (quit.req), clear wakes, mark `seatRootGone`, stop root tree.
3. Grok unhealthy + Cursor TUI-gone: call teardown and **break** (monitor exit). No `$needStart` relaunch.
4. Gate `Ensure-WatchIrcSeat`, `Sync-WatchBored`, wake forward/dequeue on `seatRootGone`.
5. Tests: source contract (no Grok restart after unhealthy); teardown writes `quit.req` on own home only; bored/wake skip when `seatRootGone`.
6. Run `tests\Test-WatchRootExit.ps1` and existing bored/wake tests. No UAT stamp.
