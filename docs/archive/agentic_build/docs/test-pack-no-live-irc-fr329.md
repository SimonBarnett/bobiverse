<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/test-pack-no-live-irc-fr329.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Test-Pack must not join live IRC (FR #329)

`tools/Test-Pack.ps1` sets `BOB_TEST_NO_LIVE_IRC=1` for the whole run.
`Start-BobWorkerIrcAgent` refuses live Ergo (`irc.ntsa.uk`) when that env is set,
and also refuses when `BOB_IRC_HOME` / home path is under `%TEMP%\bob-bridge-test-*`.

`Stop-BobBridgeTestIrcOrphans` kills any `irc_agent` whose command line contains
`bob-bridge-test-` (leaves `~/.agentic-irc-*` alone). Test-Pack calls it in `finally`.
