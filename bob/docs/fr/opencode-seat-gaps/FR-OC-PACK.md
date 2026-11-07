# FR-OC-PACK: MSI/Sync ships OpenCode fuel helpers + skill

## Goal

After Sync-BobiverseFromRepo / MSI upgrade, the flat install contains every file OpenCode selection and the launch wrapper need.

## Deliverables

- Sync/MSI include: `common/scripts/opencode_fuel.py`, `tray/tools/Get-BobOpencodeFuel.ps1` (or install tools layout), updated `Get-BobAgentFuel.ps1`, `bob/.grok/skills/bob-setup-opencode/**`.
- Layout pin test (paths exist after Sync compose).
- Wrapper `_resolve_opencode_fuel_helper_path` finds helper on install-root layout.

## Testable

1. Sync compose fixture lists the OpenCode paths.
2. `Get-BobAgentFuel` on composed install returns `opencode` key (fixture ok).
3. Missing helper fails the pin.
