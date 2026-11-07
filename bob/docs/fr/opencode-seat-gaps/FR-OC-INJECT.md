# FR-OC-INJECT: Pin inject path for OpenCode ReadLine wrapper

## Goal

Jeeves assign lines reliably reach the OpenCode PowerShell ReadLine loop and start a new `opencode run`.

## Deliverables

- Default inject path for kind=opencode (KEY_EVENT batch vs clipboard paste) pinned like Cursor FR #4462/#4464.
- Submit-verify equivalent (bob VISION S3 / FR #2696): detect that ReadLine accepted the line / run started; **Enter-only** retries inside the verify loop (never re-paste / re-inject inside verify).
- After verify FAILED: re-inject the assign **once**, then NACK/GIVEUP inject failed; before re-inject, confirm no job-specific run is already active (avoid a queued duplicate `opencode run` after the first exits).
- Log `relay: inject path=...` for opencode.

## Testable

1. Fixture inject into fake ReadLine wrapper starts a run (or records the line).
2. Failed submit uses Enter-only retries; then one re-inject; then NACK/GIVEUP with stable reason.
3. Re-inject is skipped when a job-matched run is already active.
4. Opt-out env documented.
