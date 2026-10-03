<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-empty-fuel-packet-gate-2026-09-20.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: refuse inbox packets with no fuel before grok start

- Date: 2026-09-20
- Target repo: `SimonBarnett/agentic_build`
- Raised by: hostile MRB of `9664360a70b163d31c8fdf76246fec4a0702efa6` (issue #17 fuel/model gate)
- Status: parked, not dispatched

## Summary

The fuel/model compatibility gate (`Test-BobFuelModelCompatible`) runs on fleet tick only when
`$packet.fuel` is set. A hand-written inbox packet with **no `fuel` field** and a Cursor model
id still moves to `running` and starts `grok.exe` / Fake-Grok.

This is not issue #17 AC2 (that case is a present mismatched pair). It is the same class of
hole: an unrunnable model string reaches the worker.

## Gap vs current tree (at 9664360 / main after PR #45)

- `src/Private/Invoke-BobFleet.ps1` skips the gate when `$packet.fuel` is empty, then
  `Start-BobWorker -Model $packet.model` for fleet tasks.
- Isolated Fake-Grok: inbox packet with `model=composer-2.5` and no `fuel` completed
  `state=done` / `completion.status=ok`. Fake-Grok sessions grew 0 → 1.

## Asks

1. **Tick.** `Invoke-BobFleet` must refuse a claimed packet that has a `model` and no
   runnable `fuel`, completing `failed` with a named summary. No `grok.exe` start.
2. **Coverage.** Off-DEV Test-Pack: empty-fuel + model packet fails at tick; no Fake-Grok
   session growth. No live agent, no live `gh`.

## LOCKED

- Existing `fuelModelFamilies` / `modelFamilies` / `models.*` from issue #17.
- Enqueue path still requires `-Fuel` via `Start-BobBuild` ValidateSet when the caller
  supplies one; this request is the hand-written / missing-field tick path.

## UNKNOWN

- Whether a packet with neither `fuel` nor `model` should fail or take the historic default
  worker path.

## Acceptance

- `AC1` A hand-written inbox packet with a non-empty `model` and no `fuel` completes
  `failed` with a summary naming the missing fuel. No `grok.exe` / Fake-Grok session start.
- `AC2` Test-Pack covers AC1 without a live agent, a live `gh`, or a live fleet machine.
