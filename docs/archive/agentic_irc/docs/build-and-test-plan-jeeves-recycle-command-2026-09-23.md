<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-jeeves-recycle-command-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test: Jeeves `!recycle {machine}` (#152)

**FR:** `docs/feature-request-jeeves-recycle-command-2026-09-23.md`
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/152
Simon dispatched 2026-09-23. No UAT stamp.

## Build

1. Parser: `!recycle <machine>` is a chair-only command. `bob-*` / `w-*` ignore it. `!bobiverse` unchanged.
2. Valid machines: `flamingo`, `marchhare`, `ionos`, `ce-priority-dev1`. Alias `dev1` → `ce-priority-dev1`. Any other token refused; stop nothing.
3. Valid recycle on that box: pull `agentic_irc`, restart Watch-Bobiverse (`bob-<id>`), recycle systray via existing Restart watcher in `agentic_build` `tools/Watch-BobTray.ps1` (kill every `Watch-BobTray` for that machine, rejoin `_Watch-Bobiverse-<id>`, start exactly one tray). Do not stop `BobFleet-*`.
4. `!recycle ionos` also restarts Jeeves (`irc_agent.py --chair` / `Install-BobChair.ps1`) and `bobcallback.py` so GIT uses `chair-outbox.txt`.
5. No WinRM. No SMB. No secrets. Talk seats never send `!bobiverse`.

## Tests (hermetic)

- A1: chair client handles `!recycle ionos`.
- A2: `bob-*` does not treat `!recycle` as a command.
- A3: existing `!bobiverse` tests still pass.
- A4: unknown machine refused; no process kill.
- A5: parser + refuse path with no live IRC.
- A6: valid recycle path includes `Watch-BobTray.ps1` restart (old trays gone, one left). No live recycle of flamingo from DEV1 in CI.
