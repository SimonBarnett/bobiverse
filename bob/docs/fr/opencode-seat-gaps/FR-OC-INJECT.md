# FR-OC-INJECT: Pin inject path for OpenCode ReadLine wrapper

## Goal

Jeeves assign lines reliably reach the OpenCode PowerShell ReadLine loop and start a new `opencode run`.

## Deliverables

- Default inject path for kind=opencode (KEY_EVENT batch vs clipboard paste) pinned like Cursor FR #4462/#4464.
- Submit-verify (FR #8270; VISION S3 / FR #2696 for Cursor and Grok): an OpenCode turn receipt is `turn_started` or new bytes in `opencode-turns.jsonl`. OpenCode retries do not send Enter (never re-paste / re-inject inside verify). A dead spawn fails fast (`probe=spawn kind=opencode`).
- After verify FAILED: re-inject the assign **once**, then NACK/GIVEUP inject failed; before re-inject, confirm no job-specific run is already active (avoid a queued duplicate `opencode run` after the first exits).
- Log `relay: inject path=...` for opencode.

## Testable

1. Fixture inject into fake ReadLine wrapper starts a run (or records the line).
2. Failed OpenCode submit does not send Enter. A dead spawn fails fast (`probe=spawn kind=opencode`). Then one re-inject; then GIVEUP `submit-verify failed probe=no turn receipt kind=opencode`. Cursor and Grok stay bare `submit-verify failed`.
3. Re-inject is skipped when a job-matched run is already active.
4. Opt-out env documented.
