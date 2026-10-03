<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-fuel-model-compatibility-gate-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: fuel/model compatibility gate on the job packet

- Date: 2026-09-20
- Target repo: `SimonBarnett/agentic_build`
- Raised by: hostile MRB of `2ee5075bc067def2c742966840168f805beb5980` (board: issue #16)
- Status: parked, not dispatched

## Summary

Nothing in the enqueue → tick → exec chain checks that a packet's `model` is a model the
packet's `fuel` can actually run. A `grok-build` packet can carry a Cursor model name and the
fleet will hand that string to `grok.exe` verbatim.

## Gap vs current tree (at 2ee5075)

- `config/default.json` `models.mrbCursor` = `claude-opus-5-thinking-high`,
  `models.mrbGrok` = `grok-4.6`. `Get-BobJobModel -Kind mrb -Fuel <fuel>` returns the right one
  **for the fuel it is asked about**, and that is the only place fuel and model are related.
- `Start-BobBuild` accepts `-Fuel` and `-Model` as independent parameters and persists both into
  the packet. There is no cross-check.
- `src/Private/Invoke-BobFleet.ps1:235` passes `$packet.model` straight into
  `Start-BobWorker -Model`, and `src/Public/Start-BobWorker.ps1:62-63` only substitutes a default
  when `$Model` is empty. A non-grok model name reaches `Get-BobArgv` and then grok's argv.
- `Resolve-BobGrokCliModel` exists and knows what grok.exe can list, but nothing on the enqueue
  or tick path consults it to validate an explicitly supplied `-Model`.
- No Test-Pack case asserts that a mismatched fuel/model pair is refused.

Live reproduction at this SHA (isolated `BOB_BRIDGE_HOME`, fake `gh`, injected picker):
`tools/Start-BobMrbHandoff.ps1 -Fuel cursor-models -TestSkipCursor` returns `ok=True` and writes
an inbox packet with `fuel=grok-build` and `model=claude-opus-5-thinking-high`. That specific
caller bug is a Required fix on the MRB board; the missing **gate** that let it through is this
request.

## Asks

1. **Validate at enqueue.** `Start-BobBuild` must refuse (or explicitly normalise, and say so in
   the returned object) a `-Model` that the resolved `-Fuel` cannot run: grok fuels take grok
   model ids, `cursor-models` takes Cursor model ids, `copilot` takes neither.
2. **Validate at tick.** `Invoke-BobFleet` must refuse a claimed packet whose `model` is not
   runnable by its `fuel`, completing `failed` with a named summary rather than launching
   `grok.exe` with an unrunnable model string.
3. **Single source for the fuel → model-family mapping**, in `config/default.json` alongside
   `models.*`, so adding a vendor does not mean editing predicates in three files.
4. **Coverage.** Off-DEV Test-Pack cases: mismatched pair refused at enqueue; mismatched packet
   refused at tick; matched pairs for every fuel still enqueue and tick.

## LOCKED

- Existing `models.*` keys and their current values.
- MRB models stay reserved for MRB work; build workers keep `build0.1` / `models.buildGrokFallback`
  / Cursor `composer-2.5`.

## UNKNOWN

- Whether the mapping should be a prefix/regex table or an explicit allow-list per fuel.
- Whether a mismatch at enqueue should hard-throw or downgrade to the fuel's default model with a
  warning. Ask 1 assumes throw; the human may prefer downgrade for unattended dispatch.

## Acceptance

- `AC1` `Start-BobBuild -Fuel grok-build -Model <cursor model>` does not produce an inbox packet.
- `AC2` A hand-written inbox packet with a mismatched fuel/model completes `failed` with a summary
  naming the mismatch, and no `grok.exe` is started.
- `AC3` The fuel → model-family mapping is read from config, not hard-coded in `Start-BobBuild`
  or `Invoke-BobFleet`.
- `AC4` Test-Pack covers AC1 and AC2 without a live agent, a live `gh`, or a live fleet machine.
