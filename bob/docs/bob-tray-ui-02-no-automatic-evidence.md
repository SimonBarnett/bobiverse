# BOB-TRAY-UI-02 / FR #9262 evidence: Remove Automatic from Workers

**Slice:** Workers dropdown excludes Automatic/auto id (Success S1)

## S1

Workers menu lists Grok, Cursor, OpenCode Free, and OpenCode Paid only (FR #9588). There is no Automatic row and no `auto` menu id.

| Surface | Change |
|---------|--------|
| TipForm `SeedAgentChoices` | No `AddAgentChoice(..., "auto", ...)` |
| TipForm `ApplyAgentList` | Fallback omits auto; JSON rows with `id=auto` are skipped |
| `Watch-BobTray.ps1` seed + `Get-BobTrayWorkerAgentChoices` | No Automatic/auto rows |
| `Update-BobTrayWorkerAgentsMenu` | Skips `id=auto` if list-agents still emits it |

## How measured

- Tests: `bob/tests/test_fr9262_workers_no_automatic.py`
- Dump-menu pin: `bob/tests/test_tray_dialogs_828.py` (no Automatic line under Workers)
- Docs: `bob/docs/bob-tray-dialogs.md` Workers inventory

## Out of scope

- Engine seat_target / Automatic fill policy (still may use empty agent id internally)
- Other BOB-TRAY-UI children
