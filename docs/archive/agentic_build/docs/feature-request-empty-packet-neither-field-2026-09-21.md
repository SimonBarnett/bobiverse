<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-empty-packet-neither-field-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: decide tick path when inbox packet has neither fuel nor model

- Date: 2026-09-21
- Target repo: `SimonBarnett/agentic_build`
- Raised by: hostile MRB of `1f43357843050ce8ad42ff870fff38cf7ce6c8df` (issue #54 empty-fuel gate)
- Status: locked refuse at tick (`missing_fuel_and_model`); see issue #79 / BT0z1

## Summary

Issue #54 LOCKED the case **non-empty `model` + no `fuel`**. Its UNKNOWN left the
orthogonal case: a claimed inbox packet with **neither** `fuel` nor `model`.

That packet still takes the historic default worker path. `Start-BobWorker` fills
`Get-BobJobModel -Kind build -Fuel grok-build` and starts `grok.exe` / Fake-Grok.

## Gap vs current tree (at 1f43357 / PR #78)

- `Test-BobPacketMissingFuel` returns `ok=true` when `$Model` is null or whitespace.
- `Invoke-BobFleetOnce` then moves the packet to `running` and calls
  `Start-BobWorker -Model $packet.model`. Empty model is not a refuse.
- Isolated probe on 1f43357: empty model + empty fuel is treated as allowed
  (`Test-BobPacketMissingFuel.ok=true`). No Test-Pack case locks fail vs default.

This is not issue #54 AC1 (that MUST is a present model string). Do not open a
second FR for AC1.

## Asks

1. **Lock the path.** Either refuse the packet at tick with a named completion
   summary, or keep the historic default and say so in `/docs` and the module
   contract. One path only.
2. **Coverage.** Off-DEV Test-Pack for the locked path. No live agent, no live
   `gh`, no live fleet machine.

## LOCKED

- Issue #54 AC1–AC2 stay on #54: non-empty `model` and no `fuel` must fail with
  `missing_fuel` and no grok start. This request must not weaken that MUST.
- Existing `fuelModelFamilies` / `modelFamilies` / `models.*` from issue #17.

## LOCKED (issue #79)

- Refuse at tick with completion summary `missing_fuel_and_model`. Do not start the historic
  `Get-BobJobModel -Kind build -Fuel grok-build` / Fake-Grok default worker path.

## Acceptance

- `AC1` A hand-written inbox packet with no `fuel` and no `model` follows the
  single locked path (refuse with a named summary, or historic default worker).
  The other path is not observed.
- `AC2` Test-Pack covers AC1 without a live agent, a live `gh`, or a live fleet
  machine.
