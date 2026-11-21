# BOB-06 / FR #8713 evidence: tray menu tree Status/Agents/Workers/Weights/About/Exit

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8713
**Slice:** Tray menu tree: Status/Agents/Workers/Weights/About/Exit (Success S1)

## S1

Context menu structure matches the brief and `bob/docs/mocks/systray-agents-workers/home.html`.

## How measured

1. `bob/tray/dialogs/BobTray.cs` builds Status → Agents{Plan, Priority, Jeeves} → Workers{Grok, Cursor, Open Code} → Weights → About → Exit (Plan is not a flat top-level sibling).
2. Worker CLI starts seed under Workers (`SeedAgentChoices(miWorkers, …)`); Agents holds product agents only.
3. TipForm `Watch-BobTray.ps1` mirrors the same tree.
4. Tests: `bob/tests/test_fr8713_tray_menu_tree.py`; dump-menu pin in `test_tray_dialogs_828.py`.

## Fail-when

Flat Plan sibling or missing Weights/Exit.
