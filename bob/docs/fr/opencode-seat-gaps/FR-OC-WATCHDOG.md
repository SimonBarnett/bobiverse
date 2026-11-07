# FR-OC-WATCHDOG: Heartbeat/output-based OpenCode watchdog

## Goal

Long healthy `opencode run` jobs must not be killed/paused as out-of-fuel solely because wall clock exceeded 120s.

## Deliverables

- Replace absolute `WaitForExit(BOB_OPENCODE_WATCHDOG_MS)` kill with idle/activity detection.
- Prefer a heartbeat / progress marker (or growing redirected stdout/stderr length) so a healthy silent tool call is not treated as a hang.
- Do not call `record-pause` on wall-clock or silent-hang alone while the process is alive; `record-pause` only on confirmed 402/429 / rolling-limit evidence.
- Silent hang past threshold: kill/recycle the child; do **not** pause fuel solely for silence.
- Regression tests: run >120s with periodic output or heartbeat -> no kill/pause; silent hang -> kill without pause; 402/429 text -> pause as today.

## Testable

1. Unit/integration: wrapper with output or heartbeat past 120s -> no kill and no pause entry.
2. Silent hang past threshold -> kill/recycle; **no** `record-pause` without limit evidence.
3. 429/402 text -> pause as today.

## Evidence of gap

`%LOCALAPPDATA%\Bobiverse\worker\logs\opencode-out-of-fuel.log` entries `watchdog timeout (no output)` while stdout was only collected after WaitForExit.
