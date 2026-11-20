# FR-OC-INJECT: Pin inject path for OpenCode ReadLine wrapper

## Goal

Jeeves assign lines reliably reach the OpenCode PowerShell ReadLine loop and start a new `opencode run`.

## Deliverables

- Default inject path for kind=opencode (KEY_EVENT batch vs clipboard paste) pinned like Cursor FR #4462/#4464.
- Submit-verify (FR #8270; VISION S3 / FR #2696 for Cursor and Grok): an OpenCode turn receipt is `turn_started` or new bytes in `opencode-turns.jsonl`. OpenCode retries do not send Enter (never re-paste / re-inject inside verify). A dead spawn fails fast (`probe=spawn kind=opencode`).
- After verify FAILED: re-inject the assign **once**, then GIVEUP `submit-verify failed probe=no turn receipt kind=opencode` (Cursor and Grok stay bare `submit-verify failed`); before re-inject, confirm no job-specific run is already active (avoid a queued duplicate `opencode run` after the first exits).
- Log `relay: inject path=...` for opencode.

## Testable

1. Fixture inject into fake ReadLine wrapper starts a run (or records the line).
2. Failed OpenCode submit does not send Enter. A dead spawn fails fast (`probe=spawn kind=opencode`). Then one re-inject; then GIVEUP `submit-verify failed probe=no turn receipt kind=opencode`. Cursor and Grok stay bare `submit-verify failed`.
3. Re-inject is skipped when a job-matched run is already active.
4. Opt-out env documented.

## CAST IRON: keys only (FR #8560)

OpenCode fleet seats must use batched KEY_EVENT inject (`BOB_WORKER_INJECT_PASTE=0`).
Do **not** set `BOB_WORKER_INJECT_PASTE=1`. Paste/Ctrl+V is unreliable on the ReadLine wrapper:
a stray `v` appears, submit-verify never sees `turn_started` / turn receipt, then GIVEUP loops
while digest still shows the seat "open".

Paid DeepSeek recipe: `BOB_OPENCODE_FORCE_PAID=1`, `BOB_OPENCODE_MODEL=opencode-go/deepseek-v4-pro`,
`BOB_WORKER_INJECT_PASTE=0`, disk `python bin/scripts/bob_worker.py --mode agent --agent opencode`.
