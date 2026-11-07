# FR-OC-INJECT: Pin inject path for OpenCode ReadLine wrapper

## Goal

Jeeves assign lines reliably reach the OpenCode PowerShell ReadLine loop and start a new `opencode run`.

## Deliverables

- Default inject path for kind=opencode (KEY_EVENT batch vs clipboard paste) pinned like Cursor FR #4462/#4464.
- Submit-verify equivalent: detect that ReadLine accepted the line / run started; retry Enter or re-inject once then NACK/GIVEUP inject failed.
- Log `relay: inject path=...` for opencode.

## Testable

1. Fixture inject into fake ReadLine wrapper starts a run (or records the line).
2. Failed submit retries then NACK/GIVEUP with stable reason.
3. Opt-out env documented.
