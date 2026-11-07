# FR-OC-WATCHDOG: Heartbeat/output-based OpenCode watchdog

## Goal

Long healthy `opencode run` jobs must not be killed/paused as out-of-fuel solely because wall clock exceeded 120s.

## Deliverables

- Replace absolute `WaitForExit(BOB_OPENCODE_WATCHDOG_MS)` kill with idle/no-output detection (or raise default and only kill when no stdout/stderr progress).
- Do not call `record-pause` on wall-clock alone while the process is alive and producing output.
- Keep real 402/429 / rolling-limit → pause behaviour.
- Regression test: simulated run >120s with periodic output does not pause; silent hang still kills.

## Testable

1. Unit/integration: wrapper with output past 120s → no pause entry.
2. Silent hang past threshold → kill + optional pause.
3. 429/402 text → pause as today.

## Evidence of gap

`%LOCALAPPDATA%\Bobiverse\worker\logs\opencode-out-of-fuel.log` entries `watchdog timeout (no output)` while stdout was only collected after WaitForExit.
